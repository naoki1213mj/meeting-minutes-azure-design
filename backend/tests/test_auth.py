from __future__ import annotations

import base64
import json

import pytest

from meeting_minutes_backend.auth import resolve_auth_context
from meeting_minutes_backend.errors import AppError


def test_resolve_easy_auth_principal_extracts_tenant_and_user() -> None:
    principal = {
        "claims": [
            {"typ": "http://schemas.microsoft.com/identity/claims/tenantid", "val": "tenant-a"},
            {
                "typ": "http://schemas.microsoft.com/identity/claims/objectidentifier",
                "val": "user-a",
            },
        ]
    }
    encoded = base64.b64encode(json.dumps(principal).encode("utf-8")).decode("utf-8")

    auth = resolve_auth_context({"x-ms-client-principal": encoded})

    assert auth.tenant_id == "tenant-a"
    assert auth.user_id == "user-a"


def test_missing_auth_in_production_raises_auth_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "azure")
    monkeypatch.delenv("MEETING_MINUTES_AUTH_MODE", raising=False)

    with pytest.raises(AppError) as exc_info:
        resolve_auth_context({})

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.http_status == 401


def test_dev_headers_do_not_bypass_azure_auth_without_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "azure")
    monkeypatch.delenv("MEETING_MINUTES_AUTH_MODE", raising=False)

    with pytest.raises(AppError) as exc_info:
        resolve_auth_context(
            {
                "x-dev-tenant-id": "tenant-a",
                "x-dev-user-id": "user-a",
            }
        )

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.http_status == 401


def test_dev_headers_are_ignored_in_azure_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "azure")
    monkeypatch.setenv("MEETING_MINUTES_AUTH_MODE", "demo")

    auth = resolve_auth_context(
        {
            "x-dev-tenant-id": "spoofed-tenant",
            "x-dev-user-id": "spoofed-user",
        }
    )

    assert auth.tenant_id == "demo-tenant"
    assert auth.user_id == "demo-user"


def test_easy_auth_header_is_ignored_in_azure_demo_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "azure")
    monkeypatch.setenv("MEETING_MINUTES_AUTH_MODE", "demo")
    principal = {
        "claims": [
            {"typ": "http://schemas.microsoft.com/identity/claims/tenantid", "val": "tenant-a"},
            {
                "typ": "http://schemas.microsoft.com/identity/claims/objectidentifier",
                "val": "user-a",
            },
        ]
    }
    encoded = base64.b64encode(json.dumps(principal).encode("utf-8")).decode("utf-8")

    auth = resolve_auth_context({"x-ms-client-principal": encoded})

    assert auth.tenant_id == "demo-tenant"
    assert auth.user_id == "demo-user"


def test_dev_headers_are_allowed_only_in_local_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "local")

    auth = resolve_auth_context(
        {
            "x-dev-tenant-id": "tenant-a",
            "x-dev-user-id": "user-a",
        }
    )

    assert auth.tenant_id == "tenant-a"
    assert auth.user_id == "user-a"


def test_proxy_secret_required_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "azure")
    monkeypatch.setenv("MEETING_MINUTES_AUTH_MODE", "demo")
    monkeypatch.setenv("MEETING_MINUTES_PROXY_SECRET", "proxy-secret-value")

    with pytest.raises(AppError) as exc_info:
        resolve_auth_context({})

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.http_status == 401


def test_proxy_secret_mismatch_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "azure")
    monkeypatch.setenv("MEETING_MINUTES_AUTH_MODE", "demo")
    monkeypatch.setenv("MEETING_MINUTES_PROXY_SECRET", "proxy-secret-value")

    with pytest.raises(AppError) as exc_info:
        resolve_auth_context({"x-proxy-secret": "wrong-value"})

    assert exc_info.value.http_status == 401


def test_proxy_secret_match_allows_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "azure")
    monkeypatch.setenv("MEETING_MINUTES_AUTH_MODE", "demo")
    monkeypatch.setenv("MEETING_MINUTES_PROXY_SECRET", "proxy-secret-value")

    auth = resolve_auth_context({"x-proxy-secret": "proxy-secret-value"})

    assert auth.tenant_id == "demo-tenant"
    assert auth.user_id == "demo-user"


def test_proxy_secret_unset_fails_closed_on_azure_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "azure")
    monkeypatch.setenv("MEETING_MINUTES_AUTH_MODE", "demo")
    monkeypatch.delenv("MEETING_MINUTES_PROXY_SECRET", raising=False)
    monkeypatch.setenv("WEBSITE_SITE_NAME", "mm-demo-web")

    with pytest.raises(AppError) as exc_info:
        resolve_auth_context({})

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.http_status == 503


def test_proxy_secret_unset_skipped_off_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "local")
    monkeypatch.delenv("MEETING_MINUTES_PROXY_SECRET", raising=False)
    monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)

    auth = resolve_auth_context(
        {
            "x-dev-tenant-id": "tenant-a",
            "x-dev-user-id": "user-a",
        }
    )

    assert auth.tenant_id == "tenant-a"
