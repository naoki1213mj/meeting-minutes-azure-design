from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch

from meeting_minutes_backend.blob_storage import AzureBlobSasIssuer


def test_azure_blob_sas_issuer_uses_user_delegation_key_and_https() -> None:
    service_client = Mock()
    service_client.account_name = "storageacct"
    service_client.get_user_delegation_key.return_value = Mock()
    blob_client = Mock()
    blob_client.url = "https://storageacct.blob.core.windows.net/audio/blob.mp3"
    service_client.get_blob_client.return_value = blob_client

    with (
        patch(
            "meeting_minutes_backend.blob_storage.BlobServiceClient",
            return_value=service_client,
        ),
        patch(
            "meeting_minutes_backend.blob_storage.generate_blob_sas",
            return_value="sig=REDACTED_TEST_VALUE",
        )
        as generate_sas,
    ):
        issuer = AzureBlobSasIssuer(
            account_url="https://storageacct.blob.core.windows.net",
            container_name="audio",
            credential=Mock(),
        )
        sas = issuer.create_upload_sas(
            "raw-audio/tenant/job/input.mp3",
            datetime(2026, 6, 1, tzinfo=UTC),
            ttl_minutes=120,
        )

    assert sas.url == (
        "https://storageacct.blob.core.windows.net/audio/blob.mp3?sig=REDACTED_TEST_VALUE"
    )
    service_client.get_user_delegation_key.assert_called_once()
    assert generate_sas.call_args.kwargs["account_name"] == "storageacct"
    assert generate_sas.call_args.kwargs["protocol"] == "https"
    assert generate_sas.call_args.kwargs["expiry"].minute == 0
