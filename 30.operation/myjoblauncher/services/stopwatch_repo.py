from services import app_config

# 非定型業務の記録プラグイン（dev-stopwatch）の既定の起動先HTMLパス。
# config/app.tomlのstopwatch_html_pathが未設定の場合のみ使われる後方互換用の既定値
DEFAULT_HTML_PATH = r"C:\container\mycontainer\dev-stopwatch\js-swatch.html"


def load_identifier(path: str = app_config.APP_CONFIG_PATH) -> str:
    """
    非定型ジョブの業務記録プラグイン（dev-stopwatch）連携で使う識別子（ユーザー名）。
    dev-stopwatch側のURLクエリパラメータ id にそのまま渡す
    """
    return app_config.load(path).get("stopwatch_identifier", "")


def save_identifier(identifier: str, path: str = app_config.APP_CONFIG_PATH) -> None:
    app_config.save({"stopwatch_identifier": identifier}, path)


def load_html_path(path: str = app_config.APP_CONFIG_PATH) -> str:
    """
    非定型ジョブ実行時に開く、業務記録プラグイン（dev-stopwatch）のHTMLファイルのパス。
    %USERPROFILE%等のWindows環境変数を含められる（utils/opener.build_stopwatch_url()で展開する）
    """
    return app_config.load(path).get("stopwatch_html_path", DEFAULT_HTML_PATH)


def save_html_path(html_path: str, path: str = app_config.APP_CONFIG_PATH) -> None:
    app_config.save({"stopwatch_html_path": html_path}, path)
