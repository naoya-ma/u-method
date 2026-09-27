import os
import secrets
import time
import tomllib
from dataclasses import dataclass

import tomli_w

from services import tz_repo

# ✅ この端末自身の識別情報（このPCだけのローカル状態、共有マスター同期の対象外）
LOCAL_IDENTITY_PATH = "config/device.toml"

# ✅ masterロールが集約した、既知の全端末一覧のローカルキャッシュ（共有マスター同期の対象外。
# devices/ 配下の個別ファイルをダウンロードして都度組み立てる。詳細はDESIGN.md 11章）
DEVICES_CACHE_PATH = "config/devices.toml"

# ✅ 共有ストレージ上で、端末ごとの情報を1ファイルずつ書き込むディレクトリ名。
# ファイルを端末ごとに分けることで、member端末は他端末の登録内容を一切読まず・消さずに
# 自分の情報だけを安全に追記できる（DESIGN.md 11.2 A1/B2参照）
DEVICES_REMOTE_DIR = "devices"

ROLE_MEMBER = "member"
ROLE_MASTER = "master"
ROLES = [ROLE_MEMBER, ROLE_MASTER]

# ✅ 論理番号の帯（DESIGN.md 11.2 A1）。"0000"=基盤（共有マスターの管理主体そのもの）、
# 1001以降=実運用端末。テスト用の予約帯（旧案の9000系）は撤廃済み
BASELINE_LOGICAL_NUMBER = "0000"
OPERATIONAL_RANGE_START = 1001

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford Base32（I/L/O/Uを含まない）


@dataclass
class DeviceItem:
    device_id: str            # 物理暗号（ULID）。端末ごとに一度生成したら不変
    logical_number: str = ""  # 論理番号。masterが割り当てるまでは空文字（未割当）
    owner: str = ""           # 持ち主（利用者名）
    role: str = ROLE_MEMBER   # "member" | "master"
    registered_at: str = ""   # 初回登録日（"YYYY-MM-DD"）


def generate_ulid() -> str:
    """
    ULID（https://github.com/ulid/spec）を生成する: 48bitミリ秒タイムスタンプ＋80bitランダム値を
    Crockford Base32（26文字）で表現する。デバイスの物理暗号として、複数端末が同時に
    オフラインで生成しても衝突しない一意なIDが必要なために使う。既存の`uuid7`（実行履歴の
    command_id）とは異なり、この値を切り詰めて短縮表示することは想定しない
    （切り詰めによる衝突は`next_job_id`のコメントで既知の問題として記録済み）
    """
    ts_ms = int(time.time() * 1000)
    rand = secrets.randbits(80)
    value = (ts_ms << 80) | rand
    return "".join(_ULID_ALPHABET[(value >> (5 * (25 - i))) & 0x1F] for i in range(26))


# ========================
# ✅ この端末自身の識別情報（ローカル、不変）
# ========================
def load_local_identity(path: str = LOCAL_IDENTITY_PATH) -> DeviceItem:
    """
    この端末のデバイス情報を読み込む。ファイルが無ければ物理暗号（ULID）を自動生成し、
    role=member・registered_at=今日で新規作成する（要件R1: 初回起動時に一度だけ生成し、
    以後は変更しない）
    """
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = tomllib.load(f)

        role = data.get("role", ROLE_MEMBER)
        return DeviceItem(
            device_id=data.get("device_id", ""),
            logical_number=data.get("logical_number", ""),
            owner=data.get("owner", ""),
            role=role if role in ROLES else ROLE_MEMBER,
            registered_at=data.get("registered_at", ""),
        )

    item = DeviceItem(device_id=generate_ulid(), registered_at=tz_repo.today().strftime("%Y-%m-%d"))
    save_local_identity(item, path)
    return item


