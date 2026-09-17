"""Real signup/login (PRD 5.1) - against a real PostgreSQL.

Distinct from test_auth_guard.py (which tests the token-verification guard
with a stubbed DB). This tests the actual credential path: hashing, storage,
verification, and the HTTP-level contract.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password, verify_password

pytestmark = pytest.mark.dbtest


def test_signup_then_login_round_trip(client: TestClient) -> None:
    signup = client.post(
        "/auth/signup",
        json={
            "email": "alice@example.test",
            "password": "correct-horse-battery",
            "display_name": "Alice",
        },
    )
    assert signup.status_code == 201
    body = signup.json()
    assert body["role"] == "USER"
    assert body["email"] == "alice@example.test"

    login = client.post(
        "/auth/login", json={"email": "alice@example.test", "password": "correct-horse-battery"}
    )
    assert login.status_code == 200
    assert login.json()["subject"] == body["subject"]

    token = login.json()["access_token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.test"


def test_login_rejects_wrong_password(client: TestClient) -> None:
    client.post(
        "/auth/signup",
        json={
            "email": "bob@example.test",
            "password": "correct-horse-battery",
            "display_name": "Bob",
        },
    )
    r = client.post("/auth/login", json={"email": "bob@example.test", "password": "wrong"})
    assert r.status_code == 401


def test_login_rejects_unknown_email(client: TestClient) -> None:
    r = client.post("/auth/login", json={"email": "nobody@example.test", "password": "whatever123"})
    assert r.status_code == 401


def test_signup_rejects_duplicate_email(client: TestClient) -> None:
    payload = {
        "email": "carol@example.test",
        "password": "correct-horse-battery",
        "display_name": "Carol",
    }
    first = client.post("/auth/signup", json=payload)
    assert first.status_code == 201
    second = client.post("/auth/signup", json={**payload, "display_name": "Carol Again"})
    assert second.status_code == 409


def test_signup_rejects_short_password(client: TestClient) -> None:
    r = client.post(
        "/auth/signup",
        json={"email": "dave@example.test", "password": "short", "display_name": "Dave"},
    )
    assert r.status_code == 422


def test_seeded_dev_only_user_cannot_password_login(client: TestClient) -> None:
    """A user created without a password_hash (e.g. via the seed script or
    /dev/login's underlying seed data) must not be able to log in with any
    password - password_hash is NULL, not an empty/guessable hash."""
    assert verify_password("anything", None) is False
    assert verify_password("", None) is False


def test_hash_password_is_salted_and_verifies() -> None:
    h1 = hash_password("correct-horse-battery")
    h2 = hash_password("correct-horse-battery")
    assert h1 != h2  # different random salt each time
    assert verify_password("correct-horse-battery", h1)
    assert verify_password("correct-horse-battery", h2)
    assert not verify_password("wrong", h1)
