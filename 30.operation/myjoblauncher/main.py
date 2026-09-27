import argparse
import os
import threading
import time

from services.applog import log as _applog
from services.config_loader import load_config
from services.device_repo import sync_device_at_startup
from services.execution_engine import terminate_all_active_processes
from services.history_repo import init_db
from services.scheduler_service import SchedulerService
from services.portal_repo import PORTAL_PATH
from services.startup_timer import elapsed as _elapsed
from services.startup_timer import start_heartbeat as _start_heartbeat
from services.startup_timer import startup_step as _startup_step
from services.startup_timer import stop_heartbeat as _stop_heartbeat
from services.sync_service import auto_check_app_update, auto_download_master, auto_download_portal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launcher MVP")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--gui", action="store_true", help="デスクトップウィンドウで起動する"
    )
    mode_group.add_argument(
        "--web", action="store_true", help="Webブラウザで起動する（既定）"
    )
    mode_group.add_argument(
        "--tui", action="store_true", help="ターミナルで起動する（curses、Fletを使わないモード。実行・履歴確認のみ）"
    )

    parser.add_argument("--host", default=None, help="Web起動時のバインドホスト（例: 0.0.0.0）")
    parser.add_argument("--port", type=int, default=8550, help="Web起動時のポート番号")
    parser.add_argument(
        "--verbose", action="store_true", help="起動時にメニュー項目一覧・各初期処理ステップの経過時間を出力する"
    )
    return parser.parse_args()


def _run_startup_steps(verbose: bool):
    """
    起動時の前処理（DB初期化・共有マスター/ホーム定義の自動ダウンロード・アプリ更新チェック・
    ジョブ定義読込・スケジューラ起動）をまとめて実行し、(menu_items, scheduler) を返す。

    これらはネットワークI/O（ストレージ同期）を含み、環境によっては数秒〜十数秒かかることがある。
    `--verbose`時は各ステップを`_startup_step()`で囲み、実行中はスピナー、完了時には
    区間所要時間と`_elapsed()`（プロセス起動からの累計経過時間）を出力する。
    tui/gui/webの3モードすべてから共通で呼ぶ（gui/webでは`page.run_thread()`のバックグラウンド
    スレッドから呼ばれる。詳細はmain()側のコメントを参照）
    """
    with _startup_step("DB初期化", verbose):
        init_db()

    with _startup_step("デバイス登録", verbose):
        # ✅ 統合業務管理（項目単位同期）フェーズ1: この端末の物理暗号（ULID）を
        # 初回起動時に自動生成し（以後不変）、ストレージが有効なら共有ストレージへ
        # 自分の情報を登録する（roleがmasterなら全端末一覧の集約も行う）。
        # 詳細はDESIGN.md「11. 統合業務管理（項目単位同期）」11.3 フェーズ1を参照
        identity = sync_device_at_startup("config/menu.toml")

        # ✅ ユーザーからの要望: 論理番号が未割当のままだと、統合業務管理フェーズ3の
        # 項目単位同期（services/item_sync.py、次期開発ロードマップ関連）でjob_idの
        # 名前空間がULID末尾8文字の代用にフォールバックしたままになる（CLAUDE.md
        # 「ジョブIDの採番方式」参照）。masterによる割り当て漏れ・ストレージ未接続等に
        # 気付きやすくするため、未割当の間は起動のたびにコンソール・運用ログへ警告する
        if not identity.logical_number:
            _warning = (
                f"この端末の論理番号が未割当です（物理暗号={identity.device_id[:8]}…）。"
                "「設定」タブの「デバイス管理」でmasterロールの端末に割り当てを依頼してください"
                "（未割当の間はjob_idの名前空間がULID末尾8文字の代用になります）"
            )
            print(f"[起動] 警告: {_warning}")
            _applog("WARNING", _warning, func_name="sync_device_at_startup")

    with _startup_step("共有マスター設定の同期", verbose):
        auto_download_master("config/menu.toml", verbose=verbose)

    with _startup_step("ホーム定義の同期", verbose):
        auto_download_portal("config/menu.toml", PORTAL_PATH, verbose=verbose)

    with _startup_step("アプリ更新チェック", verbose):
        auto_check_app_update("config/menu.toml", verbose=verbose)

    with _startup_step("ジョブ定義の読込", verbose):
        menu_items = load_config("config/menu.toml")

    if verbose:
        print(menu_items)

    with _startup_step("スケジューラ起動", verbose):
        scheduler = SchedulerService()
        scheduler.load_jobs(menu_items)
        scheduler.start()

    return menu_items, scheduler


