import datetime
import signal
import subprocess

import flet as ft
import uuid6

from gui.confirm_dialog import show_confirm_dialog
from gui.item_form_dialog import show_item_form_dialog
from gui.job_editor import open_edit_job_dialog, persist_jobs
from gui.job_history_dialog import show_job_history_dialog
from gui.parameter_dialog import show_parameter_dialog
from gui.safe_update import safe_update
from gui.toast import show_toast
from services.config_loader import JOB_TYPE_FLEXIBLE, TIER_SHARED_KEYS, is_skeleton_job, load_tier_config
from services.execution_engine import (
    ExecutionResult,
    build_result,
    start_process,
    start_process_no_wait,
    stream_process,
)
from services.history_repo import (
    get_job_last_status,
    get_job_run_dates,
    insert_history_with_id,
)
from services.job_classifier import classify_job
from services.run_grid_repo import load_column_widths, save_column_widths
from services import theme_repo, tier_repo, tz_repo, ui_log
from utils.opener import build_stopwatch_url, open_target
from utils.param_parser import extract_params, substitute_params

# 列定義: (見出し, ソート用キー関数 or None)
# キー関数は (no, item, cls, status_label) を受け取り、ソート用の値を返す
COLUMN_DEFS = [
    ("選択", None),
    ("No.", lambda no, item, cls, status: no),
    ("ジョブID", lambda no, item, cls, status: item.job_id),
    ("ジョブ名", lambda no, item, cls, status: item.name),
    ("Tier", lambda no, item, cls, status: (item.tier or "", item.name)),
    ("カテゴリ", lambda no, item, cls, status: (item.category or "", item.name)),
    ("種別", lambda no, item, cls, status: (item.job_type, item.name)),
    ("日次", lambda no, item, cls, status: (not cls.daily, item.name)),
    ("週次", lambda no, item, cls, status: (not bool(cls.weekly_days), item.name)),
    ("月次", lambda no, item, cls, status: (not bool(cls.monthly_days), item.name)),
    ("その他", lambda no, item, cls, status: (not cls.other, item.name)),
    ("マニュアル", lambda no, item, cls, status: (not bool(item.manual), item.name)),
    ("ステータス", lambda no, item, cls, status: (status, item.name)),
    ("履歴", None),
    ("特記事項", lambda no, item, cls, status: (item.note or "", item.name)),
]

RECENT_RUN_DATES_LIMIT = 10
MENU_PATH = "config/menu.toml"
TIER_FILTER_ALL = "全体"  # Tierによる絞り込み（ロードマップ項目6）の「絞り込みなし」選択肢


