from __future__ import annotations

from azure.storage.blob import BlobServiceClient

from .base import BlobObject, ProductFeed


class AzureProductFeed(ProductFeed):
    def __init__(self, account_url: str, container: str, sas_token: str):
        self.client = BlobServiceClient(account_url=account_url, credential=sas_token)
        self.container = self.client.get_container_client(container)

    def list_objects(self) -> list[BlobObject]:
        return [BlobObject(blob.name) for blob in self.container.list_blobs(name_starts_with="products/")]

    def read_object(self, name: str) -> str:
        return self.container.get_blob_client(name).download_blob().readall().decode("utf-8")
