"""
Adversarial Security & Authentication Tests.

Tests security boundaries, JWT attacks, and RBAC enforcement:
- Algorithm confusion ('none' algorithm attacks).
- Token signature tampering and forged secrets.
- Expired token replay attacks.
- Malformed and corrupt Authorization header parsing.
- Subject claim injection (SQL injection in sub).
- Suspended/inactive account token presentation.
- Role-based privilege escalation (Operator attempting Admin mutations).
- Cross-identity IDOR (Insecure Direct Object Reference) access control.
"""

import base64
import datetime
from typing import Dict
from httpx import AsyncClient
from jose import jwt
import pytest

from backend.api.auth import create_jwt_token
from backend.config import settings


@pytest.mark.asyncio
async def test_none_algorithm_jwt_rejected(async_client: AsyncClient):
    """
    Adversarial Attack: Attempting to bypass signature verification using 'none' algorithm.
    Expected: Rejected with 401 Unauthorized.
    """
    # Forge unsigned token with header {"alg": "none", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(b'{"sub":"1","role":"admin","exp":9999999999}').decode().rstrip("=")
    forged_token = f"{header_b64}.{payload_b64}."

    response = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tampered_signature_rejected(async_client: AsyncClient, admin_token: str):
    """
    Adversarial Attack: Modifying token signature bytes.
    Expected: Rejected with 401 Unauthorized.
    """
    parts = admin_token.split(".")
    tampered_sig = parts[2][:-4] + "AAAA"
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"

    response = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_foreign_secret_key_rejected(async_client: AsyncClient):
    """
    Adversarial Attack: Signing valid payload with an arbitrary external secret key.
    Expected: Rejected with 401 Unauthorized.
    """
    foreign_token = jwt.encode(
        {"sub": "1", "role": "admin", "exp": 9999999999},
        key="completely-wrong-attacker-secret-key-12345",
        algorithm=settings.jwt_algorithm,
    )
    response = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {foreign_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_rejected(async_client: AsyncClient):
    """
    Adversarial Attack: Replaying an expired access token.
    Expected: Rejected with 401 Unauthorized.
    """
    expired_token = create_jwt_token(
        data={"sub": "1", "role": "admin"},
        expires_delta=datetime.timedelta(seconds=-30),
    )
    response = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_header",
    [
        "",
        "Bearer",
        "Bearer ",
        "Basic dXNlcjpwYXNz",
        "Token abcdef12345",
        "Bearer not.a.valid.jwt",
        "Bearer part1.part2",
        "Bearer part1.part2.part3.part4",
    ],
)
async def test_malformed_auth_headers_rejected(async_client: AsyncClient, malformed_header: str):
    """
    Adversarial Attack: Sending malformed Authorization header formats.
    Expected: Rejected with 401 Unauthorized.
    """
    headers = {"Authorization": malformed_header} if malformed_header else {}
    response = await async_client.get("/auth/me", headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sql_injection_in_jwt_subject(async_client: AsyncClient):
    """
    Adversarial Attack: Presenting a validly signed JWT with SQL injection payload in 'sub'.
    Expected: Rejected cleanly with 401 without 500 server crash or database leakage.
    """
    sqli_token = create_jwt_token(
        data={"sub": "1' OR '1'='1; DROP TABLE staff_users; --", "role": "admin"},
        expires_delta=datetime.timedelta(minutes=15),
    )
    response = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {sqli_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_suspended_account_token_rejected(
    async_client: AsyncClient,
    inactive_headers: Dict[str, str],
):
    """
    Security Invariant: Even if a token signature is valid, deactivated/suspended accounts
    must be immediately denied access upon next API request.
    """
    response = await async_client.get("/auth/me", headers=inactive_headers)
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_privilege_escalation_operator_blocked_from_admin_routes(
    async_client: AsyncClient,
    operator_headers: Dict[str, str],
):
    """
    Privilege Escalation Gate: Valid operator token attempting to call admin-restricted endpoints.
    Expected: Strictly rejected with 403 Forbidden.
    """
    # 1. Global analytics dashboard access (restricted to admin)
    resp1 = await async_client.get(
        "/api/analytics/dashboard",
        headers=operator_headers,
    )
    assert resp1.status_code == 403

    # 2. Campaign cancellation
    resp2 = await async_client.patch(
        "/api/campaigns/1/cancel",
        headers=operator_headers,
    )
    assert resp2.status_code == 403

    # 3. Call retry
    resp3 = await async_client.post(
        "/api/calls/1/retry",
        headers=operator_headers,
    )
    assert resp3.status_code == 403
