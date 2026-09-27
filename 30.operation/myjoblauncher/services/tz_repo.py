import datetime
from zoneinfo import ZoneInfo

from services import app_config

DEFAULT_TIMEZONE = "Asia/Tokyo"


def load_timezone(path: str = app_config.APP_CONFIG_PATH) -> str:
    return app_config.load(path).get("timezone") or DEFAULT_TIMEZONE


def save_timezone(tz_name: str, path: str = app_config.APP_CONFIG_PATH) -> None:
    app_config.save({"timezone": tz_name}, path)


def get_zoneinfo(tz_name: str = None) -> ZoneInfo:
    """
    不正なタイムゾーン名の場合は ZoneInfoNotFoundError を送出する（呼び出し元で検証に使う）
    """
    return ZoneInfo(tz_name or load_timezone())


def now() -> datetime.datetime:
    """
    設定されたタイムゾーンでの「壁時計」時刻をタイムゾーン情報なし(naive)で返す。
    DB(execution_history)のTIMESTAMP列や既存コードとの整合を保つため、
    tzinfo付きにはせず、値そのものを設定タイムゾーンの現地時刻にする
    """
    return datetime.datetime.now(get_zoneinfo()).replace(tzinfo=None)


def today() -> datetime.date:
    return now().date()
