import glob
import os
import webbrowser

import flet as ft

from gui.safe_update import safe_update
from services import ui_log
from utils.mermaid_view import extract_mermaid_blocks, open_mermaid_in_browser


class HelpTab:
    """
    ヘルプタブ。docs/ 配下のMarkdownドキュメント（ユーザー向け操作ガイド）を表示する。
    ドキュメントが複数ある場合の切り替えは、表示領域を圧迫しない小さなドロップダウンで行う
    （左ペインの一覧は廃止。なるべく本文の表示領域を広く取るため）。
    Mermaid図はFlet上には描画できないため、既定のブラウザで開くボタンを提供する。
    """

    def __init__(self, page: ft.Page):
        self.page = page
        self.docs = sorted(glob.glob("docs/*.md"))
        self.current_text = ""
        self.current_title = ""

        self.doc_dropdown = ft.Dropdown(
            label="ドキュメント",
            options=[ft.DropdownOption(key=p, text=os.path.basename(p)) for p in self.docs],
            value=self.docs[0] if self.docs else None,
            on_select=self._handle_doc_select,
            visible=len(self.docs) > 1,
            width=300,
        )

        self.mermaid_button = ft.Button(
            "図をブラウザで表示",
            icon=ft.Icons.OPEN_IN_BROWSER,
            tooltip="このドキュメント内のMermaid図を既定のブラウザで表示する（インターネット接続が必要です）",
            visible=False,
            on_click=self._handle_open_mermaid,
        )

        self.markdown_view = ft.Markdown(
            value="",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            on_tap_link=self._handle_tap_link,
        )

        self.view = ft.Column(
            expand=True,
            controls=[
                self.doc_dropdown,
                self.mermaid_button,
                ft.Container(
                    expand=True,
                    content=ft.Column(
                        controls=[self.markdown_view],
                        scroll=ft.ScrollMode.ALWAYS,
                        expand=True,
                    ),
                ),
            ],
        )

        if self.docs:
            self._load_doc(self.docs[0])

    def _handle_doc_select(self, e: ft.ControlEvent) -> None:
        if self.doc_dropdown.value:
            ui_log.log_action(
                "ヘルプ", "select", os.path.basename(self.doc_dropdown.value)
            )
            self._load_doc(self.doc_dropdown.value)

    def _load_doc(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as ex:
            text = f"読み込みに失敗しました: {ex}"

        self.current_text = text
        self.current_title = path

        self.markdown_view.value = text
        safe_update(self.markdown_view)

        self.mermaid_button.visible = bool(extract_mermaid_blocks(text))
        safe_update(self.mermaid_button)

    def _handle_open_mermaid(self, e: ft.ControlEvent) -> None:
        ui_log.log_action("ヘルプ", "launch", "Mermaid図")
        open_mermaid_in_browser(self.current_text, self.current_title)

    def _handle_tap_link(self, e: ft.ControlEvent) -> None:
        if e.data:
            webbrowser.open(e.data)
