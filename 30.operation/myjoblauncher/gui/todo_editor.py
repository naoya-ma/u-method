from datetime import date

import flet as ft

from gui.confirm_dialog import show_confirm_dialog
from gui.markdown_preview_dialog import show_markdown_preview_dialog
from gui.toast import show_toast
from gui.todo_template_editor import open_add_template_dialog, open_edit_template_dialog
from services import theme_repo, todo_repo, tz_repo, ui_log

TODO_DIALOG_WIDTH = int(720 * 1.5)  # 1080
TEMPLATE_MANAGER_WIDTH = 600


def open_add_todo_dialog(page: ft.Page, todos: list, on_saved) -> None:
    _open_todo_dialog(page, None, todos, on_saved, None)


def open_edit_todo_dialog(page: ft.Page, item, todos: list, on_saved, on_deleted) -> None:
    _open_todo_dialog(page, item, todos, on_saved, on_deleted)


def _open_todo_dialog(page: ft.Page, item, todos: list, on_saved, on_deleted) -> None:
    """
    件名・内容（Markdown、記入テンプレート適用可）・期限・書き込み先・作成日を編集するダイアログ。
    テンプレート選択で「内容」欄を動的に書き換える必要があり、`gui/item_form_dialog.py`の
    固定フィールドリスト方式（フィールド間の連動不可）では表現できないため、生の`ft.AlertDialog`を
    直接組み立てる専用実装にしている
    """
    is_edit = item is not None
    templates = todo_repo.load_templates()

    subject_field = ft.TextField(
        label="件名",
        value=item.subject if is_edit else "",
        autofocus=True,
        width=TODO_DIALOG_WIDTH,
    )
    due_field = ft.TextField(
        label="期限（YYYY-MM-DD、任意）",
        value=item.due_date if is_edit else "",
        expand=1,
    )
    target_dropdown = ft.Dropdown(
        label="書き込み先",
        value=item.target if is_edit else todo_repo.TARGET_OBSIDIAN,
        options=[
            ft.DropdownOption(key=t, text=t)
            for t in (todo_repo.TARGET_OBSIDIAN, todo_repo.TARGET_EXCEL)
        ],
        expand=1,
    )
    created_at_field = ft.TextField(
        label="作成日",
        value=item.created_at if is_edit else tz_repo.today().isoformat(),
        read_only=True,
        expand=1,
    )
    content_field = ft.TextField(
        label="内容（Markdown）",
        value=item.content if is_edit else "",
        multiline=True,
        min_lines=10,
        max_lines=10,
        width=TODO_DIALOG_WIDTH,
    )
    template_dropdown = ft.Dropdown(
        label="記入テンプレート（選択すると内容欄に挿入されます）",
        options=[ft.DropdownOption(key=t.name, text=t.name) for t in templates],
        expand=1,
    )

    def apply_selected_template() -> None:
        name = template_dropdown.value
        template = next((t for t in templates if t.name == name), None)
        if template is None:
            return
        content_field.value = template.content
        content_field.update()

    def handle_template_select(e: ft.ControlEvent) -> None:
        if not template_dropdown.value:
            return

        if (content_field.value or "").strip():
            show_confirm_dialog(
                page,
                "テンプレートの適用",
                "入力済みの内容を上書きします。よろしいですか？",
                apply_selected_template,
            )
        else:
            apply_selected_template()

    def refresh_template_options() -> None:
        nonlocal templates
        templates = todo_repo.load_templates()
        template_dropdown.options = [ft.DropdownOption(key=t.name, text=t.name) for t in templates]
        if template_dropdown.value not in {t.name for t in templates}:
            template_dropdown.value = None
        template_dropdown.update()

    def handle_manage_templates(e: ft.ControlEvent) -> None:
        ui_log.log_action("TODO管理", "click", "テンプレート管理を開く")
        _open_template_manager_dialog(page, refresh_template_options)

    template_dropdown.on_select = handle_template_select

    def handle_preview(e: ft.ControlEvent) -> None:
        title = subject_field.value or "（件名未入力）"
        markdown_text = f"# {title}\n\n{content_field.value or ''}"
        show_markdown_preview_dialog(page, title, markdown_text)

    def handle_cancel(e: ft.ControlEvent) -> None:
        page.pop_dialog()

    def handle_delete(e: ft.ControlEvent) -> None:
        page.pop_dialog()
        todos.remove(item)
        todo_repo.save_todos(todos)
        ui_log.log_action("TODO管理", "delete", item.subject)
        on_deleted()

    def handle_save(e: ft.ControlEvent) -> None:
        subject = (subject_field.value or "").strip()
        if not subject:
            show_toast(page, "件名を入力してください")
            return

        due_date = (due_field.value or "").strip()
        if due_date:
            try:
                date.fromisoformat(due_date)
            except ValueError:
                show_toast(page, "期限は「YYYY-MM-DD」形式で入力してください")
                return

        page.pop_dialog()

        if is_edit:
            item.subject = subject
            item.content = content_field.value or ""
            item.due_date = due_date
            item.target = target_dropdown.value or todo_repo.TARGET_OBSIDIAN
        else:
            todos.append(
                todo_repo.TodoItem(
                    subject=subject,
                    content=content_field.value or "",
                    target=target_dropdown.value or todo_repo.TARGET_OBSIDIAN,
                    todo_id=todo_repo.next_todo_id(todos),
                    created_at=tz_repo.today().isoformat(),
                    due_date=due_date,
                )
            )
        todo_repo.save_todos(todos)
        ui_log.log_action("TODO管理", "edit" if is_edit else "add", subject)
        on_saved()

    actions = [
        ft.TextButton("キャンセル", on_click=handle_cancel, tooltip="変更を破棄して閉じる"),
        ft.TextButton("プレビュー", on_click=handle_preview, tooltip="現在の入力内容をプレビュー表示する（保存はしない）"),
    ]
    if is_edit:
        actions.append(
            ft.TextButton(
                "削除",
                on_click=handle_delete,
                tooltip="このTODOを削除する",
                style=ft.ButtonStyle(color=theme_repo.error_color()),
            )
        )
    actions.append(ft.Button("保存", on_click=handle_save, tooltip="入力内容を保存する"))

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("TODOを編集" if is_edit else "TODOを追加"),
        content=ft.Container(
            width=TODO_DIALOG_WIDTH,
            content=ft.Column(
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    subject_field,
                    ft.Row(controls=[due_field, target_dropdown, created_at_field], spacing=12),
                    ft.Row(
                        controls=[
                            template_dropdown,
                            ft.IconButton(
                                icon=ft.Icons.SETTINGS,
                                tooltip="記入テンプレートの管理（追加・編集・削除）",
                                on_click=handle_manage_templates,
                            ),
                        ],
                        spacing=4,
                    ),
                    content_field,
                ],
            ),
        ),
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dialog)


