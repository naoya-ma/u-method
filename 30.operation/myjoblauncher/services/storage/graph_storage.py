from services.storage.base_storage import StorageService


class GraphStorageService(StorageService):

    def __init__(self, graph_client):
        self.client = graph_client

    def download(self, remote_path, local_path):
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{remote_path}:/content"

        r = self.client.get(url)

        with open(local_path, "wb") as f:
            f.write(r.content)

    def upload(self, local_path, remote_path):
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{remote_path}:/content"

        with open(local_path, "rb") as f:
            self.client.put(url, f.read())

    def list_files(self, remote_path):
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{remote_path}:/children"
        return self.client.get(url).json()