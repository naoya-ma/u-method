from abc import ABC, abstractmethod


class StorageService(ABC):

    @abstractmethod
    def download(self, remote_path: str, local_path: str):
        pass

    @abstractmethod
    def upload(self, local_path: str, remote_path: str):
        pass

    @abstractmethod
    def list_files(self, remote_path: str):
        pass

    def get_remote_mtime(self, remote_path: str):
        """
        リモートファイルの最終更新日時（UNIXタイムスタンプ）を返す。
        取得非対応のストレージ種別は None を返す（呼び出し側は競合検知をスキップする）
        """
        return None

    def get_remote_hash(self, remote_path: str):
        """
        リモートファイルの内容ハッシュ値（sha256の16進文字列）を返す。
        取得非対応のストレージ種別は None を返す（呼び出し側はハッシュ比較をスキップし、
        タイムスタンプ比較の結果だけでダウンロード要否を判断する）
        """
        return None