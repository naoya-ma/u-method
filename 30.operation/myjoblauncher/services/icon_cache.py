import hashlib
import io
import os
import re
import shutil
import subprocess
import urllib.request
import winreg
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

import flet as ft
import win32api
import win32con
import win32gui
import win32ui
from PIL import Image
from win32com.shell import shell, shellcon

ICON_CACHE_DIR = "cache/icons"

# ✅ 実体（exe/favicon）からアイコンを取得できない場合の、名称キーワードによる既定アイコン判別
_FALLBACK_KEYWORDS = [
    (("code", "vscode"), ft.Icons.CODE),
    (("excel", "スプレッドシート"), ft.Icons.TABLE_CHART),
    (("cmd", "powershell", "pwsh", "terminal", "コマンドプロンプト"), ft.Icons.TERMINAL),
    (("explorer", "エクスプロー"), ft.Icons.FOLDER),
    (("note", "memo", "obsidian", "メモ"), ft.Icons.EDIT_NOTE),
    (("mail", "outlook", "メール"), ft.Icons.MAIL),
    (("calendar", "カレンダー"), ft.Icons.CALENDAR_MONTH),
    (("browser", "chrome", "edge", "firefox"), ft.Icons.PUBLIC),
    (("paint", "ペイント", "draw", "brush"), ft.Icons.BRUSH),
]
DEFAULT_FALLBACK_ICON = ft.Icons.APPS


def guess_fallback_icon(name: str) -> str:
    lower = (name or "").lower()
    for keywords, icon in _FALLBACK_KEYWORDS:
        if any(k in lower for k in keywords):
            return icon
    return DEFAULT_FALLBACK_ICON


def _cache_path(key: str) -> str:
    os.makedirs(ICON_CACHE_DIR, exist_ok=True)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return os.path.join(ICON_CACHE_DIR, f"{digest}.png")


def _lookup_app_path(exe_name: str) -> str | None:
    """
    Windowsレジストリの「App Paths」（HKCU→HKLMの順）から実行ファイルの
    フルパスを検索する。Win+Rや`start`コマンドが素の実行ファイル名（例: "onenote.exe"）を
    解決する際に実際に使われている仕組みで、PATH環境変数には登録されていない
    Office等のアプリ（レジストリのApp Pathsにのみ登録されている）を解決できる
    """
    exe_name = os.path.basename(exe_name)
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        key_path = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{exe_name}"
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, None)
        except OSError:
            continue
        if value and os.path.isfile(value):
            return value
    return None


def _is_fake_app_alias(path: str) -> bool:
    """
    `%LOCALAPPDATA%\\Microsoft\\WindowsApps\\`配下の「アプリ実行エイリアス」を判定する。
    これは実体を持たないスタブファイル（通常0バイト、reparse point）で、
    シェルがダブルクリック/コマンド実行時にリダイレクトするためのものであり、
    PE形式のアイコンリソースを持たないため`win32gui.ExtractIconEx`は必ず失敗する
    （実際に`pbrush.exe`で確認済み）。抽出を試みる前にここで判定する
    """
    normalized = path.replace("/", "\\").lower()
    if "\\windowsapps\\" not in normalized:
        return False
    try:
        return os.path.getsize(path) < 1024
    except OSError:
        return False


