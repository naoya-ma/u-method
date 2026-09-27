"""
起動処理の経過時間計測・簡易スピナー表示（`--verbose`用）。

`main.py`（起動直後〜前処理〜`ft.run()`呼び出し）と`gui/main_window.py`
（`MainWindow.__init__`内での各タブ構築）の両方から使うため、Flet非依存の
`services/`層に置いている（`gui/main_window.py`が`main.py`をimportすると循環
importになるため、共通ロジックはここに集約する）。
"""

import sys
import threading
import time
from contextlib import contextmanager

# ✅ プロセス起動直後からの経過時間の基準点（--verbose用）。このモジュールが最初に
# importされた時点（＝main.pyの他の重いimportより前に置く想定）で確定させる
_START = time.perf_counter()

_HEARTBEAT_INTERVAL_SECONDS = 0.2


def elapsed() -> float:
    return time.perf_counter() - _START


def start_heartbeat(label: str):
    """
    別スレッドで一定間隔（0.2秒）ごとにコンソールへ`\r`で同じ行を上書きしながら経過時間を
    出し続ける（tqdm的な簡易スピナー）。importやFletクライアント自身の起動処理・タブ構築のように
    内部の進捗を計測できない区間でも、「固まっていない」ことが分かるようにするのが目的。
    戻り値`(stop_event, thread)`を`stop_heartbeat()`に渡すと、スレッドの後片付け
    （行のクリア）を待ってから停止する
    """
    stop_event = threading.Event()

    def _tick() -> None:
        while not stop_event.is_set():
            sys.stdout.write(f"\r[起動] {label} 実行中...（{elapsed():.2f}秒経過）")
            sys.stdout.flush()
            stop_event.wait(_HEARTBEAT_INTERVAL_SECONDS)
        sys.stdout.write("\r" + " " * 72 + "\r")
        sys.stdout.flush()

    thread = threading.Thread(target=_tick, daemon=True)
    thread.start()
    return stop_event, thread


def stop_heartbeat(heartbeat, label: str, step_start: float) -> None:
    stop_event, thread = heartbeat
    stop_event.set()
    # ✅ スレッド側の行クリア（\r上書き）が終わるのを待ってから完了メッセージを出す。
    # 待たずに先にprint()すると、まだ消え切っていない「実行中...」の残骸と完了メッセージが
    # 同じ行に混ざって表示が乱れることがある（コンソール出力の競合、実機で確認済み）
    thread.join(timeout=1)
    print(f"[起動] {label} 完了（区間{time.perf_counter() - step_start:.2f}秒／累計{elapsed():.2f}秒経過）")


@contextmanager
def startup_step(label: str, verbose: bool):
    """`verbose`時のみ`start_heartbeat()`/`stop_heartbeat()`で囲む。offの間は素通り"""
    if not verbose:
        yield
        return

    heartbeat = start_heartbeat(label)
    step_start = time.perf_counter()
    try:
        yield
    finally:
        stop_heartbeat(heartbeat, label, step_start)
