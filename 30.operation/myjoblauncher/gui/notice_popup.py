import flet as ft

from services import notice_seen_repo, portal_repo, tz_repo


def check_and_show_urgent_notices(page: ft.Page, on_go_to_notices) -> None:
    """
    公開日時が来ていて、まだポップアップ表示していない緊急通知があれば、
    まとめて1つのポップアップで表示する（実際のMarkdown/MermaidJS表示はホームタブで行うため、
    ここではタイトル・本文をプレーンテキストとして簡易表示する）。
    「お知らせ画面へ」「キャンセル」どちらを押しても、対象の通知は以後ポップアップされないよう
    既読として記録する（services/notice_seen_repo.py、このPCだけのローカル状態）
    """
    notices = portal_repo.load_notices()
    now = tz_repo.now()
    seen = notice_seen_repo.load_seen_ids()
    pending = portal_repo.pending_urgent_notices(notices, now, seen)

    if not pending:
        return

    def close_and(fn) -> None:
        def handler(e: ft.ControlEvent = None) -> None:
            page.pop_dialog()
            notice_seen_repo.mark_seen([n.notice_id for n in pending])
            if fn:
                fn()

        return handler

    content_controls: list[ft.Control] = []
    for i, n in enumerate(pending):
        if i > 0:
            content_controls.append(ft.Divider())
        content_controls.append(ft.Text(n.title, weight=ft.FontWeight.BOLD))
        content_controls.append(ft.Text(n.publish_at or "", size=11, color=ft.Colors.OUTLINE))
        content_controls.append(ft.Text(n.content))

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("🚨 緊急のお知らせ" if len(pending) == 1 else f"🚨 緊急のお知らせ（{len(pending)}件）"),
        content=ft.Container(
            content=ft.Column(controls=content_controls, scroll=ft.ScrollMode.AUTO, tight=True),
            width=480,
            height=320,
        ),
        actions=[
            ft.TextButton("キャンセル", on_click=close_and(None), tooltip="このポップアップだけを閉じる"),
            ft.Button(
                "お知らせ画面へ",
                on_click=close_and(on_go_to_notices),
                tooltip="ポップアップを閉じて、ホームのお知らせメッセージへ移動する",
            ),
        ],
    )
    page.show_dialog(dialog)
