from services import app_config

DEFAULT_VIEW_MODE = "icon_medium"
VIEW_MODES = ("icon_large", "icon_medium", "icon_small", "list")

# gui/icon_grid_view.py の SORT_MODES と同じ値。services層はGUIに依存しないため、
# 値の定義はここに独立して持つ（GUI側からは文字列としてそのまま渡ってくるだけ）
DEFAULT_SORT_MODE = "use_count"
SORT_MODES = ("use_count", "name", "last_used")


def load_view_mode(key: str, path: str = app_config.APP_CONFIG_PATH) -> str:
    """`key`は"tools_view_mode"/"links_view_mode"のような`config/app.toml`のキー名"""
    mode = app_config.load(path).get(key)
    return mode if mode in VIEW_MODES else DEFAULT_VIEW_MODE


def save_view_mode(key: str, mode: str, path: str = app_config.APP_CONFIG_PATH) -> None:
    if mode not in VIEW_MODES:
        return
    app_config.save({key: mode}, path)


def load_sort_mode(key: str, path: str = app_config.APP_CONFIG_PATH) -> str:
    """`key`は"tools_sort_mode"/"links_sort_mode"のような`config/app.toml`のキー名"""
    mode = app_config.load(path).get(key)
    return mode if mode in SORT_MODES else DEFAULT_SORT_MODE


def save_sort_mode(key: str, mode: str, path: str = app_config.APP_CONFIG_PATH) -> None:
    if mode not in SORT_MODES:
        return
    app_config.save({key: mode}, path)
