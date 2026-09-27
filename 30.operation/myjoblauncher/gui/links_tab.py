import flet as ft

from gui.icon_grid_view import (
    RECOMMEND_OPTIONS,
    GridEntry,
    build_icon_grid,
    build_list_view,
    build_sort_mode_dropdown,
    build_view_mode_toggle,
    parse_recommend,
    sort_items,
)
from gui.item_form_dialog import show_item_form_dialog
from gui.safe_update import safe_update
from gui.toast import show_toast
from services.links_repo import LinkItem, load_links, open_link, save_links
from services import icon_cache, tz_repo, ui_log, view_mode_repo

LINKS_PATH = "config/links.toml"
VIEW_MODE_KEY = "links_view_mode"
SORT_MODE_KEY = "links_sort_mode"

# 既定幅480pxの2倍（ユーザーからの要望）
LINKS_DIALOG_WIDTH = 960

LINK_FIELDS = [
    {"key": "name", "label": "リンク名", "type": "text"},
    {
        "key": "kind",
        "label": "種類",
        "type": "dropdown",
        "options": ["url", "folder", "file"],
        "default": "url",
    },
    {"key": "target", "label": "URL または フォルダ/ファイルのパス", "type": "text"},
    {"key": "category", "label": "カテゴリ", "type": "text"},
    {
        "key": "recommend",
        "label": "おすすめ（1〜5、空欄で未設定）",
        "type": "dropdown",
        "options": list(reversed(RECOMMEND_OPTIONS)),
    },
    {"key": "comment", "label": "ひとこと", "type": "text"},
    {"key": "note", "label": "備考", "type": "text"},
]

KIND_ICON = {
    "url": ft.Icons.LINK,
    "folder": ft.Icons.FOLDER_OPEN,
    "file": ft.Icons.INSERT_DRIVE_FILE,
}


def _format_last_used(item: LinkItem) -> str:
    return item.last_used_at.replace("T", " ")[:16] if item.last_used_at else "未呼出"


