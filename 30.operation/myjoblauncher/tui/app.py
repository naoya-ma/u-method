"""
Fletを使わない、curses ベースのターミナルUI（--tui）。

スコープは「実行」（ジョブ一覧・実行・停止）と「履歴確認」のみ。
ジョブの追加・編集、ツール/リンク/日報/テーマ/Tier等の設定はGUI（--gui）・Web（--web）版を使うこと。
"""

import curses
import locale
import queue
import signal
import subprocess
import threading
import unicodedata

import uuid6

from services.config_loader import JOB_TYPE_FLEXIBLE, is_skeleton_job, load_config
from services.execution_engine import (
    ExecutionResult,
    build_result,
    start_process,
    start_process_no_wait,
    stream_process,
)
from services.history_repo import (
    STATUS_LABELS,
    get_job_daily_summary,
    get_job_executions,
    get_job_last_status,
    get_job_monthly_summary,
    insert_history_with_id,
)
from services import tz_repo
from utils.opener import build_stopwatch_url, open_target
from utils.param_parser import extract_params, substitute_params

MENU_PATH = "config/menu.toml"


def run_tui(menu_path: str = MENU_PATH) -> None:
    # curses初期化前にロケールを設定しないと、全角文字の幅計算・描画がおかしくなる
    # （Python公式ドキュメントが明記する既知の注意点。実際に踏んだ不具合の主因と判明）
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(lambda stdscr: _main_loop(stdscr, menu_path))


def _try_curs_set(visibility: int) -> None:
    """一部の端末はカーソル表示制御に対応しておらず curses.error になるため、失敗しても無視する"""
    try:
        curses.curs_set(visibility)
    except curses.error:
        pass


# ========================
# ✅ 全角文字・絵文字の表示幅を考慮した文字列操作
#
# Pythonの文字列フォーマット（f"{s:<6}"）やlen()は「文字数」で数えるが、
# 端末上での表示は全角文字・絵文字が2列分を占める（半角文字は1列）。
# 以前はこの表示幅を1本の文字列にパディングして連結していたが、端末・curses実装
# （Windowsの windows-curses/PDCurses含む）ごとの実際の表示幅・カーソル位置の扱いの
# 食い違いが後続列（ジョブ名等）の切り詰め幅にまで波及し、ジョブ名が数文字しか
# 描画されない不具合につながった（実際に踏んだ不具合）。
# そのため列を連結してのパディングはやめ、`_draw_job_list` では列ごとに固定x位置へ
# 個別にaddstrする方式にした。ここに残る _char_width/_truncate_to_width は、
# 画面右端をはみ出して curses.addstr() が例外にならないようにするための
# 切り詰め専用（`_safe_addstr` から使用）
# ========================
# services/history_repo.STATUS_LABELS 等で使われる絵文字。
# unicodedata.east_asian_width() は正式なEast Asian Width特性ではこれらを"N"(Neutral)扱いすることが多く、
# 実際の端末（Windows Terminal等）で2列表示されるのと食い違うため、既知の絵文字のみ明示的に2列として扱う
_WIDE_CHAR_OVERRIDE = set("✅❌⛔🔵⏰")


def _char_width(ch: str) -> int:
    if ch in _WIDE_CHAR_OVERRIDE:
        return 2
    return 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1


def _display_width(text: str) -> int:
    return sum(_char_width(ch) for ch in text)


def _wide_count(text: str) -> int:
    return sum(1 for ch in text if _char_width(ch) == 2)


def _pad_wide_count(text: str, target_count: int, fill: str = "　") -> str:
    """
    全角文字（表示幅2）の「個数」をtarget_countにそろえる（下記「表示幅の合計が
    行によって異なると～」の実測結果をさらに詰めた版）。
    表示幅の合計（_display_width）ではなく、全角文字の個数そのものをそろえる必要がある
    と判明した。例えば"✅ 完了"（絵文字1+半角スペース1+漢字2＝全角3個・表示幅7）は、
    全角文字4個で表示幅7にした文字列（半角スペースを含まない）とは表示幅の合計は同じでも
    全角文字の個数が異なり、結局ずれる（診断スクリプトで実機確認済み）。
    fillは全角スペース（表示幅2）を仮定し、1個につき全角文字1個分としてカウントする
    """
    return text + fill * max(0, target_count - _wide_count(text))


