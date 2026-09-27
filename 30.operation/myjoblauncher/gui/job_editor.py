import flet as ft

from gui.item_form_dialog import show_item_form_dialog
from gui.toast import show_toast
from services.config_loader import (
    JOB_TYPE_FIXED,
    JOB_TYPE_FLEXIBLE,
    JOB_TYPES,
    TIER_SHARED_KEYS,
    MenuItem,
    load_storage_config,
    load_sync_config,
    load_tier_config,
    next_job_id,
    save_config,
)
from services import tz_repo, ui_log

MENU_PATH = "config/menu.toml"

# 保存・検証用の正順（1〜5）。ダイアログの表示順は別（DROPDOWNは下から1・上に行くほど5にするため逆順で渡す）
MATURITY_OPTIONS = [str(n) for n in range(1, 6)]

# ジョブ追加・編集ダイアログ本体の横幅（既定480pxの2.5倍）
JOB_DIALOG_WIDTH = 1200

# ジョブ追加・編集ダイアログの項目順（固定）:
# ジョブ名/種別/Tier/カテゴリ/コマンド/非同期実行/スケジュール/業務マニュアル/作成日/最終更新日/成熟度/特記事項
# Tierはtier_options()の結果に応じて動的に挿入するため、build_job_fields()経由で使うこと。
# コマンド/業務マニュアル/特記事項は"wide"（他の項目の2倍幅・3行の複数行入力欄）にする
_JOB_FIELDS_BASE = [
    {"key": "name", "label": "ジョブ名", "type": "text"},
    {
        "key": "job_type",
        "label": "種別（非定型は業務記録プラグインで計測）",
        "type": "dropdown",
        "options": JOB_TYPES,
        "default": JOB_TYPE_FIXED,
    },
    {"key": "category", "label": "カテゴリ", "type": "text"},
    {
        "key": "command",
        "label": "コマンド（{{param}} で実行時入力欄を追加できます）",
        "type": "text",
        "wide": True,
    },
    {"key": "is_async", "label": "非同期実行（結果を待たずに次の操作ができます）", "type": "checkbox"},
    {"key": "schedule", "label": "スケジュール（cron: 分 時 日 月 曜日。空欄で手動実行のみ）", "type": "text"},
    {
        "key": "manual",
        "label": "業務マニュアル（URL、またはフォルダ/ファイルのパス）",
        "type": "text",
        "wide": True,
    },
    {"key": "created_at", "label": "作成日", "type": "readonly_text"},
    {"key": "updated_at", "label": "最終更新日", "type": "readonly_text"},
    {
        "key": "maturity",
        "label": "成熟度（1〜5、空欄で未設定。下から1・上に行くほど5）",
        "type": "dropdown",
        # 下(先頭)から1、上(末尾)にいくほど5になるよう、選択肢は降順で渡す
        "options": list(reversed(MATURITY_OPTIONS)),
    },
    {"key": "note", "label": "特記事項", "type": "text", "wide": True},
]


def tier_options(tier_config: dict, personal_tier_name: str) -> list[str]:
    names = [tier_config.get(key, "") for key in TIER_SHARED_KEYS]
    names.append(personal_tier_name)
    return [n for n in names if n]


def build_job_fields(tier_config: dict, personal_tier_name: str, autofocus_key: str = None) -> list[dict]:
    fields = [
        _JOB_FIELDS_BASE[0],  # ジョブ名
        _JOB_FIELDS_BASE[1],  # 種別
        {
            "key": "tier",
            "label": "Tier（未設定可、業務の階層）",
            "type": "dropdown",
            "options": tier_options(tier_config, personal_tier_name),
            "tooltip": "Tier1〜8は全体共有、個人用Tierはこのユーザーのみ有効です",
        },
        *_JOB_FIELDS_BASE[2:],
    ]

    if autofocus_key:
        fields = [{**f, "autofocus": True} if f["key"] == autofocus_key else f for f in fields]

    return fields