def _resolve_app_alias_target(alias_path: str) -> str | None:
    """
    アプリ実行エイリアス（reparse point、タグ`IO_REPARSE_TAG_APPEXECLINK`=0x8000001b）が
    指す実際の実行ファイルパスを取り出す。`pbrush.exe`のような後方互換のリダイレクトエイリアスは
    実体を持たないため、そのままではアイコンを抽出できない（`_is_fake_app_alias()`参照）。
    このreparse pointのデータ構造は「4バイトのバージョン値」＋「NUL区切りのUTF-16LE文字列列
    （PackageId／EntryPoint／Executable〈実際のターゲットパス〉…）」で、3番目の文字列が
    ターゲットの絶対パスになる（`fsutil reparsepoint query`の生データを実機で解析して確認済み。
    例: pbrush.exe → …\\Microsoft.Paint_...\\PaintApp\\mspaint.exe）
    """
    try:
        result = subprocess.run(
            ["fsutil", "reparsepoint", "query", alias_path],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        return None

    hex_bytes: list[str] = []
    for line in result.stdout.decode("cp932", errors="ignore").splitlines():
        m = re.match(r"^[0-9a-fA-F]{4}:\s+((?:[0-9a-fA-F]{2}\s+)+)", line)
        if m:
            hex_bytes.extend(m.group(1).split())

    if not hex_bytes:
        return None

    try:
        data = bytes(int(b, 16) for b in hex_bytes)
    except ValueError:
        return None

    # バイト列のまま b"\x00\x00" で区切ると、ASCII文字は上位バイトが常に0x00のため
    # 「直前の文字の上位バイト」と「終端NULの下位バイト」が偶然連続してしまい、
    # 1バイトずれて区切られてしまう（実機で確認済みの不具合）。
    # 先に全体をUTF-16LEとして文字列にデコードしてから、実際のNUL文字（\x00）で
    # 区切ることで、バイト境界のズレを避けられる
    text_all = data[4:].decode("utf-16-le", errors="ignore")
    for text in text_all.split("\x00")[:4]:
        if text and text.lower().endswith(".exe") and os.path.isfile(text):
            return text
    return None


def _search_path_literal(filename: str) -> str | None:
    """
    `shutil.which()`は、対象の拡張子がPATHEXT（既定は.COM/.EXE/.BAT/.CMD/.VBS/.VBE/.JS/.JSE/
    .WSF/.WSH/.MSCのみ）に含まれない場合、その拡張子のまま探さずPATHEXTを付け直して
    探してしまうため、`.cpl`（コントロールパネル項目、既定のPATHEXTに含まれない）のような
    拡張子のファイル名を素のまま解決できない（`sysdm.cpl`/`appwiz.cpl`で実際に確認済み）。
    PATH環境変数の各ディレクトリを直接走査し、指定されたファイル名そのものの存在を確認する
    """
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, filename)
        if os.path.isfile(candidate):
            return candidate
    return None


def _resolve_exe_path(command: str) -> str | None:
    """
    command文字列（引用符・環境変数を含む）から実在する実行ファイルパスを取り出す。
    フルパスでない場合（例: "cmd.exe"、"onenote.exe"、"sysdm.cpl"）は、
    ① レジストリの「App Paths」（`_lookup_app_path()`）→ ② PATH環境変数（`shutil.which()`、
    PATHEXTに応じて拡張子省略も解決する）→ ③ PATH環境変数の素のファイル名探索
    （`_search_path_literal()`、`.cpl`等PATHEXT既定に無い拡張子用）の順に検索する。
    ②の結果が`%LOCALAPPDATA%\\...\\WindowsApps\\`配下の「アプリ実行エイリアス」（実体を持たない
    スタブファイル、`_is_fake_app_alias()`参照）だった場合は、reparse pointから実際の
    ターゲット実行ファイルを解決する（`_resolve_app_alias_target()`。例: pbrush.exe→mspaint.exe）。
    解決できなければNone（フォールバックアイコンに委ねる）
    """
    stripped = command.strip()
    if stripped.startswith('"'):
        # 先頭が引用符の場合は、閉じ引用符までを1トークンとして扱う（パスにスペースを含む場合）
        end = stripped.find('"', 1)
        first_token = stripped[1:end] if end != -1 else stripped.strip('"')
    else:
        first_token = stripped.split(" ")[0]

    path = os.path.expandvars(first_token)
    if os.path.isfile(path):
        return path

    app_path = _lookup_app_path(path)
    if app_path:
        return app_path

    which_result = shutil.which(path)
    if which_result:
        if _is_fake_app_alias(which_result):
            return _resolve_app_alias_target(which_result)
        return which_result

    return _search_path_literal(path)


def _draw_icon_on(hicon, size: int, bg_colorref: int):
    """
    hiconをsize×sizeの単色背景に描画し、PIL Imageで返す（RGB、背景色が透けて見える）。
    `win32gui.GetDC(0)`で取得した画面DCは`win32gui.ReleaseDC()`で必ず解放すること
    （実際に踏んだ不具合: これを怠ると呼び出すたびにGDIハンドルがリークし、
    ツールの起動のたびに強制再抽出される本関数の呼び出し頻度と相まって、
    使い続けるうちにプロセスのGDIハンドル上限に達し、以降の抽出が壊れた画像
    〈アイコンが黒一色になる〉を返すようになる。「いつからか黒くなった」という
    形でしか症状が出ないため原因の特定が難しい）
    """
    hdc_screen = win32gui.GetDC(0)
    try:
        hdc = win32ui.CreateDCFromHandle(hdc_screen)
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, size, size)
        hdc_mem = hdc.CreateCompatibleDC()
        hdc_mem.SelectObject(hbmp)
        hdc_mem.FillSolidRect((0, 0, size, size), bg_colorref)
        hdc_mem.DrawIcon((0, 0), hicon)

        info = hbmp.GetInfo()
        bits = hbmp.GetBitmapBits(True)
        img = Image.frombuffer(
            "RGBA", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRA", 0, 1
        ).convert("RGB")

        hdc_mem.DeleteDC()
        win32gui.DeleteObject(hbmp.GetHandle())
        return img
    finally:
        win32gui.ReleaseDC(0, hdc_screen)


