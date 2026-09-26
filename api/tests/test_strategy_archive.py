"""POST /api/v1/admin/strategies/{id}/archive - "remove from the admin
panel" for a strategy that already has real trade history (assignments /
order intents / signals) can't be a hard DELETE, since those tables FK to
strategies.id with no cascade. Archiving hides the strategy from both
GET /api/v1/admin/strategies and GET /api/v1/strategies (the client
marketplace) without touching anything it's linked to, and is reversible
via /unarchive."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User, UserRole

pytestmark = pytest.mark.dbtest


@pytest.fixture
def admin_token(db, identity):
    admin = User(
        email="archive-admin@example.test", display_name="Admin", role=UserRole.SUPER_ADMIN.value
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return identity.issue(
        subject=str(admin.id), role=UserRole.SUPER_ADMIN, display_name="Admin", email=admin.email
    )


@pytest.fixture
def client_token(db, identity):
    user = User(
        email="archive-client@example.test", display_name="Client", role=UserRole.USER.value
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return identity.issue(
        subject=str(user.id), role=UserRole.USER, display_name="Client", email=user.email
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


def test_archive_hides_from_admin_catalog_but_keeps_the_row(
    client: TestClient, admin_token: str
) -> None:
    strategy = _published_strategy(client, admin_token, "archive-1")

    r = client.post(
        f"/api/v1/admin/strategies/{strategy['id']}/archive", headers=_auth(admin_token)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_archived"] is True
    assert body["is_active"] is False

    catalog = client.get("/api/v1/admin/strategies", headers=_auth(admin_token)).json()
    assert strategy["id"] not in [s["id"] for s in catalog]

    with_archived = client.get(
        "/api/v1/admin/strategies?include_archived=true", headers=_auth(admin_token)
    ).json()
    assert strategy["id"] in [s["id"] for s in with_archived]


def test_archived_strategy_disappears_from_client_marketplace(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    strategy = _published_strategy(client, admin_token, "archive-2")
    visible_before = client.get("/api/v1/strategies", headers=_auth(client_token)).json()
    assert strategy["id"] in [s["id"] for s in visible_before]

    client.post(f"/api/v1/admin/strategies/{strategy['id']}/archive", headers=_auth(admin_token))

    visible_after = client.get("/api/v1/strategies", headers=_auth(client_token)).json()
    assert strategy["id"] not in [s["id"] for s in visible_after]


def test_unarchive_reverses_it_but_stays_not_enabled(client: TestClient, admin_token: str) -> None:
    strategy = _published_strategy(client, admin_token, "archive-3")
    client.post(f"/api/v1/admin/strategies/{strategy['id']}/archive", headers=_auth(admin_token))

    r = client.post(
        f"/api/v1/admin/strategies/{strategy['id']}/unarchive", headers=_auth(admin_token)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_archived"] is False
    assert body["is_active"] is False  # admin must re-approve explicitly

    catalog = client.get("/api/v1/admin/strategies", headers=_auth(admin_token)).json()
    assert strategy["id"] in [s["id"] for s in catalog]


def test_non_admin_cannot_archive(client: TestClient, admin_token: str, client_token: str) -> None:
    strategy = _published_strategy(client, admin_token, "archive-4")
    r = client.post(
        f"/api/v1/admin/strategies/{strategy['id']}/archive", headers=_auth(client_token)
    )
    assert r.status_code == 403


def test_archive_unknown_strategy_is_404(client: TestClient, admin_token: str) -> None:
    r = client.post(
        "/api/v1/admin/strategies/00000000-0000-0000-0000-000000000000/archive",
        headers=_auth(admin_token),
    )
    assert r.status_code == 404
