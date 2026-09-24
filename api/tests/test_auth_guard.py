"""Unit: the role guard - a USER token cannot reach super-admin endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import UserRole

from app.identity import MockIdentityProvider


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


def test_user_token_reaches_own_dashboard(client: TestClient, user_token: str) -> None:
    # /me loads the User row (for must_change_password/subscription), so this
    # needs a real (if empty) DB, not the MagicMock-stubbed client_no_db - the
    # token's subject has no matching row, which /me handles as "no
    # subscription provisioned" rather than an error.
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    assert r.json()["role"] == "USER"
    assert r.json()["subscription"] is None


def test_user_token_cannot_reach_admin(client_no_db: TestClient, user_token: str) -> None:
    for path in ("/api/v1/admin/users", "/api/v1/admin/assignments"):
        r = client_no_db.get(path, headers={"Authorization": f"Bearer {user_token}"})
        assert r.status_code == 403, path


def test_admin_token_passes_the_guard(client_no_db: TestClient, admin_token: str) -> None:
    # Guard passes; the stubbed session then makes the handler raise -> 500,
    # never 401/403. The point here is only that the guard let it through.
    r = client_no_db.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code not in (401, 403)


def _token(identity: MockIdentityProvider, role: UserRole) -> str:
    return identity.issue(
        subject="33333333-3333-4333-8333-333333333333",
        role=role,
        display_name="R",
        email="r@example.test",
    )


@pytest.mark.parametrize(
    ("role", "in_lane", "out_of_lane"),
    [
        (UserRole.OPERATIONS_ADMIN, "/api/v1/admin/users", "/api/v1/admin/payment-submissions"),
        (UserRole.STRATEGY_ADMIN, "/api/v1/admin/alerts", "/api/v1/admin/payment-submissions"),
        (UserRole.FINANCE_ADMIN, "/api/v1/admin/payment-submissions", "/api/v1/admin/ops-summary"),
        (UserRole.AUDITOR, "/api/v1/admin/users", None),
    ],
)
def test_functional_admin_tiers_are_scoped(
    client_no_db: TestClient,
    identity: MockIdentityProvider,
    role: UserRole,
    in_lane: str,
    out_of_lane: str | None,
) -> None:
    token = _token(identity, role)
    headers = {"Authorization": f"Bearer {token}"}

    r_in = client_no_db.get(in_lane, headers=headers)
    assert r_in.status_code not in (401, 403), in_lane

    if out_of_lane is not None:
        r_out = client_no_db.get(out_of_lane, headers=headers)
        assert r_out.status_code == 403, out_of_lane


@pytest.mark.parametrize(
    ("role", "write_path", "write_body"),
    [
        (UserRole.STRATEGY_ADMIN, "/api/v1/admin/alerts", {"name": "x"}),
        (UserRole.OPERATIONS_ADMIN, "/api/v1/admin/alerts", {"name": "x"}),
        (UserRole.FINANCE_ADMIN, "/api/v1/admin/alerts", {"name": "x"}),
    ],
)
def test_auditor_and_off_lane_tiers_cannot_write(
    client_no_db: TestClient,
    identity: MockIdentityProvider,
    role: UserRole,
    write_path: str,
    write_body: dict[str, object],
) -> None:
    # STRATEGY_ADMIN is the only non-SUPER_ADMIN role allowed to write alerts;
    # ops/finance admins (and, by the same guard, AUDITOR) must be rejected.
    token = _token(identity, role)
    r = client_no_db.post(write_path, json=write_body, headers={"Authorization": f"Bearer {token}"})
    if role is UserRole.STRATEGY_ADMIN:
        assert r.status_code not in (401, 403)
    else:
        assert r.status_code == 403


def test_auditor_cannot_write_anywhere(
    client_no_db: TestClient, identity: MockIdentityProvider
) -> None:
    token = _token(identity, UserRole.AUDITOR)
    headers = {"Authorization": f"Bearer {token}"}
    assert (
        client_no_db.post("/api/v1/admin/alerts", json={"name": "x"}, headers=headers).status_code
        == 403
    )
    assert (
        client_no_db.post(
            "/api/v1/admin/strategies", json={"name": "x"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client_no_db.post(
            "/api/v1/admin/payment-submissions/some-id/approve", headers=headers
        ).status_code
        == 403
    )
