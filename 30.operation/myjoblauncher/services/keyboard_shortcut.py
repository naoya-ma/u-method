import time

import win32api
import win32con

# ✅ Windowsキー操作（ツールタブから起動）。仮想キーコードはA-Zの範囲（0x41-0x5A）
# Win+C（Copilot）はkeybd_eventによるキー入力シミュレーションを使わず、
# `explorer.exe shell:appsFolder\Microsoft.Copilot_8wekyb3d8bbwe!App`による直接起動に
# 置き換え済み（config/tools.tomlのCopilotエントリ参照）のため、ここには含めない。
# Windows Smart App Controlがkeybd_event（合成キー入力）を警戒するパターンの一つのため、
# 直接起動できるものは順次この辞書から外していく方針
WIN_SHORTCUTS = {
    "win+r": 0x52,  # ファイル名を指定して実行
    "win+e": 0x45,  # エクスプローラー
    "win+w": 0x57,  # ウィジェット
    "win+x": 0x58,  # クイックリンク（右クリックメニュー）
    "win+v": 0x56,  # クリップボード履歴
}

SHORTCUT_PREFIX = "shortcut:"


def send_win_shortcut(key: str) -> bool:
    """
    pywin32のkeybd_eventで実際にWin+<key>のキー入力をシミュレートする。
    該当キーが無ければ何もせずFalseを返す
    """
    vk_code = WIN_SHORTCUTS.get(key)
    if vk_code is None:
        return False

    win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
    return True
