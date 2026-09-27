"""
Markdownを`ft.TextSpan`ツリーへ変換する簡易レンダラー。

`ft.Markdown`（`flutter_markdown`）はリンクのタップイベント（`on_tap_link`）しか公開しておらず、
リンクにマウスを乗せたときにリンク先URLをツールチップ表示する機能を持たない。
`ft.TextSpan`はネイティブの`on_enter`/`on_exit`（Flutterの`TextSpan.onEnter`/`onExit`）を持つため、
本モジュールでは`markdown-it-py`でMarkdownを解析し、リンク部分だけ`on_enter`/`on_exit`で
ホバー中のURLを表示できる`ft.Text(spans=[...])`ベースの構造に組み立て直す。

【カーソル追従の吹き出し(ft.Stack + ft.GestureDetector.on_hover)は不採用】
`ft.Stack`で絶対配置した吹き出しをカーソルに追従させる実装を試したが、Web版（`uv run mj --web`）では
正しく動作する一方、本アプリの主力であるデスクトップ版（`uv run mj`）では吹き出しの表示・追従が
反映されないことを実機で確認した（`ft.TextSpan.on_enter`/`on_exit`自体はデスクトップでも発火するが、
`ft.Stack`内の絶対配置コントロールの表示更新がデスクトップのFlutterエンジンでは反映されない模様）。
そのため、ホバー中のURLは各Markdownブロックの直下に固定表示するシンプルな方式にしている
（コンテンツ全体を1本の`ft.Column`にまとめて返し、末尾にホバー用の`ft.Text`を含める）。

対応する構文: 見出し(h1〜h6)・段落・強調(**太字**/*斜体*)・インラインコード・フェンス付きコードブロック・
箇条書き/番号付きリスト（ネスト可）・引用・水平線・リンク・表（GFMテーブル。セル内の改行は`<br>`で表現する）。
表はmarkdown-it-pyの`"table"`ルール（core組み込み、追加パッケージ不要。`MarkdownIt("commonmark")`では
既定で無効なため`.enable("table")`している）で解析する。打消し線・タスクリスト等その他のGFM拡張は
`mdit_py_plugins`が必要なため非対応（現状のホーム/お知らせの実データでは未使用）。
"""

from __future__ import annotations

import re
from typing import Callable, Optional

import flet as ft
from markdown_it import MarkdownIt
from markdown_it.token import Token

from services import theme_repo

OnTapLink = Callable[[str], None]
OnHoverLink = Callable[[Optional[str]], None]

_HEADING_SIZES = {1: 24, 2: 20, 3: 18, 4: 16, 5: 15, 6: 14}
_BR_RE = re.compile(r"(?i)^<br\s*/?>$")

_md = MarkdownIt("commonmark").enable("table")


class _Context:
    def __init__(self, on_tap_link: OnTapLink, on_hover_link: OnHoverLink):
        self.on_tap_link = on_tap_link
        self.on_hover_link = on_hover_link


