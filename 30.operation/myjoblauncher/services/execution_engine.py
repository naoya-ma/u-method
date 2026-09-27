import os
import subprocess
import sys
import tempfile
import threading

from services import tz_repo

# ========================
# ✅ 実行中の子プロセス管理（Ctrl+C等での異常終了時、取り残しを防ぐため）
# ========================
_active_processes: set[subprocess.Popen] = set()
_active_processes_lock = threading.Lock()


def _register_process(process: subprocess.Popen) -> None:
    with _active_processes_lock:
        _active_processes.add(process)


def _unregister_process(process: subprocess.Popen) -> None:
    with _active_processes_lock:
        _active_processes.discard(process)


def terminate_all_active_processes() -> None:
    """
    アプリ終了時（Ctrl+C・ウィンドウを閉じた時）に、まだ実行中の同期ジョブの子プロセスを強制終了する。
    非同期実行（start_process_no_wait、ツール起動含む）はここでは対象外
    （アプリを閉じても動き続けることを意図した「切り離し」実行のため）
    """
    with _active_processes_lock:
        processes = list(_active_processes)

    for process in processes:
        try:
            if process.poll() is None:
                process.kill()
        except Exception:
            pass


class ExecutionResult:
    def __init__(self, command, returncode, stdout, stderr, start, end):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.start_time = start
        self.end_time = end


# ========================
# プロセス開始
# ========================
def start_process(command: str):
    """
    コマンドを非同期で起動し、Processを返す
    → ここで即返すのが重要（キャンセル可能にする）
    """

    encoding = "cp932" if sys.platform.startswith("win") else "utf-8"

    creationflags = 0
    if sys.platform.startswith("win"):
        # ✅ Ctrl+Break送信のため
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding=encoding,
        errors="replace",
        bufsize=1,               # ✅ 行単位
        creationflags=creationflags
    )

    _register_process(process)
    return process

def start_process_no_wait(command: str, cwd: str | None = None):
    """
    非同期起動（ログ取得しない）
    """
    import subprocess
    import sys

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    process = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd or None,
        creationflags=creationflags
    )

    return process


# ========================
# ✅ バッチ/PowerShellスクリプト本文の起動（gui/tools_tab.pyの「実行種別」ツール専用）
# ========================
def start_script_process(extension: str, content: str, cwd: str | None = None):
    """
    複数行のバッチ/PowerShellスクリプト本文（コメント行可）を一時ファイルへ書き出し、
    stdout/stderrを捕捉する形で起動する。ジョブ実行（start_process）と異なりコマンド文字列ではなく
    スクリプト本文を扱うため、shell=True文字列実行ではなく実行ファイル＋引数リストのPopenにする
    （テンポラリパスに空白が含まれても引用符処理をsubprocess側に委ねられ確実に動く）。
    戻り値は(process, 一時ファイルパス)。呼び出し側は実行完了後に一時ファイルを削除すること
    """
    encoding = "cp932" if sys.platform.startswith("win") else "utf-8"

    # ✅ バッチ（.bat）は既定で「エコーオン」状態のため、cmd.exeが実行前に各コマンド行を
    # 「<カレントディレクトリ>>コマンド」という形（例: "C:\...\myjoblauncher>cmd /c ..."）で
    # そのままログへエコーしてしまう（実機で確認済み）。実際にファイルを書き換える操作では
    # 全く無いが、シェルのリダイレクト演算子`>`とパスが並んで見えるため、運用ログを見た人が
    # 「システム上のファイルを壊しているのでは」と誤解しかねない（ユーザーからの指摘）。
    # 対策として、バッチ本文の先頭に`@echo off`を必ず挿入し、以降の行のエコーを抑止する
    # （ユーザー自身が既に`@echo off`を書いていても、二重になるだけで無害）
    if extension != ".ps1":
        content = "@echo off\r\n" + content

    fd, path = tempfile.mkstemp(suffix=extension, prefix="mj_tool_")
    with os.fdopen(fd, "w", encoding=encoding, errors="replace", newline="\r\n") as f:
        f.write(content)

    if extension == ".ps1":
        args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path]
    else:
        args = ["cmd.exe", "/c", path]

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform.startswith("win") else 0

    process = subprocess.Popen(
        args,
        cwd=cwd or None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding=encoding,
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
    )

    _register_process(process)
    return process, path


# ========================
# ✅ ターミナル系コマンド（cmd/powershell）専用の起動
# ========================
TERMINAL_EXE_NAMES = {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}


