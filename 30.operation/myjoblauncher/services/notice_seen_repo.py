import os
import tomllib

import tomli_w

# 緊急通知のポップアップを既に表示したnotice_idの記録（このPCだけのローカル状態）。
# 共有マスター（config/portal.toml）の同期対象外で、アプリ再起動しても同じ通知を
# 繰り返しポップアップしないようにするためのもの
SEEN_PATH = "config/notice_seen.toml"


def load_seen_ids(path: str = SEEN_PATH) -> set:
    if not os.path.exists(path):
        return set()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return set(data.get("seen_notice_ids", []))


def mark_seen(notice_ids, path: str = SEEN_PATH) -> None:
    seen = load_seen_ids(path)
    seen.update(notice_ids)

    with open(path, "wb") as f:
        tomli_w.dump({"seen_notice_ids": sorted(seen)}, f)
