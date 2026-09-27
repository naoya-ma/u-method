import os
import tomllib

import tomli_w

# Tier9: 個人専用の階層。config/menu.toml（共有マスター）とは別ファイルに保存し、
# 「マスターをダウンロード/アップロード」の対象外にする（個人のみ・全体共有しない）
TIER9_CONFIG_PATH = "config/tier9.toml"
DEFAULT_TIER9_NAME = "個人"


def load_personal_tier_name(path: str = TIER9_CONFIG_PATH) -> str:
    if not os.path.exists(path):
        return DEFAULT_TIER9_NAME

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return data.get("tier9") or DEFAULT_TIER9_NAME


def save_personal_tier_name(name: str, path: str = TIER9_CONFIG_PATH) -> None:
    with open(path, "wb") as f:
        tomli_w.dump({"tier9": name or DEFAULT_TIER9_NAME}, f)
