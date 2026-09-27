import os
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

import tomli_w

from services import app_config, tz_repo

PORTAL_PATH = "config/home.toml"

# ✅ アプリ自身が生成する、このPCだけのローカル専用お知らせ（新バージョン検知・適用完了等）。
# config/home.toml（共有マスター同期対象）とは別ファイルにし、同期の影響を受けない・
# 他ユーザーへ配信されないようにする。NoticeItem/load_notices/save_notices はどちらのファイルにも
# パス引数だけ変えて使い回せる汎用実装のため、専用のデータモデルは用意していない
SYSTEM_NOTICES_PATH = "config/system_notices.toml"

DATETIME_FORMAT = "%Y-%m-%d %H:%M"

DEFAULT_NOTICES_HEIGHT = 260


# ========================
# ✅ データモデル
# ========================
@dataclass
class NoticeItem:
    title: str                # 必須（通知タイトル）
    content: str = ""         # 通知内容（Markdown/MermaidJS）
    publish_at: str = ""      # 公開日時（"YYYY-MM-DD HH:MM"）。空欄は「即時公開」扱い
    duration_days: int = 7    # 通知期間（日数）。公開日時からこの日数が経過すると非表示になる
    urgent: bool = False      # 緊急通知フラグ（公開日時到来時にポップアップ表示）
    notice_id: str = ""       # 自動採番される安定識別子（例: "N001"）


@dataclass
class PortalConfig:
    content: str = ""         # ホーム画面本文（Markdown/MermaidJS）
    updated_at: str = ""      # 最終更新日時（"YYYY-MM-DD HH:MM"）。キャッシュの新旧判定に使う


# ========================
# ✅ 読み込み・書き込み（[[notices]] と [portal] は互いを消さないようマージして書く）
# ========================
def _load_raw(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_notices(path: str = PORTAL_PATH) -> List[NoticeItem]:
    data = _load_raw(path)
    items = []
    for m in data.get("notices", []):
        items.append(
            NoticeItem(
                title=m.get("title", ""),
                content=m.get("content", ""),
                publish_at=m.get("publish_at", ""),
                duration_days=m.get("duration_days", 7),
                urgent=bool(m.get("urgent", False)),
                notice_id=m.get("notice_id", ""),
            )
        )

    assigned = False
    for item in items:
        if not item.notice_id:
            item.notice_id = next_notice_id(items)
            assigned = True
    if assigned:
        save_notices(items, path)

    return items


def save_notices(notices: List[NoticeItem], path: str = PORTAL_PATH) -> None:
    """[portal] セクションは既存の内容のまま、[[notices]] だけを書き換える"""
    data = _load_raw(path)
    data["notices"] = [
        {
            "notice_id": n.notice_id,
            "title": n.title,
            "content": n.content,
            "publish_at": n.publish_at,
            "duration_days": n.duration_days,
            "urgent": n.urgent,
        }
        for n in notices
    ]
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def load_system_notices(path: str = SYSTEM_NOTICES_PATH) -> List[NoticeItem]:
    return load_notices(path)


def add_system_notice(
    title: str, content: str, duration_days: int = 7, path: str = SYSTEM_NOTICES_PATH
) -> None:
    """
    ローカル専用お知らせ（config/system_notices.toml）を1件追加する。
    同じtitleの通知が既にあれば何もしない（起動のたびに実行される更新検知処理等から繰り返し
    呼ばれても、同じ内容を重複して積み上げないための簡易な重複排除。titleにバージョン番号を
    含めておけば、バージョンが変わった時だけ新しい通知として追加される）。
    `publish_at`を明示的に現在時刻で設定する（空欄のままだと`is_expired()`が常にFalseを返し、
    `duration_days`を指定しても掲載期間経過後に自動で消えなくなるため）
    """
    items = load_notices(path)
    if any(item.title == title for item in items):
        return
    publish_at = tz_repo.now().strftime(DATETIME_FORMAT)
    items.append(
        NoticeItem(title=title, content=content, publish_at=publish_at, duration_days=duration_days)
    )
    save_notices(items, path)


def next_notice_id(items: List[NoticeItem]) -> str:
    """次に採番する通知ID（例: N001）。既存の最大値の次から採番し、欠番は再利用しない"""
    existing_numbers = [
        int(item.notice_id[1:])
        for item in items
        if item.notice_id.startswith("N") and item.notice_id[1:].isdigit()
    ]
    return f"N{max(existing_numbers, default=0) + 1:03d}"


def load_portal_config(path: str = PORTAL_PATH) -> PortalConfig:
    data = _load_raw(path)
    portal = data.get("portal", {})
    return PortalConfig(
        content=portal.get("content", ""),
        updated_at=portal.get("updated_at", ""),
    )


def save_portal_config(config: PortalConfig, path: str = PORTAL_PATH) -> None:
    """[[notices]] セクションは既存の内容のまま、[portal] だけを書き換える"""
    data = _load_raw(path)
    data["portal"] = {"content": config.content, "updated_at": config.updated_at}
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


# ========================
# ✅ 公開判定（公開日時・通知期間）
# ========================
def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, DATETIME_FORMAT)
    except ValueError:
        return None


def is_published(notice: NoticeItem, now: datetime) -> bool:
    publish_at = _parse_datetime(notice.publish_at)
    if publish_at is None:
        return True  # 公開日時未設定は即時公開扱い
    return now >= publish_at


def is_expired(notice: NoticeItem, now: datetime) -> bool:
    publish_at = _parse_datetime(notice.publish_at)
    if publish_at is None:
        return False
    return now >= publish_at + timedelta(days=notice.duration_days)


def visible_notices(notices: List[NoticeItem], now: datetime) -> List[NoticeItem]:
    """公開日時が来ていて、通知期間内のものだけを、公開日時の新しい順で返す"""
    shown = [n for n in notices if is_published(n, now) and not is_expired(n, now)]
    shown.sort(key=lambda n: n.publish_at, reverse=True)
    return shown


def pending_urgent_notices(notices: List[NoticeItem], now: datetime, already_seen_ids) -> List[NoticeItem]:
    """
    緊急通知のうち、公開日時が来ていて・期限切れでなく・まだポップアップ表示していないものを返す
    （already_seen_idsは services/notice_seen_repo.py の load_seen_ids() を渡す）
    """
    return [
        n
        for n in notices
        if n.urgent
        and is_published(n, now)
        and not is_expired(n, now)
        and n.notice_id not in already_seen_ids
    ]


# ========================
# ✅ 画面レイアウト設定（お知らせメッセージ表示エリアの高さ）
# ========================
def load_notices_height(path: str = app_config.APP_CONFIG_PATH) -> int:
    """
    ホームタブの「お知らせメッセージ」表示エリアの高さ（px）。
    このPCだけのローカル表示設定で、config/home.toml（共有マスター同期対象）には含めない
    （config/app.tomlの他キー同様、手動編集でも指定できる）
    """
    return app_config.load(path).get("portal_notices_height", DEFAULT_NOTICES_HEIGHT)


def save_notices_height(height: int, path: str = app_config.APP_CONFIG_PATH) -> None:
    app_config.save({"portal_notices_height": height}, path)
