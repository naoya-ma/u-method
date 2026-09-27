"""
項目単位の同期（統合業務管理フェーズ3、DESIGN.md「11. 統合業務管理（項目単位同期）」
11.3 フェーズ3 R13〜R15を参照）。`config/menu.toml`のようなファイル全体の丸ごと上書きではなく、
ジョブ（`MenuItem`）1件ごとを`job_id`で対応付けて安全にマージするための基盤。

**現状はこのモジュール単体（マージ計算ロジックのみ）で、実際の「マスターをダウンロード/
アップロード」ボタン（gui/settings_tab.py）へはまだ組み込んでいない。** 既存の丸ごと同期は
実運用で使われている（実際の共有フォルダに書き込む）ため、切り替えは別途の判断・検証を
経てから行う。このモジュールは`services/config_loader.MenuItem`専用（他の項目種別に一般化
した抽象化はまだ行わない。汎用化が必要になった時点で検討する）
"""

import hashlib
import os
from dataclasses import asdict

import tomllib
import tomli_w

# ✅ 前回の同期時点における各項目（job_id）の内容ハッシュのローカルスナップショット
# （このPCだけのローカル状態、共有マスター同期の対象外）。「両方で変更された（真の衝突）」を
# 判定するための基準点（gitのmerge-baseに相当）
SYNC_BASE_PATH = "config/menu_sync_base.toml"


def hash_item(item) -> str:
    """job_id自体は比較対象に含めず、他の全フィールドから内容ハッシュを作る"""
    data = asdict(item)
    data.pop("job_id", None)
    canonical = "|".join(f"{k}={data[k]}" for k in sorted(data))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_sync_base(path: str = SYNC_BASE_PATH) -> dict:
    if not os.path.exists(path):
        return {}

    with open(path, "rb") as f:
        return tomllib.load(f).get("hashes", {})


