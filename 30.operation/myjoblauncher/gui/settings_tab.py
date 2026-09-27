import os
import threading
import time
from zoneinfo import ZoneInfoNotFoundError

import flet as ft

from gui.confirm_dialog import show_confirm_dialog
from gui.item_form_dialog import show_item_form_dialog
from gui.job_editor import open_add_job_dialog, open_edit_job_dialog
from gui.markdown_preview_dialog import show_markdown_preview_dialog
from gui.notice_editor import open_add_notice_dialog, open_edit_notice_dialog
from gui.safe_update import safe_update
from gui.service_table_editor import open_service_table_editor_dialog
from gui.toast import show_toast
from services.config_loader import (
    TIER_SHARED_KEYS,
    MenuItem,
    create_storage,
    is_storage_enabled,
    load_config,
    load_storage_config,
    load_sync_config,
    load_tier_config,
    save_config,
)
from services.settings_repo import ApiKeyItem, encrypt_secret, load_api_keys, save_api_keys
from services import (
    applog,
    app_update_repo,
    device_repo,
    item_sync,
    job_import_export,
    job_stats,
    portal_repo,
    stopwatch_repo,
    sync_service,
    theme_repo,
    tier_repo,
    tz_repo,
    ui_log,
)
from services.path_utils import expand_path

MENU_PATH = "config/menu.toml"
SETTINGS_PATH = "config/settings.toml"

API_KEY_FIELDS = [
    {"key": "name", "label": "名前（例: Redmine）", "type": "text"},
    {"key": "url", "label": "URL", "type": "text"},
    {"key": "key", "label": "APIキー", "type": "password", "hint": "変更する場合のみ入力してください"},
    {"key": "note", "label": "備考", "type": "text"},
]