class RunTab:
    """
    実行タブ。過去の実行実績からジョブを日次/週次/月次/その他に自動分類してグリッド表示し、
    選択したジョブを実行・停止する。左端のチェックボックスで複数選択すると、即実行／時刻指定実行を選べる。
    """

    def __init__(
        self,
        page: ft.Page,
        menu_items,
        on_log,
        on_clear_log,
        on_execution_start,
        on_menu_changed=None,
        scheduler=None,
    ):
        self.page = page
        self.menu_items = menu_items
        self.on_log = on_log                          # (command_id, text, is_error) -> None
        self.on_menu_changed = on_menu_changed or (lambda: None)  # () -> None（右クリックメニューでのジョブ変更後）
        self.on_clear_log = on_clear_log               # () -> None
        self.on_execution_start = on_execution_start   # () -> None（ログタブへの誘導など）
        self.scheduler = scheduler                     # SchedulerService（時刻指定実行で使用）

        self.current_process = None
        self.active_stopwatch_item = None                       # 非定型業務: 現在計測中のジョブ
        self.stopwatch_start_times: dict[str, datetime.datetime] = {}
        self.selected_job_ids: set[str] = set()
        self.running_job_ids: set[str] = set()
        self.scheduled_job_ids: set[str] = set()
        self.ctrl_held = False
        self.sort_column_index: int | None = None
        self.sort_ascending = True
        self.column_widths: dict = load_column_widths()
        self.tier_filter = TIER_FILTER_ALL  # Tierによる絞り込み（ロードマップ項目6）
        self.search_query = ""  # 検索での絞り込み（No./ジョブID/ジョブ名/スケジュール分類）

        self.page.on_keyboard_event = self._handle_keyboard_event

        self.grid_column = ft.Column(scroll=ft.ScrollMode.ALWAYS, expand=True)

        self.selected_label = ft.Text("ジョブ未選択です。一覧から選んでください。")

        self.run_button = ft.Button(
            "実行",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self.execute_selected,
            disabled=True,
            tooltip="選択中のジョブを実行する",
        )
        self.stop_button = ft.Button(
            "停止",
            icon=ft.Icons.STOP,
            on_click=self.cancel_task,
            disabled=True,
            tooltip="実行中のジョブを強制停止する",
        )
        self.spinner = ft.ProgressBar(visible=False, tooltip="実行中です")

        self.batch_run_button = ft.Button(
            "すぐに実行",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self._run_selected_now,
            visible=False,
            tooltip="選択した全ジョブをすぐに実行する（{{param}}が必要なジョブは対象外）",
        )
        self.batch_schedule_button = ft.Button(
            "時刻を指定して実行",
            icon=ft.Icons.SCHEDULE,
            on_click=self._open_schedule_dialog,
            visible=False,
            tooltip="選択した全ジョブを指定時刻に実行する（{{param}}が必要なジョブは対象外）",
        )

        self.search_field = ft.TextField(
            label="検索で絞り込み",
            value="",
            tooltip="ジョブ番号・ジョブID・ジョブ名・スケジュール分類（日次/週次と曜日/月次と日付/その他）で絞り込む",
            width=220,
            on_change=self._handle_search_change,
        )

        self.tier_filter_dropdown = ft.Dropdown(
            label="Tierで絞り込み",
            value=TIER_FILTER_ALL,
            options=[ft.DropdownOption(key=TIER_FILTER_ALL, text=TIER_FILTER_ALL)],
            tooltip="指定したTierのジョブだけを一覧・ログに表示する",
            width=124,  # 従来幅165の3/4（さらに前は220）
            on_select=self._handle_tier_filter_change,
        )

        self.view = ft.Column(
            expand=True,
            controls=[
                # ✅ 左側（ラベル・実行系ボタン）と右側（Tier絞り込み・列幅調整）を
                # 同じ行に収めつつ右側を右寄せするため、外側Rowをalignment=SPACE_BETWEENにし、
                # 左右それぞれを内側Rowにまとめる（外側Rowの直接の子はこの2つの内側Rowのみで
                # expand=Trueは使わない）。左側の内側RowはwrapさせたいのでwrapTrue可だが、
                # 外側Row自体はwrap=Trueにしない（expand=TrueとwrapTrueの組み合わせ不具合を
                # 避けるため。詳細は下記コメント）
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Row(
                            # ✅ wrap=Trueのft.Row（Wrapウィジェット）はexpand=True（Expanded）を
                            # 持つ子を扱えない（実機でジョブ一覧が丸ごとグレーの矩形になる不具合を
                            # 実際に踏んだ）。このRow自体には他の子にexpand=Trueを与えないこと
                            wrap=True,
                            controls=[
                                ft.Text("ジョブ実行一覧", weight=ft.FontWeight.BOLD, size=18),
                                ft.Container(width=24),
                                self.run_button,
                                self.stop_button,
                                self.batch_run_button,
                                self.batch_schedule_button,
                                self.selected_label,
                            ]
                        ),
                        ft.Row(
                            controls=[
                                self.search_field,
                                self.tier_filter_dropdown,
                                ft.IconButton(
                                    icon=ft.Icons.VIEW_COLUMN,
                                    tooltip="各列の表示幅を調整する",
                                    on_click=self._open_column_width_dialog,
                                ),
                            ]
                        ),
                    ]
                ),
                ft.Container(
                    content=self.grid_column,
                    expand=True,
                    border=ft.Border.all(1, ft.Colors.OUTLINE),
                ),
                self.spinner,
            ],
        )

        self.refresh_grid()

    # ========================
    # ✅ Ctrl押下状態の追跡（Ctrl+クリックでの複数選択に使用）
    # ========================
    def _handle_keyboard_event(self, e: ft.KeyboardEvent) -> None:
        self.ctrl_held = e.ctrl

    # ========================
    # ✅ 選択状態
    # ========================
    def _get_selected_items(self) -> list:
        if not self.selected_job_ids:
            return []
        return [item for item in self.menu_items if item.job_id in self.selected_job_ids]

    def _update_action_area(self) -> None:
        selected = self._get_selected_items()
        count = len(selected)

        self.batch_run_button.visible = count >= 2
        self.batch_schedule_button.visible = count >= 2
        self.run_button.visible = count <= 1
        self.stop_button.visible = count <= 1

        if count == 0:
            self.selected_label.value = "ジョブ未選択です。一覧から選んでください。"
            self.run_button.disabled = True
        elif count == 1:
            if selected[0].enabled:
                self.selected_label.value = f"選択中のジョブ: {selected[0].name}"
                self.run_button.disabled = False
            else:
                self.selected_label.value = f"選択中のジョブ: {selected[0].name}（無効化されています）"
                self.run_button.disabled = True
        else:
            self.selected_label.value = f"{count}件のジョブを選択中（左端のチェックボックスで追加/解除）"

        safe_update(self.selected_label)
        safe_update(self.run_button)
        safe_update(self.stop_button)
        safe_update(self.batch_run_button)
        safe_update(self.batch_schedule_button)

    # ========================
    # ✅ ステータス表示
    # ========================
    def _compute_status(self, item) -> tuple[str, bool]:
        """(表示ラベル, 実行中かどうか) を返す"""
        if item.job_id in self.running_job_ids:
            return theme_repo.running_label(), True
        if item.job_id in self.scheduled_job_ids:
            return theme_repo.scheduled_label(), False

        last_status = get_job_last_status(item.command)
        return theme_repo.status_label(last_status, "―"), False

    # ========================
    # ✅ Tierによる絞り込み（ロードマップ項目6）
    # ========================
    def _tier_filter_options(self) -> list[str]:
        tier_config = load_tier_config(MENU_PATH)
        names = [tier_config.get(key, "") for key in TIER_SHARED_KEYS]
        names.append(tier_repo.load_personal_tier_name())
        return [TIER_FILTER_ALL] + [n for n in names if n]

    def _refresh_tier_filter_dropdown(self) -> None:
        options = self._tier_filter_options()
        if self.tier_filter not in options:
            self.tier_filter = TIER_FILTER_ALL

        self.tier_filter_dropdown.options = [
            ft.DropdownOption(key=name, text=name) for name in options
        ]
        self.tier_filter_dropdown.value = self.tier_filter

    def _handle_tier_filter_change(self, e: ft.ControlEvent) -> None:
        self.tier_filter = self.tier_filter_dropdown.value or TIER_FILTER_ALL
        self.refresh_grid()

    # ========================
    # ✅ 検索による絞り込み（No./ジョブID/ジョブ名/スケジュール分類）
    # ========================
    def _handle_search_change(self, e: ft.ControlEvent) -> None:
        self.search_query = (self.search_field.value or "").strip()
        self.refresh_grid()

    @staticmethod
    def _job_search_text(no: int, item, cls) -> str:
        """
        検索対象の文字列をまとめて1つにする。「日次」「週次」「月次」「その他」の
        分類ラベルに加え、週次は曜日（"月"のような略称と"月曜日"のような完全形の両方）、
        月次は日付（"1"と"1日"の両方）を含める。表示欄（daily_text等）とは別に組み立てる
        （表示欄は"〇(月,火)"のような記号込みの表示用テキストのため検索には不向き）
        """
        parts = [str(no), item.job_id, item.name]
        if cls.daily:
            parts.append("日次")
        if cls.weekly_days:
            parts.append("週次")
            parts.extend(cls.weekly_days)
            parts.extend(f"{d}曜日" for d in cls.weekly_days)
        if cls.monthly_days:
            parts.append("月次")
            parts.extend(str(d) for d in cls.monthly_days)
            parts.extend(f"{d}日" for d in cls.monthly_days)
        if cls.other:
            parts.append("その他")
        return " ".join(parts)

    def _col_width(self, label: str) -> int:
        return self.column_widths.get(label, 100)

    def _cell(self, control: ft.Control, label: str) -> ft.Container:
        return ft.Container(width=self._col_width(label), content=control)

    @staticmethod
    def _recent_dates_tooltip(run_dates: list) -> str:
        if not run_dates:
            return "実行履歴がありません"

        recent = sorted(run_dates, reverse=True)[:RECENT_RUN_DATES_LIMIT]
        return "直近の実行日（最新{}件）:\n".format(len(recent)) + "\n".join(
            d.strftime("%Y-%m-%d") for d in recent
        )

    # ========================
    # ✅ グリッド構築（日次/週次/月次/その他 分類、ソート対応）
    # ========================
    def refresh_grid(self) -> None:
        self._refresh_tier_filter_dropdown()
        safe_update(self.tier_filter_dropdown)

        # No.（管理番号）は元の登録順で固定し、ソートしても変わらない（Tier絞り込み時も同じ番号を維持する）
        rows_data = []
        for no, item in enumerate(self.menu_items, start=1):
            if self.tier_filter != TIER_FILTER_ALL and item.tier != self.tier_filter:
                continue

            run_dates = get_job_run_dates(item.command)
            cls = classify_job(item, run_dates)

            if self.search_query and self.search_query.lower() not in self._job_search_text(no, item, cls).lower():
                continue

            status_label, is_running = self._compute_status(item)
            rows_data.append((no, item, cls, status_label, is_running, run_dates))

        if self.sort_column_index is not None:
            key_func = COLUMN_DEFS[self.sort_column_index][1]
            if key_func is not None:
                rows_data.sort(key=lambda r: key_func(r[0], r[1], r[2], r[3]), reverse=not self.sort_ascending)

        rows = []
        for no, item, cls, status_label, is_running, run_dates in rows_data:
            daily_text = "〇" if cls.daily else "―"
            weekly_text = f"〇({','.join(cls.weekly_days)})" if cls.weekly_days else "―"
            monthly_text = f"〇({','.join(str(d) for d in cls.monthly_days)})" if cls.monthly_days else "―"
            other_text = "〇" if cls.other else "―"
            history_tooltip = self._recent_dates_tooltip(run_dates)

            select_tap = self._make_select_handler(item)
            name_color = theme_repo.accent_color() if is_running else None
            name_suffix = "（無効化）" if not item.enabled else "（骨組み）" if is_skeleton_job(item) else ""
            name_text = f"{item.name}{name_suffix}"

            if item.manual:
                manual_cell = ft.IconButton(
                    icon=ft.Icons.MENU_BOOK,
                    tooltip=f"「{item.name}」の業務マニュアルを開く",
                    on_click=self._make_manual_handler(item),
                )
            else:
                manual_cell = ft.Text("―")

            rows.append(
                ft.DataRow(
                    selected=(item.job_id in self.selected_job_ids),
                    cells=[
                        ft.DataCell(
                            self._cell(
                                ft.Checkbox(
                                    value=(item.job_id in self.selected_job_ids),
                                    tooltip=f"「{item.name}」を複数選択に追加/解除する",
                                    on_change=self._make_checkbox_handler(item),
                                ),
                                "選択",
                            )
                        ),
                        ft.DataCell(self._cell(ft.Text(str(no)), "No."), on_tap=select_tap),
                        ft.DataCell(self._cell(ft.Text(item.job_id), "ジョブID"), on_tap=select_tap),
                        ft.DataCell(
                            self._cell(
                                ft.GestureDetector(
                                    content=ft.Text(
                                        name_text,
                                        color=name_color,
                                        weight=ft.FontWeight.BOLD if is_running else None,
                                        italic=not item.enabled or is_skeleton_job(item),
                                    ),
                                    on_secondary_tap=self._make_context_menu_handler(item),
                                    tooltip="右クリックで操作メニューを開く",
                                ),
                                "ジョブ名",
                            ),
                            on_tap=select_tap,
                        ),
                        ft.DataCell(self._cell(ft.Text(item.tier or ""), "Tier"), on_tap=select_tap),
                        ft.DataCell(self._cell(ft.Text(item.category or ""), "カテゴリ"), on_tap=select_tap),
                        ft.DataCell(
                            self._cell(
                                ft.Text(
                                    item.job_type,
                                    tooltip="非定型業務は「実行」で業務記録プラグイン（ストップウォッチ）を起動します",
                                ),
                                "種別",
                            ),
                            on_tap=select_tap,
                        ),
                        ft.DataCell(
                            self._cell(ft.Text(daily_text, tooltip=history_tooltip), "日次"), on_tap=select_tap
                        ),
                        ft.DataCell(
                            self._cell(ft.Text(weekly_text, tooltip=history_tooltip), "週次"), on_tap=select_tap
                        ),
                        ft.DataCell(
                            self._cell(ft.Text(monthly_text, tooltip=history_tooltip), "月次"), on_tap=select_tap
                        ),
                        ft.DataCell(
                            self._cell(ft.Text(other_text, tooltip=history_tooltip), "その他"), on_tap=select_tap
                        ),
                        ft.DataCell(self._cell(manual_cell, "マニュアル")),
                        ft.DataCell(self._cell(ft.Text(status_label), "ステータス"), on_tap=select_tap),
                        ft.DataCell(
                            self._cell(
                                ft.IconButton(
                                    icon=ft.Icons.HISTORY,
                                    tooltip=f"「{item.name}」の実行履歴を見る",
                                    on_click=self._make_history_handler(item),
                                ),
                                "履歴",
                            )
                        ),
                        ft.DataCell(
                            self._cell(
                                ft.Text(item.note or "", max_lines=1, tooltip=item.note or None), "特記事項"
                            ),
                            on_tap=select_tap,
                        ),
                    ],
                )
            )

        columns = []
        for idx, (label, key_func) in enumerate(COLUMN_DEFS):
            columns.append(
                ft.DataColumn(
                    self._cell(ft.Text(label), label),
                    on_sort=self._handle_sort if key_func is not None else None,
                    tooltip=f"{label} でソート" if key_func is not None else None,
                )
            )

        table = ft.DataTable(
            columns=columns,
            rows=rows,
            sort_column_index=self.sort_column_index,
            sort_ascending=self.sort_ascending,
            column_spacing=8,
            horizontal_margin=8,
        )

        self.grid_column.controls = [ft.Row(controls=[table], scroll=ft.ScrollMode.ALWAYS)]
        safe_update(self.grid_column)

    def _handle_sort(self, e: ft.DataColumnSortEvent) -> None:
        self.sort_column_index = e.column_index
        self.sort_ascending = e.ascending
        self.refresh_grid()

    # ========================
    # ✅ 列幅の調整
    # ========================
    def _open_column_width_dialog(self, e: ft.ControlEvent = None) -> None:
        fields = [
            {
                "key": label,
                "label": f"{label} の幅 (px)",
                "type": "text",
                "default": str(self._col_width(label)),
            }
            for label, _ in COLUMN_DEFS
        ]

        def on_submit(values: dict) -> None:
            new_widths = dict(self.column_widths)

            for label, _ in COLUMN_DEFS:
                raw = (values.get(label) or "").strip()
                try:
                    width = int(raw)
                except ValueError:
                    continue
                if width > 0:
                    new_widths[label] = width

            self.column_widths = new_widths
            save_column_widths(self.column_widths)
            self.refresh_grid()

        show_item_form_dialog(self.page, "列幅を調整", fields, None, on_submit)

    def _make_select_handler(self, item):
        def handler(e: ft.ControlEvent) -> None:
            if self.ctrl_held:
                if item.job_id in self.selected_job_ids:
                    self.selected_job_ids.discard(item.job_id)
                else:
                    self.selected_job_ids.add(item.job_id)
            else:
                self.selected_job_ids = {item.job_id}

            self._update_action_area()
            self.refresh_grid()

        return handler

    def _make_checkbox_handler(self, item):
        def handler(e: ft.ControlEvent) -> None:
            if e.control.value:
                self.selected_job_ids.add(item.job_id)
            else:
                self.selected_job_ids.discard(item.job_id)

            self._update_action_area()
            self.refresh_grid()

        return handler

    def _make_history_handler(self, item):
        def handler(e: ft.ControlEvent) -> None:
            show_job_history_dialog(self.page, item.name, item.command)

        return handler

    def _make_manual_handler(self, item):
        def handler(e: ft.ControlEvent) -> None:
            try:
                open_target(item.manual)
            except Exception as ex:
                self.on_log("SYSTEM", f"マニュアルを開けませんでした: {ex}", True)

        return handler

    # ========================
    # ✅ 右クリック操作メニュー（表示位置変更・ジョブ編集・業務マニュアル編集・無効化・削除）
    # ========================
    def _make_context_menu_handler(self, item):
        def handler(e: ft.ControlEvent = None) -> None:
            self._show_job_context_menu(item)

        return handler

    def _job_edit_tier_args(self) -> tuple[dict, str]:
        # 設定タブのキャッシュに依存せず、その時点のTier設定をファイルから読み直す
        # （_tier_filter_options() と同じ方針）
        tier_config = load_tier_config(MENU_PATH)
        personal_tier_name = tier_repo.load_personal_tier_name()
        return tier_config, personal_tier_name

    def _show_job_context_menu(self, item) -> None:
        def close_and(fn):
            def wrapped(ev: ft.ControlEvent = None) -> None:
                self.page.pop_dialog()
                fn()

            return wrapped

        menu = ft.Column(
            tight=True,
            controls=[
                ft.ListTile(
                    title=ft.Text("表示位置の変更"),
                    leading=ft.Icon(ft.Icons.SWAP_VERT),
                    on_click=close_and(lambda: self._open_reorder_dialog(item)),
                ),
                ft.ListTile(
                    title=ft.Text("ジョブ情報の編集"),
                    leading=ft.Icon(ft.Icons.EDIT),
                    on_click=close_and(lambda: self._open_job_edit_dialog(item)),
                ),
                ft.ListTile(
                    title=ft.Text("業務マニュアルの編集"),
                    leading=ft.Icon(ft.Icons.MENU_BOOK),
                    on_click=close_and(lambda: self._open_job_edit_dialog(item, autofocus_key="manual")),
                ),
                ft.ListTile(
                    title=ft.Text("ジョブの有効化" if not item.enabled else "ジョブの無効化"),
                    leading=ft.Icon(ft.Icons.TOGGLE_ON if not item.enabled else ft.Icons.TOGGLE_OFF),
                    on_click=close_and(lambda: self._toggle_job_enabled(item)),
                ),
                ft.ListTile(
                    title=ft.Text("ジョブの削除", color=theme_repo.error_color()),
                    leading=ft.Icon(ft.Icons.DELETE, color=theme_repo.error_color()),
                    on_click=close_and(lambda: self._confirm_delete_job(item)),
                ),
            ],
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"「{item.name}」の操作"),
            content=menu,
            actions=[ft.TextButton("閉じる", on_click=lambda e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dialog)

    def _open_job_edit_dialog(self, item, autofocus_key: str = None) -> None:
        tier_config, personal_tier_name = self._job_edit_tier_args()

        def on_saved() -> None:
            self.refresh_grid()
            self._update_action_area()
            self.on_menu_changed()
            show_toast(self.page, "ジョブを更新しました")

        def on_deleted() -> None:
            self.selected_job_ids.discard(item.job_id)
            self.refresh_grid()
            self._update_action_area()
            self.on_menu_changed()
            show_toast(self.page, "ジョブを削除しました")

        open_edit_job_dialog(
            self.page,
            item,
            self.menu_items,
            tier_config,
            personal_tier_name,
            on_saved,
            on_deleted,
            autofocus_key=autofocus_key,
        )

    def _toggle_job_enabled(self, item) -> None:
        item.enabled = not item.enabled
        persist_jobs(self.menu_items)
        self.refresh_grid()
        self._update_action_area()
        self.on_menu_changed()
        ui_log.log_action("実行", "toggle", item.name, value="有効" if item.enabled else "無効")
        show_toast(self.page, f"「{item.name}」を{'有効化' if item.enabled else '無効化'}しました")

    def _confirm_delete_job(self, item) -> None:
        def on_confirm() -> None:
            self.menu_items.remove(item)
            self.selected_job_ids.discard(item.job_id)
            persist_jobs(self.menu_items)
            self.refresh_grid()
            self._update_action_area()
            self.on_menu_changed()
            ui_log.log_action("実行", "delete", item.name)
            show_toast(self.page, f"「{item.name}」を削除しました")

        show_confirm_dialog(
            self.page,
            "ジョブの削除",
            f"「{item.name}」を削除します。この操作は取り消せません。よろしいですか？",
            on_confirm,
            confirm_label="削除",
        )

    def _open_reorder_dialog(self, item) -> None:
        status_text = ft.Text("")

        def refresh_status() -> None:
            idx = self.menu_items.index(item)
            status_text.value = f"現在の位置: {idx + 1} / {len(self.menu_items)}"
            safe_update(status_text)

        def move(offset: int):
            def handler(e: ft.ControlEvent = None) -> None:
                idx = self.menu_items.index(item)
                new_idx = idx + offset
                if 0 <= new_idx < len(self.menu_items):
                    self.menu_items[idx], self.menu_items[new_idx] = (
                        self.menu_items[new_idx],
                        self.menu_items[idx],
                    )
                    persist_jobs(self.menu_items)
                    self.refresh_grid()
                    self.on_menu_changed()
                    ui_log.log_action("実行", "edit", item.name, detail={"new_index": new_idx + 1})
                    refresh_status()

            return handler

        def handle_close(e: ft.ControlEvent) -> None:
            self.page.pop_dialog()

        refresh_status()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"「{item.name}」の表示位置を変更"),
            content=ft.Column(
                tight=True,
                controls=[
                    status_text,
                    ft.Text("「No.」の並び順のみを変更します（他の項目は変わりません）", size=11),
                    ft.Row(
                        controls=[
                            ft.Button("↑ 上へ", icon=ft.Icons.ARROW_UPWARD, on_click=move(-1)),
                            ft.Button("↓ 下へ", icon=ft.Icons.ARROW_DOWNWARD, on_click=move(1)),
                        ]
                    ),
                ],
            ),
            actions=[ft.TextButton("閉じる", on_click=handle_close)],
        )
        self.page.show_dialog(dialog)

    # ========================
    # ✅ 実行の共通処理（単発実行・一括実行の両方から使う）
    # ========================
    def _execute_and_record(self, item, command, command_id, on_output, on_process_started=None):
        """
        コマンドを実行し、履歴に保存する。戻り値は ExecutionResult（失敗時は None）
        """
        if getattr(item, "is_async", False):
            process = start_process_no_wait(item.command)
            if on_process_started:
                on_process_started(process)

            now = tz_repo.now()
            on_output(command_id, f"{item.command} 起動（非同期）", False)
            on_output(command_id, "return=0 | async", False)

            result = ExecutionResult(item.command, 0, "", "", now, now)
            insert_history_with_id(command_id, result)
            return result

        start_time = tz_repo.now()

        def on_line(line: str) -> None:
            text = line.rstrip()
            is_error = "[ERR]" in text
            on_output(command_id, text, is_error)

        try:
            process = start_process(command)
            if on_process_started:
                on_process_started(process)

            stdout_buf, stderr_buf = stream_process(process, on_line)
            result = build_result(process, item.command, stdout_buf, stderr_buf, start_time)

        except Exception as e:
            on_output("SYSTEM", f"実行エラー: {e}", True)
            return None

        duration = (tz_repo.now() - start_time).total_seconds()
        insert_history_with_id(command_id, result)

        is_error = result.returncode != 0
        on_output(command_id, f"return={result.returncode} | {duration:.2f}s", is_error)
        return result

    # ========================
    # ✅ 単一ジョブの実行（選択1件時）
    # ========================
    def execute_selected(self, e: ft.ControlEvent = None) -> None:
        selected = self._get_selected_items()
        if len(selected) != 1:
            return

        item = selected[0]

        if not item.enabled:
            self.on_log("SYSTEM", f"「{item.name}」は無効化されているため実行できません", True)
            return

        if is_skeleton_job(item):
            self.on_log("SYSTEM", f"「{item.name}」は骨組み状態（コマンド未設定）のため実行できません", True)
            return

        if item.job_type == JOB_TYPE_FLEXIBLE:
            self._start_stopwatch_job(item)
            return

        command = item.command
        params = extract_params(command)

        if params:

            def on_submit(values: dict[str, str]) -> None:
                resolved_command = substitute_params(command, values)
                self.start_execution(item, resolved_command)

            show_parameter_dialog(self.page, params, on_submit)
            return

        self.start_execution(item, command)

    def start_execution(self, item, command: str) -> None:
        ui_log.log_action("実行", "execute", item.name)
        self.run_button.disabled = True
        safe_update(self.run_button)

        self.stop_button.content = "停止"
        self.stop_button.tooltip = "実行中のジョブを強制停止する"

        if getattr(item, "is_async", False):
            self.stop_button.disabled = True
            self.spinner.visible = False
        else:
            self.stop_button.disabled = False
            self.spinner.visible = True
        safe_update(self.stop_button)
        safe_update(self.spinner)

        self.running_job_ids.add(item.job_id)

        self.on_clear_log()
        self.on_execution_start()
        self.refresh_grid()

        self.page.run_thread(self.run_task, item, command)

    def _finish_execution(self, item) -> None:
        self.running_job_ids.discard(item.job_id)
        self.run_button.disabled = False
        self.stop_button.disabled = True
        self.spinner.visible = False
        safe_update(self.run_button)
        safe_update(self.stop_button)
        safe_update(self.spinner)
        self.refresh_grid()

    # ========================
    # ✅ 実行処理（バックグラウンドスレッド、単一選択）
    # ========================
    def run_task(self, item, command: str) -> None:
        command_id = str(uuid6.uuid7())

        def set_process(p) -> None:
            self.current_process = p

        self._execute_and_record(item, command, command_id, self.on_log, on_process_started=set_process)

        self.current_process = None
        self._finish_execution(item)

    # ========================
    # ✅ 非定型業務（業務記録プラグインで計測し、実行履歴へ記録）
    # ========================
    def _start_stopwatch_job(self, item) -> None:
        ui_log.log_action("実行", "launch", item.name)
        try:
            open_target(build_stopwatch_url(item))
        except Exception as ex:
            self.on_log("SYSTEM", f"業務記録プラグインを開けませんでした: {ex}", True)

        self.stopwatch_start_times[item.job_id] = tz_repo.now()
        self.active_stopwatch_item = item
        self.running_job_ids.add(item.job_id)

        self.run_button.disabled = True
        self.stop_button.disabled = False
        self.stop_button.content = "完了として記録"
        self.stop_button.tooltip = "業務記録プラグインでの計測を終え、経過時間を実行履歴へ記録する"
        self.spinner.visible = True
        safe_update(self.run_button)
        safe_update(self.stop_button)
        safe_update(self.spinner)

        self.on_log(
            "SYSTEM",
            f"「{item.name}」の計測を開始しました（業務記録プラグインを開きました）。終わったら「完了として記録」を押してください",
            False,
        )
        self.refresh_grid()

    def _finish_stopwatch_job(self, item) -> None:
        start_time = self.stopwatch_start_times.pop(item.job_id, None)
        end_time = tz_repo.now()
        if start_time is None:
            start_time = end_time

        self.active_stopwatch_item = None

        command_id = str(uuid6.uuid7())
        result = ExecutionResult(item.command, 0, "", "", start_time, end_time)
        insert_history_with_id(command_id, result)

        duration = (end_time - start_time).total_seconds()
        self.on_log(command_id, f"「{item.name}」の非定型業務を実行履歴へ記録しました | {duration:.2f}s", False)

        self.stop_button.content = "停止"
        self.stop_button.tooltip = "実行中のジョブを強制停止する"
        self._finish_execution(item)

    # ========================
    # ✅ 停止処理（単一選択のみ）
    # ========================
    def cancel_task(self, e: ft.ControlEvent) -> None:
        if self.active_stopwatch_item:
            ui_log.log_action("実行", "complete", self.active_stopwatch_item.name)
            self._finish_stopwatch_job(self.active_stopwatch_item)
            return

        if not self.current_process:
            return

        selected = self._get_selected_items()
        item = selected[0] if selected else None
        if item:
            ui_log.log_action("実行", "cancel", item.name)

        try:
            try:
                self.current_process.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                pass

            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self.current_process.pid)],
                capture_output=True,
            )

            self.on_log("SYSTEM", ">>> 強制停止しました", True)

        except Exception as ex:
            self.on_log("SYSTEM", f">>> 停止失敗: {ex}", True)

        finally:
            self.current_process = None
            if item:
                self._finish_execution(item)
            else:
                self.refresh_grid()

    # ========================
    # ✅ 一括実行の対象外判定（{{param}}必須・非定型業務は個別実行のみ）
    # ========================
    def _batch_skip_reason(self, item) -> str | None:
        if not item.enabled:
            return "無効化されているため"
        if is_skeleton_job(item):
            return "骨組み状態（コマンド未設定）のため"
        if item.job_type == JOB_TYPE_FLEXIBLE:
            return "非定型業務のため"
        if extract_params(item.command):
            return "パラメータ入力が必要なため"
        return None

    def _split_batch_items(self, items: list, action_label: str) -> list:
        runnable = []
        for it in items:
            reason = self._batch_skip_reason(it)
            if reason:
                hint = "" if not it.enabled else "（個別に実行してください）"
                self.on_log(
                    "SYSTEM",
                    f"「{it.name}」は{reason}{action_label}をスキップしました{hint}",
                    True,
                )
            else:
                runnable.append(it)
        return runnable

    # ========================
    # ✅ 複数選択: すぐに実行（並行実行、パラメータ入力が必要・非定型のジョブは対象外）
    # ========================
    def _run_selected_now(self, e: ft.ControlEvent = None) -> None:
        items = self._get_selected_items()
        runnable = self._split_batch_items(items, "一括実行")

        if not runnable:
            return

        ui_log.log_action(
            "実行", "execute", "一括実行", detail={"件数": len(runnable)}
        )

        for it in runnable:
            self.running_job_ids.add(it.job_id)

        self.on_execution_start()
        self.refresh_grid()

        for it in runnable:
            self.page.run_thread(self._run_batch_item, it)

    def _run_batch_item(self, item) -> None:
        command_id = str(uuid6.uuid7())
        self._execute_and_record(item, item.command, command_id, self.on_log)
        self.running_job_ids.discard(item.job_id)
        self.refresh_grid()

    # ========================
    # ✅ 複数選択: 時刻を指定して実行
    # ========================
    def _open_schedule_dialog(self, e: ft.ControlEvent = None) -> None:
        fields = [
            {
                "key": "time",
                "label": "実行時刻 (HH:MM。過ぎていれば翌日になります)",
                "type": "text",
                "default": tz_repo.now().strftime("%H:%M"),
            },
        ]

        def on_submit(values: dict) -> None:
            self._schedule_selected(values.get("time", ""))

        show_item_form_dialog(self.page, "予定時刻を指定して実行", fields, None, on_submit)

    def _schedule_selected(self, time_str: str) -> None:
        if not self.scheduler:
            self.on_log("SYSTEM", "スケジューラが利用できないため予定実行を登録できません", True)
            return

        try:
            hour, minute = (int(x) for x in time_str.strip().split(":"))
            run_at = tz_repo.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            if run_at <= tz_repo.now():
                run_at += datetime.timedelta(days=1)
        except (ValueError, AttributeError):
            self.on_log("SYSTEM", f"時刻の形式が不正です: {time_str}", True)
            return

        items = self._get_selected_items()
        runnable = self._split_batch_items(items, "予定実行")

        if runnable:
            ui_log.log_action(
                "実行", "execute", "時刻指定実行", value=time_str, detail={"件数": len(runnable)}
            )

        for it in runnable:
            self.scheduled_job_ids.add(it.job_id)
            self.scheduler.run_once_at(
                it,
                run_at,
                on_start=self._make_batch_started(it),
                on_finish=self._make_batch_finished(it),
            )

        self.refresh_grid()

        if runnable:
            self.on_log(
                "SYSTEM",
                f"{len(runnable)}件のジョブを {run_at.strftime('%Y-%m-%d %H:%M')} に実行予定として登録しました",
                False,
            )

    def _make_batch_started(self, item):
        def handler() -> None:
            self.scheduled_job_ids.discard(item.job_id)
            self.running_job_ids.add(item.job_id)
            self.refresh_grid()

        return handler

    def _make_batch_finished(self, item):
        def handler() -> None:
            self.running_job_ids.discard(item.job_id)
            self.refresh_grid()

        return handler
