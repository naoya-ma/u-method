import requests
from services.storage.base_storage import StorageService


class FlowStorageService(StorageService):

    def __init__(self, flow_url):
        self.url = flow_url

    def download(self, remote_path, local_path):
        r = requests.post(self.url, json={
            "action": "download",
            "path": remote_path
        })

        with open(local_path, "wb") as f:
            f.write(r.content)

    def upload(self, local_path, remote_path):
        with open(local_path, "rb") as f:
            requests.post(self.url, files={
                "file": f
            }, data={
                "path": remote_path
            })

    def list_files(self, remote_path):
        r = requests.post(self.url, json={
            "action": "list",
            "path": remote_path
        })
        return r.json()