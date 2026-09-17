"""Strategy Marketplace: admin catalog + entitlement grant, client browse +
multiplier selection (PRD 4.1, 4.3, 5.3, 5.8, 12).

Covers acceptance criteria: admin can create a strategy, define
timeframe/base lot/price/profit share/allowed multipliers, and turn it
ON/OFF; an entitled client can select an allowed multiplier and see the
effective lot; an admin override changes one client's sizing without
affecting another's.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User, UserRole

pytestmark = pytest.mark.dbtest


@pytest.fixture
def admin_token(db, identity):
    admin = User(email="admin@example.test", display_name="Admin", role=UserRole.SUPER_ADMIN.value)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return identity.issue(
        subject=str(admin.id), role=UserRole.SUPER_ADMIN, display_name="Admin", email=admin.email
    )


@pytest.fixture
def client_user(db):
    user = User(email="client@example.test", display_name="Client", role=UserRole.USER.value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def client_token(identity, client_user):
    return identity.issue(
        subject=str(client_user.id),
        role=UserRole.USER,
        display_name="Client",
        email=client_user.email,
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_creates_and_toggles_strategy(client: TestClient, admin_token: str) -> None:
    create = client.post(
        "/api/v1/admin/strategies",
        json={
            "strategy_key": "supertrend",
            "strategy_version": "1.0",
            "name": "Supertrend",
            "description": "ATR-based trend follower",
            "timeframe": "1h",
            "price": "99.00",
            "profit_share_percent": "20",
            "base_lot": "1.00",
        },
        headers=_auth(admin_token),
    )
    assert create.status_code == 201
    body = create.json()
    assert body["is_active"] is True
    strategy_id = body["id"]

    off = client.patch(
        f"/api/v1/admin/strategies/{strategy_id}",
        json={"is_active": False},
        headers=_auth(admin_token),
    )
    assert off.status_code == 200
    assert off.json()["is_active"] is False


def test_non_admin_cannot_create_strategy(client: TestClient, client_token: str) -> None:
    r = client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": "x", "strategy_version": "1.0", "name": "X"},
        headers=_auth(client_token),
    )
    assert r.status_code == 403


def test_client_browses_only_active_strategies(
    client: TestClient, admin_token, client_token
) -> None:
    client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": "active-one", "strategy_version": "1.0", "name": "Active One"},
        headers=_auth(admin_token),
    )
    inactive = client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": "inactive-one", "strategy_version": "1.0", "name": "Inactive One"},
        headers=_auth(admin_token),
    ).json()
    client.patch(
        f"/api/v1/admin/strategies/{inactive['id']}",
        json={"is_active": False},
        headers=_auth(admin_token),
    )

    r = client.get("/api/v1/strategies", headers=_auth(client_token))
    assert r.status_code == 200
    keys = {s["strategy_key"] for s in r.json()}
    assert "active-one" in keys
    assert "inactive-one" not in keys


def test_grant_activate_select_multiplier_effective_lot_flow(
    client: TestClient, admin_token, client_token, client_user
) -> None:
    strategy = client.post(
        "/api/v1/admin/strategies",
        json={
            "strategy_key": "trend-rider",
            "strategy_version": "2025.09",
            "name": "Trend Rider",
            "base_lot": "1.00",
        },
        headers=_auth(admin_token),
    ).json()

    grant = client.post(
        "/api/v1/admin/assignments",
        json={
            "user_id": str(client_user.id),
            "strategy_id": strategy["id"],
            "master_lot": "1.00",
            "multiplier": 1,
            "multiplier_min": 1,
            "multiplier_max": 3,
        },
        headers=_auth(admin_token),
    )
    assert grant.status_code == 201
    assignment = grant.json()
    assert assignment["effective_lot"] == "1.00"

    mine = client.get("/api/v1/me/assignments", headers=_auth(client_token))
    assert mine.status_code == 200
    assert len(mine.json()) == 1

    updated = client.patch(
        f"/api/v1/me/assignments/{assignment['id']}/multiplier",
        json={"multiplier": 2},
        headers=_auth(client_token),
    )
    assert updated.status_code == 200
    assert updated.json()["multiplier"] == "2.0000"
    assert updated.json()["effective_lot"] == "2.00"


def test_client_cannot_pick_multiplier_outside_admin_bounds(
    client: TestClient, admin_token, client_token, client_user
) -> None:
    strategy = client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": "capped", "strategy_version": "1.0", "name": "Capped"},
        headers=_auth(admin_token),
    ).json()
    assignment = client.post(
        "/api/v1/admin/assignments",
        json={
            "user_id": str(client_user.id),
            "strategy_id": strategy["id"],
            "master_lot": "1.00",
            "multiplier": 1,
            "multiplier_min": 1,
            "multiplier_max": 2,  # admin caps this client at 2X, not 3X
        },
        headers=_auth(admin_token),
    ).json()

    r = client.patch(
        f"/api/v1/me/assignments/{assignment['id']}/multiplier",
        json={"multiplier": 3},
        headers=_auth(client_token),
    )
    assert r.status_code == 422


def test_client_cannot_touch_another_clients_assignment(
    client: TestClient, admin_token, client_token, client_user, db
) -> None:
    strategy = client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": "iso-test", "strategy_version": "1.0", "name": "Iso"},
        headers=_auth(admin_token),
    ).json()

    # Grant to `other`, then try to touch it as `client_user`.
    other = User(email="other@example.test", display_name="Other", role=UserRole.USER.value)
    db.add(other)
    db.commit()
    db.refresh(other)

    assignment = client.post(
        "/api/v1/admin/assignments",
        json={
            "user_id": str(other.id),
            "strategy_id": strategy["id"],
            "master_lot": "1.00",
        },
        headers=_auth(admin_token),
    ).json()

    r = client.patch(
        f"/api/v1/me/assignments/{assignment['id']}/multiplier",
        json={"multiplier": 2},
        headers=_auth(client_token),
    )
    assert r.status_code == 404


def test_admin_override_does_not_affect_other_clients_sizing(
    client: TestClient, admin_token, client_user, db
) -> None:
    strategy = client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": "override-test", "strategy_version": "1.0", "name": "Override"},
        headers=_auth(admin_token),
    ).json()

    a1 = client.post(
        "/api/v1/admin/assignments",
        json={"user_id": str(client_user.id), "strategy_id": strategy["id"], "master_lot": "1.00"},
        headers=_auth(admin_token),
    ).json()

    second = User(email="second@example.test", display_name="Second", role=UserRole.USER.value)
    db.add(second)
    db.commit()
    db.refresh(second)

    client.post(
        "/api/v1/admin/assignments",
        json={"user_id": str(second.id), "strategy_id": strategy["id"], "master_lot": "1.00"},
        headers=_auth(admin_token),
    )

    # Override only a1's master_lot.
    patched = client.patch(
        f"/api/v1/admin/assignments/{a1['id']}",
        json={"master_lot": "5.00"},
        headers=_auth(admin_token),
    )
    assert patched.status_code == 200
    assert patched.json()["master_lot"] == "5.00"

    # a2 (the other client's assignment for the same strategy) must be untouched.
    all_assignments = client.get("/api/v1/admin/assignments", headers=_auth(admin_token)).json()
    a2_row = next(row for row in all_assignments if row["user_display_name"] == "Second")
    assert a2_row["master_lot"] == "1.00"
