from services import app_config

MAX_HISTORY = 20


def load_history(key: str, path: str = app_config.APP_CONFIG_PATH) -> list[str]:
    """
    検索欄の入力履歴を読み込む（`key`は"tools_search_history"/"log_search_history"のような
    `config/app.toml`のキー名）。新しい順、最大MAX_HISTORY件。不正な形式（リストでない・
    要素が文字列でない等）は無視してフォールバックする
    """
    history = app_config.load(path).get(key)
    if not isinstance(history, list):
        return []
    return [h for h in history if isinstance(h, str)][:MAX_HISTORY]


def add_to_history(query: str, history: list[str]) -> list[str]:
    """
    queryを履歴の先頭に追加した新しいリストを返す（historyそのものは変更しない）。
    既に同じ値があれば削除してから追加し直すため、重複を作らず「直近に使った順」を保てる。
    空文字（前後の空白のみ含む）は追加しない
    """
    query = query.strip()
    if not query:
        return history
    updated = [h for h in history if h != query]
    updated.insert(0, query)
    return updated[:MAX_HISTORY]


def save_history(key: str, history: list[str], path: str = app_config.APP_CONFIG_PATH) -> None:
    app_config.save({key: history[:MAX_HISTORY]}, path)
