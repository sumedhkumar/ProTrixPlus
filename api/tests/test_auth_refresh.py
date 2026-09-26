"""POST /auth/refresh - sliding-session renewal. web/middleware.ts calls this
when the current token is close to expiring and swaps the cookie for the
fresh one it returns, so an actively-used session doesn't expire mid-action
just because its original fixed-TTL token aged out."""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User

pytestmark = pytest.mark.dbtest


def _signup_and_login(client: TestClient, email: str) -> str:
    client.post(
        "/auth/signup",
        json={"email": email, "password": "correct-horse-battery", "display_name": "Refresh"},
    )
    login = client.post("/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return str(login.json()["access_token"])


def _unverified_exp(token: str) -> int:
    return int(jwt.decode(token, options={"verify_signature": False})["exp"])


def test_refresh_issues_a_new_token_for_the_same_user(client: TestClient) -> None:
    token = _signup_and_login(client, "refresh-a@example.test")

    time.sleep(1)  # exp is second-precision - make the new one provably later
    r = client.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "refresh-a@example.test"

    new_token = body["access_token"]
    assert new_token != token
    assert _unverified_exp(new_token) > _unverified_exp(token)

    # The new token actually works.
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {new_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "refresh-a@example.test"


def test_refresh_rejects_a_missing_or_garbage_token(client: TestClient) -> None:
    r = client.post("/auth/refresh")
    assert r.status_code == 401

    r = client.post("/auth/refresh", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_refresh_rejects_a_deactivated_user(client: TestClient, db: object) -> None:
    token = _signup_and_login(client, "refresh-deactivated@example.test")
    user = db.query(User).filter(User.email == "refresh-deactivated@example.test").first()  # type: ignore[attr-defined]
    user.is_active = False
    db.commit()  # type: ignore[attr-defined]

    r = client.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_refresh_picks_up_a_display_name_or_role_change_since_the_old_token(
    client: TestClient, db: object
) -> None:
    """Re-reads the user row rather than just re-signing the old claims, so
    it reflects reality even if something about the account changed after
    the original token was issued."""
    token = _signup_and_login(client, "refresh-renamed@example.test")
    user = db.query(User).filter(User.email == "refresh-renamed@example.test").first()  # type: ignore[attr-defined]
    user.display_name = "New Name"
    db.commit()  # type: ignore[attr-defined]

    r = client.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["display_name"] == "New Name"