def build_markdown_view(text: str, on_tap_link: OnTapLink) -> ft.Control:
    """
    Markdown文字列から表示用コントロールを組み立てる。
    リンクにマウスを乗せている間、コンテンツ直下の行にリンク先URLを表示する。
    解析に失敗した場合は元テキストをそのまま表示する
    """
    hover_text = ft.Text("", size=11, color=ft.Colors.OUTLINE, selectable=False)

    def handle_hover_link(url: Optional[str]) -> None:
        hover_text.value = url or ""
        try:
            hover_text.update()
        except Exception:
            pass  # まだページに追加されていないタイミングでの呼び出しは無視する

    ctx = _Context(on_tap_link, handle_hover_link)
    try:
        tokens = _md.parse(text or "")
        controls = _render_blocks(tokens, 0, len(tokens), ctx)
    except Exception:
        controls = [ft.Text(text or "")]
    if not controls:
        controls = [ft.Text("")]
    content_column = ft.Column(
        controls=controls,
        spacing=8,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    return ft.Column(
        controls=[content_column, hover_text],
        spacing=2,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


# ========================
# ✅ ブロック要素
# ========================
def _matching_close(tokens: list[Token], open_idx: int) -> int:
    open_level = tokens[open_idx].level
    close_type = tokens[open_idx].type.replace("_open", "_close")
    for j in range(open_idx + 1, len(tokens)):
        if tokens[j].type == close_type and tokens[j].level == open_level:
            return j
    return len(tokens) - 1


def _render_blocks(tokens: list[Token], start: int, end: int, ctx: _Context) -> list[ft.Control]:
    controls: list[ft.Control] = []
    i = start
    while i < end:
        t = tokens[i]
        if t.type == "heading_open":
            level = int(t.tag[1:]) if len(t.tag) > 1 and t.tag[1:].isdigit() else 1
            spans = _render_inline(tokens[i + 1].children or [], ctx)
            controls.append(
                ft.Text(spans=spans, size=_HEADING_SIZES.get(level, 14), weight=ft.FontWeight.BOLD)
            )
            i += 3
        elif t.type == "paragraph_open":
            spans = _render_inline(tokens[i + 1].children or [], ctx)
            controls.append(ft.Text(spans=spans, selectable=True))
            i += 3
        elif t.type in ("fence", "code_block"):
            controls.append(_code_block(t.content))
            i += 1
        elif t.type == "hr":
            controls.append(ft.Divider())
            i += 1
        elif t.type == "blockquote_open":
            close_i = _matching_close(tokens, i)
            inner = _render_blocks(tokens, i + 1, close_i, ctx)
            controls.append(_blockquote_container(inner))
            i = close_i + 1
        elif t.type in ("bullet_list_open", "ordered_list_open"):
            ordered = t.type == "ordered_list_open"
            close_i = _matching_close(tokens, i)
            items = _render_list_items(tokens, i + 1, close_i, ordered, ctx)
            controls.append(
                ft.Column(controls=items, spacing=2, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
            )
            i = close_i + 1
        elif t.type == "table_open":
            close_i = _matching_close(tokens, i)
            controls.append(_render_table(tokens, i + 1, close_i, ctx))
            i = close_i + 1
        else:
            # html_block等、未対応のトークンは無視する
            i += 1
    return controls


def _render_list_items(
    tokens: list[Token], start: int, end: int, ordered: bool, ctx: _Context
) -> list[ft.Control]:
    items: list[ft.Control] = []
    i = start
    num = 1
    while i < end:
        t = tokens[i]
        if t.type == "list_item_open":
            close_i = _matching_close(tokens, i)
            inner = _render_blocks(tokens, i + 1, close_i, ctx)
            marker = f"{num}." if ordered else "・"
            num += 1
            items.append(
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    spacing=4,
                    controls=[
                        ft.Text(marker, width=28),
                        ft.Column(
                            controls=inner,
                            spacing=4,
                            tight=True,
                            expand=True,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        ),
                    ],
                )
            )
            i = close_i + 1
        else:
            i += 1
    return items


def _code_block(content: str) -> ft.Container:
    return ft.Container(
        content=ft.Text(content.rstrip("\n"), font_family="Consolas", selectable=True),
        padding=8,
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        border_radius=4,
    )


def _blockquote_container(inner: list[ft.Control]) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            controls=inner, spacing=4, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        ),
        padding=ft.Padding.only(left=12, top=4, bottom=4, right=4),
        border=ft.Border.only(left=ft.BorderSide(3, ft.Colors.OUTLINE)),
    )


