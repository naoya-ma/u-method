import os
import tomllib

import tomli_w

RUN_GRID_PATH = "config/run_grid.toml"

# ========================
# ✅ 実行タブ グリッドの列幅（px）既定値
# ========================
DEFAULT_COLUMN_WIDTHS = {
    "選択": 40,
    "No.": 50,
    "ジョブID": 80,
    "ジョブ名": 140,
    "カテゴリ": 90,
    "Tier": 90,
    "種別": 70,
    "日次": 70,
    "週次": 110,
    "月次": 110,
    "その他": 70,
    "マニュアル": 90,
    "ステータス": 100,
    "履歴": 70,
    "特記事項": 160,
}


def load_column_widths(path: str = RUN_GRID_PATH) -> dict:
    widths = dict(DEFAULT_COLUMN_WIDTHS)

    if os.path.exists(path):
        with open(path, "rb") as f:
            data = tomllib.load(f)
        widths.update(data.get("widths", {}))

    return widths


def save_column_widths(widths: dict, path: str = RUN_GRID_PATH) -> None:
    with open(path, "wb") as f:
        tomli_w.dump({"widths": widths}, f)
