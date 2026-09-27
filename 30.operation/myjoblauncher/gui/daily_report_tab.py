import datetime
import urllib.parse

import flet as ft

from gui.confirm_dialog import show_confirm_dialog
from gui.safe_update import safe_update
from gui.toast import show_toast
from gui.todo_editor import open_add_todo_dialog, open_edit_todo_dialog
from services import theme_repo, todo_repo, tz_repo, ui_log
from services.history_repo import get_executions_on_date
from services.obsidian_repo import (
    CONFIG_PATH,
    build_report_path,
    build_tags,
    load_obsidian_config,
    render_tag_template,
    report_exists,
    save_obsidian_config,
    write_daily_report,
)
from utils.opener import open_target

SETTINGS_FIELD_WIDTH = 440                                # 個人名・タグ既定値テンプレートの入力欄の幅
OUTPUT_DIR_FIELD_WIDTH = SETTINGS_FIELD_WIDTH * 2         # 880  出力先フォルダの入力欄の幅
TOMORROW_PLAN_FIELD_WIDTH = SETTINGS_FIELD_WIDTH * 2      # 880  明日の作業予定欄の幅
TODAY_RESULTS_FIELD_WIDTH = TOMORROW_PLAN_FIELD_WIDTH     # 880  本日の作業実績欄の幅（明日の作業予定と揃える）
CONSULTATION_FIELD_WIDTH = SETTINGS_FIELD_WIDTH * 2       # 880  相談事項欄の幅
CONTACT_FIELD_WIDTH = SETTINGS_FIELD_WIDTH * 2            # 880  連絡事項欄の幅


