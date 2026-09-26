"""POST /api/v1/me/assignments/subscribe - self-service subscription
*request*. Any signed-up client can see and request any published strategy
immediately, no admin action needed to request it - but the resulting
assignment starts PENDING_APPROVAL: locked, no Setup Wizard access, until
an admin confirms the subscription price was actually paid via
POST /api/v1/admin/assignments/{id}/approve (see test_admin_approve.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User, UserRole

pytestmark = pytest.mark.dbtest


@pytest.fixture
def admin_token(db, identity):
    admin = User(
        email="subscribe-admin@example.test", display_name="Admin", role=UserRole.SUPER_ADMIN.value
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return identity.issue(
        subject=str(admin.id), role=UserRole.SUPER_ADMIN, display_name="Admin", email=admin.email
    )


@pytest.fixture
def client_user(db):
    # mt5_setup_fee_paid=True: this file tests the subscribe-request/approve
    # flow, not the payment gate in front of it - see
    # test_mt5_setup_fee.py for that.
    user = User(
        email="subscribe-client@example.test",
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


def _published_strategy(client: TestClient, admin_token: str, key: str, *, base_lot=None) -> dict:
    body = {
        "strategy_key": key,
        "strategy_version": "1.0",
        "name": key,
        "price": "10",
        "profit_share_percent": "10",
    }
    if base_lot is not None:
        body["base_lot"] = base_lot
    strategy = client.post("/api/v1/admin/strategies", json=body, headers=_auth(admin_token)).json()
    client.patch(
        f"/api/v1/admin/strategies/{strategy['id']}",
        json={"is_active": True},
        headers=_auth(admin_token),
    )
    return strategy


def test_subscribe_to_a_published_strategy_creates_pending_approval_assignment(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    strategy = _published_strategy(client, admin_token, "self-sub-1", base_lot="2.00")

    r = client.post(
        "/api/v1/me/assignments/subscribe",
        json={"strategy_id": strategy["id"]},
        headers=_auth(client_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["strategy_id"] == strategy["id"]
    assert body["status"] == "PENDING_APPROVAL"
    assert body["master_lot"] == "2.00"
    assert body["multiplier_max"] == "20.0000"
    assert body["confirmed_risk_disclosure"] is False


def test_subscribe_is_idempotent_not_duplicated(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    strategy = _published_strategy(client, admin_token, "self-sub-2")

    first = client.post(
        "/api/v1/me/assignments/subscribe",
        json={"strategy_id": strategy["id"]},
        headers=_auth(client_token),
    ).json()
    second = client.post(
        "/api/v1/me/assignments/subscribe",
        json={"strategy_id": strategy["id"]},
        headers=_auth(client_token),
    ).json()
    assert first["id"] == second["id"]

    mine = client.get("/api/v1/me/assignments", headers=_auth(client_token)).json()
    assert len([a for a in mine if a["strategy_id"] == strategy["id"]]) == 1


def test_subscribe_does_not_reset_an_already_active_subscription(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    strategy = _published_strategy(client, admin_token, "self-sub-3")
    assignment = client.post(
        "/api/v1/me/assignments/subscribe",
        json={"strategy_id": strategy["id"]},
        headers=_auth(client_token),
    ).json()

    # Simulate the assignment having gone live already (admin override path).
    client.patch(
        f"/api/v1/admin/assignments/{assignment['id']}",
        json={"status": "ACTIVE"},
        headers=_auth(admin_token),
    )

    resubscribed = client.post(
        "/api/v1/me/assignments/subscribe",
        json={"strategy_id": strategy["id"]},
        headers=_auth(client_token),
    ).json()
    assert resubscribed["status"] == "ACTIVE"


def test_cannot_subscribe_to_an_unpublished_strategy(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    unpriced = client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": "self-sub-unpublished", "strategy_version": "1.0", "name": "Draft"},
        headers=_auth(admin_token),
    ).json()

    r = client.post(
        "/api/v1/me/assignments/subscribe",
        json={"strategy_id": unpriced["id"]},
        headers=_auth(client_token),
    )
    assert r.status_code == 422


def test_subscribe_to_unknown_strategy_is_404(client: TestClient, client_token: str) -> None:
    r = client.post(
        "/api/v1/me/assignments/subscribe",
        json={"strategy_id": "00000000-0000-0000-0000-000000000000"},
        headers=_auth(client_token),
    )
    assert r.status_code == 404