def _extract_exe_icon_to_png(exe_path: str, out_path: str) -> bool:
    """
    HICONをGDIの`CreateCompatibleBitmap`+`DrawIcon`で直接ビットマップ化すると、
    アルファチャンネル無し（クラシック形式、ANDマスクのみ）のアイコンでは
    アルファが常に0（完全透明＝実質非表示）になってしまう不具合を実機で確認した
    （sakura.exe等の古い形式のアイコンで発生。VSCode/Obsidian等の近代的な32bit
    アルファ付きアイコンでは問題なかった）。
    そのため、アイコンを黒背景・白背景の2通りに描画し、その2枚の差分から
    「差分マット法」でアルファと元の色を数式的に復元する（"二重描画差分法"）:
      観測値(黒背景) = alpha * 元の色
      観測値(白背景) = alpha * 元の色 + (1-alpha) * 255
      → alpha = 255 - (白背景の観測値 - 黒背景の観測値)
      → 元の色 = 黒背景の観測値 * 255 / alpha （alpha>0のとき）
    ピクセル完全一致（等号判定）で不透明/透明の二値判定をする方式を最初に採用したが、
    アンチエイリアス・縮小描画時のわずかな誤差で不透明ピクセルまで誤って透明判定され、
    黒い斑点状のノイズが出る不具合を実機で確認した（コントロールパネル等、階調のある
    アイコンで顕著）。上記の数式ベースの復元に変更することで、わずかな誤差があっても
    滑らかにアルファ・色を復元できるため斑点が出ない。

    【重要・実機で確認済み】`win32gui.ExtractIconEx(path, 0)`は、ファイルは実在し正常な
    アイコンを持つはずでも空リストを返すことがある（`winver.exe`で実機確認済み。原因は
    アイコンリソースの格納形式がExtractIconExの想定〈インデックス0＝先頭のアイコングループ〉と
    一致しないためと推定）。この場合、Explorerがアイコン表示に使うのと同じシェルAPI
    `SHGetFileInfo`（`win32com.shell.shell.SHGetFileInfo`、`SHGFI_ICON | SHGFI_LARGEICON`）に
    フォールバックする。実機でwinver.exeに対し有効なHICONが得られることを確認済み
    """
    try:
        large, small = win32gui.ExtractIconEx(exe_path, 0)
    except Exception:
        large, small = [], []

    hicon = (large or small)[0] if (large or small) else None
    from_shell = False
    if not hicon:
        try:
            ok, info = shell.SHGetFileInfo(
                exe_path, 0, shellcon.SHGFI_ICON | shellcon.SHGFI_LARGEICON
            )
            if ok:
                hicon = info[0]
                from_shell = True
        except Exception:
            hicon = None

    if not hicon:
        return False

    try:
        size = win32api.GetSystemMetrics(win32con.SM_CXICON)
        black = _draw_icon_on(hicon, size, win32api.RGB(0, 0, 0))
        white = _draw_icon_on(hicon, size, win32api.RGB(255, 255, 255))

        result = Image.new("RGBA", (size, size))
        black_px = black.load()
        white_px = white.load()
        result_px = result.load()
        for y in range(size):
            for x in range(size):
                br, bg_, bb = black_px[x, y]
                wr, wg, wb = white_px[x, y]
                diff = ((wr - br) + (wg - bg_) + (wb - bb)) / 3.0
                alpha = max(0, min(255, round(255 - diff)))
                if alpha > 0:
                    r = max(0, min(255, round(br * 255 / alpha)))
                    g = max(0, min(255, round(bg_ * 255 / alpha)))
                    b = max(0, min(255, round(bb * 255 / alpha)))
                else:
                    r, g, b = 0, 0, 0
                result_px[x, y] = (r, g, b, alpha)

        result.save(out_path)
        return True
    except Exception:
        return False
    finally:
        for h in (large or []) + (small or []):
            try:
                win32gui.DestroyIcon(h)
            except Exception:
                pass
        if from_shell:
            try:
                win32gui.DestroyIcon(hicon)
            except Exception:
                pass


