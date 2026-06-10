from __future__ import annotations

import json
from os import PathLike
from typing import Any

from azure.core.credentials import TokenCredential
from azure.storage.blob import BlobServiceClient, ContentSettings


class BlobArtifactStore:
    def __init__(self, account_url: str, credential: TokenCredential) -> None:
        self._service_client = BlobServiceClient(account_url=account_url, credential=credential)

    def write_json(self, container_name: str, blob_name: str, data: object) -> str:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        blob_client = self._service_client.get_blob_client(container_name, blob_name)
        blob_client.upload_blob(
            payload,
            overwrite=True,
            content_settings=ContentSettings(content_type="application/json; charset=utf-8"),
        )
        return str(blob_client.url)

    def read_json(self, container_name: str, blob_name: str) -> dict[str, Any]:
        blob_client = self._service_client.get_blob_client(container_name, blob_name)
        payload = blob_client.download_blob().readall()
        data = json.loads(payload.decode("utf-8"))
        if not isinstance(data, dict):
            raise TypeError("JSON artifact must be an object")
        return data

    def write_text(self, container_name: str, blob_name: str, text: str) -> str:
        blob_client = self._service_client.get_blob_client(container_name, blob_name)
        blob_client.upload_blob(
            text.encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(content_type="text/markdown; charset=utf-8"),
        )
        return str(blob_client.url)

    def read_text(self, container_name: str, blob_name: str) -> str:
        blob_client = self._service_client.get_blob_client(container_name, blob_name)
        return blob_client.download_blob().readall().decode("utf-8")

    def get_blob_size(self, container_name: str, blob_name: str) -> int:
        blob_client = self._service_client.get_blob_client(container_name, blob_name)
        properties = blob_client.get_blob_properties()
        size = properties.size
        if size is None:
            size = properties.content_length
        return int(size)

    def download_to_path(
        self,
        container_name: str,
        blob_name: str,
        destination_path: str | PathLike[str],
    ) -> None:
        blob_client = self._service_client.get_blob_client(container_name, blob_name)
        with open(destination_path, "wb") as destination:
            blob_client.download_blob().readinto(destination)

    def upload_file(
        self,
        container_name: str,
        blob_name: str,
        source_path: str | PathLike[str],
        content_type: str,
    ) -> str:
        blob_client = self._service_client.get_blob_client(container_name, blob_name)
        with open(source_path, "rb") as source:
            blob_client.upload_blob(
                source,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
        return str(blob_client.url)
