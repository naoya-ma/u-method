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
class LinkItem:
    name: str
    target: str
    kind: str = "url"   # url / folder / file
    note: str = ""
    last_used_at: str = ""
    use_count: int = 0
    category: str = ""      # カテゴリ（自由記述）
    recommend: int = 0      # おすすめ度（1〜5）。0は未設定
    comment: str = ""       # ひとこと
    pinned: bool = False    # ピン止め（一覧の先頭に固定表示）


# ========================
# ✅ 読み込み・書き込み
# ========================
def load_links(path: str) -> List[LinkItem]:
    if not os.path.exists(path):
        return []

    with open(path, "rb") as f:
        data = tomllib.load(f)

    items: List[LinkItem] = []

    for lk in data.get("link", []):
        name = lk.get("name")
        target = lk.get("target")

        if not name or not target:
            continue

        items.append(
            LinkItem(
                name=name,
                target=target,
                kind=lk.get("kind", "url"),
                note=lk.get("note", ""),
                last_used_at=lk.get("last_used_at", ""),
                use_count=lk.get("use_count", 0),
                category=lk.get("category", ""),
                recommend=lk.get("recommend", 0),
                comment=lk.get("comment", ""),
                pinned=bool(lk.get("pinned", False)),
            )
        )

    return items


def save_links(path: str, items: List[LinkItem]) -> None:
    data = {
        "link": [
            {
                "name": item.name,
                "target": item.target,
                "kind": item.kind,
                "note": item.note,
                "last_used_at": item.last_used_at,
                "use_count": item.use_count,
                "category": item.category,
                "recommend": item.recommend,
                "comment": item.comment,
                "pinned": item.pinned,
            }
            for item in items
        ]
    }

    with open(path, "wb") as f:
        tomli_w.dump(data, f)


# ========================
# ✅ リンクを開く
# ========================
def open_link(item: LinkItem) -> None:
    if item.kind == "url":
        webbrowser.open(item.target)
    else:
        os.startfile(item.target)
