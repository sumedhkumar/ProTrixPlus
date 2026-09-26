"""POST /api/v1/admin/assignments/{id}/approve - the admin confirms a
client's self-subscribed strategy was actually paid for and unlocks it:
PENDING_APPROVAL -> SETUP_INCOMPLETE, giving the client Setup Wizard access."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User, UserRole

pytestmark = pytest.mark.dbtest


@pytest.fixture
def admin_token(db, identity):
    admin = User(
        email="approve-admin@example.test", display_name="Admin", role=UserRole.SUPER_ADMIN.value
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return identity.issue(
        subject=str(admin.id), role=UserRole.SUPER_ADMIN, display_name="Admin", email=admin.email
    )


@pytest.fixture
def client_user(db):
    # mt5_setup_fee_paid=True: this file tests admin-approval, not the
    # payment gate in front of self_subscribe.
    user = User(
        email="approve-client@example.test",
        display_name="Client",
        role=UserRole.USER.value,
        mt5_setup_fee_paid=True,
    )
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


def _pending_subscription(
    client: TestClient, admin_token: str, client_token: str, key: str
) -> dict:
    strategy = client.post(
        "/api/v1/admin/strategies",
        json={
            "strategy_key": key,
            "strategy_version": "1.0",
            "name": key,
            "price": "10",
            "profit_share_percent": "10",
        },
        headers=_auth(admin_token),
    ).json()
    client.patch(
        f"/api/v1/admin/strategies/{strategy['id']}",
        json={"is_active": True},
        headers=_auth(admin_token),
    )
    return client.post(
        "/api/v1/me/assignments/subscribe",
        json={"strategy_id": strategy["id"]},
        headers=_auth(client_token),
    ).json()


def test_admin_approves_a_pending_subscription(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    assignment = _pending_subscription(client, admin_token, client_token, "approve-1")
    assert assignment["status"] == "PENDING_APPROVAL"

    r = client.post(
        f"/api/v1/admin/assignments/{assignment['id']}/approve", headers=_auth(admin_token)
    )
    assert r.status_code == 200
    assert r.json()["status"] == "SETUP_INCOMPLETE"

    # The client can now see it unlocked too.
    mine = client.get("/api/v1/me/assignments", headers=_auth(client_token)).json()
    approved = next(a for a in mine if a["id"] == assignment["id"])
    assert approved["status"] == "SETUP_INCOMPLETE"


def test_non_admin_cannot_approve(client: TestClient, admin_token: str, client_token: str) -> None:
    assignment = _pending_subscription(client, admin_token, client_token, "approve-2")
    r = client.post(
        f"/api/v1/admin/assignments/{assignment['id']}/approve", headers=_auth(client_token)
    )
    assert r.status_code == 403


def test_cannot_approve_an_already_approved_assignment(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    assignment = _pending_subscription(client, admin_token, client_token, "approve-3")
    client.post(f"/api/v1/admin/assignments/{assignment['id']}/approve", headers=_auth(admin_token))

    r = client.post(
        f"/api/v1/admin/assignments/{assignment['id']}/approve", headers=_auth(admin_token)
    )
    assert r.status_code == 422


def test_approve_unknown_assignment_is_404(client: TestClient, admin_token: str) -> None:
    r = client.post(
        "/api/v1/admin/assignments/00000000-0000-0000-0000-000000000000/approve",
        headers=_auth(admin_token),
    )
    assert r.status_code == 404
