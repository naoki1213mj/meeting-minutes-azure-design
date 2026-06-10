from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import cast

from azure.core.credentials import TokenCredential
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    UserDelegationKey,
    generate_blob_sas,
)

from meeting_minutes_backend.blob_sas import BlobSasIssuer, UploadSas


@dataclass
class _CachedDelegationKey:
    key: UserDelegationKey
    expires_at: datetime


class AzureBlobSasIssuer(BlobSasIssuer):
    def __init__(
        self,
        account_url: str,
        container_name: str,
        credential: TokenCredential,
        ttl_minutes: int = 30,
        read_ttl_minutes: int = 90,
    ) -> None:
        self._container_name = container_name
        self._ttl_minutes = ttl_minutes
        self._read_ttl_minutes = read_ttl_minutes
        self._service_client = BlobServiceClient(account_url=account_url, credential=credential)
        self._delegation_key: _CachedDelegationKey | None = None
        self._lock = Lock()

    def create_upload_sas(
        self,
        blob_name: str,
        now: datetime,
        ttl_minutes: int | None = None,
    ) -> UploadSas:
        now_utc = _ensure_utc(now)
        start = now_utc - timedelta(minutes=5)
        expires_at = now_utc + timedelta(minutes=ttl_minutes or self._ttl_minutes)
        delegation_key = self._get_user_delegation_key(now_utc, expires_at)
        sas_token = generate_blob_sas(
            account_name=str(self._service_client.account_name),
            container_name=self._container_name,
            blob_name=blob_name,
            user_delegation_key=delegation_key,
            permission=BlobSasPermissions(create=True, write=True),
            start=start,
            expiry=expires_at,
            protocol="https",
        )
        blob_client = self._service_client.get_blob_client(self._container_name, blob_name)
        return UploadSas(url=f"{blob_client.url}?{sas_token}", expires_at=expires_at)

    def create_read_sas(
        self,
        blob_name: str,
        now: datetime,
        ttl_minutes: int | None = None,
    ) -> UploadSas:
        now_utc = _ensure_utc(now)
        start = now_utc - timedelta(minutes=5)
        expires_at = now_utc + timedelta(minutes=ttl_minutes or self._read_ttl_minutes)
        delegation_key = self._get_user_delegation_key(now_utc, expires_at)
        sas_token = generate_blob_sas(
            account_name=str(self._service_client.account_name),
            container_name=self._container_name,
            blob_name=blob_name,
            user_delegation_key=delegation_key,
            permission=BlobSasPermissions(read=True),
            start=start,
            expiry=expires_at,
            protocol="https",
        )
        blob_client = self._service_client.get_blob_client(self._container_name, blob_name)
        return UploadSas(url=f"{blob_client.url}?{sas_token}", expires_at=expires_at)

    def _get_user_delegation_key(
        self, now: datetime, required_expiry: datetime
    ) -> UserDelegationKey:
        with self._lock:
            if (
                self._delegation_key
                and self._delegation_key.expires_at > now + timedelta(minutes=15)
                and self._delegation_key.expires_at >= required_expiry
            ):
                return self._delegation_key.key

            key_start = now - timedelta(minutes=5)
            key_expiry = max(required_expiry, now + timedelta(hours=1))
            key = cast(
                UserDelegationKey,
                self._service_client.get_user_delegation_key(key_start, key_expiry),
            )
            self._delegation_key = _CachedDelegationKey(key=key, expires_at=key_expiry)
            return key


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
