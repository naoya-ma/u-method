import flet as ft

from services import theme_repo


def show_confirm_dialog(
    page: ft.Page, title: str, message: str, on_confirm, confirm_label: str = "実行"
) -> None:
    """
    「（confirm_label）」「キャンセル」の確認ダイアログ。上書き・削除等の取り消せない操作の前に使う。
    """

    def handle_ok(e: ft.ControlEvent) -> None:
        page.pop_dialog()
        on_confirm()

    def handle_cancel(e: ft.ControlEvent) -> None:
        page.pop_dialog()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Text(message),
        actions=[
            ft.TextButton("キャンセル", on_click=handle_cancel, tooltip="操作を取り消す"),
            ft.Button(
                confirm_label,
                on_click=handle_ok,
                tooltip=f"{confirm_label}する",
                style=ft.ButtonStyle(color=theme_repo.error_color()),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dialog)


def show_script_confirm_dialog(
    page: ft.Page, tool_name: str, script_kind: str, content: str, on_confirm
) -> None:
    """
    バッチ/PowerShellスクリプトの内容（先頭部分）をプレビュー表示し、実行前の承認を求める確認
    ダイアログ。スクリプト実行は任意のコマンドを実行できるため、実行前に必ず内容を確認できるよう
    にする（ユーザーからの要望）。長いスクリプトは先頭のみ表示し、以降は省略する
    """
    preview_limit = 2000
    preview = content if len(content) <= preview_limit else content[:preview_limit] + "\n...(以下省略)"

    def handle_ok(e: ft.ControlEvent) -> None:
        page.pop_dialog()
        on_confirm()

    def handle_cancel(e: ft.ControlEvent) -> None:
        page.pop_dialog()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(f"{script_kind}の実行確認: {tool_name}"),
        content=ft.Container(
            content=ft.Column(
                controls=[ft.Text(preview, selectable=True, font_family="Consolas", size=12)],
                scroll=ft.ScrollMode.AUTO,
            ),
            width=560,
            height=320,
        ),
        actions=[
            ft.TextButton("キャンセル", on_click=handle_cancel, tooltip="実行を取りやめる"),
            ft.Button(
                "実行",
                on_click=handle_ok,
                tooltip="内容を確認した上で実行する",
                style=ft.ButtonStyle(color=theme_repo.error_color()),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dialog)