def save_local_identity(item: DeviceItem, path: str = LOCAL_IDENTITY_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(_device_to_dict(item), f)


# ========================
# ✅ 個人・ロールの表現（統合業務管理フェーズ2、DESIGN.md「11.2 A2/A3」参照）。
# このアプリはログイン機構を持たないため、デバイスマスターに登録した「持ち主」を
# そのまま「今この端末を使っている利用者」として扱う（「1端末＝1人」前提、共用PCは想定外）
# ========================
def current_owner_label(identity: DeviceItem | None = None) -> str:
    """
    監査ログ等で「誰が」を示すための表示名。持ち主が未設定の場合は物理暗号の先頭8文字を
    代わりに使う（空文字のまま記録すると誰の操作か分からなくなるため、必ず何かを返す）
    """
    identity = identity or load_local_identity()
    return identity.owner or f"device:{identity.device_id[:8]}"


def is_master(identity: DeviceItem | None = None) -> bool:
    """このロール判定はクライアント側のみ（サーバーレス構成のため）。事後の監査はui_log側の記録で補完する"""
    identity = identity or load_local_identity()
    return identity.role == ROLE_MASTER


def _device_to_dict(item: DeviceItem) -> dict:
    return {
        "device_id": item.device_id,
        "logical_number": item.logical_number,
        "owner": item.owner,
        "role": item.role,
        "registered_at": item.registered_at,
    }


def _device_from_dict(data: dict) -> DeviceItem:
    role = data.get("role", ROLE_MEMBER)
    return DeviceItem(
        device_id=data.get("device_id", ""),
        logical_number=data.get("logical_number", ""),
        owner=data.get("owner", ""),
        role=role if role in ROLES else ROLE_MEMBER,
        registered_at=data.get("registered_at", ""),
    )


# ========================
# ✅ 既知の全端末一覧（masterが集約したローカルキャッシュ）
# ========================
def load_devices(path: str = DEVICES_CACHE_PATH) -> list[DeviceItem]:
    if not os.path.exists(path):
        return []

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return [_device_from_dict(d) for d in data.get("devices", []) if d.get("device_id")]


def save_devices(devices: list[DeviceItem], path: str = DEVICES_CACHE_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump({"devices": [_device_to_dict(d) for d in devices]}, f)


def next_logical_number(devices: list[DeviceItem]) -> str:
    """
    実運用帯（1001以降）で次に割り当てる論理番号を返す（既存の最大値+1、無ければ1001）。
    "0000"（基盤）は特別扱いのため対象外にする
    """
    existing = [
        int(d.logical_number)
        for d in devices
        if d.logical_number.isdigit() and int(d.logical_number) >= OPERATIONAL_RANGE_START
    ]
    return str(max(existing, default=OPERATIONAL_RANGE_START - 1) + 1)


# ========================
# ✅ 共有ストレージとの同期
# ========================
def _device_remote_path(device_id: str) -> str:
    return f"{DEVICES_REMOTE_DIR}/{device_id}.toml"


def upload_own_device(storage, identity: DeviceItem, tmp_dir: str = "config") -> None:
    """
    この端末自身の情報を `devices/<device_id>.toml` として共有ストレージへアップロードする。
    端末ごとに別ファイルへ書き込むため、他端末の登録内容を一切読まず・消さずに追加できる
    （memberはdevices.toml全体をダウンロードしない前提。DESIGN.md 11.2 A1/B2参照）
    """
    tmp_path = os.path.join(tmp_dir, f".device_upload_{identity.device_id}.toml")
    save_local_identity(identity, tmp_path)
    try:
        storage.upload(tmp_path, _device_remote_path(identity.device_id))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def refresh_own_logical_number(storage, identity: DeviceItem, tmp_dir: str = "config") -> DeviceItem:
    """
    自分の`devices/<device_id>.toml`をダウンロードし、masterが割り当てた論理番号があれば
    ローカルへ取り込む（`identity`を書き換え、`config/device.toml`へ保存する）。
    member/masterどちらも自分自身のファイルだけを読むため、`download_all_devices()`のような
    全端末一覧の取得（B2的な操作）にはならない（DESIGN.md 11.2 A1参照）。

    **`upload_own_device()`より必ず先に呼ぶこと**: 呼ぶ順序を逆にすると、まだ論理番号を
    知らないローカルの古い状態（空文字）でリモートを上書きしてしまい、masterが割り当てた
    論理番号を消してしまう（実際に踏んだ不具合）。持ち主・ロールはローカルの入力を
    常に優先し、この関数では上書きしない（論理番号だけがmaster側の一方的な更新のため）。
    ファイルがまだ存在しない（初回登録前）場合は何もしない
    """
    tmp_path = os.path.join(tmp_dir, f".device_refresh_{identity.device_id}.toml")
    try:
        storage.download(_device_remote_path(identity.device_id), tmp_path)
        with open(tmp_path, "rb") as f:
            data = tomllib.load(f)
        remote_item = _device_from_dict(data)
        if remote_item.device_id == identity.device_id and remote_item.logical_number != identity.logical_number:
            identity.logical_number = remote_item.logical_number
            save_local_identity(identity)
    except Exception:
        pass
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return identity


def download_all_devices(storage, tmp_dir: str = "config") -> list[DeviceItem]:
    """
    `devices/` 配下の全端末ファイルをダウンロードして集約する（masterロール専用）。
    個々のファイルが読み取れない場合はその端末だけスキップし、全体の集約は継続する
    """
    try:
        names = storage.list_files(DEVICES_REMOTE_DIR)
    except Exception:
        return []

    devices: list[DeviceItem] = []
    for name in names:
        if not name.endswith(".toml"):
            continue

        tmp_path = os.path.join(tmp_dir, f".device_download_{name}")
        try:
            storage.download(f"{DEVICES_REMOTE_DIR}/{name}", tmp_path)
            with open(tmp_path, "rb") as f:
                data = tomllib.load(f)
            item = _device_from_dict(data)
            if item.device_id:
                devices.append(item)
        except Exception:
            continue
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    return devices


def sync_devices_as_master(storage) -> list[DeviceItem]:
    """全端末をダウンロード・集約し、ローカルキャッシュ（config/devices.toml）へ保存する"""
    devices = download_all_devices(storage)
    save_devices(devices)
    return devices


def assign_logical_number(storage, devices: list[DeviceItem], device_id: str, logical_number: str) -> DeviceItem:
    """
    未割当の物理暗号(device_id)に論理番号を割り当て、該当端末のファイルだけを再アップロードする。
    他端末のファイルには一切触れないため、他端末の登録済み情報を消すことはない
    """
    target = next((d for d in devices if d.device_id == device_id), None)
    if target is None:
        raise ValueError(f"未知のdevice_id: {device_id}")

    target.logical_number = logical_number
    upload_own_device(storage, target)
    return target


def sync_device_at_startup(menu_path: str = "config/menu.toml") -> DeviceItem:
    """
    起動時の前処理として、①この端末のローカル識別情報（無ければ生成）を読み込み、
    ②ストレージが有効なら自分の情報を共有ストレージへアップロードし、
    ③roleがmasterなら全端末一覧もダウンロード・集約する。
    ローカル識別情報の読み込み（①）以外は失敗しても例外を伝播させない
    （他の起動時同期処理と同じフェイルセーフ方針。詳細はDESIGN.md 11.3 フェーズ1）
    """
    identity = load_local_identity()

    from services.config_loader import create_storage, is_storage_enabled, load_storage_config

    try:
        storage_config = load_storage_config(menu_path)
    except Exception:
        return identity

    if not is_storage_enabled(storage_config):
        return identity

    try:
        storage = create_storage({"storage": storage_config})
    except Exception:
        return identity

    try:
        # ✅ masterが割り当てた論理番号を先に取り込んでから（無ければ何もしない）、
        # ローカルの最新状態（学習した論理番号込み）をアップロードする。順序を逆にすると
        # 割り当て済みの論理番号を空文字で上書きしてしまう（upload_own_device()のdocstring参照）
        refresh_own_logical_number(storage, identity)
        upload_own_device(storage, identity)
    except Exception:
        pass

    if identity.role == ROLE_MASTER:
        try:
            sync_devices_as_master(storage)
        except Exception:
            pass

    return identity
