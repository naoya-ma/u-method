import flet as ft


def show_toast(page: ft.Page, text: str) -> None:
    snack = ft.SnackBar(content=ft.Text(text), open=True)
    page.overlay.append(snack)
    page.update()
