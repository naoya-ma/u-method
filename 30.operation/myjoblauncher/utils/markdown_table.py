"""
GFM形式のMarkdownテーブル（パイプ区切り）と、見出し・セルの行×列データとの相互変換。

ホーム本文（`config/home.toml`の`[portal].content`）の「よく使うサービス」表は、
以前は`| 列1 | 列2 |`のようなパイプ区切り構文を手作業で編集していたが、
セル内改行（`<br>`）・列数のそろえ・区切り行の管理が煩雑でメンテナンスしづらかった。
`gui/service_table_editor.py`の表エディタは、見出し・セルを行×列の単純なテキストとして
編集させ、保存時にこのモジュールでMarkdownテーブル構文へ組み立て直す。
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

_BR_RE = re.compile(r"(?i)<br\s*/?>")


def parse_markdown_table(markdown: str) -> tuple[list[str], list[list[str]]]:
    """
    パイプ区切りMarkdownテーブル1つを (見出しリスト, 行×列のセル文字列リスト) に分解する。
    セル内の`<br>`は編集しやすいよう改行(`\\n`)に戻す。解析できない・空の場合は
    見出し3列・行なしの空テーブルを返す（表エディタの初期状態として扱える）
    """
    md = MarkdownIt("commonmark").enable("table")
    tokens = md.parse(markdown or "")

    headers: list[str] = []
    rows: list[list[str]] = []
    current_row: list[str] | None = None
    in_thead = False

    for i, token in enumerate(tokens):
        if token.type == "thead_open":
            in_thead = True
        elif token.type == "thead_close":
            in_thead = False
        elif token.type == "tr_open":
            current_row = []
        elif token.type in ("th_close", "td_close"):
            pass
        elif token.type == "inline" and current_row is not None:
            current_row.append(_BR_RE.sub("\n", token.content))
        elif token.type == "tr_close":
            if in_thead:
                headers = current_row or []
            elif current_row is not None:
                rows.append(current_row)
            current_row = None

    if not headers:
        headers = ["列1", "列2", "列3"]
    return headers, rows


def _escape_cell(text: str) -> str:
    """セル内の改行を`<br>`へ、`|`を`\\|`へエスケープする（`|`はテーブル区切りと衝突するため）"""
    lines = [ln.strip() for ln in (text or "").split("\n")]
    return "<br>".join(lines).replace("|", "\\|")


def build_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """
    見出しリストと行×列のセル文字列（`\\n`区切りで複数行）から、
    見出し行・区切り行・データ行を持つパイプ区切りMarkdownテーブルを組み立てる。
    列数は見出しに合わせ、各行は不足分を空セルで埋め・超過分を切り詰める
    """
    col_count = len(headers)
    lines = [
        "| " + " | ".join(_escape_cell(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in range(col_count)) + " |",
    ]
    for row in rows:
        cells = (list(row) + [""] * col_count)[:col_count]
        lines.append("| " + " | ".join(_escape_cell(c) for c in cells) + " |")
    return "\n".join(lines) + "\n"
