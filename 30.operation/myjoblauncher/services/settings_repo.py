import base64
import os
import tomllib
from dataclasses import dataclass
from typing import List

import tomli_w
import win32crypt


# ========================
# ✅ データモデル
# ========================
@dataclass
class ApiKeyItem:
    name: str
    url: str = ""
    key_encrypted: str = ""   # DPAPI暗号文（Base64）
    note: str = ""


# ========================
# ✅ DPAPI暗号化・復号
# ========================
def encrypt_secret(plain: str) -> str:
    """
    現在ログイン中のWindowsユーザーの資格情報に紐づけて暗号化する。
    他ユーザー・他PCでは復号できない。
    """
    cipher = win32crypt.CryptProtectData(plain.encode("utf-8"), None, None, None, None, 0)
    return base64.b64encode(cipher).decode("ascii")


def decrypt_secret(cipher_b64: str) -> str:
    if not cipher_b64:
        return ""

    cipher = base64.b64decode(cipher_b64)
    _, plain = win32crypt.CryptUnprotectData(cipher, None, None, None, 0)
    return plain.decode("utf-8")


# ========================
# ✅ 読み込み・書き込み
# ========================
def load_api_keys(path: str) -> List[ApiKeyItem]:
    if not os.path.exists(path):
        return []

    with open(path, "rb") as f:
        data = tomllib.load(f)

    items: List[ApiKeyItem] = []

    for a in data.get("api_key", []):
        name = a.get("name")

        if not name:
            continue

        items.append(
            ApiKeyItem(
                name=name,
                url=a.get("url", ""),
                key_encrypted=a.get("key_encrypted", ""),
                note=a.get("note", ""),
            )
        )

    return items


def save_api_keys(path: str, items: List[ApiKeyItem]) -> None:
    data = {
        "api_key": [
            {
                "name": item.name,
                "url": item.url,
                "key_encrypted": item.key_encrypted,
                "note": item.note,
            }
            for item in items
        ]
    }

    with open(path, "wb") as f:
        tomli_w.dump(data, f)
