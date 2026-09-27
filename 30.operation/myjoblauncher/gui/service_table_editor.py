import flet as ft

from services import portal_repo, theme_repo, tz_repo, ui_log
from utils.markdown_table import build_markdown_table, parse_markdown_table

# ✅ ホームの「よく使うサービス」表（config/home.tomlの[portal].content、Markdownのパイプ区切り
# テーブル構文）を、列・行単位のテキストとして編集するための専用エディタ。見出し・区切り行・
# セル内改行（<br>）・列数のそろえはすべて保存時に自動生成する（utils/markdown_table.py）。
# 手作業でのMarkdownテーブル編集（設定タブの「ホーム本文」欄）に代わる、より保守しやすい入力手段

CELL_FIELD_WIDTH = 260
HEADER_FIELD_WIDTH = 220


def open_service_table_editor_dialog(page: ft.Page, on_saved) -> None:
    """
    現在の`portal_repo`のホーム本文をMarkdownテーブルとして解析し、列・行の編集ダイアログを開く。
    保存すると`build_markdown_table()`で組み立て直したMarkdownを`PortalConfig.content`へ書き込む。
    `on_saved`は保存後に呼ばれるコールバック（呼び出し元がプレビュー欄等を更新するため）
    """
    portal_config = portal_repo.load_portal_config()
    headers, rows = parse_markdown_table(portal_config.content)

    header_fields: list[ft.TextField] = []
    cell_fields: list[list[ft.TextField]] = []

    grid_row = ft.Row(scroll=ft.ScrollMode.ALWAYS, spacing=8, vertical_alignment=ft.CrossAxisAlignment.START)
    is_mounted = False

    def make_header_field(text: str) -> ft.TextField:
        return ft.TextField(value=text, width=HEADER_FIELD_WIDTH, dense=True, text_size=13)

    def make_cell_field(text: str) -> ft.TextField:
        return ft.TextField(
            value=text,
            width=CELL_FIELD_WIDTH,
            multiline=True,
            min_lines=6,
            max_lines=14,
            dense=True,
            text_size=13,
        )

    def handle_delete_column(col_index: int):
        def handler(e: ft.ControlEvent) -> None:
            if len(header_fields) <= 1:
                return
            header_fields.pop(col_index)
            for row in cell_fields:
                row.pop(col_index)
            rebuild()

        return handler

    def handle_delete_row(row_index: int):
        def handler(e: ft.ControlEvent) -> None:
            cell_fields.pop(row_index)
            rebuild()

        return handler

    def handle_add_column(e: ft.ControlEvent) -> None:
        header_fields.append(make_header_field(f"列{len(header_fields) + 1}"))
        for row in cell_fields:
            row.append(make_cell_field(""))
        rebuild()

    def handle_add_row(e: ft.ControlEvent) -> None:
        cell_fields.append([make_cell_field("") for _ in header_fields])
        rebuild()

    def rebuild() -> None:
        columns: list[ft.Control] = []
        for col_index, header_field in enumerate(header_fields):
            columns.append(
                ft.Column(
                    spacing=6,
                    controls=[
                        ft.Row(
                            spacing=2,
                            controls=[
                                header_field,
                                ft.IconButton(
                                    icon=ft.Icons.DELETE,
                                    icon_size=16,
                                    tooltip="この列を削除する",
                                    icon_color=theme_repo.error_color(),
                                    on_click=handle_delete_column(col_index),
                                ),
                            ],
                        ),
                        *[cell_fields[row_index][col_index] for row_index in range(len(cell_fields))],
                    ],
                )
            )

        # ✅ 行削除ボタン列（見出し行の高さぶん空けてから、各行の削除ボタンを縦に並べる）
        columns.append(
            ft.Column(
                spacing=6,
                controls=[
                    ft.Container(height=48),
                    *[
                        ft.IconButton(
                            icon=ft.Icons.DELETE,
                            icon_size=16,
                            tooltip=f"{row_index + 1}行目を削除する",
                            icon_color=theme_repo.error_color(),
                            on_click=handle_delete_row(row_index),
                        )
                        for row_index in range(len(cell_fields))
                    ],
                ],
            )
        )

        grid_row.controls = columns
        if is_mounted:
            grid_row.update()

    header_fields = [make_header_field(h) for h in headers]
    cell_fields = [[make_cell_field(c) for c in row] for row in rows] if rows else []
    rebuild()

    def handle_save(e: ft.ControlEvent) -> None:
        new_headers = [f.value or "" for f in header_fields]
        new_rows = [[f.value or "" for f in row] for row in cell_fields]

        portal_config.content = build_markdown_table(new_headers, new_rows)
        portal_config.updated_at = tz_repo.now().strftime(portal_repo.DATETIME_FORMAT)
        portal_repo.save_portal_config(portal_config)

        ui_log.log_action("設定", "save", "よく使うサービス表")
        page.pop_dialog()
        on_saved(portal_config.content)

    def handle_close(e: ft.ControlEvent) -> None:
        page.pop_dialog()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("よく使うサービスの編集"),
        content=ft.Container(
            width=900,
            height=560,
            content=ft.Column(
                controls=[
                    ft.Text(
                        "列（サービス種別）ごとに見出しとセルの内容を編集します。"
                        "セル内では通常の改行がそのまま行に反映され、Markdownテーブルの構文・"
                        "セル内改行（<br>）・列数のそろえは保存時に自動で組み立てます。",
                        size=12,
                        color=ft.Colors.OUTLINE,
                    ),
                    ft.Row(controls=[ft.Button("列を追加", icon=ft.Icons.ADD, on_click=handle_add_column)]),
                    ft.Container(content=grid_row, expand=True),
                    ft.Button("行を追加", icon=ft.Icons.ADD, on_click=handle_add_row),
                ],
                spacing=8,
                expand=True,
            ),
        ),
        actions=[
            ft.TextButton("キャンセル", on_click=handle_close),
            ft.Button("保存", icon=ft.Icons.SAVE, on_click=handle_save),
        ],
    )
    page.show_dialog(dialog)
    is_mounted = True