_APPSFOLDER_RE = re.compile(r"shell:appsfolder\\([^!\s\\]+![^\s\\]+)", re.IGNORECASE)


def _extract_aumid(command: str) -> str | None:
    """
    コマンド文字列から`shell:appsFolder\\<AUMID>`のAUMID（PackageFamilyName!AppId）を取り出す。
    `explorer.exe shell:appsFolder\\Claude_pzs8sxrjxfjjc!Claude`のような、
    パッケージ化アプリ（UWP/MSIX）をシェル経由で起動するコマンドで使われる書式
    """
    m = _APPSFOLDER_RE.search(command)
    return m.group(1) if m else None


def _resolve_package_install_location(package_family_name: str) -> str | None:
    """
    PowerShellの`Get-AppxPackage`でPackageFamilyName→InstallLocationを解決する。
    `-PackageFamilyName`パラメータはこの環境のPowerShellでは使えなかったため
    （実機で確認済み）、`Where-Object`でフィルタする形にしている
    """
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-AppxPackage | Where-Object { $_.PackageFamilyName -eq "
                f"'{package_family_name}' }}).InstallLocation",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    location = result.stdout.strip()
    return location if location and os.path.isdir(location) else None


def _resolve_scaled_asset(install_location: str, relative_path: str) -> str | None:
    """
    AppxManifest.xmlが指す画像パス（例: "Assets\\Square44x44Logo.png"）は、実際のディスク上では
    "Square44x44Logo.scale-200.png"のようにスケール接尾辞が付いていることが多い。
    完全一致するファイルが無ければ、同じディレクトリ・同じベース名で前方一致検索する
    """
    full_path = os.path.join(install_location, relative_path)
    if os.path.isfile(full_path):
        return full_path

    directory = os.path.dirname(full_path)
    base, ext = os.path.splitext(os.path.basename(full_path))
    if not os.path.isdir(directory):
        return None
    for fname in os.listdir(directory):
        if fname.lower().startswith(base.lower()) and fname.lower().endswith(ext.lower()):
            return os.path.join(directory, fname)
    return None


def _resolve_appsfolder_icon_source(aumid: str) -> str | None:
    """
    AUMID（PackageFamilyName!AppId）から、アイコンの取得元となる実体のパスを解決する。
    ① デスクトップブリッジ形式（Win32アプリをMSIXにパッケージしたもの。
       AppxManifest.xmlの`<Application Executable="...">`が実際のexeを指す）なら
       そのexeパスを返す（Claude Desktopで実機確認済み。以後は通常のexeアイコン抽出と同じ扱いにできる）
    ② 純粋なUWPアプリ（`Executable`属性が無い）なら、`<uap:VisualElements>`の
       `Square44x44Logo`/`Square150x150Logo`が指すPNG画像ファイルを返す
    どちらも解決できなければNone
    """
    if "!" not in aumid:
        return None
    package_family_name, app_id = aumid.split("!", 1)

    install_location = _resolve_package_install_location(package_family_name)
    if not install_location:
        return None

    manifest_path = os.path.join(install_location, "AppxManifest.xml")
    if not os.path.isfile(manifest_path):
        return None

    try:
        tree = ET.parse(manifest_path)
    except ET.ParseError:
        return None

    app_elem = None
    for elem in tree.getroot().iter():
        if elem.tag.rsplit("}", 1)[-1] == "Application" and elem.get("Id") == app_id:
            app_elem = elem
            break
    if app_elem is None:
        return None

    executable = app_elem.get("Executable")
    if executable:
        exe_path = os.path.join(install_location, executable)
        if os.path.isfile(exe_path):
            return exe_path

    for child in app_elem.iter():
        if child.tag.rsplit("}", 1)[-1] == "VisualElements":
            logo = child.get("Square44x44Logo") or child.get("Square150x150Logo")
            if logo:
                return _resolve_scaled_asset(install_location, logo)
    return None


def _save_image_as_png(source_path: str, out_path: str) -> bool:
    try:
        img = Image.open(source_path).convert("RGBA")
        img.save(out_path, format="PNG")
        return True
    except Exception:
        return False


def icon_source_path_missing(icon_source_path: str) -> bool:
    """
    ToolItem.icon_source_path（省略可）が設定されているのに、環境変数展開後のパスが実在しない
    場合にTrueを返す。誤入力（パスの打ち間違い・移動済みファイル）に気付けるよう、
    gui/tools_tab.pyが保存直後に警告トーストを出すために使う。未設定（空文字）はFalse
    """
    if not icon_source_path:
        return False
    return not os.path.isfile(os.path.expandvars(icon_source_path))


def get_tool_icon_path(item, force: bool = False) -> str | None:
    """
    item.command が実在するexe等ならアイコンを抽出してキャッシュし、そのPNGパスを返す。
    `shell:appsFolder\\<AUMID>`形式（パッケージ化アプリの起動コマンド）は
    `_resolve_appsfolder_icon_source()`で別途解決する。
    Windowsキー操作（shortcut:）や抽出失敗時はNoneを返す（呼び出し側でguess_fallback_icon()を使う）。
    `force=True`はキャッシュファイルが既に存在していても再抽出する（追加・編集・起動の直後に使う）。

    `item.icon_source_path`（省略可）が設定されており、かつ実在するファイルの場合はそちらを優先して
    使う（`_resolve_exe_path()`によるcommandからの自動解決に頼らない、ユーザー指定のアイコン取得元。
    バッチ/PowerShellスクリプト種別のツール〈commandがスクリプト本文で自動解決できない〉や、
    `winver`のようにcommandだけでは正しいexeを特定しにくいツール向け）。未設定・ファイルが
    見つからない場合、および実在はするがアイコンリソースを持たずアイコン抽出自体に失敗した場合
    （実機で確認済み: この環境の`winver.exe`は`ExtractIconEx`が空リストを返す＝アイコン0件）は、
    いずれも従来通りcommandからの自動解決にフォールバックする（`icon_source_path`の誤入力に
    気付けるよう、gui/tools_tab.py側では`icon_source_path_missing()`で別途「ファイル不在」を検知する）
    """
    override = os.path.expandvars(getattr(item, "icon_source_path", "") or "")
    if override and os.path.isfile(override):
        out_path = _cache_path(override)
        if os.path.exists(out_path) and not force:
            return out_path
        if _extract_exe_icon_to_png(override, out_path):
            return out_path
        # 指定されたファイルにアイコン情報が無い場合（例: アイコンリソースを持たないexe）は、
        # ここで諦めずに下の通常解決（commandからの自動解決）へフォールバックする
        # （`icon_source_path_missing()`で「ファイルが見つからない」ケースとは区別して扱う）

    if item.command.startswith("shortcut:"):
        return None

    aumid = _extract_aumid(item.command)
    if aumid:
        out_path = _cache_path(f"aumid:{aumid}")
        if os.path.exists(out_path) and not force:
            return out_path

        source = _resolve_appsfolder_icon_source(aumid)
        if not source:
            return None
        if source.lower().endswith(".exe") or source.lower().endswith(".dll"):
            return out_path if _extract_exe_icon_to_png(source, out_path) else None
        return out_path if _save_image_as_png(source, out_path) else None

    exe_path = _resolve_exe_path(item.command)
    if not exe_path:
        return None

    out_path = _cache_path(exe_path)
    if os.path.exists(out_path) and not force:
        return out_path

    return out_path if _extract_exe_icon_to_png(exe_path, out_path) else None


def get_link_icon_path(item, force: bool = False) -> str | None:
    """
    kind=="url" のリンクについて、favicon.icoを取得してキャッシュし、そのPNGパスを返す。
    それ以外の種別・取得失敗時はNoneを返す（呼び出し側でguess_fallback_icon()を使う）。
    `force=True`はキャッシュファイルが既に存在していても再取得する（追加・編集・起動の直後に使う）
    """
    if item.kind != "url":
        return None

    parts = urlsplit(item.target)
    if not parts.scheme or not parts.netloc:
        return None

    favicon_url = f"{parts.scheme}://{parts.netloc}/favicon.ico"
    out_path = _cache_path(favicon_url)
    if os.path.exists(out_path) and not force:
        return out_path

    try:
        with urllib.request.urlopen(favicon_url, timeout=3) as resp:
            raw = resp.read()
        img = Image.open(io.BytesIO(raw))
        img.save(out_path, format="PNG")
        return out_path
    except Exception:
        return None
