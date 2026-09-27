import flet as ft

from gui.item_form_dialog import show_item_form_dialog
from gui.toast import show_toast
from services import todo_repo, ui_log

TEMPLATE_DIALOG_WIDTH = int(700 * 1.5)  # 1050

TEMPLATE_FIELDS = [
    {"key": "name", "label": "テンプレート名", "type": "text"},
    {
        "key": "content",
        "label": "内容（Markdown見出し構成）",
        "type": "text",
        "wide": True,
        "min_lines": 7,
    },
]


def validate_template_values(values: dict) -> str | None:
    if not (values.get("name") or "").strip():
        return "テンプレート名を入力してください"
    return None


def open_add_template_dialog(page: ft.Page, templates: list, on_saved) -> None:
    def on_submit(values: dict) -> None:
        error = validate_template_values(values)
        if error:
            show_toast(page, error)
            return

        templates.append(todo_repo.TodoTemplate(name=values["name"], content=values.get("content", "")))
        todo_repo.save_templates(templates)
        ui_log.log_action("TODOテンプレート管理", "add", values["name"])
        on_saved()

    show_item_form_dialog(
        page,
        "記入テンプレートを追加",
        TEMPLATE_FIELDS,
        None,
        on_submit,
        width=TEMPLATE_DIALOG_WIDTH,
    )


def open_edit_template_dialog(page: ft.Page, item, templates: list, on_saved, on_deleted) -> None:
    initial = {"name": item.name, "content": item.content}

    def on_submit(values: dict) -> None:
        error = validate_template_values(values)
        if error:
            show_toast(page, error)
            return

        item.name = values["name"]
        item.content = values.get("content", "")
        todo_repo.save_templates(templates)
        ui_log.log_action("TODOテンプレート管理", "edit", item.name)
        on_saved()

    def on_delete() -> None:
        name = item.name
        templates.remove(item)
        todo_repo.save_templates(templates)
        ui_log.log_action("TODOテンプレート管理", "delete", name)
        on_deleted()

    show_item_form_dialog(
        page,
        f"記入テンプレートを編集: {item.name}",
        TEMPLATE_FIELDS,
        initial,
        on_submit,
        on_delete,
        width=TEMPLATE_DIALOG_WIDTH,
    )
