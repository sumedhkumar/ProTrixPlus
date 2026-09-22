"""Real signup/login (PRD 5.1) - against a real PostgreSQL.

Distinct from test_auth_guard.py (which tests the token-verification guard
with a stubbed DB). This tests the actual credential path: hashing, storage,
verification, and the HTTP-level contract.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.routers.auth as auth_router
from app.auth import hash_password, verify_password
from app.email import MockEmailSender
from app.identity.google_verifier import GoogleIdentity, GoogleTokenError

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


def test_signup_trial_without_phone_still_creates_account(client: TestClient) -> None:
    """Phone isn't collected on the trial form for now - must stay optional."""
    r = client.post(
        "/auth/signup-trial", json={"name": "Priya", "email": "priya@example.test"}
    )
    assert r.status_code == 201
    assert r.json()["email"] == "priya@example.test"


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


# ---------------------------------------------------------------------------
# Google sign-in - optional, verified email only, never bypasses the forced
# first password login. verify_google_id_token itself (JWKS/RS256 handling)
# is stubbed here; it isn't a session-token concern, see
# app/identity/google_verifier.py's own docstring for why.
# ---------------------------------------------------------------------------


def _stub_google_identity(monkeypatch: pytest.MonkeyPatch, email: str, name: str) -> None:
    monkeypatch.setattr(
        auth_router,
        "verify_google_id_token",
        lambda credential, *, client_id: GoogleIdentity(email=email, name=name),
    )


def test_signup_google_creates_trial_account_and_emails_temp_password(
    client: TestClient, mock_email: MockEmailSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_google_identity(monkeypatch, "jane@gmail.test", "Jane")

    r = client.post("/auth/signup-google", json={"credential": "fake-token"})
    assert r.status_code == 201
    assert r.json()["email"] == "jane@gmail.test"
    assert "access_token" not in r.json()  # same as /auth/signup-trial - not logged in yet

    assert len(mock_email.sent) == 1
    assert mock_email.sent[0]["to"] == "jane@gmail.test"


def test_signup_google_rejects_duplicate_email(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_google_identity(monkeypatch, "kim@gmail.test", "Kim")
    first = client.post("/auth/signup-google", json={"credential": "fake-token"})
    assert first.status_code == 201
    second = client.post("/auth/signup-google", json={"credential": "fake-token"})
    assert second.status_code == 409


def test_signup_google_rejects_invalid_credential(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(credential: str, *, client_id: str) -> GoogleIdentity:
        raise GoogleTokenError("invalid Google credential: bad signature")

    monkeypatch.setattr(auth_router, "verify_google_id_token", _raise)
    r = client.post("/auth/signup-google", json={"credential": "garbage"})
    assert r.status_code == 401


def test_login_google_rejects_unknown_account(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_google_identity(monkeypatch, "nobody@gmail.test", "Nobody")
    r = client.post("/auth/login-google", json={"credential": "fake-token"})
    assert r.status_code == 404


def test_login_google_blocked_until_first_password_login_completes(
    client: TestClient, mock_email: MockEmailSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_google_identity(monkeypatch, "liam@gmail.test", "Liam")
    client.post("/auth/signup-google", json={"credential": "fake-token"})

    still_pending = client.post("/auth/login-google", json={"credential": "fake-token"})
    assert still_pending.status_code == 403

    temp_password = mock_email.sent[0]["body_text"].split("Temporary password: ")[1].splitlines()[0]
    first_login = client.post(
        "/auth/login", json={"email": "liam@gmail.test", "password": temp_password}
    )
    assert first_login.status_code == 200
    token = first_login.json()["access_token"]
    client.post(
        "/auth/set-password",
        json={"new_password": "a-brand-new-password"},
        headers={"Authorization": f"Bearer {token}"},
    )

    now_allowed = client.post("/auth/login-google", json={"credential": "fake-token"})
    assert now_allowed.status_code == 200
    assert now_allowed.json()["email"] == "liam@gmail.test"
    assert now_allowed.json()["must_change_password"] is False