def is_terminal_command(command: str) -> bool:
    """
    コマンドのベース名がcmd/powershell/pwshかどうかを判定する（大文字小文字無視）。
    これらは独立した新規コンソールで起動する（start_terminal_process参照）
    """
    base = os.path.basename(command.strip().strip('"')).lower()
    return base in TERMINAL_EXE_NAMES


def is_bare_launcher_command(command: str) -> bool:
    """
    コマンド文字列が、パス区切り・環境変数参照・引用符・空白を含まない「素の起動名」
    （例: `ONENOTE.EXE`、`ms-settings:`、`pbrush.exe`）かどうかを判定する。
    真の場合は start_tool() が cmd.exe（shell=True）ではなく os.startfile（ShellExecute）で
    起動する。理由は is_bare_launcher_command を使う start_tool() の docstring を参照
    """
    stripped = command.strip()
    if not stripped or " " in stripped or "\\" in stripped or "/" in stripped:
        return False
    if "%" in stripped or stripped.startswith('"'):
        return False
    return True


def start_tool(command: str, args: str = "", cwd: str | None = None) -> None:
    """
    ツール起動専用（gui/tools_tab.pyから使用）。ジョブ実行（start_process/start_process_no_wait）
    とは異なるコマンド解決規則を使う。

    `is_bare_launcher_command(command)`が真（例: `ONENOTE.EXE`、`ms-settings:`）の場合は
    `os.startfile`（Windows ShellExecute）で起動する。cmd.exe（shell=True）のバイナリ名解決は
    PATH+PATHEXTのみで、Windowsレジストリの「App Paths」（ONENOTE.EXE等、Officeが登録する
    従来型の解決方式）やURIプロトコル（ms-settings:等）を解決できず、`cmd /c ONENOTE.EXE`が
    「'ONENOTE.EXE' は、内部コマンドまたは外部コマンド...として認識されていません」で
    サイレントに失敗する不具合を実機で確認した（Popenの起動自体は成功しアプリからは
    エラーに見えないため気付きにくい）。ShellExecuteはWin+Rの「ファイル名を指定して実行」と
    同じ解決方式のため、App Paths・URIプロトコル・アプリ実行エイリアスのいずれも正しく解決できる。

    それ以外（`"%LOCALAPPDATA%\\..."`のように環境変数展開が必要なパス、引用符付きフルパス等）は
    従来通り`start_process_no_wait`（cmd.exe経由）を使う。`os.startfile`は`%ENV%`のような
    環境変数トークンを展開しないため、環境変数を含むコマンドをShellExecute経由にすると
    別の不具合（存在しないパスとして失敗）を招く
    """
    if is_bare_launcher_command(command):
        os.startfile(command, arguments=args or "", cwd=cwd or None)
        return

    full_command = f"{command} {args}".strip() if args else command
    start_process_no_wait(full_command, cwd=cwd)


def start_terminal_process(command: str, args: str = "", cwd: str | None = None):
    """
    cmd/powershell/pwsh専用の起動。start_process_no_wait のような shell=True
    （Windows上では内部的に cmd.exe /c <command> という入れ子起動になる）を使わず、
    CREATE_NEW_CONSOLE で独立した新しいコンソールウィンドウを割り当てる。
    入れ子のcmd起動だとウィンドウのライフサイクルが親のcmd.exe /cにも紐づき、
    終了時の挙動がわかりにくくなるため、単独のコンソールに閉じる形にしている
    """
    full_command = f"{command} {args}".strip() if args else command

    process = subprocess.Popen(
        full_command,
        cwd=cwd or None,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

    return process
    
# ========================
# ストリーム処理
# ========================
def stream_process(process, on_output):
    """
    stdout / stderr をリアルタイム処理
    on_output(line) でUIに通知
    """

    stdout_buffer = []
    stderr_buffer = []

    try:
        # ✅ stdout
        for line in process.stdout:
            stdout_buffer.append(line)
            on_output(line)

        # ✅ stderr
        for line in process.stderr:
            stderr_buffer.append(line)
            on_output("[ERR] " + line)

        process.wait()
    finally:
        _unregister_process(process)

    return stdout_buffer, stderr_buffer


# ========================
# 結果生成
# ========================
def build_result(process, command, stdout_buffer, stderr_buffer, start_time):
    end_time = tz_repo.now()

    return ExecutionResult(
        command=command,
        returncode=process.returncode,
        stdout="".join(stdout_buffer),
        stderr="".join(stderr_buffer),
        start=start_time,
        end=end_time,
    )
