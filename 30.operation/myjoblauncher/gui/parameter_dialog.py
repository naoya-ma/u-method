import flet as ft


def show_parameter_dialog(page: ft.Page, params: list[str], on_submit) -> None:
    """
    パラメータ入力ダイアログを表示する。

    「実行」ボタンが押されると on_submit(values) を呼び出す。
    values は {パラメータ名: 入力値} の辞書。
    """
    inputs: dict[str, ft.TextField] = {}
    fields: list[ft.Control] = []

    for p in params:
        field = ft.TextField(label=p, autofocus=(len(fields) == 0))
        inputs[p] = field
        fields.append(field)

    def handle_ok(e: ft.ControlEvent) -> None:
        values = {k: (v.value or "") for k, v in inputs.items()}
        page.pop_dialog()
        on_submit(values)

    def handle_cancel(e: ft.ControlEvent) -> None:
        page.pop_dialog()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("パラメータ入力"),
        content=ft.Column(controls=fields, tight=True, width=320),
        actions=[
            ft.TextButton("キャンセル", on_click=handle_cancel),
            ft.Button("実行", on_click=handle_ok),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dialog)
