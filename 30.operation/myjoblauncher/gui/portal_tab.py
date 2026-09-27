import webbrowser

import flet as ft

from gui.safe_update import safe_update
from services import portal_repo, sync_service, theme_repo, tz_repo, ui_log
from utils.markdown_render import build_markdown_view
from utils.mermaid_view import extract_mermaid_blocks, open_mermaid_in_browser

MENU_PATH = "config/menu.toml"

MIN_NOTICES_HEIGHT = 80
MAX_NOTICES_HEIGHT = 800


class PortalTab:
    """
    ホームタブ。お知らせメッセージ・ホーム本文をMarkdownとして表示する。
    `ft.Markdown`（`flutter_markdown`）はリンクのホバー時にツールチップを表示する機能を持たないため、
    `utils/markdown_render.py`の自前レンダラー（`markdown-it-py`で解析し`ft.TextSpan`ツリーに変換）で
    描画する。本文中のリンクはクリックすると既定のブラウザで開き、マウスを乗せるとカーソル追従の
    吹き出しでリンク先URLを表示する（`utils.markdown_render.build_markdown_view`内部で完結）。
    GFM拡張（表・打消し線等）は自前レンダラーでは非対応（`docs/help.md`参照）。
    MermaidJSはこのレンダラーでも描画できないため、含まれていれば「図をブラウザで表示」ボタンで
    別途確認できるようにする（`utils/mermaid_view.py`）。
    埋め込みWebView（`flet_webview`）はデスクトップ（Windows/Linux）でまだ未対応（WebView2ベースの
    対応待ち）のため、対応されるまでの暫定方針としてこの方式にしている（CLAUDE.mdの注意事項を参照）。
    タブ表示のたびに共有マスター（config/home.toml）の新しいバージョンが無いか確認し、あれば
    ダウンロードしてキャッシュ（ローカルのconfig/home.toml）を更新してから再描画する。
    お知らせメッセージは1件ずつ見出しクリックで折りたたみ／展開でき（`_collapsed_notice_ids`、
    再起動やタブ切替では保持しないランタイムのみの状態）、表示エリア自体の高さも下端のハンドルを
    ドラッグして調整できる（`_notices_height`）。この高さはドラッグ終了時に`config/app.toml`の
    `portal_notices_height`キーへ保存し、次回起動時にも引き継がれる（`services/portal_repo.py`の
    `load_notices_height()`/`save_notices_height()`。config/home.toml〈共有マスター同期対象〉には
    含めない、このPCだけのローカル表示設定）
    """

    def __init__(self, page: ft.Page):
        self.page = page
        self._notices: list = []
        self._portal_config = portal_repo.PortalConfig()
        self._collapsed_notice_ids: set[str] = set()
        self._notices_height = portal_repo.load_notices_height()

        self.spinner = ft.ProgressRing(width=18, height=18, visible=False, tooltip="最新の情報を確認しています")
        self.refresh_button = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="最新の情報に更新する",
            on_click=self._handle_refresh_click,
        )
        self.mermaid_button = ft.Button(
            "図をブラウザで表示",
            icon=ft.Icons.OPEN_IN_BROWSER,
            tooltip="このページ内のMermaid図を既定のブラウザで表示する（インターネット接続が必要です）",
            visible=False,
            on_click=self._handle_open_mermaid,
        )

        # ✅ お知らせメッセージ（折りたたみ可能な行の一覧、固定高さ＋ドラッグでリサイズ可能）
        self.notices_column = ft.Column(scroll=ft.ScrollMode.ALWAYS, spacing=8)
        self.notices_area = ft.Container(
            content=self.notices_column,
            height=self._notices_height,
            padding=8,
            border=ft.Border.all(1, ft.Colors.OUTLINE),
        )
        self.resize_handle = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_ROW,
            on_vertical_drag_update=self._handle_resize_drag,
            on_vertical_drag_end=self._handle_resize_end,
            content=ft.Container(
                height=10,
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(ft.Icons.DRAG_HANDLE, size=16, color=ft.Colors.OUTLINE),
            ),
        )

        # ✅ ホーム本文（`render()`のたびに`content`を差し替える）
        self.portal_body_container = ft.Container()

        self.content_column = ft.Column(
            scroll=ft.ScrollMode.ALWAYS,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("お知らせメッセージ", weight=ft.FontWeight.BOLD, size=16, expand=True),
                        ft.IconButton(
                            icon=ft.Icons.UNFOLD_LESS,
                            tooltip="全て折りたたむ",
                            on_click=self._handle_collapse_all,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.UNFOLD_MORE,
                            tooltip="全て展開する",
                            on_click=self._handle_expand_all,
                        ),
                    ]
                ),
                self.notices_area,
                self.resize_handle,
                ft.Divider(),
                ft.Text("よく使うサービス", weight=ft.FontWeight.BOLD, size=16),
                self.portal_body_container,
            ],
        )

        self.view = ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("ホーム", weight=ft.FontWeight.BOLD, size=18, expand=True),
                        self.spinner,
                        self.refresh_button,
                        self.mermaid_button,
                    ]
                ),
                ft.Container(
                    content=self.content_column,
                    expand=True,
                    padding=8,
                    border=ft.Border.all(1, ft.Colors.OUTLINE),
                ),
            ],
        )

        self.render()  # 起動直後もローカルキャッシュの内容をすぐ表示する

    # ========================
    # ✅ タブ表示のたびに呼ばれる（MainWindow._show_tab から）
    # ========================
    def on_shown(self) -> None:
        self._check_and_refresh()

    def _handle_refresh_click(self, e: ft.ControlEvent) -> None:
        self._check_and_refresh()

    def _check_and_refresh(self) -> None:
        self.spinner.visible = True
        safe_update(self.spinner)
        self.page.run_thread(self._background_refresh)

    def _background_refresh(self) -> None:
        # ✅ 起動時・タブ表示のたびに毎回ここへ来るが、実際に内容が変わっていない場合（＝共有マスターに
        # 更新が無い、ローカル専用お知らせも増えていない、という大多数のケース）まで毎回`render()`
        # し直すと、キャッシュ表示→（一瞬後に）同じ内容への再描画、という無意味な「画面の切り替わり」が
        # 起動のたびに見えてしまい、ユーザーに「何が起きたのか」という不安を与える不具合を実機で
        # 確認した。そのため、ダウンロード前後で表示内容のスナップショットを比較し、実際に変化があった
        # 場合のみ`render()`する（変化が無ければスピナーの点滅だけで済む）
        before = self._content_snapshot()
        try:
            sync_service.auto_download_portal(MENU_PATH, portal_repo.PORTAL_PATH)
        except Exception:
            pass  # ローカルのキャッシュ（既存のconfig/home.toml）をそのまま使う

        self.spinner.visible = False
        safe_update(self.spinner)

        if self._content_snapshot() != before:
            self.render()

    def _content_snapshot(self) -> tuple:
        """`render()`が表示に使う内容（お知らせ全件＋ホーム本文）を比較可能なタプルにする"""
        notices = self._system_notices() + portal_repo.load_notices()
        notice_tuples = tuple(
            (n.notice_id, n.title, n.content, n.publish_at, n.duration_days, n.urgent) for n in notices
        )
        return (notice_tuples, portal_repo.load_portal_config().content)

    # ========================
    # ✅ リンク・Mermaid
    # ========================
    def _handle_tap_link(self, url: str) -> None:
        if url:
            webbrowser.open(url)

    def _handle_open_mermaid(self, e: ft.ControlEvent) -> None:
        ui_log.log_action("ホーム", "launch", "Mermaid図")
        open_mermaid_in_browser(self._combined_text(), "ホーム")

    def _combined_text(self) -> str:
        visible = self._visible_notices()
        parts = [n.content for n in visible]
        parts.append(self._portal_config.content)
        return "\n\n".join(parts)

    # ========================
    # ✅ お知らせメッセージの折りたたみ・リサイズ
    # ========================
    def _visible_notices(self) -> list:
        return portal_repo.visible_notices(self._notices, tz_repo.now())

    def _make_toggle_handler(self, notice_id: str):
        def handler(e: ft.ControlEvent) -> None:
            if notice_id in self._collapsed_notice_ids:
                self._collapsed_notice_ids.discard(notice_id)
            else:
                self._collapsed_notice_ids.add(notice_id)
            self._render_notices()

        return handler

    def _handle_collapse_all(self, e: ft.ControlEvent) -> None:
        self._collapsed_notice_ids = {n.notice_id for n in self._visible_notices()}
        ui_log.log_action("ホーム", "click", "全て折りたたむ")
        self._render_notices()

    def _handle_expand_all(self, e: ft.ControlEvent) -> None:
        self._collapsed_notice_ids.clear()
        ui_log.log_action("ホーム", "click", "全て展開する")
        self._render_notices()

    def _handle_resize_drag(self, e: ft.DragUpdateEvent) -> None:
        delta = e.primary_delta or 0
        self._notices_height = max(MIN_NOTICES_HEIGHT, min(MAX_NOTICES_HEIGHT, self._notices_height + delta))
        self.notices_area.height = self._notices_height
        safe_update(self.notices_area)

    def _handle_resize_end(self, e: ft.DragEndEvent) -> None:
        # ドラッグ中は毎フレーム保存せず、操作が終わったタイミングで1回だけ保存する
        portal_repo.save_notices_height(self._notices_height)
        ui_log.log_action("ホーム", "resize", "お知らせ表示エリア高さ", value=self._notices_height)

    # ========================
    # ✅ 描画（ローカルにキャッシュ済みのconfig/home.tomlの内容をそのまま表示）
    # ========================
    def _notice_card(self, notice: portal_repo.NoticeItem) -> ft.Container:
        urgent_mark = "🚨 " if notice.urgent else ""
        collapsed = notice.notice_id in self._collapsed_notice_ids

        header = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.CLICK,
            on_tap=self._make_toggle_handler(notice.notice_id),
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.EXPAND_MORE if collapsed else ft.Icons.EXPAND_LESS, size=18),
                    ft.Text(f"{urgent_mark}{notice.title}", weight=ft.FontWeight.BOLD, size=15, expand=True),
                    ft.Text(notice.publish_at or "（即時公開）", size=11, color=ft.Colors.OUTLINE),
                ]
            ),
        )

        controls: list[ft.Control] = [header]
        if not collapsed:
            controls.append(build_markdown_view(notice.content, self._handle_tap_link))

        return ft.Container(
            padding=12,
            border=ft.Border.all(2 if notice.urgent else 1, theme_repo.error_color() if notice.urgent else ft.Colors.OUTLINE),
            border_radius=8,
            content=ft.Column(spacing=4, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=controls),
        )

    def _render_notices(self) -> None:
        visible = self._visible_notices()
        if visible:
            self.notices_column.controls = [self._notice_card(n) for n in visible]
        else:
            self.notices_column.controls = [ft.Text("お知らせはありません", italic=True, color=ft.Colors.OUTLINE)]
        safe_update(self.notices_column)

    def _system_notices(self) -> list:
        """
        アプリ自身が生成するローカル専用お知らせ（config/system_notices.toml、新バージョン検知・
        適用完了等）。共有お知らせより手前に並べて目に留まりやすくする。notice_idの採番体系は
        共有お知らせ（config/home.toml）と独立しているため、衝突しないようプレフィックスを付ける
        """
        items = portal_repo.load_system_notices()
        for item in items:
            item.notice_id = f"sys-{item.notice_id}"
        return items

    def render(self) -> None:
        self._notices = self._system_notices() + portal_repo.load_notices()
        self._portal_config = portal_repo.load_portal_config()

        self._render_notices()

        self.portal_body_container.content = build_markdown_view(
            self._portal_config.content or "*（ホームの内容は未設定です）*",
            self._handle_tap_link,
        )
        safe_update(self.portal_body_container)

        self.mermaid_button.visible = bool(extract_mermaid_blocks(self._combined_text()))
        safe_update(self.mermaid_button)
