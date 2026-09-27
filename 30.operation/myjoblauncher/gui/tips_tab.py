import flet as ft

from gui.item_form_dialog import show_item_form_dialog
from gui.safe_update import safe_update
from gui.toast import show_toast
from services.tips_repo import TipItem, load_tips, open_tip, save_tips
from services import ui_log

TIPS_PATH = "config/tips.toml"

TIP_FIELDS = [
    {"key": "name", "label": "タイトル", "type": "text"},
    {"key": "url", "label": "URL", "type": "text"},
    {"key": "note", "label": "備考", "type": "text"},
]


class TipsTab:
    """
    TIPSタブ。役立つ外部ドキュメント・参考URLの登録・閲覧。
    """

    def __init__(self, page: ft.Page):
        self.page = page
        self.tips: list[TipItem] = load_tips(TIPS_PATH)
        self.list_view = ft.ListView(expand=True, spacing=2)

        self.view = ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("TIPS", weight=ft.FontWeight.BOLD, expand=True),
                        ft.Button(
                            "追加", icon=ft.Icons.ADD, tooltip="新しいTIPSを追加する", on_click=self._add
                        ),
                    ]
                ),
                ft.Container(
                    content=self.list_view, expand=True, border=ft.Border.all(1, ft.Colors.OUTLINE)
                ),
            ],
        )

        self._refresh()

    def _refresh(self) -> None:
        self.list_view.controls.clear()

        for item in self.tips:
            self.list_view.controls.append(
                ft.ListTile(
                    leading=ft.IconButton(
                        icon=ft.Icons.OPEN_IN_BROWSER,
                        tooltip=f"「{item.name}」をブラウザで開く",
                        on_click=self._make_open_handler(item),
                    ),
                    title=ft.Text(item.name),
                    subtitle=ft.Text(item.url, max_lines=1),
                    trailing=ft.IconButton(
                        icon=ft.Icons.EDIT,
                        tooltip=f"「{item.name}」を編集する",
                        on_click=self._make_edit_handler(item),
                    ),
                )
            )

        safe_update(self.list_view)

    def _make_open_handler(self, item: TipItem):
        def handler(e: ft.ControlEvent) -> None:
            try:
                open_tip(item)
                ui_log.log_action("TIPS", "launch", item.name)
            except Exception as ex:
                show_toast(self.page, f"開けませんでした: {ex}")

        return handler

    def _add(self, e: ft.ControlEvent) -> None:
        def on_submit(values: dict) -> None:
            self.tips.append(
                TipItem(name=values["name"], url=values["url"], note=values.get("note", ""))
            )
            ui_log.log_action("TIPS", "add", values["name"])
            self._persist("TIPSを追加しました")

        show_item_form_dialog(self.page, "TIPSを追加", TIP_FIELDS, None, on_submit)

    def _make_edit_handler(self, item: TipItem):
        def handler(e: ft.ControlEvent) -> None:
            initial = {"name": item.name, "url": item.url, "note": item.note}

            def on_submit(values: dict) -> None:
                item.name = values["name"]
                item.url = values["url"]
                item.note = values.get("note", "")
                ui_log.log_action("TIPS", "edit", item.name)
                self._persist("TIPSを更新しました")

            def on_delete() -> None:
                name = item.name
                self.tips.remove(item)
                ui_log.log_action("TIPS", "delete", name)
                self._persist("TIPSを削除しました")

            show_item_form_dialog(
                self.page, f"TIPSを編集: {item.name}", TIP_FIELDS, initial, on_submit, on_delete
            )

        return handler

    def _persist(self, message: str) -> None:
        save_tips(TIPS_PATH, self.tips)
        self._refresh()
        show_toast(self.page, message)
