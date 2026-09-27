import tomllib
from dataclasses import dataclass
from typing import List

import tomli_w

from services.storage.graph_storage import GraphStorageService
from services.storage.local_storage import LocalStorageService

JOB_TYPE_FIXED = "定型"      # 定型業務（通常どおりコマンドを実行）
JOB_TYPE_FLEXIBLE = "非定型"  # 非定型業務（業務記録プラグインで計測し、結果を履歴へ記録）
JOB_TYPES = [JOB_TYPE_FIXED, JOB_TYPE_FLEXIBLE]

# Tier1〜Tier8: 業務の階層化（全体共有・共有マスターと同期される）。名称は「設定」タブでカスタマイズ可能
TIER_SHARED_KEYS = [f"tier{i}" for i in range(1, 9)]


def is_skeleton_job(item) -> bool:
    """
    「骨組み」状態（統合業務管理フェーズ4、DESIGN.md「11.3」参照）: 成熟度未設定（0）のまま
    commandが空の定型業務。業務ヒアリング段階でジョブ名・Tier・カテゴリだけ先に登録し、
    実装（コマンド）は後から詰める運用を想定した状態で、一覧には表示するが実行はできない
    （実行系の各所〈gui/run_tab.py・services/scheduler_service.py・tui/app.py〉で除外する）。
    非定型業務はcommandが常に空でも正常（業務記録プラグインを起動するだけ）のため対象外
    """
    return item.job_type != JOB_TYPE_FLEXIBLE and not (item.command or "").strip()


# ========================
# ✅ データモデル
# ========================
@dataclass
class MenuItem:
    name: str                 # 必須
    command: str              # 必須
    is_async: bool            # 任意（デフォルト：同期）
    schedule: str = ""        # 任意（cron）
    note: str = ""            # 任意（特記事項）
    manual: str = ""          # 任意（業務マニュアルのURL/フォルダ/ファイルパス）
    job_id: str = ""          # 自動採番（安定識別子。並び替え・削除しても変わらない）
    category: str = ""        # 任意（カテゴリ。Tierとは別軸で併用する）
    job_type: str = JOB_TYPE_FIXED  # "定型" | "非定型"
    tier: str = ""            # 任意（Tierの表示名。空文字は「未設定」）
    enabled: bool = True      # 任意（デフォルト：有効）。Falseの場合は実行できない
    created_at: str = ""      # 任意（作成日、"YYYY-MM-DD"）。ジョブ追加時に自動設定
    updated_at: str = ""      # 任意（最終更新日、"YYYY-MM-DD"）。ジョブ追加・編集時に自動設定
    maturity: int = 0         # 任意（成熟度、1〜5）。0は未設定


# ========================
# ✅ 設定読み込み
# ========================
def load_config(path: str) -> List[MenuItem]:
    """
    TOMLから設定を読み込み、MenuItemリストを返す

    ・async → 省略時 False（同期）
    ・schedule → 省略時 ""
    """

    with open(path, "rb") as f:
        data = tomllib.load(f)
    

    items: List[MenuItem] = []

    for idx, m in enumerate(data.get("menu", [])):

        # ========================
        # ✅ 必須チェック
        # ========================
        name = m.get("name")
        command = m.get("command", "")

        if not name:
            raise ValueError(f"[menu {idx}] name が未設定")

        # ========================
        # ✅ オプション
        # ========================

        raw_async = m.get("async", False)
        schedule = m.get("schedule", "")
        note = m.get("note", "")
        manual = m.get("manual", "")
        job_id = m.get("job_id", "")
        category = m.get("category", "")
        job_type = m.get("job_type", JOB_TYPE_FIXED)
        job_type = job_type if job_type in JOB_TYPES else JOB_TYPE_FIXED
        tier = m.get("tier", "")
        enabled = m.get("enabled", True)
        created_at = m.get("created_at", "")
        updated_at = m.get("updated_at", "")
        maturity_raw = m.get("maturity", 0)
        maturity = maturity_raw if isinstance(maturity_raw, int) and 0 <= maturity_raw <= 5 else 0

        # 非定型業務はcommandを実行しない（業務記録プラグインを起動するだけ）ため、commandは任意。
        # 定型業務も、成熟度未設定（0）＝「骨組み」状態（統合業務管理フェーズ4、DESIGN.md「11.3」参照）
        # であればcommand未設定のまま保存・起動チェックを通過できる（一覧には表示するが実行は不可。
        # `config_loader.is_skeleton_job()`で判定し、実行系の各所で除外する）
        if not command and job_type != JOB_TYPE_FLEXIBLE and maturity != 0:
            raise ValueError(f"[menu {idx}] command が未設定")

        # ========================
        # ✅ 型チェック（安全性）
        # ========================
        is_async = False
        if not isinstance(raw_async, bool):
            raise ValueError(f"[menu {idx}] async は true/false")
        is_async = (raw_async is True)

        if not isinstance(schedule, str):
            raise ValueError(f"[menu {idx}] schedule は文字列")

        # ========================
        # ✅ インスタンス生成
        # ========================
        item = MenuItem(
            name=name,
            command=command,
            is_async=is_async,
            schedule=schedule,
            note=note if isinstance(note, str) else "",
            manual=manual if isinstance(manual, str) else "",
            job_id=job_id if isinstance(job_id, str) else "",
            category=category if isinstance(category, str) else "",
            job_type=job_type,
            tier=tier if isinstance(tier, str) else "",
            enabled=enabled if isinstance(enabled, bool) else True,
            created_at=created_at if isinstance(created_at, str) else "",
            updated_at=updated_at if isinstance(updated_at, str) else "",
            maturity=maturity if isinstance(maturity, int) and 0 <= maturity <= 5 else 0,
        )

        items.append(item)

    # ========================
    # ✅ ジョブIDの自動採番（未設定の既存ジョブに割り当て、ファイルへ反映）
    # ========================
    assigned = False
    for item in items:
        if not item.job_id:
            item.job_id = next_job_id(items)
            assigned = True

    if assigned:
        save_config(path, items, data.get("storage", {}), data.get("sync", {}), data.get("tiers", {}))

    return items