def _render_table(tokens: list[Token], start: int, end: int, ctx: _Context) -> ft.Column:
    rows: list[ft.Row] = []
    i = start
    while i < end:
        t = tokens[i]
        if t.type == "tr_open":
            close_i = _matching_close(tokens, i)
            header = tokens[i + 1].type == "th_open" if i + 1 < close_i else False
            cells = _render_table_row(tokens, i + 1, close_i, ctx)
            rows.append(
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    spacing=0,
                    controls=[
                        ft.Container(
                            content=cell,
                            expand=True,
                            padding=8,
                            # 罫線は列ごとにわずかにずれることがあるため、透明にしてずれを目立たなくする
                            border=ft.Border.all(1, ft.Colors.TRANSPARENT),
                            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE) if header else None,
                        )
                        for cell in cells
                    ],
                )
            )
            i = close_i + 1
        else:
            i += 1
    return ft.Column(controls=rows, spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)


def _render_table_row(tokens: list[Token], start: int, end: int, ctx: _Context) -> list[ft.Text]:
    cells: list[ft.Text] = []
    i = start
    while i < end:
        t = tokens[i]
        if t.type in ("th_open", "td_open"):
            close_i = _matching_close(tokens, i)
            inline_tok = tokens[i + 1] if i + 1 < close_i and tokens[i + 1].type == "inline" else None
            spans = _render_inline(inline_tok.children or [], ctx) if inline_tok else [ft.TextSpan(text="")]
            if t.type == "th_open":
                for s in spans:
                    if s.style is None:
                        s.style = ft.TextStyle(weight=ft.FontWeight.BOLD)
                    elif s.style.weight is None:
                        s.style.weight = ft.FontWeight.BOLD
            cells.append(ft.Text(spans=spans, selectable=True))
            i = close_i + 1
        else:
            i += 1
    return cells


# ========================
# ✅ インライン要素
# ========================
def _render_inline(children: list[Token], ctx: _Context) -> list[ft.TextSpan]:
    spans: list[ft.TextSpan] = []
    style_stack: list[str] = []
    link_href: Optional[str] = None

    def make_style(extra_color: Optional[str] = None, underline: bool = False) -> ft.TextStyle:
        return ft.TextStyle(
            weight=ft.FontWeight.BOLD if "strong" in style_stack else None,
            italic="em" in style_stack,
            color=extra_color,
            decoration=ft.TextDecoration.UNDERLINE if underline else None,
        )

    for c in children:
        if c.type == "text":
            spans.append(ft.TextSpan(text=c.content, style=make_style()))
        elif c.type == "softbreak":
            spans.append(ft.TextSpan(text=" ", style=make_style()))
        elif c.type == "hardbreak":
            spans.append(ft.TextSpan(text="\n", style=make_style()))
        elif c.type == "html_inline" and _BR_RE.match(c.content.strip()):
            spans.append(ft.TextSpan(text="\n", style=make_style()))
        elif c.type == "code_inline":
            spans.append(
                ft.TextSpan(
                    text=c.content,
                    style=ft.TextStyle(
                        font_family="Consolas",
                        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                    ),
                )
            )
        elif c.type in ("strong_open", "em_open"):
            style_stack.append("strong" if c.type == "strong_open" else "em")
        elif c.type in ("strong_close", "em_close"):
            tag = "strong" if c.type == "strong_close" else "em"
            if tag in style_stack:
                style_stack.remove(tag)
        elif c.type == "link_open":
            link_href = c.attrs.get("href") if c.attrs else None
        elif c.type == "link_close":
            link_href = None
        elif c.type == "image":
            alt = c.content or (c.attrs.get("alt") if c.attrs else "") or "画像"
            spans.append(ft.TextSpan(text=f"[{alt}]", style=make_style()))
        else:
            if c.content:
                spans.append(ft.TextSpan(text=c.content, style=make_style()))
            continue

        if link_href and c.type not in ("link_open", "link_close") and spans:
            last = spans[-1]
            href = link_href
            last.style = make_style(extra_color=theme_repo.accent_color(), underline=True)
            last.on_click = lambda e, href=href: ctx.on_tap_link(href)
            last.on_enter = lambda e, href=href: ctx.on_hover_link(href)
            last.on_exit = lambda e: ctx.on_hover_link(None)

    return spans or [ft.TextSpan(text="")]
