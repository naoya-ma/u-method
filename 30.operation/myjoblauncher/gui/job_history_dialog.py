import flet as ft

from services.history_repo import (
    get_job_daily_summary,
    get_job_executions,
    get_job_monthly_summary,
)
from services import theme_repo

DIALOG_WIDTH = round(560 * 1.1)  # 実行履歴ダイアログの横幅（既定の1.1倍）


def _cell_text(v) -> str:
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S.") + f"{v.microsecond // 1000:03d}"
    return str(v)


def _format_elapsed(start, end) -> str:
    if not start or not end:
        return "-"

    total_ms = round((end - start).total_seconds() * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    seconds, millis = divmod(rem_ms, 1000)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _build_report_text(job_name: str, command: str, monthly, daily, executions) -> str:
    lines = [f"ジョブ: {job_name}", f"コマンド: {command}", ""]

    lines.append("[月別集計]")
    lines.append("年月\t件数\t成功\t失敗")
    for month, total, success, fail in monthly:
        lines.append(f"{month}\t{total}\t{success}\t{fail}")

    lines.append("")
    lines.append("[日別集計]")
    lines.append("日付\t件数\t成功\t失敗")
    for day, total, success, fail in daily:
        lines.append(f"{day}\t{total}\t{success}\t{fail}")

    lines.append("")
    lines.append("[個別実行履歴]")
    lines.append("開始\t終了\t経過時間\tステータス")
    for start, end, _returncode, status in executions:
        label = theme_repo.status_label(status)
        lines.append(f"{_cell_text(start)}\t{_cell_text(end)}\t{_format_elapsed(start, end)}\t{label}")

    return "\n".join(lines)


def _build_table(headers: list[str], rows: list[tuple]) -> ft.Control:
    if not rows:
        return ft.Text("データがありません", italic=True)

    table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text(h)) for h in headers],
        rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(_cell_text(v))) for v in row]) for row in rows],
        column_spacing=16,
        horizontal_margin=8,
    )
    return ft.Column(
        controls=[ft.Row(controls=[table], scroll=ft.ScrollMode.ALWAYS)],
        scroll=ft.ScrollMode.ALWAYS,
        height=280,
    )


def show_job_history_dialog(page: ft.Page, job_name: str, command: str) -> None:
    """
    ジョブ単位の実行履歴（月別集計／日別集計／個別履歴）を表示するダイアログ
    """
    monthly = get_job_monthly_summary(command)
    daily = get_job_daily_summary(command)
    executions = get_job_executions(command)

    exec_rows = [
        (_cell_text(start), _cell_text(end), _format_elapsed(start, end), theme_repo.status_label(status))
        for start, end, _returncode, status in executions
    ]

    async def handle_copy(e: ft.ControlEvent) -> None:
        await ft.Clipboard().set(_build_report_text(job_name, command, monthly, daily, executions))

    def handle_close(e: ft.ControlEvent) -> None:
        page.pop_dialog()

    tabs = ft.Tabs(
        length=3,
        content=ft.Column(
            controls=[
                ft.TabBar(tabs=[ft.Tab(label="月別集計"), ft.Tab(label="日別集計"), ft.Tab(label="個別履歴")]),
                ft.TabBarView(
                    expand=True,
                    controls=[
                        _build_table(["年月", "件数", "成功", "失敗"], monthly),
                        _build_table(["日付", "件数", "成功", "失敗"], daily),
                        _build_table(["開始", "終了", "経過時間", "ステータス"], exec_rows),
                    ],
                ),
            ],
            height=340,
        ),
    )

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row(
            controls=[
                ft.Text(f"実行履歴: {job_name}", expand=True),
                ft.IconButton(
                    icon=ft.Icons.COPY,
                    tooltip="この履歴をテキストでコピーする",
                    on_click=handle_copy,
                ),
            ]
        ),
        content=ft.Container(content=tabs, width=DIALOG_WIDTH),
        actions=[ft.TextButton("閉じる", on_click=handle_close, tooltip="ダイアログを閉じる")],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dialog)
