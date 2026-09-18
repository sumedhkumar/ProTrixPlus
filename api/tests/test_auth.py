"""Real signup/login (PRD 5.1) - against a real PostgreSQL.

Distinct from test_auth_guard.py (which tests the token-verification guard
with a stubbed DB). This tests the actual credential path: hashing, storage,
verification, and the HTTP-level contract.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password, verify_password
from app.email import MockEmailSender

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


# ---------------------------------------------------------------------------
# Password-less trial signup + forced first-login password change
# ---------------------------------------------------------------------------


def test_signup_trial_creates_account_and_emails_temp_password(
    client: TestClient, mock_email: MockEmailSender
) -> None:
    r = client.post(
        "/auth/signup-trial",
        json={"name": "Erin", "email": "erin@example.test", "phone": "+1-555-0100"},
    )
    assert r.status_code == 201
    assert r.json()["email"] == "erin@example.test"
    assert "access_token" not in r.json()  # no token issued - must log in with the emailed password

    assert len(mock_email.sent) == 1
    assert mock_email.sent[0]["to"] == "erin@example.test"


def test_signup_trial_rejects_duplicate_email(client: TestClient) -> None:
    payload = {"name": "Frank", "email": "frank@example.test", "phone": "+1-555-0101"}
    first = client.post("/auth/signup-trial", json=payload)
    assert first.status_code == 201
    second = client.post("/auth/signup-trial", json=payload)
    assert second.status_code == 409


def test_trial_login_forces_password_change_then_set_password_clears_flag(
    client: TestClient, mock_email: MockEmailSender
) -> None:
    client.post(
        "/auth/signup-trial",
        json={"name": "Grace", "email": "grace@example.test", "phone": "+1-555-0102"},
    )
    temp_password = mock_email.sent[0]["body_text"].split("Temporary password: ")[1].splitlines()[0]

    login = client.post(
        "/auth/login", json={"email": "grace@example.test", "password": temp_password}
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    token = login.json()["access_token"]

    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["must_change_password"] is True
    assert me.json()["subscription"]["package"] == "TRIAL_7D"
    assert me.json()["subscription"]["days_remaining"] == 7

    set_pw = client.post(
        "/auth/set-password",
        json={"new_password": "a-brand-new-password"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert set_pw.status_code == 200

    me_after = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me_after.json()["must_change_password"] is False

    relogin = client.post(
        "/auth/login", json={"email": "grace@example.test", "password": "a-brand-new-password"}
    )
    assert relogin.status_code == 200
    assert relogin.json()["must_change_password"] is False


# ---------------------------------------------------------------------------
# Standard self-service forgot/reset password
# ---------------------------------------------------------------------------


def test_forgot_password_always_returns_generic_response(client: TestClient) -> None:
    client.post(
        "/auth/signup",
        json={
            "email": "helen@example.test",
            "password": "correct-horse-battery",
            "display_name": "H",
        },
    )
    known = client.post("/auth/forgot-password", json={"email": "helen@example.test"})
    unknown = client.post("/auth/forgot-password", json={"email": "nobody-at-all@example.test"})
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json() == unknown.json()


def test_reset_password_round_trip_and_token_single_use(
    client: TestClient, mock_email: MockEmailSender
) -> None:
    client.post(
        "/auth/signup",
        json={
            "email": "ivan@example.test",
            "password": "correct-horse-battery",
            "display_name": "I",
        },
    )
    client.post("/auth/forgot-password", json={"email": "ivan@example.test"})
    reset_url = mock_email.sent[-1]["body_text"].split("Reset it here (valid for 1 hour): ")[1]
    token = reset_url.split("token=")[1].splitlines()[0]

    reset = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "another-new-password"}
    )
    assert reset.status_code == 200

    old_login = client.post(
        "/auth/login", json={"email": "ivan@example.test", "password": "correct-horse-battery"}
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/auth/login", json={"email": "ivan@example.test", "password": "another-new-password"}
    )
    assert new_login.status_code == 200

    reused = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "yet-another-password"}
    )
    assert reused.status_code == 400


def test_reset_password_rejects_bogus_token(client: TestClient) -> None:
    r = client.post(
        "/auth/reset-password", json={"token": "not-a-real-token", "new_password": "whatever123"}
    )
    assert r.status_code == 400
