from services import app_config

# ✅ デスクトップ版（--gui）のウィンドウサイズの永続化（config/app.tomlのwindow_width/window_height）

DEFAULT_WIDTH = 1000
DEFAULT_HEIGHT = 720

# 安心安全機能: これより小さい/大きいサイズは異常値とみなし既定値にフォールバックする
# （何らかの原因で異常なサイズが保存され、次回起動時にウィンドウが操作不能な大きさ・
# 画面外になることを防ぐ）
MIN_WIDTH = 400
MIN_HEIGHT = 300
MAX_WIDTH = 3840
MAX_HEIGHT = 2160


def load_window_size(path: str = app_config.APP_CONFIG_PATH) -> tuple[int, int]:
    """
    保存済みのウィンドウサイズを読み込む。未設定・型不正・MIN〜MAXの範囲外の場合は
    既定値（DEFAULT_WIDTH×DEFAULT_HEIGHT）を返す
    """
    data = app_config.load(path)
    width = data.get("window_width")
    height = data.get("window_height")

    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
        return DEFAULT_WIDTH, DEFAULT_HEIGHT
    if not (MIN_WIDTH <= width <= MAX_WIDTH) or not (MIN_HEIGHT <= height <= MAX_HEIGHT):
        return DEFAULT_WIDTH, DEFAULT_HEIGHT

    return int(width), int(height)


def save_window_size(width: float, height: float, path: str = app_config.APP_CONFIG_PATH) -> None:
    app_config.save({"window_width": int(width), "window_height": int(height)}, path)
