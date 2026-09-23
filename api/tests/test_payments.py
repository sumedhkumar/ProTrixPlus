"""Manual payment-proof (UTR) submission + admin review, for paid
subscription packages. Covers: anonymous submission, authenticated (renewal)
submission, admin approve (both the new-account and renewal branches - the
stacking vs. restart-from-approval renewal math), admin reject, and that a
non-admin can't reach the review endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User, UserRole

from app.config import get_settings
from app.email import MockEmailSender

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
def existing_user(db):
    user = User(
        email="renewing@example.test",
        display_name="Renewing Client",
        role=UserRole.USER.value,
        subscription_package="TRIAL_7D",
        subscription_start=datetime.now(UTC) - timedelta(days=5),
        subscription_end=datetime.now(UTC) + timedelta(days=2),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def existing_user_token(identity, existing_user):
    return identity.issue(
        subject=str(existing_user.id),
        role=UserRole.USER,
        display_name=existing_user.display_name,
        email=existing_user.email,
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_anonymous_submission_notifies_admin(
    client: TestClient, mock_email: MockEmailSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_ADMIN_NOTIFY_EMAIL", "admin@protrixplus.test")
    get_settings.cache_clear()

    r = client.post(
        "/api/v1/payments/submit",
        json={
            "name": "Jack",
            "email": "jack@example.test",
            "phone": "+1-555-0200",
            "package": "PLAN_3M",
            "utr_reference": "UTR12345",
        },
    )
    assert r.status_code == 201
    assert r.json()["status"] == "PENDING"
    assert any("Payment review needed" in e["subject"] for e in mock_email.sent)


def test_anonymous_submission_notifies_customer(
    client: TestClient, mock_email: MockEmailSender
) -> None:
    r = client.post(
        "/api/v1/payments/submit",
        json={
            "name": "Jack",
            "email": "jack3@example.test",
            "phone": "+1-555-0207",
            "package": "PLAN_3M",
            "utr_reference": "UTR54321",
        },
    )
    assert r.status_code == 201
    assert any(
        e["to"] == "jack3@example.test" and "payment received" in e["subject"].lower()
        for e in mock_email.sent
    )


def test_submission_rejects_trial_package(client: TestClient) -> None:
    r = client.post(
        "/api/v1/payments/submit",
        json={
            "name": "Jack",
            "email": "jack2@example.test",
            "phone": "+1-555-0201",
            "package": "TRIAL_7D",
            "utr_reference": "UTR12345",
        },
    )
    assert r.status_code == 400


def test_authenticated_submission_ties_to_existing_account(
    client: TestClient, existing_user_token: str, existing_user
) -> None:
    r = client.post(
        "/api/v1/me/payments/submit",
        json={"name": "K", "phone": "+1-555-0202", "package": "PLAN_6M", "utr_reference": "UTR999"},
        headers=_auth(existing_user_token),
    )
    assert r.status_code == 201

    # admin sees it tagged to the existing account
    # (verified end-to-end in the admin-approve tests below)


def test_non_admin_cannot_list_or_review_submissions(
    client: TestClient, existing_user_token: str
) -> None:
    assert (
        client.get(
            "/api/v1/admin/payment-submissions", headers=_auth(existing_user_token)
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/admin/payment-submissions/00000000-0000-0000-0000-000000000000/approve",
            headers=_auth(existing_user_token),
        ).status_code
        == 403
    )


def test_admin_approve_anonymous_submission_creates_account_with_temp_password(
    client: TestClient, admin_token: str, mock_email: MockEmailSender
) -> None:
    submit = client.post(
        "/api/v1/payments/submit",
        json={
            "name": "Liam",
            "email": "liam@example.test",
            "phone": "+1-555-0203",
            "package": "PLAN_3M",
            "utr_reference": "UTR777",
        },
    )
    submission_id = submit.json()["id"]

    listing = client.get(
        "/api/v1/admin/payment-submissions?status=PENDING", headers=_auth(admin_token)
    )
    assert any(s["id"] == submission_id for s in listing.json())

    approve = client.post(
        f"/api/v1/admin/payment-submissions/{submission_id}/approve", headers=_auth(admin_token)
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "APPROVED"

    # a new account was created and got a welcome/temp-password email
    # (in addition to the "payment received" confirmation sent on submission)
    welcome = [
        e
        for e in mock_email.sent
        if e["to"] == "liam@example.test" and "payment confirmed" in e["subject"].lower()
    ]
    assert len(welcome) == 1

    temp_password = welcome[0]["body_text"].split("Temporary password: ")[1].splitlines()[0]
    login = client.post(
        "/auth/login", json={"email": "liam@example.test", "password": temp_password}
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True


def test_admin_approve_renewal_stacks_on_active_subscription(
    client: TestClient, admin_token: str, existing_user_token: str, existing_user, mock_email
) -> None:
    original_end = existing_user.subscription_end

    submit = client.post(
        "/api/v1/me/payments/submit",
        json={
            "name": "M",
            "phone": "+1-555-0204",
            "package": "PLAN_3M",
            "utr_reference": "UTR-STACK",
        },
        headers=_auth(existing_user_token),
    )
    submission_id = submit.json()["id"]

    approve = client.post(
        f"/api/v1/admin/payment-submissions/{submission_id}/approve", headers=_auth(admin_token)
    )
    assert approve.status_code == 200

    me = client.get("/api/v1/me", headers=_auth(existing_user_token))
    new_end = datetime.fromisoformat(me.json()["subscription"]["end"])
    # stacks on top of the still-active subscription, not from "now"
    assert new_end - original_end >= timedelta(days=89)

    # a "subscription renewed" confirmation is sent, but never a temp
    # password - the account already has its own password
    renewal_emails = [
        e
        for e in mock_email.sent
        if e["to"] == existing_user.email and "renewed" in e["subject"].lower()
    ]
    assert len(renewal_emails) == 1
    assert "Temporary password" not in renewal_emails[0]["body_text"]


def test_admin_approve_renewal_restarts_after_expiry(
    client: TestClient, admin_token: str, db, identity
) -> None:
    expired_user = User(
        email="expired@example.test",
        display_name="Expired Client",
        role=UserRole.USER.value,
        subscription_package="TRIAL_7D",
        subscription_start=datetime.now(UTC) - timedelta(days=10),
        subscription_end=datetime.now(UTC) - timedelta(days=3),
    )
    db.add(expired_user)
    db.commit()
    db.refresh(expired_user)
    token = identity.issue(
        subject=str(expired_user.id),
        role=UserRole.USER,
        display_name=expired_user.display_name,
        email=expired_user.email,
    )

    submit = client.post(
        "/api/v1/me/payments/submit",
        json={
            "name": "N",
            "phone": "+1-555-0205",
            "package": "PLAN_6M",
            "utr_reference": "UTR-RESTART",
        },
        headers=_auth(token),
    )
    submission_id = submit.json()["id"]
    before_approve = datetime.now(UTC)

    client.post(
        f"/api/v1/admin/payment-submissions/{submission_id}/approve", headers=_auth(admin_token)
    )

    me = client.get("/api/v1/me", headers=_auth(token))
    new_start = datetime.fromisoformat(me.json()["subscription"]["start"])
    # restarts from approval time, not stacked on the long-expired end date
    assert new_start >= before_approve - timedelta(seconds=5)


def test_admin_reject_submission_sends_email_and_cannot_be_reviewed_twice(
    client: TestClient, admin_token: str, mock_email: MockEmailSender
) -> None:
    submit = client.post(
        "/api/v1/payments/submit",
        json={
            "name": "Olive",
            "email": "olive@example.test",
            "phone": "+1-555-0206",
            "package": "PLAN_12M",
            "utr_reference": "UTR-BAD",
        },
    )
    submission_id = submit.json()["id"]

    reject = client.post(
        f"/api/v1/admin/payment-submissions/{submission_id}/reject",
        json={"reason": "reference not found"},
        headers=_auth(admin_token),
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "REJECTED"
    assert any(
        e["to"] == "olive@example.test" and "could not be confirmed" in e["subject"].lower()
        for e in mock_email.sent
    )

    again = client.post(
        f"/api/v1/admin/payment-submissions/{submission_id}/approve", headers=_auth(admin_token)
    )
    assert again.status_code == 400
