from __future__ import annotations

import base64
import hmac
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass

from meeting_minutes_backend.errors import AppError

PROXY_SECRET_HEADER = "x-proxy-secret"  # noqa: S105 - HTTP header name, not a secret

TENANT_CLAIM_TYPES = {
    "tid",
    "http://schemas.microsoft.com/identity/claims/tenantid",
}
USER_CLAIM_TYPES = {
    "oid",
    "http://schemas.microsoft.com/identity/claims/objectidentifier",
}


@dataclass(frozen=True)
class AuthContext:
    tenant_id: str
    user_id: str


def resolve_auth_context(headers: Mapping[str, str]) -> AuthContext:
    _require_proxy_secret(headers)

    auth_mode = os.getenv("MEETING_MINUTES_AUTH_MODE", "").lower()
    is_local = _is_local_environment()

    if auth_mode == "demo" and not is_local:
        return AuthContext(
            tenant_id=os.getenv("MEETING_MINUTES_DEMO_TENANT_ID", "demo-tenant"),
            user_id=os.getenv("MEETING_MINUTES_DEMO_USER_ID", "demo-user"),
        )

    principal = _parse_easy_auth_principal(headers)
    if principal is not None:
        return principal

    if is_local:
        tenant_id = headers.get("x-dev-tenant-id", "local-tenant")
        user_id = headers.get("x-dev-user-id", "local-user")
        return AuthContext(tenant_id=tenant_id, user_id=user_id)

    if auth_mode == "demo":
        return AuthContext(
            tenant_id=os.getenv("MEETING_MINUTES_DEMO_TENANT_ID", "demo-tenant"),
            user_id=os.getenv("MEETING_MINUTES_DEMO_USER_ID", "demo-user"),
        )

    raise AppError(
        code="AUTH_REQUIRED",
        message="認証が必要です。サインインしてから再実行してください。",
        http_status=401,
    )


def _require_proxy_secret(headers: Mapping[str, str]) -> None:
    """Enforce the App Service -> Functions shared secret.

    The frontend reverse proxy injects ``x-proxy-secret`` so that the Functions
    HTTP endpoints cannot be reached directly with a public URL. This secret is
    distinct from the customer-facing access key and is never sent to browsers.
    """

    expected = os.getenv("MEETING_MINUTES_PROXY_SECRET", "").strip()
    if not expected:
        # Fail closed only on a real Azure host where the setting must exist.
        if os.getenv("WEBSITE_SITE_NAME"):
            raise AppError(
                code="AUTH_REQUIRED",
                message="アクセス設定が未構成です。管理者にお問い合わせください。",
                http_status=503,
            )
        return

    provided = headers.get(PROXY_SECRET_HEADER, "")
    if not hmac.compare_digest(provided, expected):
        raise AppError(
            code="AUTH_REQUIRED",
            message="認証が必要です。指定されたURLとアクセスキーでアクセスしてください。",
            http_status=401,
        )


def _parse_easy_auth_principal(headers: Mapping[str, str]) -> AuthContext | None:
    encoded = headers.get("x-ms-client-principal")
    if not encoded:
        return None

    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        principal = json.loads(base64.b64decode(padded).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        raise AppError(
            code="AUTH_REQUIRED",
            message="認証情報を確認できませんでした。再度サインインしてください。",
            http_status=401,
        ) from None

    claims = principal.get("claims", [])
    if not isinstance(claims, list):
        raise AppError(
            code="AUTH_REQUIRED",
            message="認証情報を確認できませんでした。再度サインインしてください。",
            http_status=401,
        )

    claim_values: dict[str, str] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_type = claim.get("typ")
        claim_value = claim.get("val")
        if isinstance(claim_type, str) and isinstance(claim_value, str):
            claim_values[claim_type] = claim_value

    tenant_id = _first_claim_value(claim_values, TENANT_CLAIM_TYPES)
    user_id = _first_claim_value(claim_values, USER_CLAIM_TYPES) or headers.get(
        "x-ms-client-principal-id"
    )

    if not tenant_id or not user_id:
        raise AppError(
            code="AUTH_REQUIRED",
            message="認証情報に必要な識別子が含まれていません。",
            http_status=401,
        )

    return AuthContext(tenant_id=tenant_id, user_id=user_id)


def _first_claim_value(claim_values: Mapping[str, str], claim_types: set[str]) -> str | None:
    for claim_type in claim_types:
        value = claim_values.get(claim_type)
        if value:
            return value
    return None


def _is_local_environment() -> bool:
    meeting_minutes_env = os.getenv("MEETING_MINUTES_ENV")
    if meeting_minutes_env:
        return meeting_minutes_env.lower() == "local"
    return os.getenv("ENVIRONMENT", "local").lower() == "local"
