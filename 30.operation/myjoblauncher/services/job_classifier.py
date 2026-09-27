from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Set

WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]   # 0=月曜(APScheduler/Python .weekday()と同じ)
WEEKDAY_NAME_TO_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass
class JobClassification:
    daily: bool = False
    weekly_days: List[str] = field(default_factory=list)
    monthly_days: List[int] = field(default_factory=list)
    other: bool = False


# ========================
# ✅ cron設定からの分類（スケジュール登録済みジョブ）
# ========================
def _parse_cron_field(value: str) -> Optional[Set[int]]:
    """
    "*" は制限なし(None)、それ以外はカンマ区切り/範囲/曜日名を数値集合にして返す
    """
    value = value.strip()
    if value == "*":
        return None

    result: Set[int] = set()
    for part in value.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if part in WEEKDAY_NAME_TO_INDEX:
            result.add(WEEKDAY_NAME_TO_INDEX[part])
        elif "-" in part:
            a, b = part.split("-", 1)
            if a.strip().isdigit() and b.strip().isdigit():
                result.update(range(int(a), int(b) + 1))
        elif part.isdigit():
            result.add(int(part))

    return result


def _classify_from_schedule(schedule: str) -> Optional[JobClassification]:
    parts = schedule.split()
    if len(parts) != 5:
        return None

    _minute, _hour, day, _month, day_of_week = parts

    day_vals = _parse_cron_field(day)
    dow_vals = _parse_cron_field(day_of_week)

    if day_vals is None and dow_vals is None:
        return JobClassification(daily=True)

    if day_vals is None and dow_vals is not None:
        labels = [WEEKDAY_JP[d % 7] for d in sorted(dow_vals)]
        return JobClassification(weekly_days=labels)

    if day_vals is not None and dow_vals is None:
        return JobClassification(monthly_days=sorted(day_vals))

    return JobClassification(other=True)


# ========================
# ✅ 実行履歴からの分類推定（スケジュール未登録ジョブ）
# ========================
def _classify_from_history(run_dates: List[date]) -> JobClassification:
    if len(run_dates) < 3:
        return JobClassification(other=True)

    span_days = (max(run_dates) - min(run_dates)).days
    weekdays = {d.weekday() for d in run_dates}
    days_of_month = {d.day for d in run_dates}

    if len(weekdays) >= 6:
        return JobClassification(daily=True)

    if span_days >= 7:
        weekday_counts = Counter(d.weekday() for d in run_dates)
        if len(weekday_counts) <= 5 and all(c >= 2 for c in weekday_counts.values()):
            labels = [WEEKDAY_JP[d] for d in sorted(weekday_counts)]
            return JobClassification(weekly_days=labels)

    if span_days >= 45:
        dom_counts = Counter(d.day for d in run_dates)
        if len(dom_counts) <= 5 and all(c >= 2 for c in dom_counts.values()):
            return JobClassification(monthly_days=sorted(dom_counts))

    return JobClassification(other=True)


# ========================
# ✅ 公開関数
# ========================
def classify_job(item, run_dates: List[date]) -> JobClassification:
    """
    schedule(cron)が設定されていればそれを正として分類し、
    未設定なら実行履歴の日付パターンから推定する
    """
    if getattr(item, "schedule", ""):
        result = _classify_from_schedule(item.schedule)
        if result is not None:
            return result

    return _classify_from_history(run_dates)
