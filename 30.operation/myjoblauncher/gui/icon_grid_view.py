import os
from dataclasses import dataclass
from typing import Callable

import flet as ft

from services import theme_repo

# ✅ ツール・リンク共通のアイコン表示（大/中/小）・一覧表示の切り替え描画ヘルパー。
# ToolItem/LinkItemには依存しない汎用コンポーネントにしてある

ICON_MODE_SIZES = {"icon_large": 64, "icon_medium": 40, "icon_small": 24}
VIEW_MODE_LABELS = {
    "icon_large": "アイコン(大)",
    "icon_medium": "アイコン(中)",
    "icon_small": "アイコン(小)",
    "list": "一覧",
}

SORT_MODES = ("use_count", "name", "last_used", "category", "recommend")
SORT_MODE_LABELS = {
    "use_count": "使用回数",
    "name": "名前",
    "last_used": "最終実行日時",
    "category": "カテゴリ",
    "recommend": "おすすめ",
}

# おすすめ度（1〜5）の選択肢。`gui/job_editor.py`のMATURITY_OPTIONSと同じ形式
RECOMMEND_OPTIONS = [str(n) for n in range(1, 6)]


def parse_recommend(raw) -> int:
    """おすすめ度の入力文字列（フォームの値）を0〜5のintへ変換する。空欄・不正値は0（未設定）"""
    raw = (raw or "").strip() if isinstance(raw, str) else raw
    return int(raw) if str(raw) in RECOMMEND_OPTIONS else 0


def sort_items(items: list, mode: str) -> list:
    """
    ToolItem/LinkItem共通。`name`/`last_used_at`/`use_count`/`category`/`recommend`属性を
    持つ項目のリストを指定モードで並び替える（`name`/`category`は昇順、`use_count`/`last_used`/
    `recommend`は降順。`last_used`は`last_used_at`が空文字＝未実行のものがISO文字列比較で最小になるため、
    降順ソートで自然に末尾へ回る。`recommend`も未設定（0）が同様に末尾へ回る）。
    その後、`pinned`が真の項目を安定ソートで先頭にまとめる（Pythonの`sorted()`は安定ソートのため、
    ピン止め・非ピン止めそれぞれのグループ内では上記の並びが保たれる）
    """
    if mode == "name":
        ordered = sorted(items, key=lambda i: i.name)
    elif mode == "last_used":
        ordered = sorted(items, key=lambda i: i.last_used_at, reverse=True)
    elif mode == "category":
        ordered = sorted(items, key=lambda i: (i.category or "", i.name))
    elif mode == "recommend":
        ordered = sorted(items, key=lambda i: i.recommend, reverse=True)
    else:
        ordered = sorted(items, key=lambda i: i.use_count, reverse=True)

    return sorted(ordered, key=lambda i: not getattr(i, "pinned", False))


@dataclass
class GridEntry:
    label: str
    subtitle: str
    last_used_label: str
    icon_path: str | None
    fallback_icon: str
    on_launch: Callable[[], None]
    on_edit: Callable[[], None]
    tooltip: str
    category: str = ""
    pinned: bool = False
    on_toggle_pin: Callable[[], None] | None = None


def _fallback_icon(entry: GridEntry, size: int) -> ft.Control:
    # ft.Icon（Material Icons）は同じsize指定でも実アイコン（ft.Image）より
    # 視覚的に大きく見える（グリフが枠いっぱいに描画されるため）。見た目の比率を
    # 揃えるため、フォールバック時はグリフ自体を3/4に縮小し、確保する箱のサイズは
    # size×sizeのまま（Containerでラップ）にして他アイテムとの並び・間隔を変えない
    return ft.Container(
        content=ft.Icon(entry.fallback_icon, size=round(size * 0.75)),
        width=size,
        height=size,
        alignment=ft.Alignment.CENTER,
    )


def _entry_icon(entry: GridEntry, size: int) -> ft.Control:
    if entry.icon_path:
        # 【重要・実機で確認済み】以前は`open(path, "rb").read()`でバイト列を`src`に直接渡す
        # 方式だったが、Edgeでは表示されるのにFirefoxでは表示されない（アイコンが全滅で
        # フォールバックのグリッドアイコンになる）不具合を実機で確認した。原因はFletの
        # Web版（Flutter Web）がバイト列画像をブラウザへ渡す内部処理（blob/data URL化）に
        # ブラウザ間の互換性差があるためと推定される。対策として、`main.py`の`ft.run()`に
        # `assets_dir="cache/icons"`を指定してアイコンPNGを通常の静的ファイルとしてHTTP配信し、
        # ここではファイル名だけを相対パスとして`src`に渡す方式に変更した（普通の`<img>`表示と
        # 同じ経路になるため、ブラウザ間の互換性差の影響を受けない）。デスクトップ版でも
        # `assets_dir`はFletの標準機能として動作する。`error_content`に以前と同じフォールバック
        # アイコンを渡すことで、万一ファイルが見つからない場合もFlutterの壊れた画像アイコンでは
        # なく従来通りの表示になる
        return ft.Image(
            src=os.path.basename(entry.icon_path),
            width=size,
            height=size,
            error_content=_fallback_icon(entry, size),
        )
    return _fallback_icon(entry, size)


