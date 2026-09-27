import os
import urllib.parse
import webbrowser
from pathlib import Path

from services import stopwatch_repo
from services.path_utils import expand_path


def open_target(target: str) -> None:
    """
    URL（http/https/file）ならブラウザで、それ以外はローカルのフォルダ/ファイルとして開く。
    file://はクエリパラメータ付きURL（build_stopwatch_url等）を渡すために必要。
    os.startfile()はURLクエリを正しく扱えず、"?"以降を含めてファイルパスとして
    解釈しようとして失敗する（実際に踏んだ不具合: 非定型ジョブ実行時にURLパラメータが
    渡らなかった）ため、file://は必ずwebbrowser.open()を経由させること
    """
    if target.startswith(("http://", "https://", "file://")):
        webbrowser.open(target)
    else:
        os.startfile(target)


STOPWATCH_LAUNCH_COMMENT = "ランチャー連携開始"


def build_stopwatch_url(item) -> str:
    """
    業務記録プラグイン（dev-stopwatch）はURLクエリパラメータ id/job/comment で
    初期画面の「識別名(ユーザー名)」/JOB/COMMENT欄を事前入力できる（file://URIのクエリ文字列
    として渡す）。idは「設定」タブで登録した識別子（services/stopwatch_repo.py、
    config/app.tomlのstopwatch_identifier）、jobは選んだジョブ名、commentは
    myJobLauncher経由での起動であることが分かるよう固定文字列を渡す。
    起動先HTMLのパス（services/stopwatch_repo.py、config/app.tomlのstopwatch_html_path）は
    %USERPROFILE%等の環境変数を含められるため、Path().as_uri()へ渡す前に展開する
    """
    html_path = expand_path(stopwatch_repo.load_html_path())
    query = urllib.parse.urlencode(
        {
            "id": stopwatch_repo.load_identifier(),
            "job": item.name,
            "comment": STOPWATCH_LAUNCH_COMMENT,
        }
    )
    return f"{Path(html_path).as_uri()}?{query}"
