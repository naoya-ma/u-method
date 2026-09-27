import os
import tomllib
import webbrowser
from dataclasses import dataclass
from typing import List

import tomli_w


# ========================
# ✅ データモデル
# ========================
@dataclass
class TipItem:
    name: str
    url: str
    note: str = ""


# ========================
# ✅ 読み込み・書き込み
# ========================
def load_tips(path: str) -> List[TipItem]:
    if not os.path.exists(path):
        return []

    with open(path, "rb") as f:
        data = tomllib.load(f)

    items: List[TipItem] = []

    for t in data.get("tip", []):
        name = t.get("name")
        url = t.get("url")

        if not name or not url:
            continue

        items.append(TipItem(name=name, url=url, note=t.get("note", "")))

    return items


def save_tips(path: str, items: List[TipItem]) -> None:
    data = {
        "tip": [
            {"name": item.name, "url": item.url, "note": item.note}
            for item in items
        ]
    }

    with open(path, "wb") as f:
        tomli_w.dump(data, f)


# ========================
# ✅ TIPSを開く（常にブラウザ）
# ========================
def open_tip(item: TipItem) -> None:
    webbrowser.open(item.url)
