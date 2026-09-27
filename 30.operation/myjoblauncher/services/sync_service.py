import hashlib
import os
import time
import tomllib

import tomli_w

from services import applog

# 前回同期時点のリモート更新日時を記録する、このPCだけのローカルファイル
# （共有マスターの一部ではないため、ダウンロード/アップロードの対象外）。
# 複数の同期対象ファイル（menu.toml, portal.toml等）を同時に扱えるよう、
# キー（"menu"/"portal"等、呼び出し側が決める論理名）ごとにセクションを分けて保持する
SYNC_STATE_PATH = "config/sync_state.toml"

RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0


# ========================
# ✅ 同期状態（前回同期時点のリモート更新日時。キーごとに独立して管理）
# ========================
def load_sync_state(path: str = SYNC_STATE_PATH) -> dict:
    if not os.path.exists(path):
        return {}

    with open(path, "rb") as f:
        return tomllib.load(f)


def save_sync_state(key: str, mtime: float, path: str = SYNC_STATE_PATH) -> None:
    """
    key（"menu"/"portal"等）ごとに前回同期時点のリモート更新日時を記録する。
    他のキーの記録は消さないよう、既存の内容にマージしてから書き戻す
    """
    data = load_sync_state(path)
    data[key] = {"last_synced_remote_mtime": mtime}

    with open(path, "wb") as f:
        tomli_w.dump(data, f)


# ========================
# ✅ リトライ（一時的なネットワーク/ファイル共有エラー対策）
# ========================
def with_retry(func, attempts: int = RETRY_ATTEMPTS, delay_seconds: float = RETRY_DELAY_SECONDS):
    """
    func() を最大 attempts 回試みる。OSError（ファイル共有の一時的なアクセス失敗等）のみリトライし、
    最後の試行でも失敗した場合はその例外をそのまま送出する
    """
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except OSError as ex:
            last_error = ex
            if attempt < attempts:
                time.sleep(delay_seconds)

    raise last_error


# ========================
# ✅ 競合検知（アップロード前に、他の場所での更新が無いか確認）
# ========================
def has_conflict(storage, remote_path: str, key: str) -> bool:
    """
    前回同期時点のリモート更新日時と現在のリモート更新日時を比較する。
    ストレージ種別が更新日時取得に非対応（None）、または前回同期の記録が無い場合は競合なしとみなす
    """
    current_mtime = storage.get_remote_mtime(remote_path)
    if current_mtime is None:
        return False

    last_known = load_sync_state().get(key, {}).get("last_synced_remote_mtime")
    if last_known is None:
        return False

    return current_mtime > last_known


def record_sync(storage, remote_path: str, key: str) -> None:
    """ダウンロード/アップロード成功後に、その時点のリモート更新日時を「同期済み」として記録する"""
    current_mtime = storage.get_remote_mtime(remote_path)
    if current_mtime is not None:
        save_sync_state(key, current_mtime)


# ========================
# ✅ ダウンロード要否の判定（タイムスタンプ→ハッシュの順で比較し、変更が無ければスキップする）
# ========================
def _hash_file(path: str):
    """ローカルファイルのsha256ハッシュ値（16進文字列）を返す。存在しない場合は None"""
    if not os.path.exists(path):
        return None

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _should_download(storage, remote_path: str, local_path: str) -> bool:
    """
    先にリモート/ローカルの更新日時を比較し、リモートがローカルより新しい場合に限って
    さらにハッシュ値を比較する。ハッシュが一致すれば（内容は変わっていないため）ダウンロードを
    スキップできると判定する。更新日時・ハッシュのいずれかが取得できない（ストレージ種別が
    非対応、またはローカルファイルが未存在）場合は判定できないため、従来通り常にダウンロードする
    """
    remote_mtime = storage.get_remote_mtime(remote_path)
    if remote_mtime is None or not os.path.exists(local_path):
        return True

    local_mtime = os.path.getmtime(local_path)
    if remote_mtime <= local_mtime:
        return False

    remote_hash = storage.get_remote_hash(remote_path)
    if remote_hash is None:
        return True

    return remote_hash != _hash_file(local_path)


