"""
統合業務管理フェーズ4: ジョブの集計（成熟度・Tier別集計、停滞ジョブの抽出。
DESIGN.md「11.3」フェーズ4参照）
"""

from dataclasses import dataclass
from datetime import date, timedelta

from services.config_loader import MenuItem, is_skeleton_job
from services import tz_repo

DEFAULT_STALLED_DAYS = 30


@dataclass
class JobAggregation:
    maturity_counts: dict  # {0〜5: 件数}
    tier_counts: dict  # {Tier名(空文字="未設定"): 件数}
    stalled_jobs: list  # 骨組み状態のまま長期間放置されているジョブ（MenuItemのリスト）
    stalled_days: int


def _parse_date(value: str):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def compute_job_aggregation(menu_items: list, stalled_days: int = DEFAULT_STALLED_DAYS) -> JobAggregation:
    """
    成熟度別・Tier別のジョブ件数集計と、「骨組み状態（`services.config_loader.is_skeleton_job()`
    が真＝成熟度未設定・command未設定）のまま`stalled_days`日以上動きが無いジョブ」の抽出を行う。
    基準日は`updated_at`（無ければ`created_at`）。両方とも空（日付未設定・旧データ）の場合は
    判定できないため停滞ジョブには含めない（誤判定で無関係な古いジョブまで大量に挙がるのを防ぐ）
    """
    maturity_counts = {n: 0 for n in range(6)}
    tier_counts: dict = {}
    stalled_jobs = []

    today = tz_repo.today()
    threshold = today - timedelta(days=stalled_days)

    for item in menu_items:
        maturity_counts[item.maturity] = maturity_counts.get(item.maturity, 0) + 1
        tier_counts[item.tier] = tier_counts.get(item.tier, 0) + 1

        if is_skeleton_job(item):
            base_date = _parse_date(item.updated_at) or _parse_date(item.created_at)
            if base_date is not None and base_date <= threshold:
                stalled_jobs.append(item)

    return JobAggregation(
        maturity_counts=maturity_counts,
        tier_counts=tier_counts,
        stalled_jobs=stalled_jobs,
        stalled_days=stalled_days,
    )
