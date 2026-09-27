import flet as ft

from services import app_config

# ========================
# ✅ テーマ定義
# ========================
THEME_MODERN_DARK = "modern_dark"
THEME_MODERN_LIGHT = "modern_light"
THEME_MODERN_SYSTEM = "modern_system"
THEME_MONOTONE = "monotone"

THEMES = [THEME_MODERN_DARK, THEME_MODERN_LIGHT, THEME_MODERN_SYSTEM, THEME_MONOTONE]

THEME_LABELS = {
    THEME_MODERN_DARK: "シンプルモダン（ダーク）",
    THEME_MODERN_LIGHT: "シンプルモダン（ライト）",
    THEME_MODERN_SYSTEM: "シンプルモダン（システム）",
    THEME_MONOTONE: "モノトーン（緑×黒）",
}

DEFAULT_THEME = THEME_MODERN_DARK

# モノトーンテーマの配色（この2色のみを使う）
MONOTONE_GREEN = "#33FF33"
MONOTONE_GREEN_DIM = "#1F8F1F"
MONOTONE_BLACK = "#000000"


# ========================
# ✅ 設定の読み書き
# ========================
def load_theme(path: str = app_config.APP_CONFIG_PATH) -> str:
    theme = app_config.load(path).get("theme")
    return theme if theme in THEMES else DEFAULT_THEME


def save_theme(theme: str, path: str = app_config.APP_CONFIG_PATH) -> None:
    app_config.save({"theme": theme}, path)


# ========================
# ✅ テーマに応じた個別色（ログ・実行中表示・削除ボタン等、ハードコードされた強調色の置き換え用）
# ========================
def is_monotone(theme: str = None) -> bool:
    return (theme or load_theme()) == THEME_MONOTONE


def accent_color(theme: str = None) -> str:
    """実行中のジョブ名など、強調表示に使う色"""
    return MONOTONE_GREEN if is_monotone(theme) else ft.Colors.BLUE


def error_color(theme: str = None) -> str:
    """エラー表示・削除/上書き等の破壊的操作ボタンに使う色"""
    return MONOTONE_GREEN if is_monotone(theme) else ft.Colors.RED


def success_color(theme: str = None) -> str:
    """成功表示に使う色"""
    return MONOTONE_GREEN_DIM if is_monotone(theme) else ft.Colors.GREEN


# ========================
# ✅ テーマに応じたステータス表示文字（色付き絵文字の代わりに、モノトーン時は昔ながらの記号を使う）
# ========================
MONOTONE_STATUS_LABELS = {
    "SUCCESS": "○ 完了",
    "ERROR": "× 失敗",
    "CANCEL": "△ 中断",
}
MONOTONE_RUNNING_LABEL = "● 実行中"
MONOTONE_SCHEDULED_LABEL = "◇ 予定"


def status_label(status: str, default_label: str = None, theme: str = None) -> str:
    """
    実行履歴のステータス表示文字列。既定は services.history_repo.STATUS_LABELS（色付き絵文字）、
    モノトーン時は昔ながらの記号（○×△）に差し替える。
    default_label を省略した場合、既定の解決先が無い状態（None等）は STATUS_LABELS.get(status, status) と同じ規則で解決する
    """
    from services.history_repo import STATUS_LABELS

    if default_label is None:
        default_label = STATUS_LABELS.get(status, status)

    if is_monotone(theme):
        return MONOTONE_STATUS_LABELS.get(status, default_label)
    return default_label


def running_label(theme: str = None) -> str:
    """実行タブのステータス列（実行中）"""
    return MONOTONE_RUNNING_LABEL if is_monotone(theme) else "🔵 実行中"


def scheduled_label(theme: str = None) -> str:
    """実行タブのステータス列（実行予定）"""
    return MONOTONE_SCHEDULED_LABEL if is_monotone(theme) else "⏰ 予定"


# ========================
# ✅ ページへのテーマ適用
# ========================
_TEXT_STYLE_VARIANTS = [
    "display_large", "display_medium", "display_small",
    "headline_large", "headline_medium", "headline_small",
    "title_large", "title_medium", "title_small",
    "body_large", "body_medium", "body_small",
    "label_large", "label_medium", "label_small",
]


def _monotone_text_theme() -> ft.TextTheme:
    """全文字サイズのデフォルト色を緑に統一する（個別に color を指定していない ft.Text も緑になる）"""
    return ft.TextTheme(
        **{name: ft.TextStyle(color=MONOTONE_GREEN) for name in _TEXT_STYLE_VARIANTS}
    )