def _pin_button(entry: GridEntry, **position) -> ft.IconButton:
    """
    ピン止めの切り替えボタン。編集アイコンと異なりホバー中だけでなく常時表示する
    （ユーザーからの要望: 「カード/一覧上にピンアイコンを常設し、クリックでその場でON/OFF」）
    """
    return ft.IconButton(
        icon=ft.Icons.PUSH_PIN if entry.pinned else ft.Icons.PUSH_PIN_OUTLINED,
        icon_size=14,
        icon_color=theme_repo.accent_color() if entry.pinned else None,
        tooltip="ピン止めを解除する" if entry.pinned else "ピン止めする（一覧の先頭に固定表示）",
        on_click=lambda e, entry=entry: entry.on_toggle_pin() if entry.on_toggle_pin else None,
        **position,
    )


def build_icon_grid(entries: list[GridEntry], mode: str) -> ft.GridView:
    """
    アイコン＋名前のみを表示する（常時表示の編集アイコンは視覚的なノイズになるため無くした）。
    編集ボタンはマウスホバー中だけ右上に表示する（`ft.Container.on_hover`、e.dataはbool）。
    ピン止めはここでは表示しない（一覧表示モードのみで表示・変更できる。ユーザーからの要望:
    アイコン表示モード〈大/中/小〉ではピン止めアイコンを出さない）
    """
    size = ICON_MODE_SIZES.get(mode, ICON_MODE_SIZES["icon_medium"])

    cards = []
    for entry in entries:
        edit_button = ft.IconButton(
            icon=ft.Icons.EDIT,
            icon_size=14,
            tooltip=f"「{entry.label}」を編集する",
            on_click=lambda e, entry=entry: entry.on_edit(),
            visible=False,
            top=0,
            right=0,
        )

        def make_hover_handler(button: ft.IconButton):
            def handler(e: ft.ControlEvent) -> None:
                button.visible = bool(e.data)
                button.update()

            return handler

        cards.append(
            ft.Container(
                content=ft.Stack(
                    controls=[
                        ft.Column(
                            controls=[
                                _entry_icon(entry, size),
                                ft.Text(entry.label, size=11, max_lines=2, text_align=ft.TextAlign.CENTER),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=4,
                            tight=True,
                        ),
                        edit_button,
                    ],
                ),
                tooltip=entry.tooltip,
                alignment=ft.Alignment.CENTER,
                padding=8,
                border=ft.Border.all(1, ft.Colors.OUTLINE),
                border_radius=6,
                on_click=lambda e, entry=entry: entry.on_launch(),
                on_hover=make_hover_handler(edit_button),
            )
        )

    return ft.GridView(
        controls=cards,
        max_extent=size * 2 + 24,
        child_aspect_ratio=1.0,
        spacing=8,
        run_spacing=8,
        expand=True,
    )


def build_list_view(entries: list[GridEntry]) -> ft.ListView:
    tiles = []
    for entry in entries:
        # ✅ アイコン・名前以外にカテゴリも表示する（ユーザーからの要望）。カテゴリ未設定の
        # 項目では表示を省略し、"カテゴリ: "というラベルだけが空欄で残るのを避ける
        category_part = f"カテゴリ: {entry.category}　" if entry.category else ""
        tiles.append(
            ft.ListTile(
                leading=_entry_icon(entry, 24),
                title=ft.Text(entry.label),
                subtitle=ft.Text(
                    f"{category_part}{entry.subtitle}　最終: {entry.last_used_label}", max_lines=1
                ),
                trailing=ft.Row(
                    tight=True,
                    controls=[
                        _pin_button(entry),
                        ft.IconButton(
                            icon=ft.Icons.EDIT,
                            tooltip=f"「{entry.label}」を編集する",
                            on_click=lambda e, entry=entry: entry.on_edit(),
                        ),
                    ],
                ),
                on_click=lambda e, entry=entry: entry.on_launch(),
            )
        )

    return ft.ListView(controls=tiles, expand=True, spacing=2)


def build_view_mode_toggle(current_mode: str, on_change: Callable[[str], None]) -> ft.Row:
    icons = {
        "icon_large": ft.Icons.GRID_VIEW,
        "icon_medium": ft.Icons.APPS,
        "icon_small": ft.Icons.VIEW_MODULE,
        "list": ft.Icons.VIEW_LIST,
    }

    def make_handler(mode: str):
        def handler(e: ft.ControlEvent) -> None:
            on_change(mode)

        return handler

    return ft.Row(
        controls=[
            ft.IconButton(
                icon=icons[mode],
                tooltip=VIEW_MODE_LABELS[mode],
                icon_color=ft.Colors.PRIMARY if mode == current_mode else None,
                on_click=make_handler(mode),
            )
            for mode in ("icon_large", "icon_medium", "icon_small", "list")
        ],
        spacing=0,
    )


def build_sort_mode_dropdown(current_mode: str, on_change: Callable[[str], None]) -> ft.Dropdown:
    def handle_select(e: ft.ControlEvent) -> None:
        if e.control.value:
            on_change(e.control.value)

    return ft.Dropdown(
        label="並び替え",
        value=current_mode,
        options=[ft.DropdownOption(key=m, text=SORT_MODE_LABELS[m]) for m in SORT_MODES],
        on_select=handle_select,
        width=160,
        dense=True,
    )
