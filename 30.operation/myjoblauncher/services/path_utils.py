import os
import re


def expand_path(value: str) -> str:
    """
    %USERPROFILE%や%OneDriveCommercial%等のWindows環境変数を含むパス文字列を展開する。
    値が空文字の場合はそのまま返す
    """
    return os.path.expandvars(value) if value else value


# ✅ collapse_path() が環境変数トークンへ置き換える際の優先順位（ユーザー指定）。
# 例えば%LOCALAPPDATA%配下は%USERPROFILE%配下にも含まれるため、より具体的な変数を先に判定する必要がある
ENV_VAR_PRIORITY = [
    "ProgramFiles(x86)",
    "ProgramFiles",
    "SystemRoot",
    "APPDATA",
    "LOCALAPPDATA",
    "OneDriveCommercial",
    "OneDrive",
    "USERPROFILE",
]


def collapse_path(value: str) -> str:
    """
    絶対パス文字列を、既知のWindows環境変数トークンへ置き換える（expand_path()の逆）。
    ドラッグ&ドロップや手入力で渡された絶対パスを、他PCでも使えるポータブルな形（既存の
    config/tools.toml等が既に使っている%USERPROFILE%等の表記）へ揃えるために使う。
    ENV_VAR_PRIORITY の順に、値の中に実際の展開結果（大文字小文字無視）が含まれていないか調べ、
    最初に見つかった変数だけを適用する（複数の変数を1つの文字列に混在させない）。
    該当が無ければ元の文字列をそのまま返す
    """
    if not value:
        return value

    for name in ENV_VAR_PRIORITY:
        expanded = os.environ.get(name)
        if not expanded:
            continue
        pattern = re.compile(re.escape(expanded), re.IGNORECASE)
        if pattern.search(value):
            return pattern.sub(f"%{name}%", value)

    return value
