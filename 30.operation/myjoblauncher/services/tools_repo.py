import os
import tomllib
from dataclasses import dataclass
from typing import List

import tomli_w

# 実行種別。「通常コマンド」（既定、従来通りのexe起動）以外を選ぶと、コマンド欄はバッチ/PowerShellの
# スクリプト本文（複数行・コメント行可）として扱われ、実行前に内容プレビュー付きの確認ダイアログを出し、
# 出力は捕捉して運用ログへ出力する（gui/tools_tab.pyの_run_script_tool系メソッド参照）
SCRIPT_KIND_NORMAL = "通常コマンド"
SCRIPT_KIND_BATCH = "バッチスクリプト"
SCRIPT_KIND_POWERSHELL = "PowerShellスクリプト"
SCRIPT_KINDS = (SCRIPT_KIND_NORMAL, SCRIPT_KIND_BATCH, SCRIPT_KIND_POWERSHELL)
SCRIPT_KIND_EXTENSIONS = {SCRIPT_KIND_BATCH: ".bat", SCRIPT_KIND_POWERSHELL: ".ps1"}


# ========================
# ✅ データモデル
# ========================
@dataclass
class ToolItem:
    name: str
    command: str
    working_dir: str = ""
    args: str = ""
    note: str = ""
    last_used_at: str = ""
    use_count: int = 0
    category: str = ""      # カテゴリ（自由記述）
    recommend: int = 0      # おすすめ度（1〜5）。0は未設定
    comment: str = ""       # ひとこと
    pinned: bool = False    # ピン止め（一覧の先頭に固定表示）
    script_kind: str = SCRIPT_KIND_NORMAL  # 実行種別（通常コマンド/バッチスクリプト/PowerShellスクリプト）
    icon_source_path: str = ""  # アイコン取得専用のexeパス（省略可。commandから自動解決できない場合に使う）


# ========================
# ✅ 読み込み・書き込み
# ========================
def load_tools(path: str) -> List[ToolItem]:
    if not os.path.exists(path):
        return []

    with open(path, "rb") as f:
        data = tomllib.load(f)

    items: List[ToolItem] = []

    for t in data.get("tool", []):
        name = t.get("name")
        command = t.get("command")

        if not name or not command:
            continue

        items.append(
            ToolItem(
                name=name,
                command=command,
                working_dir=t.get("working_dir", ""),
                args=t.get("args", ""),
                note=t.get("note", ""),
                last_used_at=t.get("last_used_at", ""),
                use_count=t.get("use_count", 0),
                category=t.get("category", ""),
                recommend=t.get("recommend", 0),
                comment=t.get("comment", ""),
                pinned=bool(t.get("pinned", False)),
                script_kind=t.get("script_kind") or SCRIPT_KIND_NORMAL,
                icon_source_path=t.get("icon_source_path", ""),
            )
        )

    return items


def save_tools(path: str, items: List[ToolItem]) -> None:
    data = {
        "tool": [
            {
                "name": item.name,
                "command": item.command,
                "working_dir": item.working_dir,
                "args": item.args,
                "note": item.note,
                "last_used_at": item.last_used_at,
                "use_count": item.use_count,
                "category": item.category,
                "recommend": item.recommend,
                "comment": item.comment,
                "pinned": item.pinned,
                "script_kind": item.script_kind,
                "icon_source_path": item.icon_source_path,
            }
            for item in items
        ]
    }

    with open(path, "wb") as f:
        tomli_w.dump(data, f)