# ========================
# ✅ 記入テンプレートの管理（一覧・追加・編集・削除）
# ========================
def _open_template_manager_dialog(page: ft.Page, on_changed) -> None:
    templates = todo_repo.load_templates()
    list_view = ft.ListView(spacing=2, height=300)

    def build_rows() -> None:
        list_view.controls = [
            ft.ListTile(
                title=ft.Text(t.name),
                subtitle=ft.Text(f"見出し{t.content.count('###')}個" if t.content else "（内容未設定）"),
                trailing=ft.Row(
                    tight=True,
                    controls=[
                        ft.IconButton(
                            icon=ft.Icons.EDIT,
                            tooltip=f"「{t.name}」を編集する",
                            on_click=_make_edit_template_handler(page, t, templates, build_rows, list_view, on_changed),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE,
                            tooltip=f"「{t.name}」を削除する",
                            icon_color=theme_repo.error_color(),
                            on_click=_make_delete_template_handler(page, t, templates, build_rows, list_view, on_changed),
                        ),
                    ],
                ),
            )
            for t in templates
        ]

    def handle_add(e: ft.ControlEvent) -> None:
        def on_saved() -> None:
            build_rows()
            list_view.update()
            on_changed()

        open_add_template_dialog(page, templates, on_saved)

    def handle_close(e: ft.ControlEvent) -> None:
        page.pop_dialog()

    build_rows()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("記入テンプレートの管理"),
        content=ft.Container(
            width=TEMPLATE_MANAGER_WIDTH,
            content=ft.Column(
                tight=True,
                controls=[
                    ft.Button("テンプレートを追加", icon=ft.Icons.ADD, on_click=handle_add),
                    ft.Container(content=list_view, border=ft.Border.all(1, ft.Colors.OUTLINE)),
                ],
            ),
        ),
        actions=[ft.TextButton("閉じる", on_click=handle_close)],
    )
    page.show_dialog(dialog)


def _make_edit_template_handler(page: ft.Page, item, templates: list, build_rows, list_view, on_changed):
    def handler(e: ft.ControlEvent) -> None:
        def on_saved() -> None:
            build_rows()
            list_view.update()
            on_changed()

        def on_deleted() -> None:
            build_rows()
            list_view.update()
            on_changed()

        open_edit_template_dialog(page, item, templates, on_saved, on_deleted)

    return handler


def _make_delete_template_handler(page: ft.Page, item, templates: list, build_rows, list_view, on_changed):
    def handler(e: ft.ControlEvent) -> None:
        def do_delete() -> None:
            templates.remove(item)
            todo_repo.save_templates(templates)
            ui_log.log_action("TODOテンプレート管理", "delete", item.name)
            build_rows()
            list_view.update()
            on_changed()

        show_confirm_dialog(page, "テンプレートの削除", f"「{item.name}」を削除しますか？", do_delete)

    return handler
