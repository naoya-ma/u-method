import json
import os
from typing import Optional

from services import device_repo, tz_repo

UI_LOG_DIR = "logs"

# ✅ action は下記の定型コードのみを使う（検証・フォールバックはしない。将来増やす場合はここに追記する）
# tab(タブ切替) / click(ボタン押下) / select(選択) / execute(ジョブ実行) / cancel(停止) /
# add / edit / delete(CRUD) / toggle(有効化等の状態切替) / save(設定保存) / sync(ダウンロード/アップロード) /
# launch(外部ツール/リンク起動) / import(取込) / output(出力) / complete(TODO完了) / resize(表示領域リサイズ)


def log_action(
    tab: str,
    action: str,
    target: str,
    value=None,
    detail: Optional[dict] = None,
) -> None:
    """
    主要なUI操作を1件のJSON Lines行として logs/ui-YYYYMMDD.log に追記する。
    「ログ」タブには表示しない（services/applog.py の運用ログとは別目的の記録専用ログのため）。
    value/detail に自由記述の内容（ジョブコマンド・TODO本文・お知らせ本文・APIキー等）を含めないこと。
    書き込み失敗は握りつぶす（services/applog.py と同じ方針、ログ出力の失敗でアプリを落とさない）。

    `actor`（この端末のデバイスマスター登録上の持ち主）を自動で付与する（統合業務管理フェーズ2、
    DESIGN.md「11.2 A2/A3・E1」参照）。ログイン機構が無いため、権限判定はクライアント側限定に
    なるが、この`actor`により「誰が」を事後に追跡できる。持ち主が未設定でも必ず何かを記録する
    （`device_repo.current_owner_label()`が未設定時は物理暗号の先頭8文字にフォールバックする）
    """
    now = tz_repo.now()
    try:
        actor = device_repo.current_owner_label()
    except Exception:
        actor = ""

    entry = {
        "datetime": now.isoformat(timespec="microseconds"),
        "actor": actor,
        "tab": tab,
        "action": action,
        "target": target,
    }
    if value is not None:
        entry["value"] = value
    if detail:
        entry["detail"] = detail

    try:
        os.makedirs(UI_LOG_DIR, exist_ok=True)
        path = os.path.join(UI_LOG_DIR, f"ui-{now.strftime('%Y%m%d')}.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
