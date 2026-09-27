import inspect
import os
import socket
from typing import Callable, Optional

from services import app_name_repo, log_format_repo, tz_repo

LEVELS = ("INFO", "NORMAL", "WARNING", "ERROR")

# ✅ 画面表示用のシンク。gui/main_window.py が起動時に register_sink() で登録する
# （services/ はFlet非依存を維持するため、GUI側からの注入方式にしている）
_sinks: list[Callable[[str, str], None]] = []


def register_sink(callback: Callable[[str, str], None]) -> None:
    _sinks.append(callback)


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def log(
    level: str,
    message: str,
    reason: Optional[str] = None,
    func_name: Optional[str] = None,
    command_id: Optional[str] = None,
) -> str:
    """
    標準フォーマット（既定: "ID| 日時| 端末名| アプリ名| 機能名| 区分| メッセージ内容"、config/log_format.toml で変更可）
    で1行組み立て、設定された出力先（file/screen）へ出力する。
    func_name省略時は呼び出し元の関数名を自動取得する。reasonを渡すとメッセージ末尾に「理由＝...」を付記する。
    command_id（ジョブ実行のULID等）は先頭列に出す。省略時は空文字。
    日時は標準の`datetime.strftime`（既定`%f`はマイクロ秒6桁）に従う。
    戻り値は整形済みの1行（呼び出し元でさらに使いたい場合用）
    """
    if level not in LEVELS:
        level = "INFO"

    fmt = log_format_repo.load_format()

    func = func_name or inspect.stack()[1].function
    now = tz_repo.now()
    content = f"{message} 理由＝{reason}" if reason else message

    line = fmt["format"].format(
        command_id=command_id or "",
        datetime=now.strftime(fmt["datetime_format"]),
        hostname=_hostname(),
        app_name=app_name_repo.load_display_name() or "myJobLauncher",
        func=func,
        level=level,
        message=content,
    )

    destinations = fmt["destinations"]

    if "file" in destinations:
        try:
            log_dir = fmt["log_dir"]
            os.makedirs(log_dir, exist_ok=True)
            path = os.path.join(log_dir, f"app-{now.strftime('%Y%m%d')}.log")
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass  # ログ出力自体の失敗でアプリを落とさない

    if "screen" in destinations:
        for sink in _sinks:
            try:
                sink(line, level)
            except Exception:
                pass

    return line
