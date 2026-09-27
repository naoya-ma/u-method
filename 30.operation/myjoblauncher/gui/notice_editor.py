from datetime import datetime

import flet as ft

from gui.item_form_dialog import show_item_form_dialog
from gui.markdown_preview_dialog import show_markdown_preview_dialog
from gui.toast import show_toast
from services import portal_repo, ui_log

NOTICE_DIALOG_WIDTH = 900

NOTICE_FIELDS = [
    {"key": "title", "label": "通知タイトル", "type": "text"},
    {"key": "publish_at", "label": "公開日時（YYYY-MM-DD HH:MM、空欄は即時公開）", "type": "text"},
    {"key": "duration_days", "label": "通知期間（日数）", "type": "text", "default": "7"},
    {"key": "urgent", "label": "緊急通知（公開日時が来たらポップアップ表示）", "type": "checkbox"},
    {"key": "content", "label": "通知内容（Markdown/MermaidJS）", "type": "text", "wide": True},
]


def validate_notice_values(values: dict) -> str | None:
    if not (values.get("title") or "").strip():
        return "通知タイトルを入力してください"

    publish_at = (values.get("publish_at") or "").strip()
    if publish_at:
        try:
            datetime.strptime(publish_at, portal_repo.DATETIME_FORMAT)
        except ValueError:
            return "公開日時は「YYYY-MM-DD HH:MM」形式で入力してください"

    duration_raw = (values.get("duration_days") or "").strip()
    if duration_raw:
        try:
            if int(duration_raw) < 0:
                raise ValueError
        except ValueError:
            return "通知期間は0以上の整数で入力してください"

    return None


def _duration_from_values(values: dict) -> int:
    raw = (values.get("duration_days") or "").strip()
    return int(raw) if raw else 7


def _preview_notice(page: ft.Page, values: dict) -> None:
    title = values.get("title") or "（タイトル未入力）"
    urgent_mark = "🚨 " if values.get("urgent") else ""
    publish_at = values.get("publish_at") or "（即時公開）"
    markdown_text = (
        f"### {urgent_mark}{title}\n\n*{publish_at}*\n\n---\n\n{values.get('content') or ''}"
    )
    show_markdown_preview_dialog(page, title, markdown_text)


def open_add_notice_dialog(page: ft.Page, notices: list, on_saved) -> None:
    def on_submit(values: dict) -> None:
        error = validate_notice_values(values)
        if error:
            show_toast(page, error)
            return

        notices.append(
            portal_repo.NoticeItem(
                title=values["title"],
                content=values.get("content", ""),
                publish_at=(values.get("publish_at") or "").strip(),
                duration_days=_duration_from_values(values),
                urgent=bool(values.get("urgent")),
                notice_id=portal_repo.next_notice_id(notices),
            )
        )
        portal_repo.save_notices(notices)
        ui_log.log_action("お知らせ管理", "add", values["title"])
        on_saved()

    show_item_form_dialog(
        page,
        "お知らせを追加",
        NOTICE_FIELDS,
        None,
        on_submit,
        width=NOTICE_DIALOG_WIDTH,
        on_preview=lambda values: _preview_notice(page, values),
    )


def open_edit_notice_dialog(page: ft.Page, item, notices: list, on_saved, on_deleted) -> None:
    initial = {
        "title": item.title,
        "publish_at": item.publish_at,
        "duration_days": str(item.duration_days),
        "urgent": item.urgent,
        "content": item.content,
    }

    def on_submit(values: dict) -> None:
        error = validate_notice_values(values)
        if error:
            show_toast(page, error)
            return

        item.title = values["title"]
        item.content = values.get("content", "")
        item.publish_at = (values.get("publish_at") or "").strip()
        item.duration_days = _duration_from_values(values)
        item.urgent = bool(values.get("urgent"))
        portal_repo.save_notices(notices)
        ui_log.log_action("お知らせ管理", "edit", item.title)
        on_saved()

    def on_delete() -> None:
        title = item.title
        notices.remove(item)
        portal_repo.save_notices(notices)
        ui_log.log_action("お知らせ管理", "delete", title)
        on_deleted()

    show_item_form_dialog(
        page,
        f"お知らせを編集: {item.title}",
        NOTICE_FIELDS,
        initial,
        on_submit,
        on_delete,
        width=NOTICE_DIALOG_WIDTH,
        on_preview=lambda values: _preview_notice(page, values),
    )
