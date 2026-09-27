from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from services.config_loader import is_skeleton_job
from services.execution_engine import start_process, stream_process, build_result
from services.history_repo import insert_history_with_id
from services import applog, tz_repo

import uuid6
import os


class SchedulerService:

    def __init__(self):
        # ✅ cronスケジュールは設定されたタイムゾーン（既定: Asia/Tokyo）で解釈する
        self.scheduler = BackgroundScheduler(timezone=tz_repo.get_zoneinfo())
        os.makedirs("logs", exist_ok=True)

    # ========================
    # スケジューラ開始
    # ========================
    def start(self):
        self.scheduler.start()

    # ========================
    # ジョブ登録
    # ========================
    def load_jobs(self, menu_items):
        """
        TOMLのスケジュール設定を読み込み
        cron形式: "0 9 * * *"
        """

        for item in menu_items:
            if not item.schedule:
                continue

            if getattr(item, "job_type", "定型") == "非定型":
                print(f"[Scheduler] 非定型業務はスケジュール実行の対象外です: {item.name}")
                continue

            if not getattr(item, "enabled", True):
                print(f"[Scheduler] 無効化されたジョブはスケジュール実行の対象外です: {item.name}")
                continue

            if is_skeleton_job(item):
                print(f"[Scheduler] 骨組み状態（コマンド未設定）のジョブはスケジュール実行の対象外です: {item.name}")
                continue

            try:
                parts = item.schedule.split()
                if len(parts) != 5:
                    print(f"[Scheduler] format error: {item.name}")
                    continue

                minute, hour, day, month, day_of_week = parts

                trigger = CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week
                )

                self.scheduler.add_job(
                    self._execute_job,
                    trigger=trigger,
                    args=[item],
                    id=f"job_{item.name}",
                    replace_existing=True
                )

                print(f"[Scheduler] 登録: {item.name} ({item.schedule})")

            except Exception as e:
                print(f"[Scheduler] 登録失敗: {item.name} - {e}")

    # ========================
    # 実行処理（スケジュール）
    # ========================
    def _execute_job(self, item):
        """
        スケジューラ経由でコマンド実行
        GUIとは独立して動く
        """

        print(f"[Scheduler] 実行開始: {item.name}")

        command_id = str(uuid6.uuid7())

        start_time = tz_repo.now()

        def on_output(line):
            text = line.rstrip()
            is_error = "[ERR]" in text
            applog.log(
                "ERROR" if is_error else "INFO",
                text,
                func_name="_execute_job",
                command_id=command_id,
            )

        try:
            # ✅ プロセス開始
            process = start_process(item.command)

            # ✅ ストリーム処理
            stdout_buf, stderr_buf = stream_process(process, on_output)

            # ✅ 結果作成
            result = build_result(
                process,
                item.command,
                stdout_buf,
                stderr_buf,
                start_time
            )

            insert_history_with_id(command_id, result)

            duration = (result.end_time - result.start_time).total_seconds()

            print(
                f"[Scheduler] 完了: {item.name} "
                f"return={result.returncode} time={duration:.2f}s"
            )

        except Exception as e:
            print(f"[Scheduler] エラー: {item.name} - {e}")

    # ========================
    # 単発の予定実行（実行タブの複数選択「時刻を指定して実行」用）
    # ========================
    def run_once_at(self, item, run_at, on_start=None, on_finish=None):
        """
        指定日時に1回だけ item を実行する。GUIとは独立したスレッドで動作するため、
        on_start/on_finish で呼び出し元（RunTab）へ開始・終了を通知できる。
        """

        def job_func():
            if on_start:
                on_start()
            try:
                self._execute_job(item)
            finally:
                if on_finish:
                    on_finish()

        job_id = f"once_{item.name}_{uuid6.uuid7()}"
        self.scheduler.add_job(job_func, trigger="date", run_date=run_at, id=job_id, replace_existing=False)

    # ========================
    # 停止
    # ========================
    def shutdown(self):
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            pass
