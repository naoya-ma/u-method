import duckdb
import uuid6
from datetime import datetime

DB_FILE = "app.db"

# ========================
# ✅ ステータス表示（実行タブ・履歴ダイアログで共通利用）
# ========================
STATUS_LABELS = {
    "SUCCESS": "✅ 完了",
    "ERROR": "❌ 失敗",
    "CANCEL": "⛔ 中断",
}


def init_db():
    """
    テーブル初期化
    """
    conn = duckdb.connect(DB_FILE)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS execution_history (
                id VARCHAR,
                command TEXT,
                returncode BIGINT,
                stdout TEXT,
                stderr TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT
            )
        """)
    finally:
        conn.close()


def insert_history(result):
    """
    実行履歴を保存
    """
    conn = duckdb.connect(DB_FILE)
    try:
        conn.execute("""
            INSERT INTO execution_history
            (id, command, returncode, stdout, stderr, start_time, end_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid6.uuid7()),   # ✅ 時系列ソート可能ID
            result.command,
            result.returncode,
            result.stdout,
            result.stderr,
            result.start_time,
            result.end_time
        ))
    finally:
        conn.close()


def insert_history_with_id(command_id, result):
    conn = duckdb.connect(DB_FILE)
    try:
        status = classify_status(int(result.returncode))

        conn.execute("""
            INSERT INTO execution_history
            (id, command, returncode, stdout, stderr, start_time, end_time, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            command_id,
            result.command,
            int(result.returncode),
            result.stdout,
            result.stderr,
            result.start_time,
            result.end_time,
            status
        ))
    finally:
        conn.close()


def get_history(limit=50):
    conn = duckdb.connect(DB_FILE)
    try:
        return conn.execute("""
            SELECT id, command, returncode, start_time, status
            FROM execution_history
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()


def get_history_detail(command_id):
    conn = duckdb.connect(DB_FILE)
    try:
        return conn.execute("""
            SELECT command, returncode, stdout, stderr, start_time
            FROM execution_history
            WHERE id = ?
        """, (command_id,)).fetchone()
    finally:
        conn.close()


def get_history_by_date(from_date: datetime, to_date: datetime):
    """
    期間指定検索（拡張用）
    """
    conn = duckdb.connect(DB_FILE)
    try:
        return conn.execute("""
            SELECT command, returncode, start_time
            FROM execution_history
            WHERE start_time BETWEEN ? AND ?
            ORDER BY start_time DESC
        """, (from_date, to_date)).fetchall()
    finally:
        conn.close()


def refresh_history(self):
    self.history_list.clear()

    history = get_history()

    for h in history:
        command_id, command, code, start, status = h

        # ✅ 見た目アイコン
        if status == "SUCCESS":
            icon = "✅"
        elif status == "CANCEL":
            icon = "⛔"
        else:
            icon = "❌"

        self.history_list.addItem(f"{icon} {command_id} | {command} | {status}")


def get_job_run_dates(command: str) -> list:
    """
    指定コマンドの実行日（date）一覧を返す（分類ロジック用）
    """
    conn = duckdb.connect(DB_FILE)
    try:
        rows = conn.execute("""
            SELECT start_time
            FROM execution_history
            WHERE command = ?
            ORDER BY start_time
        """, (command,)).fetchall()
    finally:
        conn.close()

    return [r[0].date() for r in rows]


def get_job_executions(command: str) -> list:
    """
    指定コマンドの個別実行履歴（新しい順）
    (start_time, end_time, returncode, status)
    """
    conn = duckdb.connect(DB_FILE)
    try:
        return conn.execute("""
            SELECT start_time, end_time, returncode, status
            FROM execution_history
            WHERE command = ?
            ORDER BY start_time DESC
        """, (command,)).fetchall()
    finally:
        conn.close()


def get_job_last_status(command: str):
    """
    指定コマンドの最新の実行ステータス（'SUCCESS'/'CANCEL'/'ERROR'）。履歴が無ければ None
    """
    conn = duckdb.connect(DB_FILE)
    try:
        row = conn.execute("""
            SELECT status
            FROM execution_history
            WHERE command = ?
            ORDER BY start_time DESC
            LIMIT 1
        """, (command,)).fetchone()
    finally:
        conn.close()

    return row[0] if row else None


def get_executions_on_date(target_date) -> list:
    """
    指定日(date)に開始された全ジョブの実行一覧 (command, start_time, end_time, status)
    日報タブの「本日実施したジョブを取り込む」で使用
    """
    conn = duckdb.connect(DB_FILE)
    try:
        return conn.execute("""
            SELECT command, start_time, end_time, status
            FROM execution_history
            WHERE CAST(start_time AS DATE) = ?
            ORDER BY start_time
        """, (target_date,)).fetchall()
    finally:
        conn.close()


def get_job_monthly_summary(command: str) -> list:
    """
    指定コマンドの月別集計 (month, 件数, 成功数, 失敗数)
    """
    conn = duckdb.connect(DB_FILE)
    try:
        return conn.execute("""
            SELECT
                strftime(start_time, '%Y-%m') AS month,
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS success,
                SUM(CASE WHEN status != 'SUCCESS' THEN 1 ELSE 0 END) AS fail
            FROM execution_history
            WHERE command = ?
            GROUP BY month
            ORDER BY month DESC
        """, (command,)).fetchall()
    finally:
        conn.close()


def get_job_daily_summary(command: str) -> list:
    """
    指定コマンドの日別集計 (date, 件数, 成功数, 失敗数)
    """
    conn = duckdb.connect(DB_FILE)
    try:
        return conn.execute("""
            SELECT
                strftime(start_time, '%Y-%m-%d') AS day,
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS success,
                SUM(CASE WHEN status != 'SUCCESS' THEN 1 ELSE 0 END) AS fail
            FROM execution_history
            WHERE command = ?
            GROUP BY day
            ORDER BY day DESC
        """, (command,)).fetchall()
    finally:
        conn.close()


def classify_status(returncode: int) -> str:
    if returncode == 0:
        return "SUCCESS"
    elif returncode == 3221225786:  # Windows Ctrl+C / kill
        return "CANCEL"
    else:
        return "ERROR"