class LinksTab:
    """
    よく使うリンクタブ。URL・ローカルフォルダ・ローカルファイルを開く。
    アイコン表示（大/中/小）・一覧表示を切り替え可能（既定はアイコン表示・中）。
    一覧は使用回数/名前/最終呼出日時で並び替え可能（既定は使用回数の多い順）
    """

    def __init__(self, page: ft.Page):
        self.page = page
        self.links: list[LinkItem] = load_links(LINKS_PATH)
        self.view_mode = view_mode_repo.load_view_mode(VIEW_MODE_KEY)
        self.sort_mode = view_mode_repo.load_sort_mode(SORT_MODE_KEY)
        self.body = ft.Container(expand=True, border=ft.Border.all(1, ft.Colors.OUTLINE))
        self.sort_dropdown = build_sort_mode_dropdown(self.sort_mode, self._handle_sort_mode_change)
        self.toggle_row = build_view_mode_toggle(self.view_mode, self._handle_view_mode_change)

        self.view = ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("よく使うリンク", weight=ft.FontWeight.BOLD, expand=True),
                        self.sort_dropdown,
                        self.toggle_row,
                        ft.Button(
                            "追加", icon=ft.Icons.ADD, tooltip="新しいリンクを追加する", on_click=self._add
                        ),
                    ]
                ),
                self.body,
            ],
        )

        self._refresh()

    # ========================
    # ✅ 表示モード切替
    # ========================
    def _handle_view_mode_change(self, mode: str) -> None:
        self.view_mode = mode
        view_mode_repo.save_view_mode(VIEW_MODE_KEY, mode)
        self.toggle_row = build_view_mode_toggle(self.view_mode, self._handle_view_mode_change)
        self.view.controls[0].controls[2] = self.toggle_row
        safe_update(self.view)
        self._refresh()

    # ========================
    # ✅ 並び替え
    # ========================
    def _handle_sort_mode_change(self, mode: str) -> None:
        self.sort_mode = mode
        view_mode_repo.save_sort_mode(SORT_MODE_KEY, mode)
        self._refresh()

    # ========================
    # ✅ 描画
    # ========================
    def _refresh(self) -> None:
        ordered = sort_items(self.links, self.sort_mode)

        entries = [
            GridEntry(
                label=item.name,
                subtitle=item.target,
                last_used_label=_format_last_used(item),
                icon_path=icon_cache.get_link_icon_path(item),
                fallback_icon=KIND_ICON.get(item.kind, icon_cache.guess_fallback_icon(item.name)),
                on_launch=self._make_open_handler(item),
                on_edit=self._make_edit_handler(item),
                tooltip=f"クリックするとリンク先を開きます\n({item.target})",
                category=item.category,
                pinned=item.pinned,
                on_toggle_pin=self._make_pin_handler(item),
            )
            for item in ordered
        ]

        if self.view_mode == "list":
            self.body.content = build_list_view(entries)
        else:
            self.body.content = build_icon_grid(entries, self.view_mode)

        safe_update(self.body)

    def _make_open_handler(self, item: LinkItem):
        def handler() -> None:
            try:
                open_link(item)
                item.use_count += 1
                item.last_used_at = tz_repo.now().isoformat()
                save_links(LINKS_PATH, self.links)
                icon_cache.get_link_icon_path(item, force=True)
                ui_log.log_action("リンク", "launch", item.name)
                self._refresh()
            except Exception as ex:
                show_toast(self.page, f"開けませんでした: {ex}")

        return handler

    def _make_pin_handler(self, item: LinkItem):
        def handler() -> None:
            item.pinned = not item.pinned
            ui_log.log_action("リンク", "toggle", item.name, value="pinned" if item.pinned else "unpinned")
            self._persist("ピン止めしました" if item.pinned else "ピン止めを解除しました")

        return handler

    def _add(self, e: ft.ControlEvent) -> None:
        def on_submit(values: dict) -> None:
            new_item = LinkItem(
                name=values["name"],
                target=values["target"],
                kind=values.get("kind") or "url",
                note=values.get("note", ""),
                category=values.get("category", ""),
                recommend=parse_recommend(values.get("recommend")),
                comment=values.get("comment", ""),
            )
            self.links.append(new_item)
            icon_cache.get_link_icon_path(new_item, force=True)
            ui_log.log_action("リンク", "add", values["name"])
            self._persist("リンクを追加しました")

        show_item_form_dialog(
            self.page, "リンクを追加", LINK_FIELDS, None, on_submit, width=LINKS_DIALOG_WIDTH
        )

    def _make_edit_handler(self, item: LinkItem):
        def handler() -> None:
            initial = {
                "name": item.name,
                "target": item.target,
                "kind": item.kind,
                "category": item.category,
                "recommend": str(item.recommend) if item.recommend else "",
                "comment": item.comment,
                "note": item.note,
            }

            def on_submit(values: dict) -> None:
                item.name = values["name"]
                item.target = values["target"]
                item.kind = values.get("kind") or "url"
                item.category = values.get("category", "")
                item.recommend = parse_recommend(values.get("recommend"))
                item.comment = values.get("comment", "")
                item.note = values.get("note", "")
                icon_cache.get_link_icon_path(item, force=True)
                ui_log.log_action("リンク", "edit", item.name)
                self._persist("リンクを更新しました")

            def on_delete() -> None:
                name = item.name
                self.links.remove(item)
                ui_log.log_action("リンク", "delete", name)
                self._persist("リンクを削除しました")

            show_item_form_dialog(
                self.page,
                f"リンクを編集: {item.name}",
                LINK_FIELDS,
                initial,
                on_submit,
                on_delete,
                width=LINKS_DIALOG_WIDTH,
            )

        return handler

    def _persist(self, message: str) -> None:
        save_links(LINKS_PATH, self.links)
        self._refresh()
        show_toast(self.page, message)