class DailyReportTab:
    """
    Obsidian Vault（または任意のフォルダ）へ、個人単位・日付単位で
    「本日の作業実績」「明日の作業予定」をMarkdownとして出力する。
    """

    def __init__(self, page: ft.Page, menu_items: list = None):
        self.page = page
        self.menu_items = menu_items or []
        self.config = load_obsidian_config(CONFIG_PATH)
        self.last_written_path = None
        self.todos = todo_repo.load_todos()
        self.todo_settings = todo_repo.load_todo_settings()

        self.vault_dir_field = ft.TextField(
            label="出力先フォルダ（Obsidian Vault等）",
            value=self.config.vault_dir,
            tooltip="日報を出力するObsidian Vault、または任意のフォルダのパス",
            width=OUTPUT_DIR_FIELD_WIDTH,
        )
        self.person_name_field = ft.TextField(
            label="個人名",
            value=self.config.person_name,
            tooltip="出力先フォルダの下に、この名前のサブフォルダを作って出力します（個人単位の管理用）",
            width=SETTINGS_FIELD_WIDTH,
        )
        self.default_tags_template_field = ft.TextField(
            label="タグの既定値（テンプレート）",
            value=self.config.default_tags_template,
            tooltip="「タグ」欄の初期値。{yymmdd} と書くと対象日の日付（例: 2026-09-21 → 260921）に置き換わります"
            "（例: プロジェクトA-{yymmdd}）。対象日を変更すると自動で再展開されます",
            width=SETTINGS_FIELD_WIDTH,
        )
        self.excel_path_field = ft.TextField(
            label="Excel出力先ファイル（TODOの書き込み先）",
            value=self.todo_settings.excel_path,
            tooltip="TODOの書き込み先に「Excel」を選んだ項目を「済にする」際に、1行追記する .xlsx ファイルのパス",
            width=OUTPUT_DIR_FIELD_WIDTH,
        )

        self.date_field = ft.TextField(
            label="対象日 (YYYY-MM-DD)",
            value=tz_repo.today().isoformat(),
            tooltip="日報を出力する日付。過去・未来の日付にも出力できます",
            width=180,
        )

        self.today_results_field = ft.TextField(
            label="本日の作業実績",
            value="",
            multiline=True,
            min_lines=6,
            max_lines=14,
            tooltip="対象日に行った作業の実績を入力してください",
            width=TODAY_RESULTS_FIELD_WIDTH,
        )
        self.tomorrow_plan_field = ft.TextField(
            label="明日の作業予定",
            value="",
            multiline=True,
            min_lines=6,
            max_lines=14,
            tooltip="翌日以降の作業予定を入力してください",
            width=TOMORROW_PLAN_FIELD_WIDTH,
        )

        self.todo_list_column = ft.Column(spacing=4, tight=True)

        self.consultation_field = ft.TextField(
            label="相談事項",
            value="",
            multiline=True,
            min_lines=3,
            max_lines=8,
            tooltip="日報出力のたびに入力する自由記述欄です（保存はされません）",
            width=CONSULTATION_FIELD_WIDTH,
        )
        self.contact_field = ft.TextField(
            label="連絡事項",
            value="",
            multiline=True,
            min_lines=3,
            max_lines=8,
            tooltip="日報出力のたびに入力する自由記述欄です（保存はされません）",
            width=CONTACT_FIELD_WIDTH,
        )

        self.tags_field = ft.TextField(
            label="タグ（カンマ区切り、任意）",
            value=render_tag_template(self.config.default_tags_template, tz_repo.today()),
            tooltip="Obsidianのプロパティ(tags)に追加するタグ。「日報」と対象日は自動で付与されます（例: 会議, 障害対応）",
        )

        self.result_text = ft.Text("", selectable=True)
        self.open_button = ft.Button(
            "Obsidianで開く",
            icon=ft.Icons.OPEN_IN_NEW,
            tooltip="出力したファイルをObsidianで開く（Obsidianがインストールされている場合）",
            visible=False,
            on_click=self._handle_open_in_obsidian,
        )

        self.view = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
            controls=[
                ft.Text("Obsidian 日報出力", weight=ft.FontWeight.BOLD),
                self.vault_dir_field,
                self.person_name_field,
                self.default_tags_template_field,
                self.excel_path_field,
                ft.Button(
                    "既定値を保存",
                    icon=ft.Icons.SAVE,
                    tooltip="出力先フォルダ・個人名・タグの既定値テンプレート・Excel出力先ファイルを保存する",
                    on_click=self._save_settings,
                ),
                ft.Divider(),
                ft.Row(
                    controls=[
                        self.date_field,
                        ft.IconButton(
                            icon=ft.Icons.TODAY,
                            tooltip="対象日を今日にする",
                            on_click=self._set_today,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CHEVRON_LEFT,
                            tooltip="対象日を1日前にする",
                            on_click=self._make_shift_handler(-1),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CHEVRON_RIGHT,
                            tooltip="対象日を1日後にする",
                            on_click=self._make_shift_handler(1),
                        ),
                    ]
                ),
                ft.Row(
                    controls=[
                        ft.Button(
                            "本日実施したジョブを取り込む",
                            icon=ft.Icons.DOWNLOAD,
                            tooltip="対象日に実行したジョブ（定型・非定型）の実行履歴を「本日の作業実績」へ取り込みます",
                            on_click=self._handle_import_jobs,
                        ),
                    ]
                ),
                self.today_results_field,
                self.tomorrow_plan_field,
                ft.Divider(),
                ft.Container(
                    width=TOMORROW_PLAN_FIELD_WIDTH,
                    padding=ft.Padding.only(left=14),
                    content=ft.Column(
                        spacing=4,
                        tight=True,
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text("TODO", expand=True),
                                    ft.Button(
                                        "TODOを追加",
                                        icon=ft.Icons.ADD_TASK,
                                        on_click=self._handle_add_todo,
                                    ),
                                ]
                            ),
                            self.todo_list_column,
                        ],
                    ),
                ),
                ft.Divider(),
                self.consultation_field,
                self.contact_field,
                self.tags_field,
                ft.Row(
                    controls=[
                        ft.Button(
                            "Obsidianへ出力",
                            icon=ft.Icons.UPLOAD_FILE,
                            tooltip="入力内容を対象日のMarkdownファイルへ出力する",
                            on_click=self._handle_output,
                        ),
                        self.open_button,
                    ]
                ),
                self.result_text,
            ],
        )

        self._render_todo_list()  # 起動直後も永続化済みのTODOをすぐ表示する

    # ========================
    # ✅ 保存先設定
    # ========================
    def _save_settings(self, e: ft.ControlEvent) -> None:
        self.config.vault_dir = self.vault_dir_field.value or ""
        self.config.person_name = self.person_name_field.value or ""
        self.config.default_tags_template = self.default_tags_template_field.value or ""
        save_obsidian_config(CONFIG_PATH, self.config)

        self.todo_settings.excel_path = self.excel_path_field.value or ""
        todo_repo.save_todo_settings(self.todo_settings)

        self._apply_tags_template()
        ui_log.log_action("日報", "save", "日報既定値")
        show_toast(self.page, "既定値を保存しました")

    # ========================
    # ✅ 対象日の操作
    # ========================
    def _set_today(self, e: ft.ControlEvent) -> None:
        self.date_field.value = tz_repo.today().isoformat()
        self.date_field.update()
        self._apply_tags_template()

    def _make_shift_handler(self, delta_days: int):
        def handler(e: ft.ControlEvent) -> None:
            d = self._parse_date() or tz_repo.today()
            d = d + datetime.timedelta(days=delta_days)
            self.date_field.value = d.isoformat()
            self.date_field.update()
            self._apply_tags_template()

        return handler

    def _parse_date(self) -> datetime.date | None:
        try:
            return datetime.date.fromisoformat((self.date_field.value or "").strip())
        except ValueError:
            return None

    def _apply_tags_template(self) -> None:
        """タグ欄を、対象日で展開した既定値テンプレートへ再設定する（対象日変更・既定値保存の直後に呼ぶ）"""
        if not self.config.default_tags_template:
            return

        target_date = self._parse_date() or tz_repo.today()
        self.tags_field.value = render_tag_template(self.config.default_tags_template, target_date)
        self.tags_field.update()

    # ========================
    # ✅ 本日実施したジョブの取り込み
    # ========================
    def _handle_import_jobs(self, e: ft.ControlEvent) -> None:
        target_date = self._parse_date()
        if target_date is None:
            show_toast(self.page, "対象日は YYYY-MM-DD 形式で入力してください")
            return

        executions = get_executions_on_date(target_date)
        if not executions:
            show_toast(self.page, f"{target_date.isoformat()} の実行履歴はありません")
            return

        command_to_item = {item.command: item for item in self.menu_items}

        lines = []
        for command, start_time, end_time, status in executions:
            item = command_to_item.get(command)
            name = item.name if item else command
            job_type = item.job_type if item else ""

            time_range = f"{start_time.strftime('%H:%M')}〜{end_time.strftime('%H:%M')}"

            if job_type == "非定型":
                duration = (end_time - start_time).total_seconds() / 60
                lines.append(f"- [非定型] {name} ({time_range}, {duration:.0f}分)")
            else:
                label = theme_repo.status_label(status)
                lines.append(f"- [定型] {name} ({time_range}, {label})")

        imported = "\n".join(lines)
        existing = (self.today_results_field.value or "").strip()
        self.today_results_field.value = f"{existing}\n{imported}".strip() if existing else imported
        self.today_results_field.update()

        ui_log.log_action("日報", "import", "本日実施したジョブ", detail={"件数": len(executions)})
        show_toast(self.page, f"{len(executions)}件のジョブを取り込みました")

    # ========================
    # ✅ 出力
    # ========================
    def _handle_output(self, e: ft.ControlEvent) -> None:
        vault_dir = self.vault_dir_field.value or ""
        person_name = self.person_name_field.value or ""

        if not vault_dir or not person_name:
            show_toast(self.page, "出力先フォルダと個人名を入力してください")
            return

        target_date = self._parse_date()
        if target_date is None:
            show_toast(self.page, "対象日は YYYY-MM-DD 形式で入力してください")
            return

        if report_exists(vault_dir, person_name, target_date):
            show_confirm_dialog(
                self.page,
                "日報の上書き",
                f"{target_date.isoformat()} の日報は既に存在します。上書きしますか？",
                lambda: self._write(vault_dir, person_name, target_date),
            )
        else:
            self._write(vault_dir, person_name, target_date)

    def _write(self, vault_dir: str, person_name: str, target_date: datetime.date) -> None:
        extra_tags = [t.strip() for t in (self.tags_field.value or "").split(",") if t.strip()]

        try:
            path = write_daily_report(
                vault_dir,
                person_name,
                target_date,
                self.today_results_field.value or "",
                self.tomorrow_plan_field.value or "",
                todo_repo.build_todo_markdown(self.todos),
                self.consultation_field.value or "",
                self.contact_field.value or "",
                extra_tags=extra_tags,
            )
        except Exception as ex:
            show_toast(self.page, f"出力に失敗しました: {ex}")
            return

        self.last_written_path = path
        ui_log.log_action("日報", "output", "日報Markdown出力", value=target_date.isoformat())

        tags = build_tags(target_date, extra_tags)
        self.result_text.value = f"出力しました: {path}\nタグ: {', '.join(tags)}"
        self.result_text.update()

        self.open_button.visible = True
        self.open_button.update()

        show_toast(self.page, "Obsidianへ出力しました")

    def _handle_open_in_obsidian(self, e: ft.ControlEvent) -> None:
        if not self.last_written_path:
            return

        uri = "obsidian://open?path=" + urllib.parse.quote(str(self.last_written_path))
        try:
            open_target(uri)
        except Exception as ex:
            show_toast(self.page, f"開けませんでした: {ex}")

    # ========================
    # ✅ TODO（日付をまたいで持ち越す永続リスト）
    # ========================
    def _render_todo_list(self) -> None:
        if self.todos:
            self.todo_list_column.controls = [self._todo_row(t) for t in self.todos]
        else:
            self.todo_list_column.controls = [ft.Text("TODOはありません", italic=True, color=ft.Colors.OUTLINE)]
        safe_update(self.todo_list_column)

    def _todo_row(self, item: todo_repo.TodoItem) -> ft.Control:
        text_style = ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH) if item.done else None
        controls: list[ft.Control] = [
            ft.Icon(
                ft.Icons.CHECK_BOX if item.done else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                size=18,
            ),
            ft.Text(item.subject, style=text_style, expand=True),
        ]
        if item.due_date:
            controls.append(ft.Text(f"期限: {item.due_date}", size=11, color=ft.Colors.OUTLINE))
        controls.append(ft.Text(item.target, size=11, color=ft.Colors.OUTLINE, width=70))
        if not item.done:
            controls.append(
                ft.IconButton(
                    icon=ft.Icons.DONE,
                    tooltip="書き込み先へ記録して完了にする",
                    on_click=self._make_todo_complete_handler(item),
                )
            )
            controls.append(
                ft.IconButton(
                    icon=ft.Icons.EDIT,
                    tooltip="編集",
                    on_click=self._make_todo_edit_handler(item),
                )
            )
        controls.append(
            ft.IconButton(
                icon=ft.Icons.DELETE,
                tooltip="削除",
                icon_color=theme_repo.error_color(),
                on_click=self._make_todo_delete_handler(item),
            )
        )
        return ft.Row(controls=controls, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _handle_add_todo(self, e: ft.ControlEvent) -> None:
        open_add_todo_dialog(self.page, self.todos, self._render_todo_list)

    def _make_todo_edit_handler(self, item: todo_repo.TodoItem):
        def handler(e: ft.ControlEvent) -> None:
            open_edit_todo_dialog(self.page, item, self.todos, self._render_todo_list, self._render_todo_list)

        return handler

    def _make_todo_delete_handler(self, item: todo_repo.TodoItem):
        def handler(e: ft.ControlEvent) -> None:
            def do_delete() -> None:
                self.todos.remove(item)
                todo_repo.save_todos(self.todos)
                ui_log.log_action("日報", "delete", item.subject)
                self._render_todo_list()

            show_confirm_dialog(self.page, "TODOの削除", f"「{item.subject}」を削除しますか？", do_delete)

        return handler

    def _make_todo_complete_handler(self, item: todo_repo.TodoItem):
        def handler(e: ft.ControlEvent) -> None:
            self._complete_todo(item)

        return handler

    def _complete_todo(self, item: todo_repo.TodoItem) -> None:
        vault_dir = self.vault_dir_field.value or ""
        person_name = self.person_name_field.value or ""
        excel_path = self.excel_path_field.value or ""

        if item.target == todo_repo.TARGET_EXCEL:
            if not excel_path:
                show_toast(self.page, "Excel出力先ファイルを設定してください")
                return
        else:
            if not vault_dir or not person_name:
                show_toast(self.page, "出力先フォルダと個人名を設定してください")
                return

        item.done_at = tz_repo.today().isoformat()
        try:
            if item.target == todo_repo.TARGET_EXCEL:
                todo_repo.write_todo_to_excel(item, excel_path)
            else:
                todo_repo.write_todo_to_obsidian(item, vault_dir, person_name)
        except Exception as ex:
            item.done_at = ""
            show_toast(self.page, f"書き込みに失敗しました: {ex}")
            return

        item.done = True
        todo_repo.save_todos(self.todos)
        ui_log.log_action("日報", "complete", item.subject)
        self._render_todo_list()
        show_toast(self.page, "TODOを完了として記録しました")