def next_job_id(items: List[MenuItem], namespace: str = None) -> str:
    """
    次に採番するジョブID。統合業務管理フェーズ3（DESIGN.md「11. 統合業務管理（項目単位同期）」
    11.3 フェーズ3）以降は"J<namespace>-<3桁連番>"（例: "J1001-001"）の形式で採番する。

    namespaceは既定でこの端末のデバイス論理番号（`services/device_repo.py`、未割当なら
    物理暗号ULIDの**末尾**8文字で代用）。ULIDの先頭側は48bitミリ秒タイムスタンプが占めるため、
    同じタイミングで導入された複数端末は先頭が似通ってしまう（衝突しやすい）。末尾側は
    80bitの純粋な乱数部分のため、未割当時の代用先としてこちらを使う。
    いずれの場合もnamespaceは端末ごとに一意なため、複数端末が同時にオフラインで新規追加しても
    job_idが衝突しない（詳細はDESIGN.md「11.2 B1」参照）。

    既存の"J001"形式（旧方式、namespace無し）のIDはそのまま維持し、遡って変換しない
    （新規追加分のみ新方式に切り替える。DESIGN.md「11.3」R12参照）
    """
    if namespace is None:
        from services import device_repo

        identity = device_repo.load_local_identity()
        namespace = identity.logical_number or identity.device_id[-8:]

    prefix = f"J{namespace}-"
    existing_numbers = [
        int(item.job_id[len(prefix):])
        for item in items
        if item.job_id.startswith(prefix) and item.job_id[len(prefix):].isdigit()
    ]
    return f"{prefix}{max(existing_numbers, default=0) + 1:03d}"


# ========================
# ✅ 設定書き込み（ジョブ管理画面用）
# ========================
def save_config(
    path: str,
    items: List[MenuItem],
    storage: dict,
    sync: dict = None,
    tiers: dict = None,
) -> None:
    """
    MenuItemリストと[storage]・[sync]・[tiers]設定をTOMLファイルへ書き戻す。
    tiers（Tier1〜Tier8の名称、全体共有）を渡さずに呼ぶと、既存の[tiers]セクションが消えるので注意
    """
    data = {
        "menu": [
            {
                "name": item.name,
                "command": item.command,
                "async": item.is_async,
                "schedule": item.schedule,
                "note": item.note,
                "manual": item.manual,
                "job_id": item.job_id,
                "category": item.category,
                "job_type": item.job_type,
                "tier": item.tier,
                "enabled": item.enabled,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "maturity": item.maturity,
            }
            for item in items
        ],
    }

    if storage:
        data["storage"] = storage

    if sync:
        data["sync"] = sync

    if tiers:
        data["tiers"] = tiers

    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def load_storage_config(path: str) -> dict:
    """
    [storage]セクションのみを辞書で返す（設定画面編集用）
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)

    return data.get("storage", {})


def load_sync_config(path: str) -> dict:
    """
    [sync]セクション（共有マスター設定ファイルの同期先パス）を辞書で返す
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)

    return data.get("sync", {})


def load_tier_config(path: str) -> dict:
    """
    [tiers]セクション（Tier1〜Tier8の名称。全体共有、共有マスターと同期される）を辞書で返す。
    未設定のキーは空文字（=そのTierは使わない）
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)

    tiers = data.get("tiers", {})
    return {key: tiers.get(key, "") for key in TIER_SHARED_KEYS}


def is_storage_enabled(storage_config: dict) -> bool:
    """
    [storage].enabled（既定True、キー省略時は有効＝従来通りの動作を維持する）。
    Falseの場合、共有マスター/ホーム定義の同期（自動・手動どちらも）・アプリ更新の検知/
    ダウンロード/適用を一切行わない、ユーザーが明示的にストレージ連携全体を止めるための
    全体スイッチ（ユーザーからの要望）。個々の[sync].remote_path等の設定有無とは独立した判定
    """
    return bool(storage_config.get("enabled", True))


def create_storage(config):

    t = config["storage"]["type"]

    if t == "graph":
        token = get_token()
        client = GraphClient(token)
        return GraphStorageService(client)

    elif t == "local":
        return LocalStorageService(config["storage"]["local"]["base_dir"])

    elif t == "flow":
        from services.storage.flow_storage import FlowStorageService  # requests依存のため遅延import

        return FlowStorageService(config["storage"]["flow"]["url"])

    else:
        raise ValueError("unknown storage type")
        