"""Unit: the role guard - a USER token cannot reach super-admin endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import UserRole


@pytest.fixture
def user_token(identity) -> str:
    return identity.issue(
        subject="11111111-1111-4111-8111-111111111111",
        role=UserRole.USER,
        display_name="U",
        email="u@example.test",
    )


@pytest.fixture
def admin_token(identity) -> str:
    return identity.issue(
        subject="22222222-2222-4222-8222-222222222222",
        role=UserRole.SUPER_ADMIN,
        display_name="A",
        email="a@example.test",
    )


def test_no_token_is_401(client_no_db: TestClient) -> None:
    assert client_no_db.get("/api/v1/me").status_code == 401
    assert client_no_db.get("/api/v1/admin/users").status_code == 401


def test_garbage_token_is_401(client_no_db: TestClient) -> None:
    r = client_no_db.get("/api/v1/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_user_token_reaches_own_dashboard(client_no_db: TestClient, user_token: str) -> None:
    r = client_no_db.get("/api/v1/me", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    assert r.json()["role"] == "USER"


def test_user_token_cannot_reach_admin(client_no_db: TestClient, user_token: str) -> None:
    for path in ("/api/v1/admin/users", "/api/v1/admin/assignments"):
        r = client_no_db.get(path, headers={"Authorization": f"Bearer {user_token}"})
        assert r.status_code == 403, path


def test_admin_token_passes_the_guard(client_no_db: TestClient, admin_token: str) -> None:
    # Guard passes; the stubbed session then makes the handler raise -> 500,
    # never 401/403. The point here is only that the guard let it through.
    r = client_no_db.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code not in (401, 403)
