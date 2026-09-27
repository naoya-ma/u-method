import webbrowser

import flet as ft

from utils.markdown_render import build_markdown_view
from utils.mermaid_view import extract_mermaid_blocks, open_mermaid_in_browser


def show_markdown_preview_dialog(page: ft.Page, title: str, markdown_text: str) -> None:
    """
    Markdownのプレビュー用ダイアログ。`utils/markdown_render.py`の自前レンダラーで描画する。
    `ft.Markdown`（`flutter_markdown`）はリンクのホバー時にツールチップを表示する機能を持たないため、
    `markdown-it-py`で解析し`ft.TextSpan`ツリーに組み立て直す自前レンダラーを使う
    （`gui/portal_tab.py`と同じ方式）。本文中のリンクはクリックすると既定のブラウザで開き、
    マウスを乗せるとカーソル追従の吹き出しでリンク先URLを表示する。
    GFM拡張（表・打消し線等）は自前レンダラーでは非対応（`docs/help.md`参照）。
    MermaidJSはこのレンダラーでも描画できないため、含まれていれば「図をブラウザで表示」ボタンで
    別途確認できるようにする（`utils/mermaid_view.py`）。
    将来的にWindows/LinuxでWebView2ベースの埋め込みWebView（`flet_webview`）が使えるようになったら、
    この方式から埋め込み表示への切り替えを検討すること
    """

    def handle_tap_link(url: str) -> None:
        if url:
            webbrowser.open(url)

    def handle_open_mermaid(e: ft.ControlEvent) -> None:
        open_mermaid_in_browser(markdown_text, title)

    def handle_close(e: ft.ControlEvent) -> None:
        page.pop_dialog()

    mermaid_button = ft.Button(
        "図をブラウザで表示",
        icon=ft.Icons.OPEN_IN_BROWSER,
        tooltip="このプレビュー内のMermaid図を既定のブラウザで表示する（インターネット接続が必要です）",
        visible=bool(extract_mermaid_blocks(markdown_text)),
        on_click=handle_open_mermaid,
    )

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(f"プレビュー: {title}"),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    mermaid_button,
                    build_markdown_view(markdown_text, handle_tap_link),
                ],
                scroll=ft.ScrollMode.ALWAYS,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            width=1050,
            height=500,
        ),
        actions=[ft.TextButton("閉じる", on_click=handle_close)],
    )
    page.show_dialog(dialog)
