"""POST /api/v1/me/mt5-setup-fee/pay - the one-time, account-wide (not
per-strategy) demo payment gating self_subscribe. Covers the real cost of
provisioning a client's MetaApi account; no real payment processor is
wired in yet, so this just flips User.mt5_setup_fee_paid."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User, UserRole

pytestmark = pytest.mark.dbtest


@pytest.fixture
def admin_token(db, identity):
    admin = User(
        email="fee-admin@example.test", display_name="Admin", role=UserRole.SUPER_ADMIN.value
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return identity.issue(
        subject=str(admin.id), role=UserRole.SUPER_ADMIN, display_name="Admin", email=admin.email
    )


@pytest.fixture
def client_user(db):
    user = User(email="fee-client@example.test", display_name="Client", role=UserRole.USER.value)
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


def _published_strategy(client: TestClient, admin_token: str, key: str) -> dict:
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
    return strategy


def test_me_reports_unpaid_by_default(client: TestClient, client_token: str) -> None:
    r = client.get("/api/v1/me", headers=_auth(client_token))
    assert r.json()["mt5_setup_fee_paid"] is False


def test_subscribe_is_rejected_until_the_setup_fee_is_paid(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    strategy = _published_strategy(client, admin_token, "fee-gate-1")
    r = client.post(
        "/api/v1/me/assignments/subscribe",
        json={"strategy_id": strategy["id"]},
        headers=_auth(client_token),
    )
    assert r.status_code == 422
    assert "mt5 account setup fee" in r.json()["detail"].lower()


def test_paying_the_fee_unlocks_subscribe(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    strategy = _published_strategy(client, admin_token, "fee-gate-2")

    pay = client.post("/api/v1/me/mt5-setup-fee/pay", headers=_auth(client_token))
    assert pay.status_code == 200
    assert pay.json() == {"mt5_setup_fee_paid": True, "already_paid": False}

    me = client.get("/api/v1/me", headers=_auth(client_token))
    assert me.json()["mt5_setup_fee_paid"] is True

    r = client.post(
        "/api/v1/me/assignments/subscribe",
        json={"strategy_id": strategy["id"]},
        headers=_auth(client_token),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "PENDING_APPROVAL"


def test_paying_twice_is_idempotent(client: TestClient, client_token: str) -> None:
    first = client.post("/api/v1/me/mt5-setup-fee/pay", headers=_auth(client_token))
    second = client.post("/api/v1/me/mt5-setup-fee/pay", headers=_auth(client_token))
    assert first.json() == {"mt5_setup_fee_paid": True, "already_paid": False}
    assert second.json() == {"mt5_setup_fee_paid": True, "already_paid": True}


def test_one_payment_unlocks_every_strategy_not_just_one(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    """Account-wide, not per-strategy - paying once must unlock subscribing
    to any strategy, since the fee covers the MetaApi account itself."""
    strategy_a = _published_strategy(client, admin_token, "fee-gate-a")
    strategy_b = _published_strategy(client, admin_token, "fee-gate-b")
    client.post("/api/v1/me/mt5-setup-fee/pay", headers=_auth(client_token))

    for strategy in (strategy_a, strategy_b):
        r = client.post(
            "/api/v1/me/assignments/subscribe",
            json={"strategy_id": strategy["id"]},
            headers=_auth(client_token),
        )
        assert r.status_code == 200