def _monotone_theme() -> ft.Theme:
    # ✅ ColorSchemeの全項目を緑/黒系で明示指定する。
    # 未指定のまま残すと、FletがMaterial3既定の配色（青紫系）で補完してしまい、
    # NavigationRailの選択中アイコン等、一部の部品だけ白/紫っぽく見える不具合の原因になる
    color_scheme = ft.ColorScheme(
        primary=MONOTONE_GREEN,
        on_primary=MONOTONE_BLACK,
        primary_container=MONOTONE_BLACK,
        on_primary_container=MONOTONE_GREEN,
        secondary=MONOTONE_GREEN,
        on_secondary=MONOTONE_BLACK,
        secondary_container=MONOTONE_BLACK,
        on_secondary_container=MONOTONE_GREEN,
        tertiary=MONOTONE_GREEN,
        on_tertiary=MONOTONE_BLACK,
        tertiary_container=MONOTONE_BLACK,
        on_tertiary_container=MONOTONE_GREEN,
        error=MONOTONE_GREEN,
        on_error=MONOTONE_BLACK,
        error_container=MONOTONE_BLACK,
        on_error_container=MONOTONE_GREEN,
        surface=MONOTONE_BLACK,
        on_surface=MONOTONE_GREEN,
        on_surface_variant=MONOTONE_GREEN_DIM,
        outline=MONOTONE_GREEN_DIM,
        outline_variant=MONOTONE_GREEN_DIM,
        shadow=MONOTONE_BLACK,
        scrim=MONOTONE_BLACK,
        inverse_surface=MONOTONE_GREEN,
        on_inverse_surface=MONOTONE_BLACK,
        inverse_primary=MONOTONE_BLACK,
        surface_tint=MONOTONE_GREEN,
        surface_bright=MONOTONE_BLACK,
        surface_dim=MONOTONE_BLACK,
        surface_container=MONOTONE_BLACK,
        surface_container_low=MONOTONE_BLACK,
        surface_container_lowest=MONOTONE_BLACK,
        surface_container_high=MONOTONE_BLACK,
        surface_container_highest=MONOTONE_BLACK,
        primary_fixed=MONOTONE_BLACK,
        primary_fixed_dim=MONOTONE_BLACK,
        on_primary_fixed=MONOTONE_GREEN,
        on_primary_fixed_variant=MONOTONE_GREEN,
        secondary_fixed=MONOTONE_BLACK,
        secondary_fixed_dim=MONOTONE_BLACK,
        on_secondary_fixed=MONOTONE_GREEN,
        on_secondary_fixed_variant=MONOTONE_GREEN,
        tertiary_fixed=MONOTONE_BLACK,
        tertiary_fixed_dim=MONOTONE_BLACK,
        on_tertiary_fixed=MONOTONE_GREEN,
        on_tertiary_fixed_variant=MONOTONE_GREEN,
    )

    return ft.Theme(
        color_scheme=color_scheme,
        text_theme=_monotone_text_theme(),
        primary_text_theme=_monotone_text_theme(),
        scaffold_bgcolor=MONOTONE_BLACK,
        canvas_color=MONOTONE_BLACK,
        divider_color=MONOTONE_GREEN_DIM,
        card_bgcolor=MONOTONE_BLACK,
        hint_color=MONOTONE_GREEN_DIM,
        icon_theme=ft.IconTheme(color=MONOTONE_GREEN),
        list_tile_theme=ft.ListTileTheme(
            icon_color=MONOTONE_GREEN,
            text_color=MONOTONE_GREEN,
            title_text_style=ft.TextStyle(color=MONOTONE_GREEN),
            subtitle_text_style=ft.TextStyle(color=MONOTONE_GREEN_DIM),
        ),
        dropdown_theme=ft.DropdownTheme(text_style=ft.TextStyle(color=MONOTONE_GREEN)),
        data_table_theme=ft.DataTableTheme(
            heading_text_style=ft.TextStyle(color=MONOTONE_GREEN, weight=ft.FontWeight.BOLD),
            data_text_style=ft.TextStyle(color=MONOTONE_GREEN),
        ),
        navigation_rail_theme=ft.NavigationRailTheme(
            bgcolor=MONOTONE_BLACK,
            indicator_color=MONOTONE_GREEN_DIM,
            selected_label_text_style=ft.TextStyle(color=MONOTONE_GREEN, weight=ft.FontWeight.BOLD),
            unselected_label_text_style=ft.TextStyle(color=MONOTONE_GREEN_DIM),
        ),
        use_material3=True,
    )


def apply_theme(page: ft.Page, theme: str = None) -> None:
    theme = theme if theme in THEMES else load_theme()

    if theme == THEME_MONOTONE:
        page.theme_mode = ft.ThemeMode.DARK
        page.theme = _monotone_theme()
        page.dark_theme = _monotone_theme()
    elif theme == THEME_MODERN_LIGHT:
        page.theme_mode = ft.ThemeMode.LIGHT
        page.theme = ft.Theme(use_material3=True)
        page.dark_theme = None
    elif theme == THEME_MODERN_SYSTEM:
        page.theme_mode = ft.ThemeMode.SYSTEM
        page.theme = ft.Theme(use_material3=True)
        page.dark_theme = ft.Theme(use_material3=True)
    else:  # THEME_MODERN_DARK
        page.theme_mode = ft.ThemeMode.DARK
        page.theme = ft.Theme(use_material3=True)
        page.dark_theme = None