def save_sync_base(hashes: dict, path: str = SYNC_BASE_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump({"hashes": hashes}, f)


def merge_menu_items(local_items, remote_items, base_hashes: dict):
    """
    job_idで対応付け、`base_hashes`（前回同期時点の内容ハッシュ、`load_sync_base()`で読む）と
    比較して安全にマージする。

    - 片方にしか存在しない項目は「新規追加」として採用する。ただし`base_hashes`に記録があり、
      かつ存在する側の内容がそのハッシュと一致する（＝前回同期後に変更されていない）場合は、
      「もう片方で削除された」と解釈し、削除を伝播する（マージ結果に含めない）
    - 両方に存在する項目は、それぞれが`base_hashes`と比較して変更されているかを見る:
      - 内容が完全に一致 → そのまま採用
      - どちらか一方だけ変更（`base_hashes`に記録が無い場合は両方「変更あり」とみなす、
        安全側に倒すため） → 変更された方を採用
      - 両方変更されている → 真の衝突として`conflicts`に積み、`merged`には一旦ローカルを残す
        （呼び出し側が人に確認を求め、選択結果で上書きする前提。このモジュール自身は
        ダイアログ等のUIを持たない）。**このとき`new_hashes`にはこのjob_idのハッシュを
        意図的に記録しない**（実機で確認済みの重大な不具合の修正: 記録してしまうと、
        次回同期時に「ローカルの内容が新しい基準点」として扱われ、リモート側が今回と
        全く同じ〈未解決の〉内容のままでも「リモート側だけが変更された」と誤認し、
        無警告でリモートの内容へ静かに切り替わってしまう。記録を省略しておくことで、
        両者の内容が実際に一致するまで、同じ衝突が毎回正しく再検出され続ける）

    戻り値: (merged_items, conflicts, new_hashes, stats)
      merged_items: マージ後の項目リスト（順序は保証しない、呼び出し側で並べ替えること）
      conflicts: [(job_id, local_item, remote_item), ...]
      new_hashes: マージ後の内容で作り直した{job_id: hash}（次回の`base_hashes`として
        `save_sync_base()`で保存する）
      stats: 差分件数の内訳（診断ログ出力用。マージのループ内でその場で集計するため、
        どの項目もどこかのバケツに必ず入り、取りこぼし〈後述の実際に踏んだ不具合〉が無い）。
        キー: `local_count`（マージ前のローカル件数）/`remote_count`（比較対象の件数）/
        `merged_count`（マージ後の件数）/`added`（ローカルに無かった項目がリモートから
        新規に取り込まれた数）/`updated`（両方に存在し、リモート側の変更が採用された数）/
        `unchanged`（マージ後もローカルの内容がそのまま残った数、内容が完全一致・
        ローカルのみ変更・衝突で結局ローカルを残したケースを含む）/`removed`（ローカルに
        あった項目が「相手側で削除された」と判定されマージ後に無くなった数）/
        `not_restored`（リモートにあった項目が「こちら側で既に削除済み」と判定され、
        取り込まれなかった数。下記の既知の限界の直接的な結果で、この数が想定外に大きい
        場合はこのPCの`config/menu_sync_base.toml`が実際の同期履歴と整合していない
        〈他デバイスからのコピー等〉疑いがある）/`conflicts`（真の衝突件数、
        `len(conflicts)`と同じ）/`removed_items`・`not_restored_items`（`removed`/
        `not_restored`の件数だけでは対象のジョブ名が分からず切り分けできないため、
        該当した`MenuItem`そのものを積んだリスト。診断ログでジョブ名を表示する用途）

    **削除の扱いについての既知の限界（実機で実際に踏んだ不具合）**: `base_hashes`
    （`config/menu_sync_base.toml`）はこのPCだけのローカル状態のはずだが、新規端末の
    セットアップ時に既存端末のconfigフォルダを丸ごとコピーする等で、実際にはこのPCが
    一度も同期していない項目のハッシュが紛れ込むことがある。この場合、「そのPCには
    存在しないが相手には存在する」項目を「相手が削除した」と誤認し、正当な項目が
    永久に復元されなくなる（`not_restored`が実際にはゼロであるべき状況で不自然に
    大きくなる）。**新しくPC/デバイスをセットアップする場合、`config/menu_sync_base.toml`
    は絶対に他デバイスからコピーせず、空の状態（ファイル自体が無い状態）から
    始めること。** job_idが一度も`base_hashes`に記録されていない（＝一度も同期を
    経ていない）状態で片方にしか存在しない項目は、常に「新規追加」として扱われる
    （このため`base_hashes`が空であれば、この不具合は原理的に起こらない）
    """
    local_by_id = {item.job_id: item for item in local_items if item.job_id}
    remote_by_id = {item.job_id: item for item in remote_items if item.job_id}
    all_ids = set(local_by_id) | set(remote_by_id)

    merged = []
    conflicts = []
    new_hashes = {}
    added = 0
    updated = 0
    unchanged = 0
    removed = 0
    not_restored = 0
    removed_items = []  # ✅ 診断ログでどのジョブが対象だったか名前を示すため、件数だけでなく中身も残す
    not_restored_items = []

    for job_id in all_ids:
        local_item = local_by_id.get(job_id)
        remote_item = remote_by_id.get(job_id)
        base_hash = base_hashes.get(job_id)

        if remote_item is None:
            # ローカルにのみ存在: 新規追加、またはリモート側で削除された
            if base_hash is not None and hash_item(local_item) == base_hash:
                removed += 1  # 変更されていないのに相手に無い＝相手側で削除された
                removed_items.append(local_item)
                continue
            merged.append(local_item)
            new_hashes[job_id] = hash_item(local_item)
            unchanged += 1  # ローカルの内容そのままなので「変化なし」
            continue

        if local_item is None:
            # リモートにのみ存在: 新規追加、またはローカルで削除された
            if base_hash is not None and hash_item(remote_item) == base_hash:
                not_restored += 1  # こちら側で削除済みと判定し、取り込まなかった
                not_restored_items.append(remote_item)
                continue
            merged.append(remote_item)
            new_hashes[job_id] = hash_item(remote_item)
            added += 1
            continue

        # 両方に存在する
        local_hash = hash_item(local_item)
        remote_hash = hash_item(remote_item)

        if local_hash == remote_hash:
            merged.append(local_item)
            new_hashes[job_id] = local_hash
            unchanged += 1
            continue

        local_changed = base_hash is None or local_hash != base_hash
        remote_changed = base_hash is None or remote_hash != base_hash

        if local_changed and remote_changed:
            conflicts.append((job_id, local_item, remote_item))
            merged.append(local_item)
            # ✅【重要・実機で確認済みの不具合】ここで`new_hashes[job_id] = local_hash`と
            # 記録してしまうと、次回の同期で「ローカルの内容が新しい基準点」として扱われる。
            # すると、リモート側が今回と同じ（未解決の）内容のままでも「リモート側だけが
            # 変更された」と誤認し、次回は無警告でリモートの内容へ静かに切り替わってしまう
            # （＝衝突が一度しか検出されず、その後は解決していないのに片方の内容が
            # 気付かれずに勝手に採用され続ける）。base_hashesへの記録を意図的に省略し、
            # このjob_idを「まだ一度も同期が確定していない」状態のままにしておくことで、
            # 次回以降も両者の内容が現状のまま食い違っている限り必ず衝突として再検出される
            # （人が実際にどちらかの内容を変更するまで、毎回ローカルを維持しつつ警告し続ける）
            unchanged += 1  # 衝突のためローカルの内容を維持＝ローカルから見て変化なし
        elif remote_changed:
            merged.append(remote_item)
            new_hashes[job_id] = remote_hash
            updated += 1
        else:
            merged.append(local_item)
            new_hashes[job_id] = local_hash
            unchanged += 1

    stats = {
        "local_count": len(local_by_id),
        "remote_count": len(remote_by_id),
        "merged_count": len(merged),
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "removed": removed,
        "not_restored": not_restored,
        "conflicts": len(conflicts),
        "removed_items": removed_items,
        "not_restored_items": not_restored_items,
    }

    return merged, conflicts, new_hashes, stats


def format_sync_progress_lines(
    stats: dict,
    verb: str = "ダウンロード",
    existing_label: str = "既存件数",
    incoming_label: str = "ダウンロード件数",
) -> tuple[str, str]:
    """
    `merge_menu_items()`が返す`stats`から、開始時・完了時の診断ログ2行を組み立てる
    （ユーザーからの要望: 何件ダウンロードして何件上書き・スキップしたのかログ・コンソールで
    切り分けできるようにする）。ダウンロード/アップロードの両方の呼び出し元で使う共通の
    ヘルパーで、`verb`/`existing_label`/`incoming_label`だけ呼び出し側の文脈に合わせて渡す
    （`stats`自体は常に「マージ前のローカル」を基準に集計されているため、アップロード時は
    incoming_label を「マスター件数」等に変え、「既存件数」＝このPCの件数として読む）

    戻り値: (開始行, 完了行)。`removed`/`not_restored`が1件以上ある場合、完了行の末尾に
    対象のジョブ名（先頭5件、`stats['removed_items']`/`stats['not_restored_items']`から）
    を付記する（件数だけでは対象が分からず切り分けできないため）
    """
    diff = stats["added"] - stats["removed"]
    sign = "+" if diff >= 0 else ""

    start_line = (
        f"メニュー項目の差分{verb}を開始します。"
        f"{existing_label}={stats['local_count']}, {incoming_label}={stats['remote_count']}"
    )

    def _names(items: list, limit: int = 5) -> str:
        shown = "、".join(f"「{it.name}」" for it in items[:limit])
        more = f" 他{len(items) - limit}件" if len(items) > limit else ""
        return f"{shown}{more}"

    detail_parts = [
        f"{incoming_label}={stats['remote_count']}",
        f"追加={stats['added']}",
        f"更新={stats['updated']}",
        f"スキップ={stats['unchanged']}",
    ]
    if stats["removed"]:
        detail_parts.append(f"削除={stats['removed']}（{_names(stats['removed_items'])}）")
    if stats["not_restored"]:
        detail_parts.append(f"否認={stats['not_restored']}（{_names(stats['not_restored_items'])}）")
    if stats["conflicts"]:
        detail_parts.append(f"衝突={stats['conflicts']}")

    end_line = (
        f"メニュー項目の差分{verb}が完了しました。{', '.join(detail_parts)}"
        f" --> 既存{stats['local_count']}, 差分={sign}{diff}, 合計={stats['merged_count']}"
    )

    return start_line, end_line
