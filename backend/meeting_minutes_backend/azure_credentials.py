from __future__ import annotations

import os
from typing import Protocol

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential


class CredentialFactory(Protocol):
    def __call__(self) -> TokenCredential:
        pass


def build_credential() -> TokenCredential:
    environment = os.getenv("MEETING_MINUTES_ENV", os.getenv("ENVIRONMENT", "local")).lower()
    if environment == "local":
        return DefaultAzureCredential()

    managed_identity_client_id = os.getenv("AZURE_CLIENT_ID")
    if managed_identity_client_id:
        return ManagedIdentityCredential(client_id=managed_identity_client_id)
    return ManagedIdentityCredential()
