import os
import re
from datetime import timedelta

import flet as ft

from gui.safe_update import safe_update
from services import log_format_repo, search_history_repo, theme_repo, tz_repo

_LEVEL_PATTERN = re.compile(r"\|\s*(ERROR|WARNING|NORMAL|INFO)\s*\|")

SEARCH_HISTORY_KEY = "log_search_history"

RANGE_DAILY = "日別"
RANGE_WEEKLY = "週別"
RANGE_MONTHLY = "月別"
RANGES = (RANGE_DAILY, RANGE_WEEKLY, RANGE_MONTHLY)

LEVEL_FILTER_ALL = "ALL"
LEVEL_FILTER_OPTIONS = (LEVEL_FILTER_ALL, "INFO", "NORMAL", "WARNING", "ERROR")
LEVEL_FILTER_LABELS = {
    LEVEL_FILTER_ALL: "すべて",
    "INFO": "INFOのみ",
    "NORMAL": "NORMALのみ",
    "WARNING": "WARNINGのみ",
    "ERROR": "ERRORのみ",
}


class LogTab:
    """
    実行ログ表示タブ。コピー・クリアアイコンを備える。
    全行を1つの ft.Text(spans=[...]) にまとめて描画することで、
    複数行にまたがる任意範囲のテキスト選択・コピーができるようにする
    （ft.ListView に行ごとの ft.Text を並べる方式では、選択がコントロールごとに
    独立してしまい複数行をまたいだドラッグ選択ができないため）。

    表示中の全行は self.lines（(line, level)のタプル）に保持し、self.log_spans は
    そこから範囲（日別/週別/月別）・種別・検索キーワードでフィルタした「見た目」を
    保持するだけにしている。フィルタが変わったときだけ self.lines から作り直す
    （_rebuild_view）ことで、ライブ追記（append_line）自体は従来通りO(1)の追記のまま
    に保っている（フィルタ変更のたびに全件再構築するのは操作頻度が低いため許容できる）
    """

    def __init__(self, page: ft.Page):
        self.page = page
        self.lines: list[tuple[str, str]] = []
        self.range_mode = RANGE_DAILY
        self.level_filter = LEVEL_FILTER_ALL
        self.search_query = ""
        self.search_history: list[str] = search_history_repo.load_history(SEARCH_HISTORY_KEY)

        self.log_spans: list[ft.TextSpan] = []
        self.log_text = ft.Text(spans=self.log_spans, selectable=True, no_wrap=True)

        # ✅ 横スクロール対応: 内側のft.Row（scroll=ALWAYS、主軸=水平）でlog_textを包み、
        # no_wrap=Trueの長い行がラップされず、代わりにRowが横スクロールで見せる。
        # 外側のft.Column（scroll=ALWAYS、主軸=垂直）が従来通り縦スクロールを担う
        self.log_row = ft.Row(controls=[self.log_text], scroll=ft.ScrollMode.ALWAYS)
        self.log_view = ft.Column(
            controls=[self.log_row],
            scroll=ft.ScrollMode.ALWAYS,
            expand=True,
        )

        self.range_row = self._build_range_row()
        self.range_container = ft.Row(controls=[self.range_row])

        self.search_button = ft.IconButton(
            icon=ft.Icons.SEARCH,
            tooltip="文字列で検索する",
            on_click=self._open_search_dialog,
        )

        self.level_dropdown = ft.Dropdown(
            value=self.level_filter,
            options=[
                ft.DropdownOption(key=k, text=LEVEL_FILTER_LABELS[k]) for k in LEVEL_FILTER_OPTIONS
            ],
            dense=True,
            width=130,
            tooltip="表示する区分を絞り込む",
            on_select=self._handle_level_change,
        )

        self.view = ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("実行ログ", weight=ft.FontWeight.BOLD),
                        ft.Container(width=16),
                        self.range_container,
                        ft.Container(width=8),
                        self.search_button,
                        ft.Container(width=8),
                        self.level_dropdown,
                        ft.Container(expand=True),
                        ft.IconButton(
                            icon=ft.Icons.COPY,
                            tooltip="表示中のログをすべてコピーする",
                            on_click=self._handle_copy,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_SWEEP,
                            tooltip="ログ表示をクリアする（保存済みの実行履歴・ログファイルは削除されません）",
                            on_click=self._handle_clear,
                        ),
                    ]
                ),
                ft.Container(
                    content=self.log_view,
                    expand=True,
                    border=ft.Border.all(1, ft.Colors.OUTLINE),
                    padding=4,
                ),
            ],
        )

        self._load_range_log()

    # ========================
    # ✅ 範囲（日別/週別/月別）
    # ========================
    def _build_range_row(self) -> ft.Row:
        return ft.Row(
            spacing=4,
            controls=[
                ft.TextButton(
                    mode,
                    tooltip=f"{mode}で表示する",
                    style=ft.ButtonStyle(
                        color=theme_repo.accent_color() if mode == self.range_mode else None,
                    ),
                    on_click=lambda e, mode=mode: self._handle_range_change(mode),
                )
                for mode in RANGES
            ],
        )

    def _handle_range_change(self, mode: str) -> None:
        self.range_mode = mode
        self.range_row = self._build_range_row()
        self.range_container.controls = [self.range_row]
        safe_update(self.range_container)
        self._load_range_log()

    def _dates_for_range(self):
        today = tz_repo.today()
        if self.range_mode == RANGE_WEEKLY:
            start = today - timedelta(days=today.weekday())
        elif self.range_mode == RANGE_MONTHLY:
            start = today.replace(day=1)
        else:
            start = today

        dates = []
        d = start
        while d <= today:
            dates.append(d)
            d += timedelta(days=1)
        return dates

    def _load_range_log(self) -> None:
        """
        選択中の範囲（日別=当日のみ/週別=週の月曜〜当日/月別=1日〜当日）に該当する
        logs/app-YYYYMMDD.log をすべて読み込み直す。存在しない日のファイルは無視する
        （運用ログはベストエフォートの補助機能のため、失敗してもタブ表示は妨げない）
        """
        self.lines.clear()
        try:
            fmt = log_format_repo.load_format()
            log_dir = fmt["log_dir"]
            for d in self._dates_for_range():
                path = os.path.join(log_dir, f"app-{d:%Y%m%d}.log")
                if not os.path.exists(path):
                    continue
                with open(path, "r", encoding="utf-8") as f:
                    for raw in f:
                        text = raw.rstrip("\n")
                        if text.strip():
                            self.lines.append((text, self._parse_level(text)))
        except Exception:
            pass

        self._rebuild_view()

    @staticmethod
    def _parse_level(line: str) -> str:
        """既定フォーマットの `...| {level}| ...` 部分から区分を抜き出す（見つからなければ空文字）"""
        m = _LEVEL_PATTERN.search(line)
        return m.group(1) if m else ""

    # ========================
    # ✅ 種別・検索での絞り込み
    # ========================
    def _passes_filters(self, line: str, level: str) -> bool:
        if self.level_filter != LEVEL_FILTER_ALL and level != self.level_filter:
            return False
        if self.search_query and self.search_query.lower() not in line.lower():
            return False
        return True

    def _handle_level_change(self, e: ft.ControlEvent) -> None:
        self.level_filter = e.control.value or LEVEL_FILTER_ALL
        self._rebuild_view()

    def _open_search_dialog(self, e: ft.ControlEvent) -> None:
        field = ft.TextField(
            label="検索キーワード（大文字小文字は区別しません、空欄で解除）",
            value=self.search_query,
            autofocus=True,
            width=320,
        )

        def handle_pick(ev: ft.ControlEvent, query: str) -> None:
            field.value = query
            field.update()

        history_controls = (
            [
                ft.TextButton(query, on_click=lambda ev, query=query: handle_pick(ev, query))
                for query in self.search_history
            ]
            if self.search_history
            else [ft.Text("履歴はありません", italic=True, size=12)]
        )

        def handle_search(ev: ft.ControlEvent) -> None:
            query = (field.value or "").strip()
            self.page.pop_dialog()
            self.search_query = query
            self.search_history = search_history_repo.add_to_history(query, self.search_history)
            search_history_repo.save_history(SEARCH_HISTORY_KEY, self.search_history)
            self._update_search_button()
            self._rebuild_view()

        def handle_cancel(ev: ft.ControlEvent) -> None:
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("ログ検索"),
            content=ft.Column(
                controls=[
                    field,
                    ft.Text("検索履歴（最大20件、選ぶと入力欄へ反映）", size=12, weight=ft.FontWeight.BOLD),
                    ft.Column(controls=history_controls, height=160, scroll=ft.ScrollMode.AUTO),
                ],
                tight=True,
                width=320,
            ),
            actions=[
                ft.TextButton("キャンセル", on_click=handle_cancel, tooltip="変更を破棄して閉じる"),
                ft.Button("検索", on_click=handle_search, tooltip="この条件で絞り込む"),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.show_dialog(dialog)

    def _update_search_button(self) -> None:
        active = bool(self.search_query)
        self.search_button.icon_color = theme_repo.accent_color() if active else None
        self.search_button.tooltip = (
            f"文字列で検索する（現在: {self.search_query}）" if active else "文字列で検索する"
        )
        safe_update(self.search_button)

    # ========================
    # ✅ ログ追記・再描画
    # ========================
    def append_line(self, line: str, level: str) -> None:
        """
        services/applog.py が標準フォーマットで組み立てた1行を追記する。
        色分けは行内容の部分文字列判定ではなく区分（level）で行う。
        現在の絞り込み条件を満たす行のみ画面へ追記する（満たさない行もself.linesには
        保持するため、条件を緩めれば再表示できる）
        """
        self.lines.append((line, level))
        if self._passes_filters(line, level):
            self._append_span(line, level)
            safe_update(self.log_text)

    def _rebuild_view(self) -> None:
        """種別・検索・範囲のいずれかが変わったとき、self.linesから表示を作り直す"""
        self.log_spans.clear()
        for line, level in self.lines:
            if self._passes_filters(line, level):
                self._append_span(line, level)
        safe_update(self.log_text)

    def _append_span(self, line: str, level: str) -> None:
        if level == "ERROR":
            color, weight = theme_repo.error_color(), ft.FontWeight.BOLD
        elif level == "WARNING":
            color, weight = theme_repo.error_color(), None
        else:
            color, weight = None, None

        if self.log_spans:
            self.log_spans.append(ft.TextSpan(text="\n"))
        self.log_spans.append(
            ft.TextSpan(text=line, style=ft.TextStyle(color=color, weight=weight))
        )

    def clear(self) -> None:
        self.lines.clear()
        self.log_spans.clear()
        safe_update(self.log_text)

    # ========================
    # ✅ ツールバー操作
    # ========================
    async def _handle_copy(self, e: ft.ControlEvent) -> None:
        text = "".join(s.text for s in self.log_spans)
        await ft.Clipboard().set(text)

    def _handle_clear(self, e: ft.ControlEvent) -> None:
        self.clear()