def _truncate_to_width(text: str, max_width: int) -> str:
    """表示幅ベースで、max_width列に収まるように末尾を切り詰める"""
    if max_width <= 0:
        return ""

    result = []
    width = 0
    for ch in text:
        w = _char_width(ch)
        if width + w > max_width:
            break
        result.append(ch)
        width += w
    return "".join(result)


# ========================
# ✅ メイン画面（ジョブ一覧）
# ========================
def _main_loop(stdscr, menu_path: str) -> None:
    _try_curs_set(0)
    stdscr.keypad(True)
    # 外部プロセスの出力等でコンソール画面が乱れても、無操作中も一定間隔で再描画して復旧する
    stdscr.timeout(500)

    selected = 0
    selected_ids: set = set()

    while True:
        # サブ画面側で timeout(-1) 等に変更されている場合があるため、毎回この値に戻す
        stdscr.timeout(500)

        menu_items = load_config(menu_path)

        if not menu_items:
            _draw_message(stdscr, "ジョブが登録されていません（config/menu.toml）。qで終了します")
            if stdscr.getch() in (ord("q"), ord("Q")):
                return
            continue

        selected = max(0, min(selected, len(menu_items) - 1))
        _draw_job_list(stdscr, menu_items, selected, selected_ids)

        key = stdscr.getch()
        if key == -1:
            continue  # タイムアウト（キー入力なし）。再描画のためループを継続する
        elif key in (ord("q"), ord("Q")):
            return
        elif key in (curses.KEY_UP, ord("k")):
            selected = (selected - 1) % len(menu_items)
        elif key in (curses.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(menu_items)
        elif key == ord(" "):
            job_id = menu_items[selected].job_id
            if job_id in selected_ids:
                selected_ids.discard(job_id)
            else:
                selected_ids.add(job_id)
        elif key in (curses.KEY_ENTER, 10, 13, ord("r"), ord("R")):
            if selected_ids:
                _run_batch(stdscr, menu_items, selected_ids)
                selected_ids.clear()
            else:
                _run_job(stdscr, menu_items[selected])
        elif key in (ord("h"), ord("H")):
            _show_history(stdscr, menu_items[selected])

        # ✅ 画面遷移から戻った直後は、外部プロセスの出力等で乱れている可能性があるため必ず全画面再描画する
        _force_redraw(stdscr)


def _force_redraw(stdscr) -> None:
    """
    curses自身の差分描画キャッシュを無視して、次のrefresh()で画面全体を強制的に再描画させる。
    サブプロセスの出力等、curses管理外の書き込みで端末画面が乱れた状態からの復旧に使う
    """
    stdscr.clearok(True)
    stdscr.touchwin()


def _draw_message(stdscr, message: str) -> None:
    stdscr.clear()
    for row, line in enumerate(message.split("\n")):
        try:
            stdscr.addstr(row, 0, line)
        except curses.error:
            pass
    stdscr.refresh()


# ジョブ一覧の列は「1本の文字列を作ってパディング→まとめてaddstr」ではなく、
# 列ごとに固定x位置へ個別にaddstrする（上記コメント参照）。
# 「非定型」（3文字）や絵文字混じりの状態ラベルが実際の端末でどれだけ物理的な
# 列幅を取るかは端末・curses実装依存で確実には読めないため、隣接列と衝突しないよう
# 理論上の必要幅より余裕を持たせた間隔にしてある
_COL_MARK_X = 0
_COL_NO_X = 4
_COL_ID_X = 9
_COL_TYPE_X = 16
_COL_STATUS_X = 26
_COL_NAME_X = 42

# windows-curses/PDCurses実機で、同じ行の手前に書いた文字列に含まれる「全角文字の個数」が
# 行によって異なると、固定x位置へのaddstr(y, x, ...)が絶対位置にならず、後続列がずれて
# 描画されるバグを確認した（本セッションで診断スクリプトにより実機確認済み。文字数や
# 表示幅の合計をそろえるだけでは不十分で、"✅ 完了"（全角3個+半角1個、表示幅7）のように
# 半角文字を含む文字列と、全角文字だけの文字列とでは、表示幅の合計が同じでも全角文字の
# 個数が異なり結局ずれる。全角文字の「個数」そのものをそろえる必要がある）。
# 種別「定型」(全角2個)/「非定型」(全角3個)、状態ラベル「―」(全角0個)/"✅ 完了"等(全角3個)は
# 行ごとに全角文字数が変わるため、後続列を書く前に必ず_pad_wide_count()でそろえること
_TYPE_WIDE_COUNT = 3  # 「非定型」の全角文字数に合わせる
_STATUS_WIDE_COUNT = 3  # "✅ 完了"/"❌ 失敗"/"⛔ 中断"の全角文字数に合わせる（半角スペースは含まない）


def _draw_job_list(stdscr, menu_items, selected: int, selected_ids: set) -> None:
    stdscr.clear()
    height, width = stdscr.getmaxyx()

    _safe_addstr(stdscr, 0, 0, "myJobLauncher (TUI)", width, curses.A_BOLD)
    _safe_addstr(
        stdscr,
        1,
        0,
        "↑/↓ or j/k:選択  Space:複数選択切替  Enter/r:実行(複数選択時は一括)  h:履歴  q:終了",
        width,
    )

    # A_BOLD/A_REVERSE/A_UNDERLINEを全角文字に付けると、この環境
    # （windows-curses/PDCurses＋コマンドプロンプト）では描画が途中で壊れる
    # （実際に踏んだ不具合。「種別」「状態」「名前」等の全角文字列には
    #   A_NORMAL以外の属性を付けないこと。ASCIIのみの文字列は安全）
    # 「種別」「状態」はデータ行と同じ全角文字数（_TYPE_WIDE_COUNT/_STATUS_WIDE_COUNT）に
    # パディングする。ヘッダーとデータ行で手前の列の全角文字数が違うと、_COL_NAME_Xの
    # 実際の描画位置がヘッダーとデータ行とでずれてしまう（上記と同じ理由）
    _safe_addstr(stdscr, 3, _COL_NO_X, "No.", width, curses.A_BOLD)
    _safe_addstr(stdscr, 3, _COL_ID_X, "ID", width, curses.A_BOLD)
    _safe_addstr(stdscr, 3, _COL_TYPE_X, _pad_wide_count("種別", _TYPE_WIDE_COUNT), width)
    _safe_addstr(stdscr, 3, _COL_STATUS_X, _pad_wide_count("状態", _STATUS_WIDE_COUNT), width)
    _safe_addstr(stdscr, 3, _COL_NAME_X, "名前", width)

    visible_rows = max(1, height - 5)
    top = max(0, selected - visible_rows + 1) if selected >= visible_rows else 0

    for row, idx in enumerate(range(top, min(len(menu_items), top + visible_rows))):
        item = menu_items[idx]
        status = STATUS_LABELS.get(get_job_last_status(item.command), "―")
        mark = "[x]" if item.job_id in selected_ids else "[ ]"
        y = 4 + row
        # カーソル行のハイライトは、種別・状態・ジョブ名（全角文字を含む）の手前で
        # A_REVERSEを一切使わないこと。全角文字を含まないASCIIだけの反転背景であっても、
        # 同じ行の後方に全角文字を書くと描画位置がずれる・途中で切れることを実機で確認した
        # （行全体に反転背景を敷こうとして一度試し、実際に不具合が再現した。実際に踏んだ不具合）。
        # そのためハイライトはASCIIのみのチェック印・No.・ID列（_COL_TYPE_X未満）に限定する
        ascii_attr = curses.A_REVERSE if idx == selected else curses.A_NORMAL
        if idx == selected:
            _safe_addstr(stdscr, y, 0, " " * max(0, _COL_TYPE_X - 1), width, curses.A_REVERSE)
        _safe_addstr(stdscr, y, _COL_MARK_X, mark, width, ascii_attr)
        _safe_addstr(stdscr, y, _COL_NO_X, f"{idx + 1:>3}", width, ascii_attr)
        _safe_addstr(stdscr, y, _COL_ID_X, item.job_id, width, ascii_attr)
        _safe_addstr(stdscr, y, _COL_TYPE_X, _pad_wide_count(item.job_type, _TYPE_WIDE_COUNT), width)
        _safe_addstr(stdscr, y, _COL_STATUS_X, _pad_wide_count(status, _STATUS_WIDE_COUNT), width)
        name_suffix = " (無効)" if not item.enabled else " (骨組み)" if is_skeleton_job(item) else ""
        name_text = f"{item.name}{name_suffix}"
        _safe_addstr(stdscr, y, _COL_NAME_X, name_text, width)

    if selected_ids:
        _safe_addstr(stdscr, height - 1, 0, f"{len(selected_ids)}件選択中", width, curses.A_DIM)

    stdscr.refresh()


def _safe_addstr(stdscr, y: int, x: int, text: str, width: int, attr=curses.A_NORMAL) -> None:
    """
    表示幅（全角=2列）ベースで画面幅に収まるよう切り詰めてから書き込む。
    それでも端末サイズの都合で失敗する場合（画面端での書き込みエラー等）は無視する
    """
    truncated = _truncate_to_width(text, max(0, width - x - 1))
    try:
        stdscr.addstr(y, x, truncated, attr)
    except curses.error:
        pass


# ========================
# ✅ ジョブ実行
# ========================
def _run_job(stdscr, item) -> None:
    if not item.enabled:
        _draw_message(stdscr, f"「{item.name}」は無効化されているため実行できません\n何かキーを押すと戻ります")
        stdscr.getch()
        return

    if is_skeleton_job(item):
        _draw_message(stdscr, f"「{item.name}」は骨組み状態（コマンド未設定）のため実行できません\n何かキーを押すと戻ります")
        stdscr.getch()
        return

    if item.job_type == JOB_TYPE_FLEXIBLE:
        _run_stopwatch_job(stdscr, item)
        return

    command = item.command
    params = extract_params(command)

    if params:
        values = _prompt_params(stdscr, params)
        command = substitute_params(command, values)

    if item.is_async:
        _run_async_job(stdscr, item, command)
    else:
        _run_sync_job(stdscr, item, command)


# ========================
# ✅ 複数選択（Space）からの一括実行
# ========================
def _batch_skip_reason(item) -> str:
    """GUI版（gui/run_tab.py の _batch_skip_reason）と同じ除外判定"""
    if not item.enabled:
        return "無効化されているため"
    if is_skeleton_job(item):
        return "骨組み状態（コマンド未設定）のため"
    if item.job_type == JOB_TYPE_FLEXIBLE:
        return "非定型業務のため"
    if extract_params(item.command):
        return "パラメータ入力が必要なため"
    return None


def _run_batch(stdscr, menu_items: list, selected_ids: set) -> None:
    targets = [item for item in menu_items if item.job_id in selected_ids]
    summary: list = []

    runnable = []
    for item in targets:
        reason = _batch_skip_reason(item)
        if reason:
            summary.append(f"  スキップ: {item.name}（{reason}。個別に実行してください）")
        else:
            runnable.append(item)

    for i, item in enumerate(runnable, start=1):
        progress = f"{i}/{len(runnable)}"
        if item.is_async:
            try:
                start_process_no_wait(item.command)
                now = tz_repo.now()
                insert_history_with_id(
                    str(uuid6.uuid7()), ExecutionResult(item.command, 0, "", "", now, now)
                )
                summary.append(f"  起動（非同期）: {item.name}")
            except Exception as ex:
                summary.append(f"  失敗: {item.name}（{ex}）")
            continue

        _run_sync_job(stdscr, item, item.command, progress=progress)
        summary.append(f"  実行: {item.name}")

    _draw_message(stdscr, "一括実行が完了しました\n\n" + "\n".join(summary) + "\n\n何かキーを押すと戻ります")
    stdscr.getch()


def _prompt_params(stdscr, params: list) -> dict:
    _try_curs_set(1)
    curses.echo()
    values = {}
    try:
        for i, name in enumerate(params):
            stdscr.clear()
            stdscr.addstr(0, 0, f"パラメータ入力 {i + 1}/{len(params)}（空欄可、Enterで確定）")
            prompt = f"{name}: "
            stdscr.addstr(2, 0, prompt)
            stdscr.refresh()
            raw = stdscr.getstr(2, len(prompt), 200)
            values[name] = raw.decode("utf-8", errors="replace")
    finally:
        curses.noecho()
        _try_curs_set(0)
    return values


def _run_async_job(stdscr, item, command: str) -> None:
    command_id = str(uuid6.uuid7())
    now = tz_repo.now()

    try:
        start_process_no_wait(command)
    except Exception as ex:
        _draw_message(stdscr, f"起動に失敗しました: {ex}\n何かキーを押すと戻ります")
        stdscr.getch()
        return

    result = ExecutionResult(item.command, 0, "", "", now, now)
    insert_history_with_id(command_id, result)

    _draw_message(stdscr, f"「{item.name}」を非同期で起動しました。何かキーを押すと戻ります")
    stdscr.getch()


def _run_sync_job(stdscr, item, command: str, progress: str = None) -> None:
    start_time = tz_repo.now()

    try:
        process = start_process(command)
    except Exception as ex:
        _draw_message(stdscr, f"起動に失敗しました: {ex}\n何かキーを押すと戻ります")
        stdscr.getch()
        return

    output_queue: "queue.Queue" = queue.Queue()
    state = {"result": None}

    def on_output(line: str) -> None:
        output_queue.put(line.rstrip("\n"))

    def worker() -> None:
        stdout_buf, stderr_buf = stream_process(process, on_output)
        state["result"] = build_result(process, item.command, stdout_buf, stderr_buf, start_time)
        output_queue.put(None)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    lines: list = []
    stopped = False
    finished = False

    stdscr.timeout(150)
    while not finished:
        try:
            while True:
                line = output_queue.get_nowait()
                if line is None:
                    finished = True
                    break
                lines.append(line)
        except queue.Empty:
            pass

        _draw_log(stdscr, item.name, lines, running=not finished, stopped=stopped, progress=progress)

        key = stdscr.getch()
        if key in (ord("s"), ord("S")) and not stopped and not finished:
            stopped = True
            _terminate_process(process)

    stdscr.timeout(-1)
    thread.join(timeout=5)

    result = state["result"]
    if result is not None:
        insert_history_with_id(str(uuid6.uuid7()), result)

    _draw_log(
        stdscr,
        item.name,
        lines,
        running=False,
        stopped=stopped,
        footer="完了しました。何かキーを押すと戻ります",
        progress=progress,
    )
    stdscr.getch()


def _terminate_process(process) -> None:
    """GUI版（gui/run_tab.py の cancel_task）と同じ手順で強制停止する"""
    try:
        process.send_signal(signal.CTRL_BREAK_EVENT)
    except Exception:
        pass

    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
    except Exception:
        pass


def _draw_log(
    stdscr,
    job_name: str,
    lines: list,
    running: bool,
    stopped: bool = False,
    footer: str = None,
    progress: str = None,
) -> None:
    stdscr.clear()
    height, width = stdscr.getmaxyx()

    if running:
        status, hint = "実行中", "s:停止"
    elif stopped:
        status, hint = "停止しました", footer or "何かキーを押すと戻ります"
    else:
        status, hint = "完了", footer or "何かキーを押すと戻ります"

    title = f"実行: {job_name}  [{status}]"
    if progress:
        title = f"[{progress}] {title}"

    # job_name等の全角文字を含むためA_BOLDは付けない（上記「全角文字の表示幅対応」参照）
    _safe_addstr(stdscr, 0, 0, title, width)
    _safe_addstr(stdscr, 1, 0, hint, width)

    visible_rows = max(1, height - 3)
    for row, line in enumerate(lines[-visible_rows:]):
        _safe_addstr(stdscr, 2 + row, 0, line, width)

    stdscr.refresh()


# ========================
# ✅ 非定型業務（業務記録プラグインで計測し、実行履歴へ記録）
# ========================
def _run_stopwatch_job(stdscr, item) -> None:
    start_time = tz_repo.now()

    try:
        open_target(build_stopwatch_url(item))
    except Exception as ex:
        _draw_message(stdscr, f"業務記録プラグインを開けませんでした: {ex}\n何かキーを押すと戻ります")
        stdscr.getch()
        return

    _draw_message(
        stdscr,
        f"「{item.name}」の計測を開始しました（業務記録プラグインを開きました）。\n"
        "作業が終わったら Enter を押すと実行履歴へ記録します（qでキャンセル）",
    )

    while True:
        key = stdscr.getch()
        if key in (10, 13, curses.KEY_ENTER):
            break
        if key in (ord("q"), ord("Q")):
            return

    end_time = tz_repo.now()
    result = ExecutionResult(item.command, 0, "", "", start_time, end_time)
    insert_history_with_id(str(uuid6.uuid7()), result)

    duration = (end_time - start_time).total_seconds()
    _draw_message(stdscr, f"実行履歴へ記録しました（{duration:.1f}秒）。何かキーを押すと戻ります")
    stdscr.getch()


# ========================
# ✅ 履歴確認
# ========================
def _show_history(stdscr, item) -> None:
    monthly = get_job_monthly_summary(item.command)
    daily = get_job_daily_summary(item.command)
    executions = get_job_executions(item.command)

    lines = [f"ジョブ: {item.name}", f"コマンド: {item.command}", ""]

    lines.append("[月別集計] 年月 / 件数 / 成功 / 失敗")
    if monthly:
        for month, total, success, fail in monthly:
            lines.append(f"  {month}  {total}件  成功{success}  失敗{fail}")
    else:
        lines.append("  (実行履歴がありません)")

    lines.append("")
    lines.append("[日別集計] 日付 / 件数 / 成功 / 失敗")
    for day, total, success, fail in daily:
        lines.append(f"  {day}  {total}件  成功{success}  失敗{fail}")

    lines.append("")
    lines.append("[個別実行履歴（新しい順、最大50件）] 開始 - 終了 / 経過 / 状態")
    for start, end, _returncode, status in executions[:50]:
        label = STATUS_LABELS.get(status, status)
        lines.append(f"  {start:%Y-%m-%d %H:%M:%S} - {end:%H:%M:%S}  {_format_elapsed(start, end)}  {label}")

    offset = 0
    stdscr.timeout(-1)
    while True:
        _draw_scrollable(stdscr, "履歴（↑/↓ or j/k でスクロール、qで戻る）", lines, offset)
        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            return
        elif key in (curses.KEY_UP, ord("k")):
            offset = max(0, offset - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            offset += 1


def _format_elapsed(start, end) -> str:
    if not start or not end:
        return "-"
    total_seconds = int((end - start).total_seconds())
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def _draw_scrollable(stdscr, title: str, lines: list, offset: int) -> None:
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    # 呼び出し元のtitleは全角文字を含みうるためA_BOLDは付けない（上記「全角文字の表示幅対応」参照）
    _safe_addstr(stdscr, 0, 0, title, width)

    visible_rows = max(1, height - 2)
    max_offset = max(0, len(lines) - visible_rows)
    offset = min(offset, max_offset)

    for row, line in enumerate(lines[offset : offset + visible_rows]):
        _safe_addstr(stdscr, 2 + row, 0, line, width)

    stdscr.refresh()