def main() -> None:
    args = parse_args()
    # ✅ 既定はWeb版（--gui省略時にflet.exeのネイティブデスクトップランタイムを起動しないため。
    #    Windows Smart App Controlがこの未署名バイナリの起動をブロックする不具合を実機で確認済み）
    mode = "tui" if args.tui else "gui" if args.gui else "web"

    if mode == "tui":
        # ✅ Fletを使わない、curses ベースのターミナルUI（実行・履歴確認のみ）。
        # ウィンドウ/ブラウザを開く前処理が無いため、従来通り起動前に同期的に前処理を済ませる
        menu_items, scheduler = _run_startup_steps(args.verbose)
        try:
            from tui.app import run_tui

            run_tui("config/menu.toml")
        except KeyboardInterrupt:
            print("\nCtrl+C detected → shutting down...")
        finally:
            scheduler.shutdown()
            terminate_all_active_processes()
        return

    # ✅ 起動時の前処理（共有マスター同期・アプリ更新チェック等のネットワークI/O）は
    # 数秒〜十数秒かかることがあり、これを画面表示より前に同期的に行っていた旧実装では、
    # ウィンドウ/ブラウザタブが開くまでの間ユーザーには一切の進捗が見えず「結構な待ち時間」に
    # 感じられる不具合をユーザーから指摘された（--gui/--web共通）。対策として、まず
    # `ft.run()`でウィンドウ/サーバーを即座に起動してスプラッシュを表示し、前処理自体は
    # `page.run_thread()`のバックグラウンドスレッドへ回してから、完了後にMainWindowへ
    # 差し替える構成にした（②の段階）。さらに、`import flet`自体やFletクライアント自身の
    # 起動処理（ウィンドウ生成/ブラウザタブオープン）はFletにすら依存できない「見えない区間」
    # のため、`ft.run()`を呼ぶ直前からコンソールの簡易スピナーを走らせておく（①の段階）。
    # schedulerは背景スレッド側で生成されるため、プロセス終了時の後始末（finallyブロック）
    # から参照できるよう、可変コンテナ（辞書）で受け渡す
    state = {"scheduler": None}

    launch_label = "Fletを起動しウィンドウ/ブラウザタブを開く準備"
    launch_heartbeat = _start_heartbeat(launch_label) if args.verbose else None
    launch_start = time.perf_counter()

    # ✅ GUI/Web版のみ、この時点で初めてFletを読み込む（--tui時はFletを一切使わない）
    import flet as ft
    from gui.main_window import MainWindow

    def flet_main(page: ft.Page) -> None:
        # ✅ ①の区間（Flet自体のimport・クライアント起動）はここで終わり、②（Flet自身の
        # スプラッシュ＋前処理）へ引き継ぐ
        if launch_heartbeat is not None:
            _stop_heartbeat(launch_heartbeat, launch_label, launch_start)

        page.title = "myJobLauncher"

        # ✅ スプラッシュもMainWindow構築後の本画面と同じ配色で見せるため、テーマは
        # スプラッシュ表示より前に適用しておく（MainWindow.__init__側でも同じ呼び出しを
        # 行うが、apply_theme()はべき等なので二重適用しても害は無い）
        from services import theme_repo

        theme_repo.apply_theme(page)

        # ✅ 起動スプラッシュ: 前処理（ネットワークI/O含む）が終わるまでの間、
        # 「起動中です」を即座に表示する（ユーザーからの要望）
        splash_view = ft.Container(
            content=ft.Column(
                [
                    ft.ProgressRing(),
                    ft.Container(height=16),
                    ft.Text("起動中です。しばらくお待ちください…"),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
        page.add(splash_view)

        def build() -> None:
            menu_items, scheduler = _run_startup_steps(args.verbose)
            state["scheduler"] = scheduler

            if mode == "gui":
                from services import window_repo

                # ✅ 起動時のちらつき対策として一時的に page.window.visible=False→True の
                # 切り替えを試したが、実機（--gui）で「最終的にウィンドウが非表示のまま戻って
                # こない」不具合が発生したため撤去した（Flet 1.0.1のデスクトップクライアントで
                # 一度hiddenにした後の再表示が確実に反映されない模様。詳細はCLAUDE.mdの注意事項）。
                # ウィンドウの表示/非表示切り替えは今後再検討する場合も実機で必ず確認すること
                width, height = window_repo.load_window_size()
                page.window.width = width
                page.window.height = height

                # ✅ ウィンドウを閉じたらスケジューラ・実行中の子プロセスも停止（デスクトップ時のみ）。
                # リサイズ完了時（RESIZED、ドラッグ中のRESIZEは対象外）には現在のウィンドウサイズを
                # 保存し、次回起動時に復元する（window_repo.load_window_size()が異常値は
                # 既定値へフォールバックするため、保存前のバリデーションはここでは不要）
                def on_window_event(e: ft.WindowEvent) -> None:
                    if e.type == ft.WindowEventType.CLOSE:
                        scheduler.shutdown()
                        terminate_all_active_processes()
                    elif e.type == ft.WindowEventType.RESIZED:
                        window_repo.save_window_size(page.window.width, page.window.height)

                page.window.on_event = on_window_event

            elif mode == "web":
                # ✅ --web版もブラウザタブを閉じたらコンソール（サーバープロセス）ごと
                # 自動終了してほしいというユーザーからの要望（--guiでウィンドウを閉じたときの
                # 挙動と揃える）。ただしpage.on_disconnectはブラウザの単純なリロード（F5等）
                # でも一度切断→即再接続という形で発火するため、切断を検知したら即座に
                # プロセスを終了せず、数秒待っても再接続（on_connect）が来ない場合のみ
                # 「タブを閉じた」とみなして終了する（デバウンス）
                disconnect_state = {"timer": None}

                def _shutdown_after_disconnect() -> None:
                    scheduler.shutdown()
                    terminate_all_active_processes()
                    os._exit(0)

                def on_disconnect(e: ft.ControlEvent) -> None:
                    timer = threading.Timer(3.0, _shutdown_after_disconnect)
                    timer.daemon = True
                    disconnect_state["timer"] = timer
                    timer.start()

                def on_connect(e: ft.ControlEvent) -> None:
                    timer = disconnect_state["timer"]
                    if timer is not None:
                        timer.cancel()
                        disconnect_state["timer"] = None

                page.on_disconnect = on_disconnect
                page.on_connect = on_connect

            # ✅ MainWindow構築完了時（splash_view.visible=False + root_row.visible=True +
            # page.update()の一括切り替え）にスプラッシュから本画面へ一気に差し替わる
            MainWindow(page, menu_items, scheduler, splash_view=splash_view, verbose=args.verbose)

            if args.verbose:
                print(f"[起動] 画面構築 完了（累計{_elapsed():.2f}秒経過）")

        page.run_thread(build)

    try:
        # ✅ イベントループ開始
        # assets_dir: ツール/リンクのアイコンPNG（services/icon_cache.py）をFletの静的アセット
        # 配信でHTTP経由で読み込ませるため（詳細はgui/icon_grid_view.pyの_entry_icon()コメント、
        # CLAUDE.mdの注意事項を参照）。相対パス文字列だとFletが`os.getcwd()`基準で解決するが、
        # `uv run mj`（インストール済みスクリプトのシム経由）で起動した場合はcwdが
        # リポジトリ直下にならないことがある（`.venv\\Scripts`になる等）ことを実機で確認したため、
        # `__file__`基準の絶対パスを明示的に組み立てて渡す
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "icons")
        if mode == "web":
            ft.run(flet_main, view=ft.AppView.WEB_BROWSER, host=args.host, port=args.port, assets_dir=assets_dir)
        else:
            ft.run(flet_main, assets_dir=assets_dir)
    except KeyboardInterrupt:
        print("\nCtrl+C detected → shutting down...")
    finally:
        # 終了処理（念のため）: スケジューラ停止 → 実行中の子プロセスを強制終了
        # （DBコネクション・設定ファイルは各操作の try/finally で都度close済み）
        if state["scheduler"] is not None:
            state["scheduler"].shutdown()
        terminate_all_active_processes()


if __name__ == "__main__":
    main()