class SettingsTab:
    """
    設定タブ。ジョブ管理・ストレージ設定・APIキー管理を行う。
    """

    def __init__(self, page: ft.Page, menu_items: list[MenuItem], on_menu_changed):
        self.page = page
        self.menu_items = menu_items                 # MainWindowと共有するリスト
        self.on_menu_changed = on_menu_changed        # () -> None（保存後にRunTab側を再読込）

        self.storage_config = load_storage_config(MENU_PATH)
        self.sync_config = load_sync_config(MENU_PATH)
        self.tier_config = load_tier_config(MENU_PATH)              # Tier1〜8名（全体共有）
        self.personal_tier_name = tier_repo.load_personal_tier_name()  # Tier9名（個人のみ）
        self.api_keys = load_api_keys(SETTINGS_PATH)

        self.job_list = ft.ListView(spacing=2, height=440)

        # ✅ 統合業務管理フェーズ4: ジョブの一括インポート/エクスポート・集計
        # （DESIGN.md「11.3」フェーズ4、services/job_import_export.py・services/job_stats.py参照）
        self.job_export_path_field = ft.TextField(
            label="エクスポート先ファイルパス（.xlsx）",
            value=r"%USERPROFILE%\Desktop\myJobLauncher_jobs.xlsx",
            tooltip="ジョブ一覧を書き出すExcelファイルのパス。"
            "%USERPROFILE%等のWindows環境変数が使えます",
            width=1920,
        )
        self.job_import_path_field = ft.TextField(
            label="インポート元ファイルパス（.xlsx）",
            tooltip="一括インポートするExcelファイルのパス。"
            "%USERPROFILE%等のWindows環境変数が使えます",
            width=1920,
        )
        self.job_import_mode_dropdown = ft.Dropdown(
            label="インポートモード",
            value=job_import_export.MODE_ADD,
            options=[
                ft.DropdownOption(key=job_import_export.MODE_ADD, text="新規追加のみ（job_id列は無視）"),
                ft.DropdownOption(
                    key=job_import_export.MODE_UPDATE, text="更新のみ（job_id列必須・一致した行だけ更新）"
                ),
            ],
            tooltip="「新規追加のみ」は全行を新しいジョブとして追加します（job_id列があっても無視）。"
            "「更新のみ」はjob_id列が既存ジョブと一致する行だけ内容を更新し、"
            "一致しない行はスキップします（誤って無関係な行を追加しないための安全設計）",
            width=560,
        )
        self.job_aggregation_container = ft.Column(visible=False, spacing=4)
        self.api_key_list = ft.ListView(spacing=2, height=180)
        self.notice_list = ft.ListView(spacing=2, height=360)

        self.notices = portal_repo.load_notices()
        self.portal_config = portal_repo.load_portal_config()
        self.portal_content_field = ft.TextField(
            label="ホーム本文（Markdown/MermaidJS）",
            value=self.portal_config.content,
            multiline=True,
            min_lines=16,
            max_lines=16,
            width=2400,
            tooltip="ホームタブに表示する本文。16行を超える入力は内部スクロールで表示されます",
        )

        self.storage_enabled_switch = ft.Switch(
            label="ストレージ設定を有効にする",
            value=self.storage_config.get("enabled", True),
            tooltip="OFFにすると、共有マスター/ホーム定義の同期（自動・手動とも）、"
            "アプリ更新の検知・ダウンロード・適用を一切行わなくなります"
            "（下記のパス等の設定は残ったまま、全体を止める1つのスイッチです）",
        )
        self.storage_type = ft.Dropdown(
            label="ストレージ種別",
            value=self.storage_config.get("type", "local"),
            options=[ft.DropdownOption(key=k, text=k) for k in ("local", "graph", "flow")],
            tooltip="OneDrive/SharePoint連携の方式（graph/flowは開発中のため未動作です）",
            on_select=self._handle_storage_type_change,
        )
        self.storage_base_dir = ft.TextField(
            label="ローカル保存先フォルダ",
            value=self.storage_config.get("local", {}).get("base_dir", ""),
            tooltip="ストレージ種別が local のときに使うフォルダパス"
            "（%USERPROFILE%や%OneDriveCommercial%等の環境変数が使えます）",
            visible=self.storage_type.value == "local",
            width=1920,
        )
        self.storage_flow_url = ft.TextField(
            label="Power Automate 呼び出しURL",
            value=self.storage_config.get("flow", {}).get("url", ""),
            tooltip="ストレージ種別が flow のときに使うHTTPトリガーURL",
            visible=self.storage_type.value == "flow",
        )
        self.sync_remote_path = ft.TextField(
            label="共有マスター設定ファイルのパス",
            value=self.sync_config.get("remote_path", "menu.toml"),
            tooltip="上記ストレージ設定を基準にした、共有マスター設定ファイルの相対パス/ファイル名",
        )
        self.sync_portal_remote_path = ft.TextField(
            label="共有ホーム定義ファイルのパス",
            value=self.sync_config.get("portal_remote_path", "home.toml"),
            tooltip="上記ストレージ設定を基準にした、共有ホーム定義ファイル（お知らせ・ホーム本文）の相対パス/ファイル名",
        )
        self.sync_app_update_manifest_remote_path = ft.TextField(
            label="アプリ更新マニフェストのパス（省略可）",
            value=self.sync_config.get("app_update_manifest_remote_path", ""),
            tooltip="上記ストレージ設定を基準にした、アプリ更新マニフェスト（バージョン情報）ファイルの相対パス/ファイル名。空欄なら更新チェックをしない",
            width=1920,
        )
        self.sync_app_update_archive_remote_path = ft.TextField(
            label="アプリ更新ZIPのパス（省略可）",
            value=self.sync_config.get("app_update_archive_remote_path", ""),
            tooltip="上記ストレージ設定を基準にした、アプリ更新パッケージ（ZIP）ファイルの相対パス/ファイル名",
            width=1920,
        )

        self.timezone_field = ft.TextField(
            label="タイムゾーン（IANA名）",
            value=tz_repo.load_timezone(),
            tooltip="日付・時刻の基準タイムゾーン（例: Asia/Tokyo）。実行履歴・日報・スケジュール実行に使用。"
            "スケジュール実行への反映にはアプリの再起動が必要です",
            width=260,
        )

        self.stopwatch_identifier_field = ft.TextField(
            label="識別子（ユーザー名）",
            value=stopwatch_repo.load_identifier(),
            tooltip="非定型ジョブの実行時に業務記録プラグイン（ストップウォッチ）へ渡す識別子（ユーザー名）",
            width=260,
        )

        self.stopwatch_html_path_field = ft.TextField(
            label="業務記録プラグインの起動先HTMLパス",
            value=stopwatch_repo.load_html_path(),
            tooltip="非定型ジョブの実行時に開くHTMLファイルのパス（file://等のスキームは付けない）。"
            "%USERPROFILE%等の環境変数が使えます。例: %USERPROFILE%\\box\\stopwatch\\js-swatch.html",
            width=880,
        )

        self.theme_dropdown = ft.Dropdown(
            label="テーマ",
            value=theme_repo.load_theme(),
            options=[
                ft.DropdownOption(key=key, text=theme_repo.THEME_LABELS[key])
                for key in theme_repo.THEMES
            ],
            tooltip="画面の配色テーマ。保存すると即座に切り替わります",
            width=260,
        )

        self.tier_fields: dict[str, ft.TextField] = {
            key: ft.TextField(
                label=f"Tier{key[4:]} 名称（空欄でこのTierを使わない）",
                value=self.tier_config.get(key, ""),
                tooltip="全体共有のTier。共有マスター（menu.toml）と一緒に同期されます",
                width=220,
            )
            for key in TIER_SHARED_KEYS
        }
        self.tier9_field = ft.TextField(
            label="Tier9 名称（個人用・必須）",
            value=self.personal_tier_name,
            tooltip="このPC/ユーザーのみのTier。共有マスターとは同期されません",
            width=220,
        )

        # ✅ 統合業務管理（項目単位同期）フェーズ1: デバイス管理（DESIGN.md「11. 統合業務管理」参照）。
        # 物理暗号（ULID）は初回起動時に自動生成され不変。論理番号はmasterロールが割り当てる
        self.device_identity = device_repo.load_local_identity()
        self.devices_cache = device_repo.load_devices()

        self.device_id_field = ft.TextField(
            label="物理暗号（ULID）",
            value=self.device_identity.device_id,
            read_only=True,
            tooltip="この端末を一意に識別するID。初回起動時に自動生成され、以後変更されません",
            width=880,
        )
        self.device_logical_number_field = ft.TextField(
            label="論理番号",
            value=self.device_identity.logical_number or "（未割当）",
            read_only=True,
            tooltip="masterロールの端末が割り当てる管理用の番号（0000=基盤、1001以降=実運用端末）",
            width=220,
        )
        self.device_owner_field = ft.TextField(
            label="持ち主（利用者名）",
            value=self.device_identity.owner,
            tooltip="この端末を主に使う利用者名",
            width=260,
        )
        self.device_role_dropdown = ft.Dropdown(
            label="ロール",
            value=self.device_identity.role,
            options=[
                ft.DropdownOption(key=device_repo.ROLE_MEMBER, text="member（通常端末）"),
                ft.DropdownOption(key=device_repo.ROLE_MASTER, text="master（デバイス管理者）"),
            ],
            tooltip="masterはデバイス一覧のダウンロード/アップロード（論理番号の割り当て）ができます。"
            "memberは自分の情報のアップロードのみ行います",
            width=260,
            on_select=self._handle_device_role_change,
        )
        self.device_list = ft.ListView(spacing=2, height=240)
        self.device_master_container = ft.Column(
            visible=self.device_identity.role == device_repo.ROLE_MASTER,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("デバイス一覧（管理者用）", weight=ft.FontWeight.BOLD, expand=True),
                        ft.Button(
                            "デバイス一覧を取得",
                            icon=ft.Icons.SYNC,
                            tooltip="共有ストレージのdevices/配下から全端末の登録状況をダウンロード・集約する",
                            on_click=self._sync_devices_master,
                        ),
                    ]
                ),
                ft.Container(content=self.device_list, border=ft.Border.all(1, ft.Colors.OUTLINE)),
            ],
        )

        self.app_update_container = ft.Column(spacing=4)

        # ✅ 統合業務管理ロードマップ項目30「設定タブの分類タブ化」: 従来は全セクションを
        # 1本の縦長スクロールに積んでいたが、セクション数が増えて見通しが悪くなったため、
        # 分類ごとにft.Tabsで分割する（左メニューのNavigationRailとは軸が違う〈横方向のタブ〉ため
        # 二重のタブ構造には見えない設計）。各タブの中身は従来通りのft.Column（タブごとに
        # 独立してスクロール）で、既存のコントロールインスタンス・保存処理は一切変更していない
        # （並べ替えただけ）。分類はDESIGN.md「10. 今後のロードマップ」項目30の分類案に従う
        general_tab = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
            controls=[
                ft.Text("アプリ設定", weight=ft.FontWeight.BOLD),
                self.timezone_field,
                ft.Button(
                    "タイムゾーンを保存",
                    icon=ft.Icons.SAVE,
                    tooltip="日付・時刻の基準タイムゾーンを保存する",
                    on_click=self._save_timezone,
                ),
                self.theme_dropdown,
                ft.Button(
                    "テーマを保存",
                    icon=ft.Icons.SAVE,
                    tooltip="画面のテーマを保存して切り替える",
                    on_click=self._save_theme,
                ),
                self.stopwatch_identifier_field,
                ft.Button(
                    "識別子（ユーザー名）を保存",
                    icon=ft.Icons.SAVE,
                    tooltip="非定型ジョブ実行時に業務記録プラグインへ渡す識別子（ユーザー名）を保存する",
                    on_click=self._save_stopwatch_identifier,
                ),
                self.stopwatch_html_path_field,
                ft.Button(
                    "起動先HTMLパスを保存",
                    icon=ft.Icons.SAVE,
                    tooltip="非定型ジョブ実行時に開く業務記録プラグインのHTMLファイルのパスを保存する",
                    on_click=self._save_stopwatch_html_path,
                ),
            ],
        )

        job_tab = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("ジョブ管理", weight=ft.FontWeight.BOLD, expand=True),
                        ft.Button(
                            "ジョブを追加",
                            icon=ft.Icons.ADD,
                            tooltip="実行タブに表示する新しいジョブを追加する",
                            on_click=self._add_job,
                        ),
                    ]
                ),
                ft.Container(content=self.job_list, border=ft.Border.all(1, ft.Colors.OUTLINE)),
                ft.Text("ジョブの一括インポート／エクスポート・集計", weight=ft.FontWeight.BOLD),
                ft.Text(
                    "業務ヒアリング結果のExcelから一括登録・更新、または現在のジョブ一覧をExcelへ"
                    "出力できます。列名はジョブ編集ダイアログと同じ項目の固定見出しです"
                    "（エクスポートしたファイルをそのまま編集して再インポートできます）。"
                    "成熟度を空欄のまま登録すると「骨組み」状態（コマンド未設定でも保存できるが実行は不可）になります。",
                    size=11,
                    color=ft.Colors.OUTLINE,
                ),
                self.job_export_path_field,
                ft.Button(
                    "ジョブ一覧をエクスポート",
                    icon=ft.Icons.FILE_DOWNLOAD,
                    tooltip="現在のジョブ一覧をExcel(.xlsx)へ書き出す",
                    on_click=self._export_jobs,
                ),
                ft.Divider(height=1),
                self.job_import_path_field,
                self.job_import_mode_dropdown,
                ft.Button(
                    "ジョブを一括インポート",
                    icon=ft.Icons.FILE_UPLOAD,
                    tooltip="Excel(.xlsx)からジョブを一括登録・更新する（内容確認後に反映）",
                    on_click=self._import_jobs,
                ),
                ft.Divider(height=1),
                ft.Button(
                    "成熟度・Tier別集計／停滞ジョブを表示",
                    icon=ft.Icons.BAR_CHART,
                    tooltip="成熟度・Tierごとのジョブ件数と、骨組み状態のまま長期間放置されているジョブを表示する",
                    on_click=self._show_job_aggregation,
                ),
                self.job_aggregation_container,
            ],
        )

        storage_manage_tab = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
            controls=[
                ft.Text("ストレージ設定", weight=ft.FontWeight.BOLD),
                self.storage_enabled_switch,
                self.storage_type,
                self.storage_base_dir,
                self.storage_flow_url,
                self.sync_remote_path,
                self.sync_portal_remote_path,
                self.sync_app_update_manifest_remote_path,
                self.sync_app_update_archive_remote_path,
                ft.Button(
                    "ストレージ設定を保存",
                    icon=ft.Icons.SAVE,
                    tooltip="ストレージ設定・共有マスター/ホーム定義ファイルのパスを保存する",
                    on_click=self._save_storage,
                ),
            ],
        )

        master_sync_tab = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
            controls=[
                ft.Text("マスター同期", weight=ft.FontWeight.BOLD),
                ft.Text(
                    "設定ファイル（menu.toml）を共有フォルダのマスターと同期します。"
                    "起動時に自動でダウンロードも行われます。アップロード時、共有マスターが他で更新されていれば警告します。",
                    size=11,
                    color=ft.Colors.OUTLINE,
                ),
                ft.Row(
                    controls=[
                        ft.Button(
                            "マスターをダウンロード",
                            icon=ft.Icons.DOWNLOAD,
                            tooltip="共有フォルダのマスター設定で、このPCのジョブ・ストレージ設定を上書きする",
                            on_click=self._download_master,
                        ),
                        ft.Button(
                            "マスターへアップロード",
                            icon=ft.Icons.UPLOAD,
                            tooltip="このPCの設定を共有フォルダのマスター設定へ反映する",
                            on_click=self._upload_master,
                        ),
                    ]
                ),
                ft.Divider(),
                ft.Text(
                    "お知らせ・ホーム本文（config/home.toml）を共有フォルダのホーム定義と同期します。"
                    "ホームタブ表示時に新しいバージョンが無いか自動で確認・ダウンロードされます。",
                    size=11,
                    color=ft.Colors.OUTLINE,
                ),
                ft.Row(
                    controls=[
                        ft.Button(
                            "ホーム定義をダウンロード",
                            icon=ft.Icons.DOWNLOAD,
                            tooltip="共有フォルダのホーム定義で、このPCのお知らせ・ホーム本文を上書きする",
                            on_click=self._download_portal,
                        ),
                        ft.Button(
                            "ホーム定義をアップロード",
                            icon=ft.Icons.UPLOAD,
                            tooltip="このPCのお知らせ・ホーム本文を共有フォルダのホーム定義へ反映する",
                            on_click=self._upload_portal,
                        ),
                    ]
                ),
            ],
        )

        device_tab = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
            controls=[
                ft.Text("デバイス管理", weight=ft.FontWeight.BOLD),
                ft.Text(
                    "物理暗号（ULID）は初回起動時に自動生成され、以後変更されません。"
                    "論理番号はmasterロールの端末が割り当てます。memberは自分の情報のアップロードのみ行い、"
                    "他端末の登録内容はダウンロードしません。",
                    size=11,
                    color=ft.Colors.OUTLINE,
                ),
                self.device_id_field,
                ft.Row(controls=[self.device_logical_number_field, self.device_owner_field, self.device_role_dropdown]),
                ft.Button(
                    "デバイス情報を保存",
                    icon=ft.Icons.SAVE,
                    tooltip="持ち主・ロールを保存し、ストレージが有効ならこの端末の情報を共有ストレージへ登録する",
                    on_click=self._save_device_identity,
                ),
                self.device_master_container,
            ],
        )

        tier_tab = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
            controls=[
                ft.Text("Tier設定（業務の階層）", weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Tier1〜8は全体共有（共有マスターと同期）、Tier9は個人のみです。"
                    "空欄のTierはジョブ編集時の選択肢に出ません。",
                    size=11,
                    color=ft.Colors.OUTLINE,
                ),
                ft.Row(controls=[self.tier_fields[k] for k in TIER_SHARED_KEYS[:4]], wrap=True),
                ft.Row(controls=[self.tier_fields[k] for k in TIER_SHARED_KEYS[4:]], wrap=True),
                self.tier9_field,
                ft.Button(
                    "Tier設定を保存",
                    icon=ft.Icons.SAVE,
                    tooltip="Tier1〜9の名称を保存する",
                    on_click=self._save_tiers,
                ),
            ],
        )

        home_tab = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("お知らせメッセージ管理", weight=ft.FontWeight.BOLD, expand=True),
                        ft.Button(
                            "お知らせを追加",
                            icon=ft.Icons.ADD,
                            tooltip="ホームタブに表示する新しいお知らせを追加する",
                            on_click=self._add_notice,
                        ),
                    ]
                ),
                ft.Container(content=self.notice_list, border=ft.Border.all(1, ft.Colors.OUTLINE)),
                ft.Text("ホーム定義", weight=ft.FontWeight.BOLD),
                self.portal_content_field,
                ft.Row(
                    controls=[
                        ft.Button(
                            "ホーム本文を保存",
                            icon=ft.Icons.SAVE,
                            tooltip="ホームタブに表示する本文を保存する",
                            on_click=self._save_portal_content,
                        ),
                        ft.Button(
                            "プレビュー",
                            icon=ft.Icons.PREVIEW,
                            tooltip="現在の入力内容をプレビュー表示する（保存はしない）",
                            on_click=self._preview_portal_content,
                        ),
                        ft.Button(
                            "よく使うサービスの表を編集",
                            icon=ft.Icons.TABLE_CHART,
                            tooltip="「よく使うサービス」の表を列・行単位で編集する（Markdown構文は自動生成）",
                            on_click=self._open_service_table_editor,
                        ),
                    ]
                ),
                ft.Text(
                    "お知らせ・ホーム本文（config/home.toml）の共有フォルダとの同期は"
                    "「マスター同期」タブから行えます。",
                    size=11,
                    color=ft.Colors.OUTLINE,
                ),
            ],
        )

        security_tab = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("各種APIキー", weight=ft.FontWeight.BOLD, expand=True),
                        ft.Button(
                            "APIキーを追加",
                            icon=ft.Icons.ADD,
                            tooltip="Redmine等、外部サービスのAPIキーを登録する",
                            on_click=self._add_api_key,
                        ),
                    ]
                ),
                ft.Text(
                    "登録したAPIキーは、このPC・このWindowsユーザーでのみ復号できる形式で暗号化して保存されます。",
                    size=11,
                    color=ft.Colors.OUTLINE,
                ),
                ft.Container(content=self.api_key_list, border=ft.Border.all(1, ft.Colors.OUTLINE)),
            ],
        )

        app_update_tab = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
            controls=[self.app_update_container],
        )

        self.view = ft.Tabs(
            length=9,
            selected_index=0,
            expand=True,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label="一般"),
                            ft.Tab(label="ジョブ管理"),
                            ft.Tab(label="ストレージ管理"),
                            ft.Tab(label="マスター同期"),
                            ft.Tab(label="デバイス管理"),
                            ft.Tab(label="業務管理"),
                            ft.Tab(label="ホーム"),
                            ft.Tab(label="セキュリティ"),
                            ft.Tab(label="アプリ更新"),
                        ]
                    ),
                    ft.TabBarView(
                        expand=True,
                        controls=[
                            general_tab,
                            job_tab,
                            storage_manage_tab,
                            master_sync_tab,
                            device_tab,
                            tier_tab,
                            home_tab,
                            security_tab,
                            app_update_tab,
                        ],
                    ),
                ],
            ),
        )

        self.refresh_job_list()
        self._refresh_api_key_list()
        self._refresh_notice_list()
        self._refresh_app_update_section()
        self._refresh_device_list()

    # ========================
    # ✅ アプリ設定（タイムゾーン）
    # ========================
    def _save_timezone(self, e: ft.ControlEvent) -> None:
        tz_name = (self.timezone_field.value or "").strip() or tz_repo.DEFAULT_TIMEZONE

        try:
            tz_repo.get_zoneinfo(tz_name)
        except ZoneInfoNotFoundError:
            show_toast(self.page, f"不正なタイムゾーン名です: {tz_name}")
            return

        tz_repo.save_timezone(tz_name)
        ui_log.log_action("設定", "save", "タイムゾーン", value=tz_name)
        show_toast(self.page, "タイムゾーンを保存しました（スケジュール実行への反映にはアプリの再起動が必要です）")

    def _save_theme(self, e: ft.ControlEvent) -> None:
        theme = self.theme_dropdown.value or theme_repo.DEFAULT_THEME

        theme_repo.save_theme(theme)
        theme_repo.apply_theme(self.page, theme)
        self.page.update()
        ui_log.log_action("設定", "save", "テーマ", value=theme)

        show_toast(
            self.page,
            "テーマを保存しました（既に表示中の一部の強調色は、画面の再表示で反映されます）",
        )

    def _save_stopwatch_identifier(self, e: ft.ControlEvent) -> None:
        identifier = (self.stopwatch_identifier_field.value or "").strip()
        stopwatch_repo.save_identifier(identifier)
        ui_log.log_action("設定", "save", "業務記録プラグイン識別子")
        show_toast(self.page, "識別子（ユーザー名）を保存しました")

    def _save_stopwatch_html_path(self, e: ft.ControlEvent) -> None:
        html_path = (self.stopwatch_html_path_field.value or "").strip() or stopwatch_repo.DEFAULT_HTML_PATH
        self.stopwatch_html_path_field.value = html_path
        safe_update(self.stopwatch_html_path_field)

        stopwatch_repo.save_html_path(html_path)
        ui_log.log_action("設定", "save", "業務記録プラグイン起動先HTMLパス")
        show_toast(self.page, "起動先HTMLパスを保存しました")

    def _save_tiers(self, e: ft.ControlEvent) -> None:
        self.tier_config = {
            key: (field.value or "").strip() for key, field in self.tier_fields.items()
        }
        self.personal_tier_name = (self.tier9_field.value or "").strip() or tier_repo.DEFAULT_TIER9_NAME
        self.tier9_field.value = self.personal_tier_name
        safe_update(self.tier9_field)

        save_config(MENU_PATH, self.menu_items, self.storage_config, self.sync_config, self.tier_config)
        tier_repo.save_personal_tier_name(self.personal_tier_name)
        ui_log.log_action("設定", "save", "Tier設定")

        show_toast(self.page, "Tier設定を保存しました")

    # ========================
    # ✅ ジョブ管理
    # ========================
    def refresh_job_list(self) -> None:
        self.job_list.controls.clear()

        for item in self.menu_items:
            subtitle = item.command
            prefix = [p for p in (item.tier, item.category) if p]
            if prefix:
                subtitle = f"[{'/'.join(prefix)}] {subtitle}"
            name_text = f"{item.job_id}  {item.name}（{item.job_type}）"
            if not item.enabled:
                name_text += "  [無効]"

            self.job_list.controls.append(
                ft.ListTile(
                    title=ft.Text(name_text),
                    subtitle=ft.Text(subtitle, max_lines=1),
                    trailing=ft.IconButton(
                        icon=ft.Icons.EDIT,
                        tooltip=f"「{item.name}」を編集する",
                        on_click=self._make_edit_job_handler(item),
                    ),
                )
            )

        safe_update(self.job_list)

    def _add_job(self, e: ft.ControlEvent) -> None:
        def on_saved() -> None:
            self.refresh_job_list()
            self.on_menu_changed()
            show_toast(self.page, "ジョブを追加しました")

        open_add_job_dialog(
            self.page, self.menu_items, self.tier_config, self.personal_tier_name, on_saved
        )

    def _make_edit_job_handler(self, item: MenuItem):
        def handler(e: ft.ControlEvent) -> None:
            def on_saved() -> None:
                self.refresh_job_list()
                self.on_menu_changed()
                show_toast(self.page, "ジョブを更新しました")

            def on_deleted() -> None:
                self.refresh_job_list()
                self.on_menu_changed()
                show_toast(self.page, "ジョブを削除しました")

            open_edit_job_dialog(
                self.page,
                item,
                self.menu_items,
                self.tier_config,
                self.personal_tier_name,
                on_saved,
                on_deleted,
            )

        return handler

    # ========================
    # ✅ ジョブの一括インポート/エクスポート・集計（統合業務管理フェーズ4）
    # ========================
    def _export_jobs(self, e: ft.ControlEvent) -> None:
        path = expand_path((self.job_export_path_field.value or "").strip())
        if not path:
            show_toast(self.page, "エクスポート先ファイルパスを入力してください")
            return

        try:
            job_import_export.export_jobs_to_excel(self.menu_items, path)
        except Exception as ex:
            show_toast(self.page, f"エクスポートに失敗しました: {ex}")
            return

        ui_log.log_action("設定", "output", "ジョブ一覧エクスポート")
        show_toast(self.page, f"ジョブ一覧を書き出しました（{len(self.menu_items)}件）: {path}")

    def _import_jobs(self, e: ft.ControlEvent) -> None:
        path = expand_path((self.job_import_path_field.value or "").strip())
        if not path:
            show_toast(self.page, "インポート元ファイルパスを入力してください")
            return

        mode = self.job_import_mode_dropdown.value or job_import_export.MODE_ADD

        try:
            result = job_import_export.import_jobs_from_excel(path, mode, self.menu_items)
        except Exception as ex:
            show_toast(self.page, f"インポートに失敗しました: {ex}")
            return

        if not result.added and not result.updates:
            show_toast(
                self.page,
                f"インポート対象がありませんでした（スキップ{len(result.errors)}件。"
                "内容をご確認ください）",
            )
            return

        error_lines = "\n".join(f"・{err.row_number}行目: {err.message}" for err in result.errors[:5])
        if len(result.errors) > 5:
            error_lines += f"\n・他{len(result.errors) - 5}件"
        error_block = f"\n\nスキップされた行（{len(result.errors)}件）:\n{error_lines}" if result.errors else ""

        def do_apply() -> None:
            self.menu_items[:] = job_import_export.apply_import_result(self.menu_items, result)
            save_config(MENU_PATH, self.menu_items, self.storage_config, self.sync_config, self.tier_config)
            self.refresh_job_list()
            self.on_menu_changed()
            ui_log.log_action(
                "設定",
                "import",
                "ジョブ一括インポート",
                detail=f"モード={mode}/追加{len(result.added)}件/更新{len(result.updates)}件/スキップ{len(result.errors)}件",
            )
            show_toast(
                self.page,
                f"インポートしました（追加{len(result.added)}件・更新{len(result.updates)}件）",
            )

        show_confirm_dialog(
            self.page,
            "ジョブの一括インポート",
            f"追加{len(result.added)}件・更新{len(result.updates)}件を反映します。"
            f"{error_block}\n\nよろしいですか？",
            do_apply,
            confirm_label="インポート",
        )

    def _show_job_aggregation(self, e: ft.ControlEvent) -> None:
        agg = job_stats.compute_job_aggregation(self.menu_items)

        maturity_text = "  ".join(
            f"{n if n else '未設定'}: {count}件" for n, count in sorted(agg.maturity_counts.items())
        )
        tier_text = "\n".join(
            f"・{name or '（未設定）'}: {count}件"
            for name, count in sorted(agg.tier_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        if agg.stalled_jobs:
            stalled_text = "\n".join(f"・{item.job_id}  {item.name}" for item in agg.stalled_jobs)
        else:
            stalled_text = "（該当なし）"

        self.job_aggregation_container.controls = [
            ft.Text("成熟度別件数", weight=ft.FontWeight.BOLD, size=13),
            ft.Text(maturity_text),
            ft.Text("Tier別件数", weight=ft.FontWeight.BOLD, size=13),
            ft.Text(tier_text or "（ジョブがありません）"),
            ft.Text(
                f"停滞ジョブ（骨組み状態のまま{agg.stalled_days}日以上動きが無いもの、"
                f"{len(agg.stalled_jobs)}件）",
                weight=ft.FontWeight.BOLD,
                size=13,
            ),
            ft.Text(stalled_text),
        ]
        self.job_aggregation_container.visible = True
        safe_update(self.job_aggregation_container)
        ui_log.log_action("設定", "click", "ジョブ集計表示")

    # ========================
    # ✅ ストレージ設定
    # ========================
    def _handle_storage_type_change(self, e: ft.ControlEvent) -> None:
        self.storage_base_dir.visible = self.storage_type.value == "local"
        self.storage_flow_url.visible = self.storage_type.value == "flow"
        self.storage_base_dir.update()
        self.storage_flow_url.update()

    def _save_storage(self, e: ft.ControlEvent) -> None:
        storage: dict = {
            "enabled": bool(self.storage_enabled_switch.value),
            "type": self.storage_type.value or "local",
        }

        if self.storage_base_dir.value:
            storage["local"] = {"base_dir": self.storage_base_dir.value}
        if self.storage_flow_url.value:
            storage["flow"] = {"url": self.storage_flow_url.value}

        sync: dict = {}
        if self.sync_remote_path.value:
            sync["remote_path"] = self.sync_remote_path.value
        if self.sync_portal_remote_path.value:
            sync["portal_remote_path"] = self.sync_portal_remote_path.value
        if self.sync_app_update_manifest_remote_path.value:
            sync["app_update_manifest_remote_path"] = self.sync_app_update_manifest_remote_path.value
        if self.sync_app_update_archive_remote_path.value:
            sync["app_update_archive_remote_path"] = self.sync_app_update_archive_remote_path.value

        self.storage_config = storage
        self.sync_config = sync
        save_config(MENU_PATH, self.menu_items, storage, sync, self.tier_config)
        ui_log.log_action("設定", "save", "ストレージ設定", value=storage.get("type"))
        show_toast(self.page, "ストレージ設定を保存しました")

    # ========================
    # ✅ アプリの更新（次期開発ロードマップ項目2。検知・DLは起動時に自動、適用はここでの手動操作）
    # ========================
    def _refresh_app_update_section(self) -> None:
        info = app_update_repo.load_update_state()
        controls = [
            ft.Text("アプリの更新", weight=ft.FontWeight.BOLD),
            ft.Text(f"現在のバージョン: {app_update_repo.get_current_version()}", size=12),
        ]

        if info:
            controls.append(
                ft.Text(
                    f"利用可能な更新: {info.version}"
                    f"（公開: {info.published_by or '不明'}, {info.published_at or '日時不明'}）",
                    size=12,
                )
            )
            if info.notes:
                controls.append(ft.Text(info.notes, size=11, color=ft.Colors.OUTLINE))
            controls.append(
                ft.Button(
                    "更新を適用",
                    icon=ft.Icons.SYSTEM_UPDATE,
                    tooltip="ダウンロード済みの新しいバージョンを適用する（適用後、アプリを終了します。再度起動してください）",
                    on_click=self._handle_apply_update,
                )
            )
        else:
            controls.append(ft.Text("更新はありません（最新版です）", size=12, color=ft.Colors.OUTLINE))

        self.app_update_container.controls = controls
        safe_update(self.app_update_container)

    def _handle_apply_update(self, e: ft.ControlEvent) -> None:
        info = app_update_repo.load_update_state()
        if not info:
            return

        def do_apply() -> None:
            if not app_update_repo.is_self_overwrite_enabled():
                if not is_storage_enabled(self.storage_config):
                    show_toast(
                        self.page,
                        "ストレージ設定が無効化されているため、更新の適用は行いません"
                        "（上記「ストレージ設定を有効にする」をONにしてください）",
                    )
                else:
                    show_toast(
                        self.page,
                        "自己更新機能は既定で無効化されています"
                        "（config/app.tomlの[app_update]セクションに"
                        "enable_self_overwrite=trueを追記すると有効化できます）",
                    )
                return

            # ✅ apply_update()はZIP展開（ファイルI/O）で数秒かかることがあり、確認ダイアログの
            # on_click（Fletのイベントループ上で同期実行される）で直接呼ぶとその間アプリ全体が
            # 固まって見える（実機で確認済み: 「スピナーが回りっぱなしで反応が無い」不具合報告）。
            # ジョブ実行と同じ`page.run_thread()`でバックグラウンドスレッドへ逃がす
            show_toast(self.page, f"バージョン {info.version} の適用を開始しました…")
            self.page.run_thread(self._apply_update_worker, info)

        show_confirm_dialog(
            self.page,
            "更新の適用",
            f"バージョン {info.version} を適用します。適用後はアプリを終了しますので、再度起動し直してください。よろしいですか？",
            do_apply,
            confirm_label="適用",
        )

    def _apply_update_worker(self, info) -> None:
        """
        `_handle_apply_update`の`do_apply`から`page.run_thread()`経由で呼ばれる。ファイルI/O
        （ZIP展開）をUIスレッドから切り離すことで、適用中もアプリが固まって見えないようにする
        """

        def print_progress(current: int, total: int, name: str) -> None:
            # ✅ 上書き中に何が起きているか分かりにくいというユーザーからの要望で、
            # コンソールに簡易な進捗バーを出す（\rで同じ行を上書き、完了時のみ改行する）
            width = 30
            filled = int(width * current / total) if total else width
            bar = "#" * filled + "-" * (width - filled)
            pct = int(100 * current / total) if total else 100
            end = "\n" if current >= total else ""
            print(f"\r[Update] 展開中 [{bar}] {pct}% ({current}/{total}) {name}", end=end, flush=True)

        print(f"[Update] バージョン {info.version} の適用を開始します")
        ok = app_update_repo.apply_update(info, on_progress=print_progress)
        if not ok:
            print("[Update] 更新の適用に失敗しました")
            show_toast(self.page, "更新の適用に失敗しました")
            return

        print(f"[Update] バージョン {info.version} の適用が完了しました")
        ui_log.log_action("設定", "click", "アプリ更新を適用", value=info.version)
        portal_repo.add_system_notice(
            title=f"バージョン {info.version} への更新が完了しました",
            content=(
                f"myJobLauncher はバージョン **{info.version}** への更新を正常に適用しました。"
                "次回起動分から反映されています。"
            ),
            duration_days=1,
        )
        self._refresh_app_update_section()
        # ✅ --web版はこの後サーバープロセスを終了するため、ブラウザ側はWebSocket切断を検知して
        # 再接続を試み続ける（サーバーは戻ってこないため、この「再接続中」表示はスピナーが
        # 回り続けているように見える。実機で確認済み・Fletのwebクライアント側の挙動でアプリの
        # コードからは制御できない）。強制終了する必要はなく、単にこのタブ/ウィンドウを
        # 閉じればよい旨をメッセージで明示する
        show_toast(
            self.page,
            f"更新を適用しました（v{info.version}）。数秒後にアプリを終了します。"
            "画面が反応しなくなったら、このタブ/ウィンドウを閉じて`uv run mj`等で再度起動してください"
            "（強制終了の操作は不要です）",
        )

        def _exit_soon() -> None:
            time.sleep(2.5)
            os._exit(0)

        threading.Thread(target=_exit_soon, daemon=True).start()

    # ========================
    # ✅ 設定ファイルの同期（共有マスターとの download/upload）
    # ========================
    def _check_storage_enabled(self) -> bool:
        """
        ストレージ設定が無効化されている場合、トーストで案内してFalseを返す（呼び出し元は
        処理を中断する）。共有マスター/ホーム定義の手動ダウンロード・アップロード4箇所の
        入口で使う。自動同期側は`services/sync_service.py`の`_auto_download()`が同様に判定する
        """
        if is_storage_enabled(self.storage_config):
            return True
        show_toast(self.page, "ストレージ設定が無効化されているため、同期を行いません（上記スイッチをONにしてください）")
        return False

    # ========================
    # ✅ デバイス管理（統合業務管理・項目単位同期フェーズ1、DESIGN.md「11. 統合業務管理」参照）
    # ========================
    def _handle_device_role_change(self, e: ft.ControlEvent) -> None:
        """ロール変更時、保存前でも管理者向けセクションの表示/非表示を即時切り替える"""
        self.device_master_container.visible = self.device_role_dropdown.value == device_repo.ROLE_MASTER
        safe_update(self.device_master_container)

    def _save_device_identity(self, e: ft.ControlEvent) -> None:
        """
        持ち主・ロールを保存する。物理暗号（ULID）は不変のため編集欄には含めない。
        ストレージが有効な場合のみ、この端末の情報を`devices/<device_id>.toml`へ登録する
        （member/masterどちらでも自分の情報は登録する。ダウンロードはmasterのみ「デバイス一覧を取得」で行う）
        """
        self.device_identity.owner = (self.device_owner_field.value or "").strip()
        self.device_identity.role = self.device_role_dropdown.value or device_repo.ROLE_MEMBER
        device_repo.save_local_identity(self.device_identity)
        ui_log.log_action("設定", "save", "デバイス情報")

        self.device_master_container.visible = self.device_identity.role == device_repo.ROLE_MASTER
        safe_update(self.device_master_container)

        if not is_storage_enabled(self.storage_config):
            show_toast(self.page, "デバイス情報をこのPCに保存しました（ストレージ設定が無効化されているため共有ストレージへの登録はスキップしました）")
            return

        try:
            storage = create_storage({"storage": self.storage_config})
            # ✅ 先にmasterが割り当てた論理番号を取り込み、その後で最新のローカル状態を
            # アップロードする（順序を逆にすると割り当て済みの論理番号を空文字で
            # 上書きしてしまう。services/device_repo.pyのrefresh_own_logical_number()参照）
            sync_service.with_retry(lambda: device_repo.refresh_own_logical_number(storage, self.device_identity))
            sync_service.with_retry(lambda: device_repo.upload_own_device(storage, self.device_identity))
            self.device_logical_number_field.value = self.device_identity.logical_number or "（未割当）"
            safe_update(self.device_logical_number_field)
            show_toast(self.page, "デバイス情報を保存し、共有ストレージへ登録しました")
        except Exception as ex:
            show_toast(self.page, f"デバイス情報はこのPCに保存しましたが、共有ストレージへの登録に失敗しました: {ex}")

    def _refresh_device_list(self) -> None:
        self.device_list.controls.clear()

        for item in self.devices_cache:
            subtitle = f"role={item.role} / 登録日={item.registered_at or '(不明)'} / ID={item.device_id[:8]}…"
            trailing = None
            if not item.logical_number and self.device_identity.role == device_repo.ROLE_MASTER:
                trailing = ft.IconButton(
                    icon=ft.Icons.PLAYLIST_ADD,
                    tooltip="この端末に論理番号を割り当てる",
                    on_click=self._make_assign_device_handler(item),
                )
            self.device_list.controls.append(
                ft.ListTile(
                    title=ft.Text(f"{item.logical_number or '（未割当）'}　{item.owner or '（持ち主未設定）'}"),
                    subtitle=ft.Text(subtitle),
                    trailing=trailing,
                )
            )

        safe_update(self.device_list)

    def _sync_devices_master(self, e: ft.ControlEvent) -> None:
        if not self._check_storage_enabled():
            return

        try:
            storage = create_storage({"storage": self.storage_config})
            self.devices_cache = sync_service.with_retry(lambda: device_repo.sync_devices_as_master(storage))

            # ✅ 取得した一覧に自分自身の端末が含まれていれば、既に割り当て済みの論理番号を
            # このセクション上部の表示（device_identity）にも反映する
            own = next((d for d in self.devices_cache if d.device_id == self.device_identity.device_id), None)
            if own is not None and own.logical_number != self.device_identity.logical_number:
                self.device_identity.logical_number = own.logical_number
                device_repo.save_local_identity(self.device_identity)
                self.device_logical_number_field.value = own.logical_number or "（未割当）"
                safe_update(self.device_logical_number_field)

            self._refresh_device_list()
            ui_log.log_action("設定", "sync", "デバイス一覧取得")
            show_toast(self.page, f"デバイス一覧を取得しました（{len(self.devices_cache)}件）")
        except Exception as ex:
            show_toast(self.page, f"デバイス一覧の取得に失敗しました: {ex}")

    def _make_assign_device_handler(self, item: device_repo.DeviceItem):
        def handler(e: ft.ControlEvent) -> None:
            if not self._check_storage_enabled():
                return

            def on_submit(values: dict) -> None:
                logical_number = (values.get("logical_number") or "").strip()
                if not logical_number:
                    show_toast(self.page, "論理番号を入力してください")
                    return
                try:
                    storage = create_storage({"storage": self.storage_config})
                    sync_service.with_retry(
                        lambda: device_repo.assign_logical_number(
                            storage, self.devices_cache, item.device_id, logical_number
                        )
                    )
                    device_repo.save_devices(self.devices_cache)

                    # ✅ 割り当て対象が自分自身の端末だった場合、devices_cache側の更新だけでは
                    # このセクション上部の表示（device_identity/読み取り専用欄）には反映されない
                    # （別オブジェクトのため）。自分自身への割り当てはローカル識別情報も同期する
                    if item.device_id == self.device_identity.device_id:
                        self.device_identity.logical_number = logical_number
                        device_repo.save_local_identity(self.device_identity)
                        self.device_logical_number_field.value = logical_number
                        safe_update(self.device_logical_number_field)

                    self._refresh_device_list()
                    ui_log.log_action("設定", "save", "デバイス論理番号割当", value=logical_number)
                    show_toast(self.page, f"論理番号 {logical_number} を割り当てました")
                except Exception as ex:
                    show_toast(self.page, f"論理番号の割り当てに失敗しました: {ex}")

            show_item_form_dialog(
                self.page,
                f"論理番号の割り当て（ID: {item.device_id[:8]}…）",
                [{"key": "logical_number", "label": "論理番号", "type": "text", "autofocus": True}],
                {"logical_number": device_repo.next_logical_number(self.devices_cache)},
                on_submit,
            )

        return handler

    def _fetch_remote_menu(self, storage, remote_path: str):
        """
        共有マスターの現在の内容をダウンロードし、(items, storage_cfg, sync_cfg, tiers) を返す。

        **リモートファイル自体が存在しない場合（初回アップロード前等）のみ**、空のジョブ一覧・
        空の設定として扱う。それ以外の失敗（ネットワーク断・アクセス権限・破損データ等）は
        例外をそのまま呼び出し元へ伝播させ、マージを中断する。

        **重要（実機で確認済みの不具合）**: 以前はダウンロード失敗全般を「空」として
        握りつぶしていたが、これは危険だった。空のリモート一覧を「リモートの現在の状態」と
        誤認すると、項目単位マージ（`item_sync.merge_menu_items()`）の削除伝播ロジックが
        「ローカルの全ジョブがリモート側で削除された」と解釈し、実際には健全なジョブまで
        まとめて削除してしまう（マスターに存在しないはずのjob_idが消えるという不具合として
        実機で報告された）。「存在しない」と「取得できない」は明確に区別すること
        """
        tmp_path = MENU_PATH + ".remote_tmp"
        try:
            try:
                sync_service.with_retry(lambda: storage.download(remote_path, tmp_path))
            except FileNotFoundError:
                return [], {}, {}, {}

            items = load_config(tmp_path)
            storage_cfg = load_storage_config(tmp_path)
            sync_cfg = load_sync_config(tmp_path)
            tiers_cfg = load_tier_config(tmp_path)
            return items, storage_cfg, sync_cfg, tiers_cfg
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _report_merge_conflicts(self, conflicts: list) -> None:
        """
        両方で変更されていた（真の衝突）ジョブがあれば、ローカルの内容を維持したことと
        対象ジョブ名をトーストで案内する（統合業務管理フェーズ3、DESIGN.md「11.3」R15）。
        現状は個別に選択するダイアログは無く、「ローカル優先」で自動解決し、
        あとで手動で見直してもらう運用（次期スコープ）
        """
        if not conflicts:
            return
        names = "、".join(f"「{local_item.name}」" for _, local_item, _ in conflicts[:5])
        more = f" 他{len(conflicts) - 5}件" if len(conflicts) > 5 else ""
        show_toast(
            self.page,
            f"{len(conflicts)}件のジョブが両方の端末で変更されていたため、"
            f"このPCの内容を維持しました（要確認）: {names}{more}",
        )

    def _download_master(self, e: ft.ControlEvent) -> None:
        if not self._check_storage_enabled():
            return

        def do_download() -> None:
            try:
                storage = create_storage({"storage": self.storage_config})
                remote_path = self.sync_remote_path.value

                remote_items, remote_storage, remote_sync, remote_tiers = self._fetch_remote_menu(
                    storage, remote_path
                )
                base_hashes = item_sync.load_sync_base()
                merged_items, conflicts, new_hashes, stats = item_sync.merge_menu_items(
                    self.menu_items, remote_items, base_hashes
                )
                start_line, end_line = item_sync.format_sync_progress_lines(stats, verb="ダウンロード")
                print(f"[Sync] {start_line}")
                applog.log("INFO", start_line, func_name="_download_master")
                print(f"[Sync] {end_line}")
                applog.log("INFO", end_line, func_name="_download_master")

                # ✅ ジョブ一覧は項目単位でマージするが、[storage]/[sync]/[tiers]は
                # 従来通り「ダウンロード＝共有フォルダの値で上書き」のファイル単位同期を維持する
                # （これらは成長するコレクションではなく共有設定そのものなので、丸ごと同期のままでよい）
                save_config(MENU_PATH, merged_items, remote_storage, remote_sync, remote_tiers)
                item_sync.save_sync_base(new_hashes)
                sync_service.record_sync(storage, remote_path, "menu")

                self.menu_items[:] = merged_items
                self.storage_config = load_storage_config(MENU_PATH)
                self.sync_config = load_sync_config(MENU_PATH)
                self.tier_config = load_tier_config(MENU_PATH)

                for key in TIER_SHARED_KEYS:
                    self.tier_fields[key].value = self.tier_config.get(key, "")
                    safe_update(self.tier_fields[key])

                self.refresh_job_list()
                self.on_menu_changed()
                ui_log.log_action("設定", "sync", "共有マスターダウンロード（項目単位マージ）")
                show_toast(self.page, "マスター設定を取り込みました（ジョブは項目単位でマージ）")
                self._report_merge_conflicts(conflicts)
            except Exception as ex:
                show_toast(self.page, f"ダウンロードに失敗しました: {ex}")

        show_confirm_dialog(
            self.page,
            "マスター設定のダウンロード",
            "共有フォルダのマスター設定を取り込みます。ジョブは項目（job_id）単位で安全にマージされ、"
            "このPCで未同期の追加・変更は失われません（ストレージ設定・Tier名は共有フォルダの値で上書きされます）。"
            "よろしいですか？",
            do_download,
        )

    def _upload_master(self, e: ft.ControlEvent) -> None:
        if not self._check_storage_enabled():
            return

        def do_upload() -> None:
            try:
                storage = create_storage({"storage": self.storage_config})
                remote_path = self.sync_remote_path.value

                remote_items, _remote_storage, _remote_sync, _remote_tiers = self._fetch_remote_menu(
                    storage, remote_path
                )
                base_hashes = item_sync.load_sync_base()
                merged_items, conflicts, new_hashes, stats = item_sync.merge_menu_items(
                    self.menu_items, remote_items, base_hashes
                )
                start_line, end_line = item_sync.format_sync_progress_lines(
                    stats, verb="アップロード", incoming_label="マスター件数"
                )
                print(f"[Sync] {start_line}")
                applog.log("INFO", start_line, func_name="_upload_master")
                print(f"[Sync] {end_line}")
                applog.log("INFO", end_line, func_name="_upload_master")

                # ✅ [storage]/[sync]/[tiers]はこのPCの現在値をそのまま共有フォルダへ反映する
                # （従来の「アップロード＝このPCの値で上書き」の挙動を維持）。ジョブ一覧だけを
                # 項目単位マージ済みのものに差し替える
                save_config(MENU_PATH, merged_items, self.storage_config, self.sync_config, self.tier_config)
                sync_service.with_retry(lambda: storage.upload(MENU_PATH, remote_path))
                item_sync.save_sync_base(new_hashes)
                sync_service.record_sync(storage, remote_path, "menu")

                self.menu_items[:] = merged_items
                self.refresh_job_list()
                self.on_menu_changed()
                ui_log.log_action("設定", "sync", "共有マスターアップロード（項目単位マージ）")
                show_toast(self.page, "マスター設定へ反映しました（ジョブは項目単位でマージ）")
                self._report_merge_conflicts(conflicts)
            except Exception as ex:
                show_toast(self.page, f"アップロードに失敗しました: {ex}")

        show_confirm_dialog(
            self.page,
            "マスター設定へアップロード",
            "このPCの設定を共有フォルダへ反映します。ジョブは項目（job_id）単位で安全にマージされ、"
            "共有フォルダ側で未取込の追加・変更は失われません（ストレージ設定・Tier名はこのPCの値で上書きされます）。"
            "よろしいですか？",
            do_upload,
        )

    # ========================
    # ✅ お知らせメッセージ管理
    # ========================
    def _refresh_notice_list(self) -> None:
        self.notice_list.controls.clear()

        for item in self.notices:
            subtitle_parts = [item.publish_at or "（即時公開）", f"期間{item.duration_days}日"]
            if item.urgent:
                subtitle_parts.append("緊急")
            self.notice_list.controls.append(
                ft.ListTile(
                    title=ft.Text(f"{item.notice_id}  {item.title}"),
                    subtitle=ft.Text("  /  ".join(subtitle_parts)),
                    trailing=ft.IconButton(
                        icon=ft.Icons.EDIT,
                        tooltip=f"「{item.title}」を編集する",
                        on_click=self._make_edit_notice_handler(item),
                    ),
                )
            )

        safe_update(self.notice_list)

    def _add_notice(self, e: ft.ControlEvent) -> None:
        def on_saved() -> None:
            self._refresh_notice_list()
            show_toast(self.page, "お知らせを追加しました")

        open_add_notice_dialog(self.page, self.notices, on_saved)

    def _make_edit_notice_handler(self, item):
        def handler(e: ft.ControlEvent) -> None:
            def on_saved() -> None:
                self._refresh_notice_list()
                show_toast(self.page, "お知らせを更新しました")

            def on_deleted() -> None:
                self._refresh_notice_list()
                show_toast(self.page, "お知らせを削除しました")

            open_edit_notice_dialog(self.page, item, self.notices, on_saved, on_deleted)

        return handler

    # ========================
    # ✅ ホーム本文の編集・プレビュー・同期
    # ========================
    def _save_portal_content(self, e: ft.ControlEvent) -> None:
        self.portal_config.content = self.portal_content_field.value or ""
        self.portal_config.updated_at = tz_repo.now().strftime(portal_repo.DATETIME_FORMAT)
        portal_repo.save_portal_config(self.portal_config)
        ui_log.log_action("設定", "save", "ホーム本文")
        show_toast(self.page, "ホーム本文を保存しました")

    def _preview_portal_content(self, e: ft.ControlEvent) -> None:
        show_markdown_preview_dialog(self.page, "ホーム", self.portal_content_field.value or "")

    def _open_service_table_editor(self, e: ft.ControlEvent) -> None:
        def on_saved(new_content: str) -> None:
            self.portal_config = portal_repo.load_portal_config()
            self.portal_content_field.value = new_content
            safe_update(self.portal_content_field)
            show_toast(self.page, "よく使うサービスの表を保存しました")

        open_service_table_editor_dialog(self.page, on_saved)

    def _download_portal(self, e: ft.ControlEvent) -> None:
        if not self._check_storage_enabled():
            return

        def do_download() -> None:
            try:
                storage = create_storage({"storage": self.storage_config})
                remote_path = self.sync_portal_remote_path.value
                sync_service.with_retry(
                    lambda: storage.download(remote_path, portal_repo.PORTAL_PATH)
                )
                sync_service.record_sync(storage, remote_path, "portal")

                self.notices = portal_repo.load_notices()
                self.portal_config = portal_repo.load_portal_config()
                self.portal_content_field.value = self.portal_config.content
                safe_update(self.portal_content_field)
                self._refresh_notice_list()
                ui_log.log_action("設定", "sync", "ホーム定義ダウンロード")
                show_toast(self.page, "ホーム定義をダウンロードしました")
            except Exception as ex:
                show_toast(self.page, f"ダウンロードに失敗しました: {ex}")

        show_confirm_dialog(
            self.page,
            "ホーム定義のダウンロード",
            "共有フォルダのホーム定義で、このPCのお知らせ・ホーム本文を上書きします。よろしいですか？",
            do_download,
        )

    def _upload_portal(self, e: ft.ControlEvent) -> None:
        if not self._check_storage_enabled():
            return

        def perform_upload(storage, remote_path: str) -> None:
            try:
                sync_service.with_retry(
                    lambda: storage.upload(portal_repo.PORTAL_PATH, remote_path)
                )
                sync_service.record_sync(storage, remote_path, "portal")
                ui_log.log_action("設定", "sync", "ホーム定義アップロード")
                show_toast(self.page, "ホーム定義へアップロードしました")
            except Exception as ex:
                show_toast(self.page, f"アップロードに失敗しました: {ex}")

        def do_upload() -> None:
            try:
                storage = create_storage({"storage": self.storage_config})
                remote_path = self.sync_portal_remote_path.value
            except Exception as ex:
                show_toast(self.page, f"アップロードに失敗しました: {ex}")
                return

            if sync_service.has_conflict(storage, remote_path, "portal"):
                show_confirm_dialog(
                    self.page,
                    "競合の可能性",
                    "共有ホーム定義は前回の同期後に、他の場所で更新されている可能性があります。"
                    "このままアップロードすると、その変更が上書きされます。続行しますか？",
                    lambda: perform_upload(storage, remote_path),
                )
            else:
                perform_upload(storage, remote_path)

        show_confirm_dialog(
            self.page,
            "ホーム定義へアップロード",
            "このPCのお知らせ・ホーム本文で、共有フォルダのホーム定義を上書きします。よろしいですか？",
            do_upload,
        )

    # ========================
    # ✅ APIキー管理
    # ========================
    def _refresh_api_key_list(self) -> None:
        self.api_key_list.controls.clear()

        for item in self.api_keys:
            self.api_key_list.controls.append(
                ft.ListTile(
                    title=ft.Text(item.name),
                    subtitle=ft.Text(item.url, max_lines=1),
                    trailing=ft.IconButton(
                        icon=ft.Icons.EDIT,
                        tooltip=f"「{item.name}」のAPIキー設定を編集する",
                        on_click=self._make_edit_api_key_handler(item),
                    ),
                )
            )

        safe_update(self.api_key_list)

    def _add_api_key(self, e: ft.ControlEvent) -> None:
        def on_submit(values: dict) -> None:
            plain = values.get("key", "")
            self.api_keys.append(
                ApiKeyItem(
                    name=values["name"],
                    url=values.get("url", ""),
                    key_encrypted=encrypt_secret(plain) if plain else "",
                    note=values.get("note", ""),
                )
            )
            ui_log.log_action("設定", "add", values["name"])
            self._persist_api_keys("APIキーを追加しました")

        show_item_form_dialog(self.page, "APIキーを追加", API_KEY_FIELDS, None, on_submit)

    def _make_edit_api_key_handler(self, item: ApiKeyItem):
        def handler(e: ft.ControlEvent) -> None:
            # ✅ 既存のAPIキーは復号して表示しない（欄は常に空欄）
            initial = {"name": item.name, "url": item.url, "note": item.note}

            def on_submit(values: dict) -> None:
                item.name = values["name"]
                item.url = values.get("url", "")
                item.note = values.get("note", "")

                plain = values.get("key", "")
                if plain:
                    item.key_encrypted = encrypt_secret(plain)

                ui_log.log_action("設定", "edit", item.name)
                self._persist_api_keys("APIキーを更新しました")

            def on_delete() -> None:
                name = item.name
                self.api_keys.remove(item)
                ui_log.log_action("設定", "delete", name)
                self._persist_api_keys("APIキーを削除しました")

            show_item_form_dialog(
                self.page, f"APIキーを編集: {item.name}", API_KEY_FIELDS, initial, on_submit, on_delete
            )

        return handler

    def _persist_api_keys(self, message: str) -> None:
        save_api_keys(SETTINGS_PATH, self.api_keys)
        self._refresh_api_key_list()
        show_toast(self.page, message)
