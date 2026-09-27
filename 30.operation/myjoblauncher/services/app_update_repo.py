import os
import shutil
import tomllib
import zipfile
from dataclasses import dataclass

import tomli_w

from services import app_config, applog

PYPROJECT_PATH = "pyproject.toml"
UPDATE_STATE_PATH = "config/app_update_state.toml"

# ✅ 上書き対象（pyproject.tomlの[tool.hatch.build.targets.wheel].includeと同じ構成）
SOURCE_TARGETS = ["main.py", "gui", "services", "tui", "utils"]


@dataclass
class AppUpdateInfo:
    version: str
    published_by: str
    published_at: str
    notes: str
    archive_local_path: str


def get_current_version(path: str = PYPROJECT_PATH) -> str:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return data.get("project", {}).get("version", "0.0.0")


def _update_pyproject_version(new_version: str, path: str = PYPROJECT_PATH) -> None:
    """
    pyproject.tomlの[project].versionを書き換える。apply_update()がソースを上書きした直後に
    呼ぶ。pyproject.toml自体はSOURCE_TARGETSに含まれておらずZIP展開で更新されないため、
    これを呼ばないとget_current_version()（＝「設定」タブの「現在のバージョン」表示）が
    適用後もいつまでも旧バージョンを報告し続けてしまう（実機で確認済みの不具合）
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)
    data.setdefault("project", {})["version"] = new_version
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def _parse_version(v: str) -> tuple:
    """"1.10.0" > "1.9.0" のような数値比較のため、"."区切りをintタプル化する（文字列比較はしない）"""
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_newer(remote_version: str, current_version: str) -> bool:
    return _parse_version(remote_version) > _parse_version(current_version)


def load_update_state(path: str = UPDATE_STATE_PATH) -> AppUpdateInfo | None:
    """
    このPCだけのローカル状態（共有マスター同期の対象外。config/sync_state.tomlや
    config/notice_seen.tomlと同じ位置づけ）。検知済みの更新情報＋ダウンロード済みZIPの
    ローカルパスを保持する。ファイルが無い・内容が不完全な場合はNone（更新なし扱い）
    """
    if not os.path.exists(path):
        return None

    with open(path, "rb") as f:
        data = tomllib.load(f)

    if not data.get("version"):
        return None

    return AppUpdateInfo(
        version=data.get("version", ""),
        published_by=data.get("published_by", ""),
        published_at=data.get("published_at", ""),
        notes=data.get("notes", ""),
        archive_local_path=data.get("archive_local_path", ""),
    )


def save_update_state(info: AppUpdateInfo | None, path: str = UPDATE_STATE_PATH) -> None:
    """`info=None`で「更新なし（適用済み等）」としてクリアする"""
    if info is None:
        if os.path.exists(path):
            os.remove(path)
        return

    data = {
        "version": info.version,
        "published_by": info.published_by,
        "published_at": info.published_at,
        "notes": info.notes,
        "archive_local_path": info.archive_local_path,
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def is_self_overwrite_enabled(menu_path: str = "config/menu.toml") -> bool:
    """
    自己書き換え（apply_updateによるソースファイルの実行時上書き）を実際に行うかどうかの判定。
    次の両方を満たす場合のみTrue（ユーザーからの要望: ストレージ連携全体を無効化している場合は
    自己更新も行わないようにする）:
      ①config/app.tomlの[app_update].enable_self_overwrite が true（既定False・GUI無しの
        隠しオプション、直接編集でのみ設定可能）
      ②config/menu.toml（menu_path）の[storage].enabled が有効
        （`services/config_loader.is_storage_enabled()`、キー省略時は既定で有効）

    ①の理由: 「起動中のプロセスが自分自身のソースを書き換えて直後にプロセスを終了する」挙動は、
    Windows Smart App Control（Windows 11のアプリ実行制限機能）が典型的に警戒するパターンで、
    実機でこの機能追加後にアプリ自体がブロックされる不具合を確認した。コード署名を導入しない
    運用のため、既定でこの経路を無効化し、必要な環境でのみ明示的に有効化できるようにしている
    """
    data = app_config.load()
    if not bool(data.get("app_update", {}).get("enable_self_overwrite", False)):
        return False

    from services.config_loader import is_storage_enabled, load_storage_config

    try:
        storage_config = load_storage_config(menu_path)
    except Exception:
        return False  # menu.tomlが読めない＝判定不能のため安全側でFalseにする

    return is_storage_enabled(storage_config)


def apply_update(info: AppUpdateInfo, on_progress=None) -> bool:
    """
    ダウンロード済みZIP（info.archive_local_path）を展開し、リポジトリ直下の
    main.py/gui/services/tui/utils を上書きする。適用後はローカル状態をクリアする。
    例外は握りつぶしFalseを返す（ログ出力して握りつぶす既存方針、アプリ全体を落とさない）。
    is_self_overwrite_enabled()がFalse（既定、またはストレージ設定が無効化されている間）は、
    ファイルには一切触れずFalseを返す。

    `on_progress(current: int, total: int, name: str)`を渡すと、展開対象ファイルを1件処理する
    たびに呼び出す（呼び出し元、例: gui/settings_tab.pyがコンソールへの進捗表示に使う。
    上書き中に何が起きているか分かりにくいというユーザーからの要望）
    """
    if not is_self_overwrite_enabled():
        applog.log(
            "WARNING",
            "自己更新（ソース上書き）は無効化されているため適用をスキップしました"
            "（[app_update].enable_self_overwrite=false、または[storage].enabled=falseのいずれか）",
            func_name="apply_update",
        )
        return False

    if not info.archive_local_path or not os.path.isfile(info.archive_local_path):
        return False

    try:
        with zipfile.ZipFile(info.archive_local_path) as zf:
            names = zf.namelist()
            allowed = tuple(SOURCE_TARGETS)
            targets = [name for name in names if name.split("/")[0] in allowed]
            total = len(targets)
            for i, name in enumerate(targets, start=1):
                zf.extract(name, ".")
                if on_progress:
                    on_progress(i, total, name)
    except Exception:
        return False

    try:
        _update_pyproject_version(info.version)
    except Exception:
        pass  # バージョン表記の更新に失敗してもソース上書き自体は成功しているため、適用は成功扱いのまま

    save_update_state(None)
    return True
