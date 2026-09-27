import hashlib
import shutil
import os
from services.path_utils import expand_path
from services.storage.base_storage import StorageService


class LocalStorageService(StorageService):

    def __init__(self, base_dir):
        self.base_dir = expand_path(base_dir)

    def _full(self, remote_path):
        return os.path.join(self.base_dir, remote_path)

    def download(self, remote_path, local_path):
        shutil.copy(self._full(remote_path), local_path)

    def upload(self, local_path, remote_path):
        full_path = self._full(remote_path)
        # ✅ デバイス管理（devices/<device_id>.toml等）のように、端末ごとに別ファイルへ
        # 書き込む用途では、リモート側のサブディレクトリがまだ存在しないことがあるため、
        # 上書きコピー前に親フォルダを作成しておく
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
        shutil.copy(local_path, full_path)

    def list_files(self, remote_path):
        path = self._full(remote_path)
        if not os.path.isdir(path):
            # ✅ まだ誰も書き込んでいない（フォルダ自体が無い）場合は空一覧を返す。
            # デバイス管理のように、最初は誰も居ないディレクトリを対象にする用途があるため
            return []
        return os.listdir(path)

    def get_remote_mtime(self, remote_path):
        path = self._full(remote_path)
        if not os.path.exists(path):
            return None
        return os.path.getmtime(path)

    def get_remote_hash(self, remote_path):
        path = self._full(remote_path)
        if not os.path.exists(path):
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
