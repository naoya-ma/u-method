import os
import tomllib

import tomli_w

APP_CONFIG_PATH = "config/app.toml"


def load(path: str = APP_CONFIG_PATH) -> dict:
    if not os.path.exists(path):
        return {}

    with open(path, "rb") as f:
        return tomllib.load(f)


def save(updates: dict, path: str = APP_CONFIG_PATH) -> None:
    """
    既存のキー（タイムゾーン・テーマ等）を消さないよう、現在の内容にマージしてから書き戻す
    """
    data = load(path)
    data.update(updates)

    with open(path, "wb") as f:
        tomli_w.dump(data, f)
