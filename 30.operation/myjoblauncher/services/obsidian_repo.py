import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import tomli_w

from services.path_utils import expand_path

CONFIG_PATH = "config/obsidian.toml"


# ========================
# ✅ データモデル
# ========================
@dataclass
class ObsidianConfig:
    vault_dir: str = ""              # Obsidian Vault、または任意の出力先フォルダ
    person_name: str = ""            # 個人単位の識別名（出力先のサブフォルダ名になる）
    default_tags_template: str = ""  # 「タグ」欄の初期値テンプレート（{yymmdd} で対象日に置換）


# ========================
# ✅ 設定読み込み・保存
# ========================
def load_obsidian_config(path: str) -> ObsidianConfig:
    if not os.path.exists(path):
        return ObsidianConfig()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return ObsidianConfig(
        vault_dir=data.get("vault_dir", ""),
        person_name=data.get("person_name", ""),
        default_tags_template=data.get("default_tags_template", ""),
    )


def save_obsidian_config(path: str, config: ObsidianConfig) -> None:
    data = {
        "vault_dir": config.vault_dir,
        "person_name": config.person_name,
        "default_tags_template": config.default_tags_template,
    }

    with open(path, "wb") as f:
        tomli_w.dump(data, f)


# ========================
# ✅ タグ既定値テンプレートの日付置換
# ========================
def render_tag_template(template: str, target_date: date) -> str:
    """
    タグ欄の初期値テンプレートを対象日で展開する。
    {yymmdd} を対象日の YYMMDD 形式（例: 2026-09-21 → 260921）に置き換える
    """
    return template.replace("{yymmdd}", target_date.strftime("%y%m%d"))


# ========================
# ✅ 日報ファイルの出力先
# ========================
def build_report_path(vault_dir: str, person_name: str, target_date: date) -> Path:
    """
    出力先: <vault_dir>/<YYYY-MM-DD>日報<person_name>.md
    （個人名はサブフォルダではなくファイル名に含める）。
    vault_dirは%USERPROFILE%等のWindows環境変数を含められる
    """
    vault_dir = expand_path(vault_dir)
    return Path(vault_dir) / f"{target_date.isoformat()}日報{person_name}.md"


def report_exists(vault_dir: str, person_name: str, target_date: date) -> bool:
    return build_report_path(vault_dir, person_name, target_date).exists()


# ========================
# ✅ Obsidianプロパティ（YAML frontmatter）
# ========================
def _yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_tags(target_date: date, extra_tags: list[str] | None = None) -> list[str]:
    """
    自動付与タグ「日報/YYYYMMDD」（Obsidianの階層タグ表記）＋ 画面から入力された追加タグ（重複除去、順序維持）
    """
    tags = [f"日報/{target_date.strftime('%Y%m%d')}"]

    for tag in extra_tags or []:
        tag = tag.strip()
        if tag and tag not in tags:
            tags.append(tag)

    return tags


def build_frontmatter(tags: list[str]) -> str:
    if not tags:
        return ""

    lines = ["---", "tags:"] + [f"  - {_yaml_quote(t)}" for t in tags] + ["---", ""]
    return "\n".join(lines)


def write_daily_report(
    vault_dir: str,
    person_name: str,
    target_date: date,
    today_results: str,
    tomorrow_plan: str,
    todo_markdown: str,
    consultation: str,
    contact: str,
    extra_tags: list[str] | None = None,
) -> Path:
    """
    「本日の作業実績」「明日の作業予定」「TODO」「相談事項」「連絡事項」をMarkdownとして
    この順で出力する（既存ファイルは上書き）。
    Obsidianのプロパティ（YAML frontmatter）として tags（日報／対象日／追加タグ）を先頭に付与する
    """
    path = build_report_path(vault_dir, person_name, target_date)
    path.parent.mkdir(parents=True, exist_ok=True)

    tags = build_tags(target_date, extra_tags)

    content = (
        build_frontmatter(tags)
        + f"\n# {target_date.isoformat()} 日報 - {person_name}\n\n"
        f"## 本日の作業実績\n\n{today_results}\n\n"
        f"## 明日の作業予定\n\n{tomorrow_plan}\n\n"
        f"## TODO\n\n{todo_markdown}\n\n"
        f"## 相談事項\n\n{consultation}\n\n"
        f"## 連絡事項\n\n{contact}\n"
    )

    path.write_text(content, encoding="utf-8")
    return path
