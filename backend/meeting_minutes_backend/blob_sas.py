from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from urllib.parse import quote


@dataclass(frozen=True)
class UploadSas:
    url: str
    expires_at: datetime


class BlobSasIssuer(Protocol):
    def create_upload_sas(
        self,
        blob_name: str,
        now: datetime,
        ttl_minutes: int | None = None,
    ) -> UploadSas:
        pass

    def create_read_sas(
        self,
        blob_name: str,
        now: datetime,
        ttl_minutes: int | None = None,
    ) -> UploadSas:
        pass


class LocalBlobSasIssuer:
    def __init__(self, ttl_minutes: int = 30) -> None:
        self._ttl_minutes = ttl_minutes

    def create_upload_sas(
        self,
        blob_name: str,
        now: datetime,
        ttl_minutes: int | None = None,
    ) -> UploadSas:
        expires_at = now + timedelta(minutes=ttl_minutes or self._ttl_minutes)
        encoded_blob_name = quote(blob_name, safe="/")
        return UploadSas(
            url=f"https://local.blob.invalid/{encoded_blob_name}?sig=local-dev-placeholder",
            expires_at=expires_at,
        )

    def create_read_sas(
        self,
        blob_name: str,
        now: datetime,
        ttl_minutes: int | None = None,
    ) -> UploadSas:
        return self.create_upload_sas(blob_name, now, ttl_minutes=ttl_minutes)
