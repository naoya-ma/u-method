import os
import tomllib

import tomli_w

LOG_FORMAT_PATH = "config/log_format.toml"

DEFAULT_FORMAT = "{command_id}| {datetime}| {hostname}| {app_name}| {func}| {level}| {message}"
DEFAULT_DATETIME_FORMAT = "%Y/%m/%d %H:%M:%S.%f"  # %f は標準のdatetime.strftime通りマイクロ秒6桁
DEFAULT_DESTINATIONS = ["file", "screen"]  # "file" | "screen"（複数指定可）
DEFAULT_LOG_DIR = "logs"


def load_format(path: str = LOG_FORMAT_PATH) -> dict:
    """
    運用ログ（services/applog.py）のフォーマット設定。config/log_format.toml が無い、
    またはキーが個別に欠けている場合はそれぞれ既定値にフォールバックする（未使用時はファイル自体が無い）
    """
    data = {}
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = tomllib.load(f)

    return {
        "format": data.get("format", DEFAULT_FORMAT),
        "datetime_format": data.get("datetime_format", DEFAULT_DATETIME_FORMAT),
        "destinations": data.get("destinations", DEFAULT_DESTINATIONS),
        "log_dir": data.get("log_dir", DEFAULT_LOG_DIR),
    }


def save_format(updates: dict, path: str = LOG_FORMAT_PATH) -> None:
    """既存キーとマージして保存する（他キーを消さない。専用の編集GUIは無く、直接編集での利用を想定）"""
    data = load_format(path)
    data.update(updates)
    with open(path, "wb") as f:
        tomli_w.dump(data, f)
