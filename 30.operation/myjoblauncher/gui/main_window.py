import os
import time

import flet as ft

from gui.daily_report_tab import DailyReportTab
from gui.help_tab import HelpTab
from gui.links_tab import LinksTab
from gui.log_tab import LogTab
from gui.notice_popup import check_and_show_urgent_notices
from gui.portal_tab import PortalTab
from gui.run_tab import RunTab
from gui.settings_tab import SettingsTab
from gui.tips_tab import TipsTab
from gui.tools_tab import ToolsTab
from services import app_name_repo, applog, theme_repo, ui_log
from services.startup_timer import startup_step

# (アイコン, ラベル) の並びが左メニュー・コンテンツの表示順を兼ねる
NAV_DESTINATIONS = [
    (ft.Icons.DASHBOARD, "ホーム"),
    (ft.Icons.PLAY_ARROW, "実行"),
    (ft.Icons.SETTINGS, "設定"),
    (ft.Icons.ARTICLE, "ログ"),
    (ft.Icons.BUILD, "ツール"),
    (ft.Icons.LINK, "リンク"),
    (ft.Icons.EDIT_CALENDAR, "日報"),
    (ft.Icons.HELP, "ヘルプ"),
    (ft.Icons.TIPS_AND_UPDATES, "TIPS"),
]
PORTAL_TAB_INDEX = 0
LOG_TAB_INDEX = 3

# ✅ 【一時的なデバッグ用】起動性能の最適化はまだこれから（ユーザーからの要望:
# 「性能改善すべき箇所は今後出てくると思いますので、初期の段階では...5秒重しを
# かけておきましょう」）。スプラッシュ→本画面への切替直前にこの秒数だけ待つことで、
# スプラッシュ画面を目視確認しやすくする（現状は最速で1〜2秒程度で切り替わってしまい、
# スクリーンショット等での確認が難しいため）。0にすれば即座に無効化できる
SPLASH_MIN_DELAY_SECONDS = 5.0