# ========================
# ✅ 起動時の自動ダウンロード（menu.toml / portal.toml 共通の下請け処理）
# ========================
def _auto_download(
    local_path: str, storage_config: dict, remote_path: str, key: str, label: str, verbose: bool = False
) -> bool:
    """
    ストレージ/同期設定が未設定・利用不可・ダウンロード失敗の場合は何もせず False を返す
    （ローカルのファイルをそのまま使う。ダウンロードは一時ファイルに書き込んでから
    差し替えるため、失敗してもローカルのファイルは壊れない）

    `verbose=True`（`--verbose`起動時）の場合のみ、「変更が無いためスキップ」メッセージを
    コンソール（`print()`）と運用ログ（`applog.log()`、INFOレベル）の両方へ出す
    （ユーザーからの要望: 通常起動時は毎回同じ内容のログで埋まらないようにしつつ、
    `--verbose`診断時だけ確認できるようにする）
    """
    from services.config_loader import create_storage, is_storage_enabled

    if not storage_config or not remote_path:
        return False

    if not is_storage_enabled(storage_config):
        print(f"[Sync] {label}はストレージ設定が無効化されているため自動ダウンロードをスキップしました")
        return False

    try:
        storage = create_storage({"storage": storage_config})
    except Exception as ex:
        print(f"[Sync] 起動時の自動ダウンロードをスキップしました（{label}、ストレージ利用不可）: {ex}")
        return False

    if not _should_download(storage, remote_path, local_path):
        if verbose:
            message = f"[Sync] {label}は変更が無いため自動ダウンロードをスキップしました"
            print(message)
            applog.log("INFO", message, func_name="_auto_download")
        return False

    if has_conflict(storage, remote_path, key):
        print(f"[Sync] 警告: {label}が前回同期後に更新されています。自動ダウンロードで上書きします")

    tmp_path = local_path + ".download_tmp"
    try:
        with_retry(lambda: storage.download(remote_path, tmp_path))
    except Exception as ex:
        print(f"[Sync] {label}の起動時自動ダウンロードに失敗しました: {ex}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False

    os.replace(tmp_path, local_path)
    record_sync(storage, remote_path, key)
    print(f"[Sync] 起動時に{label}を自動ダウンロードしました")
    return True


def auto_download_master(menu_path: str, verbose: bool = False) -> bool:
    """
    アプリ起動時に共有マスター（config/menu.toml）の自動取り込みを試みる。
    ジョブ一覧は項目（job_id）単位で安全にマージする（統合業務管理フェーズ3、
    DESIGN.md「11. 統合業務管理（項目単位同期）」11.3 R13〜R15参照）。このPCで
    まだアップロードしていないジョブの追加・変更は、この自動ダウンロードで
    消えることはない（`_auto_download()`の丸ごと上書き方式は使わない）。
    `[storage]`/`[sync]`/`[tiers]`は従来通り共有フォルダの値で上書きする（丸ごと同期のまま。
    これらは成長するコレクションではなく共有設定そのものなので変更していない）
    """
    from services.config_loader import (
        create_storage,
        is_storage_enabled,
        load_config,
        load_storage_config,
        load_sync_config,
        load_tier_config,
        save_config,
    )
    from services import item_sync

    try:
        storage_config = load_storage_config(menu_path)
        sync_config = load_sync_config(menu_path)
    except Exception:
        return False

    remote_path = sync_config.get("remote_path")
    if not storage_config or not remote_path:
        return False

    if not is_storage_enabled(storage_config):
        print("[Sync] 共有マスター設定はストレージ設定が無効化されているため自動ダウンロードをスキップしました")
        return False

    try:
        storage = create_storage({"storage": storage_config})
    except Exception as ex:
        print(f"[Sync] 起動時の自動ダウンロードをスキップしました（共有マスター設定、ストレージ利用不可）: {ex}")
        return False

    if not _should_download(storage, remote_path, menu_path):
        if verbose:
            message = "[Sync] 共有マスター設定は変更が無いため自動ダウンロードをスキップしました"
            print(message)
            applog.log("INFO", message, func_name="auto_download_master")
        return False

    tmp_path = menu_path + ".download_tmp"
    try:
        with_retry(lambda: storage.download(remote_path, tmp_path))
    except Exception as ex:
        print(f"[Sync] 共有マスター設定の起動時自動ダウンロードに失敗しました: {ex}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False

    try:
        local_items = load_config(menu_path)
        remote_items = load_config(tmp_path)
        remote_storage = load_storage_config(tmp_path)
        remote_sync = load_sync_config(tmp_path)
        remote_tiers = load_tier_config(tmp_path)

        base_hashes = item_sync.load_sync_base()
        merged_items, conflicts, new_hashes, stats = item_sync.merge_menu_items(
            local_items, remote_items, base_hashes
        )
        start_line, end_line = item_sync.format_sync_progress_lines(stats, verb="ダウンロード")
        print(f"[Sync] {start_line}")
        print(f"[Sync] {end_line}")

        save_config(menu_path, merged_items, remote_storage, remote_sync, remote_tiers)
        item_sync.save_sync_base(new_hashes)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    record_sync(storage, remote_path, "menu")

    if conflicts:
        print(
            f"[Sync] 起動時に共有マスター設定を自動取り込みしました"
            f"（{len(conflicts)}件のジョブは両方で変更されていたため、このPCの内容を維持しました）"
        )
    else:
        print("[Sync] 起動時に共有マスター設定を自動取り込みしました（ジョブは項目単位でマージ）")

    return True


def auto_download_portal(menu_path: str, portal_path: str, verbose: bool = False) -> bool:
    """
    アプリ起動時にホーム定義（config/home.toml）の自動ダウンロードを試みる。
    ストレージ設定はmenu.tomlの[storage]を共用し、リモートパスのみmenu.tomlの
    [sync].portal_remote_path を別途使う（ホーム定義は独立したファイルのため）
    """
    from services.config_loader import load_storage_config, load_sync_config

    try:
        storage_config = load_storage_config(menu_path)
        sync_config = load_sync_config(menu_path)
    except Exception:
        return False

    remote_path = sync_config.get("portal_remote_path")
    return _auto_download(portal_path, storage_config, remote_path, "portal", "ホーム定義", verbose=verbose)


# ========================
# ✅ アプリ最新版の自動ダウンロード（次期開発ロードマップ項目2。検知・DLのみ、適用は設定タブの手動ボタン）
# ========================
APP_UPDATE_CACHE_DIR = "cache/app_update"
APP_UPDATE_MANIFEST_LOCAL_PATH = "cache/app_update/manifest.toml"


def auto_check_app_update(menu_path: str, verbose: bool = False) -> None:
    """
    起動時にアプリ更新マニフェスト（[sync].app_update_manifest_remote_path）をチェックし、
    現在のバージョンより新しければZIP本体（[sync].app_update_archive_remote_path）も
    自動ダウンロードしてローカルに保存する（config/app_update_state.toml）。
    適用（ソースへの実際の上書き）はここでは行わない。
    ストレージ/同期設定が未設定・利用不可・ダウンロード失敗時は何もしない
    （既存のauto_download_master/auto_download_portalと同じフェイルセーフ方針）
    """
    import tomllib

    from services import app_update_repo
    from services.config_loader import load_storage_config, load_sync_config

    try:
        storage_config = load_storage_config(menu_path)
        sync_config = load_sync_config(menu_path)
    except Exception:
        return

    manifest_remote_path = sync_config.get("app_update_manifest_remote_path")
    archive_remote_path = sync_config.get("app_update_archive_remote_path")
    if not manifest_remote_path or not archive_remote_path:
        return

    os.makedirs(APP_UPDATE_CACHE_DIR, exist_ok=True)

    if not _auto_download(
        APP_UPDATE_MANIFEST_LOCAL_PATH,
        storage_config,
        manifest_remote_path,
        "app_update_manifest",
        "アプリ更新マニフェスト",
        verbose=verbose,
    ):
        return

    try:
        with open(APP_UPDATE_MANIFEST_LOCAL_PATH, "rb") as f:
            manifest = tomllib.load(f)
        remote_version = manifest["version"]
    except Exception as ex:
        print(f"[Sync] アプリ更新マニフェストの読み込みに失敗しました: {ex}")
        return

    current_version = app_update_repo.get_current_version()
    if not app_update_repo.is_newer(remote_version, current_version):
        print(f"[Sync] アプリは最新版です（現在: {current_version}）")
        app_update_repo.save_update_state(None)
        return

    archive_local_path = os.path.join(APP_UPDATE_CACHE_DIR, f"update-{remote_version}.zip")
    if not _auto_download(
        archive_local_path,
        storage_config,
        archive_remote_path,
        "app_update_archive",
        "アプリ更新パッケージ",
        verbose=verbose,
    ):
        return

    app_update_repo.save_update_state(
        app_update_repo.AppUpdateInfo(
            version=remote_version,
            published_by=manifest.get("published_by", ""),
            published_at=manifest.get("published_at", ""),
            notes=manifest.get("notes", ""),
            archive_local_path=archive_local_path,
        )
    )
    print(f"[Sync] 新しいバージョン {remote_version} をダウンロードしました（現在: {current_version}）")

    # ✅ アプリの更新は「設定」タブを開かないと気付けないため、ホームの「お知らせ」にも出す
    # （ユーザーからの要望）。config/system_notices.toml（ローカル専用、共有マスター非同期）へ保存し、
    # titleにバージョン番号を含めることで、同じバージョンの再検知（起動のたびに走る）では
    # 重複追加されないようにしてある（add_system_notice側の重複排除）
    from services import portal_repo

    portal_repo.add_system_notice(
        title=f"新しいバージョン {remote_version} が利用可能です",
        content=(
            f"myJobLauncher の新しいバージョン **{remote_version}**（現在: {current_version}）が"
            "利用可能です。\n\n「設定」タブの「アプリの更新」セクションから適用できます。"
            + (f"\n\n{manifest.get('notes')}" if manifest.get("notes") else "")
        ),
    )