def validate_job_values(values: dict) -> str | None:
    """
    保存前チェック。load_config() が起動時に課す必須制約（name必須、commandは非定型・
    骨組み状態〈成熟度未設定〉以外必須）を画面側でも先に検査し、不正な値がファイルへ
    書き込まれて次回起動時にクラッシュするのを防ぐ
    """
    if not (values.get("name") or "").strip():
        return "ジョブ名を入力してください"

    maturity_raw = (values.get("maturity") or "").strip()
    if maturity_raw and maturity_raw not in MATURITY_OPTIONS:
        return "成熟度は1〜5で選択してください"

    job_type = values.get("job_type") or JOB_TYPE_FIXED
    is_skeleton = not maturity_raw  # 成熟度未設定（0相当）＝骨組み状態
    if not (values.get("command") or "").strip() and job_type != JOB_TYPE_FLEXIBLE and not is_skeleton:
        return "コマンドを入力してください（非定型ジョブ・成熟度未設定〈骨組み〉以外は必須です）"

    return None


def _maturity_from_values(values: dict) -> int:
    raw = (values.get("maturity") or "").strip()
    return int(raw) if raw else 0


def persist_jobs(menu_items: list[MenuItem]) -> None:
    """
    [storage]/[sync]/[tiers]は都度ファイルから読み直して渡す（設定タブ側のキャッシュに
    依存せず、実行タブなどどのタブからの保存でも既存セクションを消さないようにするため）
    """
    storage = load_storage_config(MENU_PATH)
    sync = load_sync_config(MENU_PATH)
    tiers = load_tier_config(MENU_PATH)
    save_config(MENU_PATH, menu_items, storage, sync, tiers)


def open_add_job_dialog(
    page: ft.Page,
    menu_items: list[MenuItem],
    tier_config: dict,
    personal_tier_name: str,
    on_saved,
) -> None:
    def on_submit(values: dict) -> None:
        error = validate_job_values(values)
        if error:
            show_toast(page, error)
            return

        today = tz_repo.today().isoformat()
        menu_items.append(
            MenuItem(
                name=values["name"],
                command=values["command"],
                is_async=bool(values.get("is_async")),
                schedule=values.get("schedule", ""),
                note=values.get("note", ""),
                manual=values.get("manual", ""),
                category=values.get("category", ""),
                job_type=values.get("job_type") or JOB_TYPE_FIXED,
                tier=values.get("tier") or "",
                job_id=next_job_id(menu_items),
                created_at=today,
                updated_at=today,
                maturity=_maturity_from_values(values),
            )
        )
        persist_jobs(menu_items)
        ui_log.log_action("ジョブ管理", "add", values["name"])
        on_saved()

    fields = build_job_fields(tier_config, personal_tier_name)
    initial = {
        "created_at": "（保存時に自動設定）",
        "updated_at": "（保存時に自動設定）",
    }
    show_item_form_dialog(page, "ジョブを追加", fields, initial, on_submit, width=JOB_DIALOG_WIDTH)


def open_edit_job_dialog(
    page: ft.Page,
    item: MenuItem,
    menu_items: list[MenuItem],
    tier_config: dict,
    personal_tier_name: str,
    on_saved,
    on_deleted,
    autofocus_key: str = None,
) -> None:
    initial = {
        "name": item.name,
        "command": item.command,
        "schedule": item.schedule,
        "is_async": item.is_async,
        "note": item.note,
        "manual": item.manual,
        "category": item.category,
        "job_type": item.job_type,
        "tier": item.tier,
        "created_at": item.created_at or "（未設定）",
        "updated_at": item.updated_at or "（未設定）",
        "maturity": str(item.maturity) if item.maturity else "",
    }

    def on_submit(values: dict) -> None:
        error = validate_job_values(values)
        if error:
            show_toast(page, error)
            return

        item.name = values["name"]
        item.command = values["command"]
        item.schedule = values.get("schedule", "")
        item.is_async = bool(values.get("is_async"))
        item.note = values.get("note", "")
        item.manual = values.get("manual", "")
        item.category = values.get("category", "")
        item.job_type = values.get("job_type") or JOB_TYPE_FIXED
        item.tier = values.get("tier") or ""
        item.maturity = _maturity_from_values(values)
        item.updated_at = tz_repo.today().isoformat()
        if not item.created_at:
            item.created_at = item.updated_at
        persist_jobs(menu_items)
        ui_log.log_action("ジョブ管理", "edit", item.name)
        on_saved()

    def on_delete() -> None:
        name = item.name
        menu_items.remove(item)
        persist_jobs(menu_items)
        ui_log.log_action("ジョブ管理", "delete", name)
        on_deleted()

    fields = build_job_fields(tier_config, personal_tier_name, autofocus_key=autofocus_key)
    show_item_form_dialog(
        page, f"ジョブを編集: {item.name}", fields, initial, on_submit, on_delete, width=JOB_DIALOG_WIDTH
    )