class MainWindow:
    """
    アプリ全体の画面構成（左メニュー: ホーム/実行/設定/ログ/ツール/リンク/日報/ヘルプ/TIPS）を組み立て、
    各タブ間の連携（コールバック配線）を担う。個々のタブの実装は gui/*_tab.py を参照。
    """

    def __init__(
        self,
        page: ft.Page,
        menu_items,
        scheduler=None,
        splash_view: ft.Control = None,
        verbose: bool = False,
    ):
        """
        `splash_view`: main.py側で先に表示している起動スプラッシュ（あれば）。
        本画面の準備ができたタイミングで、これも一緒に非表示にする（詳細は下記コメント）。
        `verbose`: `--verbose`時、各タブの構築にかかった時間をコンソールへ出力する
        （ユーザーからの要望: `--web`の起動が`--gui`より体感遅い原因の切り分け用）
        """
        self.page = page
        self.menu_items = menu_items

        os.makedirs("logs", exist_ok=True)
        os.makedirs("config", exist_ok=True)

        page.title = "myJobLauncher"
        theme_repo.apply_theme(page)

        with startup_step("Portalタブ構築", verbose):
            self.portal_tab = PortalTab(page)
        with startup_step("Logタブ構築", verbose):
            self.log_tab = LogTab(page)
        applog.register_sink(self._handle_applog_sink)
        with startup_step("Runタブ構築", verbose):
            self.run_tab = RunTab(
                page,
                self.menu_items,
                on_log=self._handle_run_log,
                on_clear_log=self.log_tab.clear,
                on_execution_start=self._switch_to_log_tab,
                on_menu_changed=self._on_menu_changed,
                scheduler=scheduler,
            )
        with startup_step("Settingsタブ構築", verbose):
            self.settings_tab = SettingsTab(page, self.menu_items, on_menu_changed=self._on_menu_changed)
        with startup_step("Toolsタブ構築", verbose):
            self.tools_tab = ToolsTab(page)
        with startup_step("Linksタブ構築", verbose):
            self.links_tab = LinksTab(page)
        with startup_step("DailyReportタブ構築", verbose):
            self.daily_report_tab = DailyReportTab(page, self.menu_items)
        with startup_step("Helpタブ構築", verbose):
            self.help_tab = HelpTab(page)
        with startup_step("Tipsタブ構築", verbose):
            self.tips_tab = TipsTab(page)

        self.views = [
            self.portal_tab.view,
            self.run_tab.view,
            self.settings_tab.view,
            self.log_tab.view,
            self.tools_tab.view,
            self.links_tab.view,
            self.daily_report_tab.view,
            self.help_tab.view,
            self.tips_tab.view,
        ]

        display_name = app_name_repo.load_display_name()
        self.nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=88,
            min_extended_width=160,
            leading=(
                ft.Container(
                    padding=ft.Padding.only(top=16, bottom=16, left=4, right=4),
                    content=ft.Text(
                        display_name,
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER,
                    ),
                )
                if display_name
                else None
            ),
            destinations=[
                ft.NavigationRailDestination(icon=icon, label=label)
                for icon, label in NAV_DESTINATIONS
            ],
            on_change=self._handle_nav_change,
        )

        self.content_area = ft.Container(content=self.views[0], expand=True, padding=12)

        # ✅ 起動時のちらつき防止: root_row（visible=False）をpage.add()した直後は画面に
        # 何も追加されないので、main.py側のsplash_viewがまだ画面に残っていれば、
        # ここまでの構築中もユーザーには「起動中」表示が見え続ける。各タブの初期描画・
        # レイアウト確定が済むまで非表示のままにしておき、準備が整ってから一気に表示へ
        # 切り替えることで、各タブが順に描画されていくような不自然な見え方（ちらつき）を
        # 解消する（ユーザーからの要望）
        self.root_row = ft.Row(
            expand=True,
            visible=False,
            controls=[
                self.nav_rail,
                ft.VerticalDivider(width=1),
                self.content_area,
            ],
        )
        with startup_step("root_rowのpage.add()（クライアントへの初回送信）", verbose):
            page.add(self.root_row)

        # ✅ ページ追加（マウント）後でないとWebViewへload_html()できないため、ここで初回描画する
        with startup_step("PortalTab.on_shown()", verbose):
            self.portal_tab.on_shown()

        # ✅ 【一時的なデバッグ用】SPLASH_MIN_DELAY_SECONDS参照。実際の切替処理とは別ステップに
        # しておくことで、verboseログ上で「本物の切替コスト」と「意図的な待機」を混同しない
        if SPLASH_MIN_DELAY_SECONDS > 0:
            with startup_step(f"デバッグ用待機（SPLASH_MIN_DELAY_SECONDS={SPLASH_MIN_DELAY_SECONDS}秒）", verbose):
                time.sleep(SPLASH_MIN_DELAY_SECONDS)

        # ✅ ここまでで初期画面の組み立てが完了。スプラッシュ（あれば）を消して
        # 本画面を一気に表示する
        with startup_step("スプラッシュ→本画面への切替page.update()", verbose):
            if splash_view is not None:
                splash_view.visible = False
            self.root_row.visible = True
            page.update()

        # ✅ 起動時、公開日時が来ている緊急通知があればポップアップ表示する
        check_and_show_urgent_notices(page, self._go_to_portal_notices)

    # ========================
    # ✅ 左メニューの切替
    # ========================
    def _handle_nav_change(self, e: ft.ControlEvent) -> None:
        index = self.nav_rail.selected_index
        ui_log.log_action("(左メニュー)", "tab", NAV_DESTINATIONS[index][1])
        self._show_tab(index)

    def _show_tab(self, index: int) -> None:
        self.nav_rail.selected_index = index
        self.content_area.content = self.views[index]
        self.nav_rail.update()
        self.content_area.update()

        if index == PORTAL_TAB_INDEX:
            self.portal_tab.on_shown()

    # ========================
    # ✅ 緊急通知ポップアップの「お知らせ画面へ」
    # ========================
    def _go_to_portal_notices(self) -> None:
        # お知らせメッセージはホームタブの先頭に表示されるため、タブを表示するだけでよい
        self._show_tab(PORTAL_TAB_INDEX)

    # ========================
    # ✅ ジョブ実行開始時、ログを確認しやすいようログタブへ切替
    # ========================
    def _switch_to_log_tab(self) -> None:
        self._show_tab(LOG_TAB_INDEX)

    # ========================
    # ✅ ジョブ設定変更時、実行タブ・設定タブ双方を再読込
    # ========================
    def _on_menu_changed(self) -> None:
        self.run_tab.refresh_grid()
        self.settings_tab.refresh_job_list()

    # ========================
    # ✅ 運用ログ（services/applog.py）
    # ========================
    def _handle_applog_sink(self, line: str, level: str) -> None:
        """applog.log()からの画面表示要求を「ログ」タブへ橋渡しする"""
        self.log_tab.append_line(line, level)

    def _handle_run_log(self, command_id: str, text: str, is_error: bool) -> None:
        """
        RunTabの従来の`on_log(command_id, text, is_error)`呼び出しを`applog.log()`へ変換する。
        gui/run_tab.py内の多数の`self.on_log(...)`呼び出し箇所はこのシグネチャのまま変更不要
        """
        level = "ERROR" if is_error else "INFO"
        cid = None if command_id == "SYSTEM" else command_id
        applog.log(level, text, func_name="RunTab", command_id=cid)
