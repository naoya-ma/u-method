from services import app_config


def load_display_name(path: str = app_config.APP_CONFIG_PATH) -> str:
    """
    左メニュー最上部（NavigationRail.leading）に表示するアプリケーション名。
    config/app.toml の app_name キーで指定する任意設定。省略時（キー無し・空文字）は表示しない
    """
    return app_config.load(path).get("app_name", "")


def save_display_name(name: str, path: str = app_config.APP_CONFIG_PATH) -> None:
    app_config.save({"app_name": name}, path)
