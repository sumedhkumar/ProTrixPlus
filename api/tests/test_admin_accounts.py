"""Admin team management: invite/promote admins, multi-role accounts, and
deactivate/reactivate. Covers app/services/admin_accounts.py and the
SUPER_ADMIN-only endpoints added to app/routers/admin.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import (
    AdminInvite,
    PaymentSubmission,
    Strategy,
    StrategyAssignment,
    User,
    UserRole,
)

from app.email import MockEmailSender
from app.services import admin_accounts

pytestmark = pytest.mark.dbtest


@pytest.fixture
def super_admin(db, identity):
    user = User(email="root2@example.test", display_name="Root2", role=UserRole.SUPER_ADMIN.value)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = identity.issue(
        subject=str(user.id), role=UserRole.SUPER_ADMIN, display_name="Root2", email=user.email
    )
    return user, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _extract_between(text: str, prefix: str) -> str:
    return text.split(prefix, 1)[1].splitlines()[0]


def test_invite_new_admin_creates_account_with_multiple_roles(
    client: TestClient, super_admin, mock_email: MockEmailSender
) -> None:
    _, token = super_admin
    r = client.post(
        "/api/v1/admin/invites",
        json={
            "email": "newadmin@example.test",
            "display_name": "New Admin",
            "roles": ["OPERATIONS_ADMIN", "FINANCE_ADMIN"],
        },
        headers=_auth(token),
    )
    assert r.status_code == 201
    assert r.json()["invited"] is True

    assert len(mock_email.sent) == 1
    body = mock_email.sent[0]["body_text"]
    assert "Operations Admin" in body
    assert "Finance Admin" in body
    invite_url = _extract_between(body, "Set your password here (valid for 7 days): ")
    raw_token = invite_url.split("token=")[1]

    reset = client.post(
        "/auth/reset-password", json={"token": raw_token, "new_password": "a-brand-new-password"}
    )
    assert reset.status_code == 200

    login = client.post(
        "/auth/login", json={"email": "newadmin@example.test", "password": "a-brand-new-password"}
    )
    assert login.status_code == 200
    new_token = login.json()["access_token"]

    # Multi-role: this one account reaches BOTH an ops-only and a
    # finance-only admin endpoint regardless of which role became primary.
    ops = client.get("/api/v1/admin/ops-summary", headers=_auth(new_token))
    assert ops.status_code == 200
    finance = client.get("/api/v1/admin/payment-submissions", headers=_auth(new_token))
    assert finance.status_code == 200
    # But not a strategy-only one.
    strategy = client.get("/api/v1/admin/alerts", headers=_auth(new_token))
    assert strategy.status_code == 403


def test_invite_existing_email_updates_roles_without_new_token(
    client: TestClient, super_admin, db, mock_email: MockEmailSender
) -> None:
    _, token = super_admin
    existing = User(
        email="already@example.test",
        display_name="Already",
        role=UserRole.USER.value,
        password_hash="irrelevant",
    )
    db.add(existing)
    db.commit()

    r = client.post(
        "/api/v1/admin/invites",
        json={
            "email": "already@example.test",
            "display_name": "Already Admin",
            "roles": ["AUDITOR"],
        },
        headers=_auth(token),
    )
    assert r.status_code == 201
    assert r.json()["invited"] is False
    assert len(mock_email.sent) == 1
    assert "roles are now" in mock_email.sent[0]["body_text"]


def test_invite_rejects_user_role_only(client: TestClient, super_admin) -> None:
    _, token = super_admin
    r = client.post(
        "/api/v1/admin/invites",
        json={"email": "justuser@example.test", "display_name": "J", "roles": ["USER"]},
        headers=_auth(token),
    )
    assert r.status_code == 400


def test_non_super_admin_cannot_invite(client: TestClient, db, identity) -> None:
    ops = User(
        email="ops-only@example.test", display_name="Ops", role=UserRole.OPERATIONS_ADMIN.value
    )
    db.add(ops)
    db.commit()
    db.refresh(ops)
    ops_token = identity.issue(
        subject=str(ops.id), role=UserRole.OPERATIONS_ADMIN, display_name="Ops", email=ops.email
    )
    r = client.post(
        "/api/v1/admin/invites",
        json={"email": "x@example.test", "display_name": "X", "roles": ["OPERATIONS_ADMIN"]},
        headers=_auth(ops_token),
    )
    assert r.status_code == 403


def test_patch_user_roles_updates_and_notifies(
    client: TestClient, super_admin, mock_email: MockEmailSender
) -> None:
    _, token = super_admin
    invite = client.post(
        "/api/v1/admin/invites",
        json={
            "email": "editme@example.test",
            "display_name": "Edit Me",
            "roles": ["STRATEGY_ADMIN"],
        },
        headers=_auth(token),
    ).json()
    mock_email.sent.clear()

    r = client.patch(
        f"/api/v1/admin/users/{invite['id']}/roles",
        json={"roles": ["STRATEGY_ADMIN", "AUDITOR"]},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert len(mock_email.sent) == 1


def test_deactivate_blocks_login_then_reactivate_restores_it(
    client: TestClient, super_admin
) -> None:
    _, token = super_admin
    signup = client.post(
        "/auth/signup",
        json={
            "email": "todeactivate@example.test",
            "password": "correct-horse-battery",
            "display_name": "D",
        },
    )
    user_id = signup.json()["subject"]

    deact = client.post(f"/api/v1/admin/users/{user_id}/deactivate", headers=_auth(token))
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False

    login = client.post(
        "/auth/login",
        json={"email": "todeactivate@example.test", "password": "correct-horse-battery"},
    )
    assert login.status_code == 401

    react = client.post(f"/api/v1/admin/users/{user_id}/reactivate", headers=_auth(token))
    assert react.status_code == 200
    assert react.json()["is_active"] is True

    login2 = client.post(
        "/auth/login",
        json={"email": "todeactivate@example.test", "password": "correct-horse-battery"},
    )
    assert login2.status_code == 200


def test_deactivate_revokes_an_already_issued_token(
    client: TestClient, super_admin, db, identity
) -> None:
    # Login-time checks aren't enough - an admin who already holds a live
    # token before being deactivated must be locked out immediately too.
    _, token = super_admin
    signup = client.post(
        "/auth/signup",
        json={
            "email": "livesession@example.test",
            "password": "correct-horse-battery",
            "display_name": "Live",
        },
    )
    user_id = signup.json()["subject"]
    live_token = identity.issue(
        subject=user_id, role=UserRole.USER, display_name="Live", email="livesession@example.test"
    )

    assert client.get("/api/v1/me", headers=_auth(live_token)).status_code == 200

    deact = client.post(f"/api/v1/admin/users/{user_id}/deactivate", headers=_auth(token))
    assert deact.status_code == 200

    r = client.get("/api/v1/me", headers=_auth(live_token))
    assert r.status_code == 401


def test_cannot_deactivate_own_account(client: TestClient, super_admin) -> None:
    user, token = super_admin
    r = client.post(f"/api/v1/admin/users/{user.id}/deactivate", headers=_auth(token))
    assert r.status_code == 400


def test_cannot_strip_own_super_admin_role_when_the_only_one(
    client: TestClient, super_admin
) -> None:
    # Unlike deactivation, editing roles has no self-action guard, so a lone
    # SUPER_ADMIN demoting themselves is the real way to get locked out -
    # this is the scenario set_user_roles's last-active-SUPER_ADMIN check
    # actually has to catch.
    user, token = super_admin
    r = client.patch(
        f"/api/v1/admin/users/{user.id}/roles",
        json={"roles": ["AUDITOR"]},
        headers=_auth(token),
    )
    assert r.status_code == 400


def test_can_strip_super_admin_role_when_another_one_remains(
    client: TestClient, super_admin, db
) -> None:
    user, token = super_admin
    other = User(
        email="other-root@example.test", display_name="Other", role=UserRole.SUPER_ADMIN.value
    )
    db.add(other)
    db.commit()

    r = client.patch(
        f"/api/v1/admin/users/{user.id}/roles",
        json={"roles": ["AUDITOR"]},
        headers=_auth(token),
    )
    assert r.status_code == 200


def test_invite_cannot_strip_last_super_admin_via_email(
    client: TestClient, super_admin, mock_email: MockEmailSender
) -> None:
    # The invite endpoint upserts by email, so re-submitting the lone
    # SUPER_ADMIN's own address with a lesser role set must be blocked exactly
    # like the PATCH /users/{id}/roles path already is.
    user, token = super_admin
    r = client.post(
        "/api/v1/admin/invites",
        json={"email": user.email, "display_name": user.display_name, "roles": ["AUDITOR"]},
        headers=_auth(token),
    )
    assert r.status_code == 400
    assert "last active SUPER_ADMIN" in r.json()["detail"]


def test_invite_can_change_last_super_admins_extra_roles_only(
    client: TestClient, super_admin
) -> None:
    # Sanity check the guard only fires on actually dropping SUPER_ADMIN.
    user, token = super_admin
    r = client.post(
        "/api/v1/admin/invites",
        json={
            "email": user.email,
            "display_name": user.display_name,
            "roles": ["SUPER_ADMIN", "AUDITOR"],
        },
        headers=_auth(token),
    )
    assert r.status_code == 201


def test_editing_roles_of_a_passwordless_invitee_resends_setup_link(
    client: TestClient, super_admin, mock_email: MockEmailSender
) -> None:
    _, token = super_admin
    client.post(
        "/api/v1/admin/invites",
        json={"email": "pending@example.test", "display_name": "Pending", "roles": ["AUDITOR"]},
        headers=_auth(token),
    )
    mock_email.sent.clear()

    r = client.post(
        "/api/v1/admin/invites",
        json={
            "email": "pending@example.test",
            "display_name": "Pending",
            "roles": ["AUDITOR", "OPERATIONS_ADMIN"],
        },
        headers=_auth(token),
    )
    assert r.status_code == 201
    assert r.json()["invited"] is True
    assert len(mock_email.sent) == 1
    assert "Set your password here" in mock_email.sent[0]["body_text"]


def test_me_exposes_extra_roles_for_a_multi_role_admin(
    client: TestClient, super_admin, mock_email: MockEmailSender
) -> None:
    _, token = super_admin
    invite = client.post(
        "/api/v1/admin/invites",
        json={
            "email": "multirole@example.test",
            "display_name": "Multi",
            "roles": ["OPERATIONS_ADMIN", "FINANCE_ADMIN"],
        },
        headers=_auth(token),
    ).json()
    body = mock_email.sent[0]["body_text"]
    raw_token = _extract_between(body, "Set your password here (valid for 7 days): ").split(
        "token="
    )[1]
    client.post(
        "/auth/reset-password", json={"token": raw_token, "new_password": "a-brand-new-password"}
    )
    login = client.post(
        "/auth/login", json={"email": "multirole@example.test", "password": "a-brand-new-password"}
    )
    me = client.get("/api/v1/me", headers=_auth(login.json()["access_token"]))
    assert me.status_code == 200
    primary_and_extra = {me.json()["role"], *me.json()["extra_roles"]}
    assert primary_and_extra == {"OPERATIONS_ADMIN", "FINANCE_ADMIN"}
    assert invite["id"]  # sanity: invite actually created the account we logged into


def test_cannot_delete_an_active_account(client: TestClient, super_admin, db) -> None:
    target = User(
        email="stillactive@example.test", display_name="Still Active", role=UserRole.AUDITOR.value
    )
    db.add(target)
    db.commit()
    _, token = super_admin
    r = client.delete(f"/api/v1/admin/users/{target.id}", headers=_auth(token))
    assert r.status_code == 400
    assert "deactivated" in r.json()["detail"]


def test_cannot_delete_own_account(client: TestClient, super_admin) -> None:
    user, token = super_admin
    r = client.delete(f"/api/v1/admin/users/{user.id}", headers=_auth(token))
    assert r.status_code == 400


def test_delete_nonexistent_user_is_404(client: TestClient, super_admin) -> None:
    _, token = super_admin
    r = client.delete(
        "/api/v1/admin/users/00000000-0000-4000-8000-000000000000", headers=_auth(token)
    )
    assert r.status_code == 404


def test_delete_a_deactivated_admin_with_no_history_removes_the_row(
    client: TestClient, super_admin, db
) -> None:
    target = User(
        email="cleandelete@example.test",
        display_name="Clean Delete",
        role=UserRole.AUDITOR.value,
        is_active=False,
    )
    db.add(target)
    db.commit()
    target_id = target.id
    _, token = super_admin

    r = client.delete(f"/api/v1/admin/users/{target_id}", headers=_auth(token))
    assert r.status_code == 204

    assert db.get(User, target_id) is None
    # And it's gone from the admin-listing surface too.
    listing = client.get("/api/v1/admin/users", headers=_auth(token))
    assert all(u["id"] != str(target_id) for u in listing.json())


def test_delete_refuses_an_account_with_client_history(client: TestClient, super_admin, db) -> None:
    target = User(
        email="wasaclient@example.test",
        display_name="Was A Client",
        role=UserRole.AUDITOR.value,
        is_active=False,
    )
    db.add(target)
    db.commit()
    strategy = Strategy(strategy_key="s1", strategy_version="v1", name="S1")
    db.add(strategy)
    db.commit()
    db.add(StrategyAssignment(user_id=target.id, strategy_id=strategy.id, master_lot=1))
    db.commit()
    _, token = super_admin

    r = client.delete(f"/api/v1/admin/users/{target.id}", headers=_auth(token))
    assert r.status_code == 400
    assert "history" in r.json()["detail"]
    assert db.get(User, target.id) is not None


def test_delete_anonymizes_but_keeps_records_it_only_referenced(
    client: TestClient, super_admin, db
) -> None:
    # The account reviewed a payment and invited another admin - both those
    # other rows must survive the delete, just with the identity blanked.
    reviewer = User(
        email="reviewer@example.test",
        display_name="Reviewer",
        role=UserRole.FINANCE_ADMIN.value,
        is_active=False,
    )
    db.add(reviewer)
    db.commit()
    submission = PaymentSubmission(
        name="Jane",
        email="jane@example.test",
        phone="+911234567890",
        package="PLAN_3M",
        utr_reference="UTR-DEL-1",
        status="APPROVED",
        reviewed_by=reviewer.id,
    )
    invitee = User(
        email="invitedby-reviewer@example.test", display_name="Invitee", role=UserRole.AUDITOR.value
    )
    db.add_all([submission, invitee])
    db.commit()
    invite = AdminInvite(
        user_id=invitee.id,
        invited_by=reviewer.id,
        token_hash="x" * 64,
        expires_at=submission.submitted_at,
    )
    db.add(invite)
    db.commit()
    submission_id, invite_id = submission.id, invite.id

    _, token = super_admin
    r = client.delete(f"/api/v1/admin/users/{reviewer.id}", headers=_auth(token))
    assert r.status_code == 204

    db.expire_all()
    assert db.get(PaymentSubmission, submission_id).reviewed_by is None
    assert db.get(AdminInvite, invite_id).invited_by is None


def test_ensure_bootstrap_super_admin_is_idempotent(db) -> None:
    user1, token1 = admin_accounts.ensure_bootstrap_super_admin(db, email="Bootstrap@Example.test")
    assert token1 is not None
    assert user1.role == UserRole.SUPER_ADMIN.value

    user2, token2 = admin_accounts.ensure_bootstrap_super_admin(db, email="bootstrap@example.test")
    assert token2 is None
    assert user2.id == user1.id


def test_ensure_bootstrap_super_admin_promotes_an_existing_plain_user(db) -> None:
    # Realistic case: the designated bootstrap email signed up as an ordinary
    # client (role=USER) before being promoted. set_user_roles rejects USER
    # as a target role, so this must never pass it through.
    plain = User(email="wasauser@example.test", display_name="Was A User", role=UserRole.USER.value)
    db.add(plain)
    db.commit()

    user, raw_token = admin_accounts.ensure_bootstrap_super_admin(db, email="wasauser@example.test")
    assert raw_token is None
    assert user.role == UserRole.SUPER_ADMIN.value
    assert user.id == plain.id

    # Idempotent on a second call too.
    user2, token2 = admin_accounts.ensure_bootstrap_super_admin(db, email="wasauser@example.test")
    assert token2 is None
    assert user2.role == UserRole.SUPER_ADMIN.value
