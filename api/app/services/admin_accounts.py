"""Admin-team management: invite/promote admins, edit their role sets, and
deactivate/reactivate accounts. See UserRoleGrant's docstring
(protrix_contracts.db.models) for why a user's admin roles are split between
a single primary ``User.role`` (embedded in the JWT) and any number of extra
rows here.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from protrix_contracts.db.models import (
    AdminInvite,
    Mt5Connection,
    OrderIntent,
    PasswordResetToken,
    PaymentSubmission,
    StrategyAssignment,
    User,
    UserRole,
    UserRoleGrant,
)
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

INVITE_TOKEN_TTL = timedelta(days=7)

# Precedence for which selected role becomes the account's primary `role`
# (used for the JWT / display / USER-vs-admin data scoping). Arbitrary but
# fixed - actual permission checks always consider the full role set
# (see app/security.py's require_role), so this only affects display.
_PRIMARY_PRECEDENCE: tuple[UserRole, ...] = (
    UserRole.SUPER_ADMIN,
    UserRole.FINANCE_ADMIN,
    UserRole.OPERATIONS_ADMIN,
    UserRole.STRATEGY_ADMIN,
    UserRole.AUDITOR,
    UserRole.USER,
)

# Admin invites/role-edits always grant at least one non-USER role - plain
# USER accounts come from self-serve signup or an approved payment, not here.
_INVITABLE_ROLES = frozenset(UserRole) - {UserRole.USER}


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


class ConfirmationRequiredError(Exception):
    """Raised when inviting an email that belongs to an existing account with
    a current or past subscription (a real/former client) - too consequential
    to silently turn into an admin. The caller must resubmit with
    ``confirm=True`` after showing this context to the SUPER_ADMIN."""

    def __init__(
        self,
        *,
        display_name: str,
        role: str,
        extra_roles: list[str],
        subscription_package: str | None,
        is_active: bool,
    ) -> None:
        super().__init__("this email belongs to an existing client account - confirm to proceed")
        self.display_name = display_name
        self.role = role
        self.extra_roles = extra_roles
        self.subscription_package = subscription_package
        self.is_active = is_active


def _split_primary_and_extra(roles: set[UserRole]) -> tuple[UserRole, set[UserRole]]:
    primary = next(r for r in _PRIMARY_PRECEDENCE if r in roles)
    return primary, roles - {primary}


def _replace_extra_roles(session: Session, user_id: uuid.UUID, extra: set[UserRole]) -> None:
    session.execute(delete(UserRoleGrant).where(UserRoleGrant.user_id == user_id))
    for role in extra:
        session.add(UserRoleGrant(user_id=user_id, role=role.value))


def _guard_against_removing_last_super_admin(
    session: Session, user: User, roles: set[UserRole]
) -> None:
    if (
        UserRole.SUPER_ADMIN not in roles
        and user.is_active
        and _is_super_admin(session, user)
        and not _has_other_active_super_admin(session, exclude_user_id=user.id)
    ):
        raise ValidationError("cannot remove the last active SUPER_ADMIN's role")


def _invalidate_pending_invites(session: Session, user_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    for invite in session.scalars(
        select(AdminInvite).where(AdminInvite.user_id == user_id, AdminInvite.used_at.is_(None))
    ):
        invite.used_at = now


def invite_or_update_admin(
    session: Session,
    *,
    email: str,
    display_name: str,
    roles: set[UserRole],
    invited_by: str | None,
    confirm: bool = False,
) -> tuple[User, str | None]:
    """Give `email` the given admin roles. If the account doesn't exist yet,
    create it (no password) and return a raw invite token to email; if it
    already exists, just update its role set and return `None` (they can
    already log in, no new credential flow needed) - unless it's a current or
    past subscriber, in which case this raises ConfirmationRequiredError
    unless `confirm=True` (see that class's docstring)."""
    if not roles or (roles - _INVITABLE_ROLES):
        raise ValidationError("at least one admin role (not USER) is required")
    primary, extra = _split_primary_and_extra(roles)
    email_norm = email.lower()

    user = session.scalar(select(User).where(User.email == email_norm))
    if user is not None:
        if user.subscription_package is not None and not confirm:
            raise ConfirmationRequiredError(
                display_name=user.display_name,
                role=user.role,
                extra_roles=extra_roles_for(session, user.id),
                subscription_package=user.subscription_package,
                is_active=user.is_active,
            )
        _guard_against_removing_last_super_admin(session, user, roles)
        user.role = primary.value
        if display_name:
            user.display_name = display_name
        _replace_extra_roles(session, user.id, extra)

        raw_token = None
        if user.password_hash is None:
            # Account exists but never completed its first password setup -
            # editing its roles again must still leave them a way in, so
            # re-issue a setup link instead of a "log in" notification.
            _invalidate_pending_invites(session, user.id)
            raw_token = _create_invite_token(session, user_id=user.id, invited_by=invited_by)

        session.commit()
        return user, raw_token

    user = User(
        email=email_norm,
        display_name=display_name,
        role=primary.value,
        is_active=True,
        password_hash=None,
        must_change_password=False,
    )
    session.add(user)
    session.flush()  # assign user.id before it's referenced below
    _replace_extra_roles(session, user.id, extra)

    raw_token = _create_invite_token(session, user_id=user.id, invited_by=invited_by)
    session.commit()
    return user, raw_token


def _create_invite_token(session: Session, *, user_id: uuid.UUID, invited_by: str | None) -> str:
    raw_token = secrets.token_urlsafe(32)
    session.add(
        AdminInvite(
            user_id=user_id,
            invited_by=uuid.UUID(invited_by) if invited_by else None,
            token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            expires_at=datetime.now(UTC) + INVITE_TOKEN_TTL,
        )
    )
    return raw_token


def resend_invite(session: Session, user_id: str, *, invited_by: str | None) -> tuple[User, str]:
    """Issue a fresh invite token for an account that hasn't completed its
    first password setup yet, invalidating any previous unused ones."""
    user = session.get(User, uuid.UUID(user_id))
    if user is None:
        raise NotFoundError(f"user {user_id} not found")
    if user.password_hash is not None:
        raise ValidationError("this account already completed setup - nothing to resend")
    _invalidate_pending_invites(session, user.id)
    raw_token = _create_invite_token(session, user_id=user.id, invited_by=invited_by)
    session.commit()
    return user, raw_token


def set_user_roles(session: Session, user_id: str, roles: set[UserRole]) -> User:
    user = session.get(User, uuid.UUID(user_id))
    if user is None:
        raise NotFoundError(f"user {user_id} not found")
    if not roles or (roles - _INVITABLE_ROLES):
        raise ValidationError("at least one admin role (not USER) is required")
    _guard_against_removing_last_super_admin(session, user, roles)
    primary, extra = _split_primary_and_extra(roles)
    user.role = primary.value
    _replace_extra_roles(session, user.id, extra)
    session.commit()
    return user


def _has_other_active_super_admin(session: Session, *, exclude_user_id: uuid.UUID) -> bool:
    primary_count = session.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.role == UserRole.SUPER_ADMIN.value,
            User.is_active.is_(True),
            User.id != exclude_user_id,
        )
    )
    if primary_count:
        return True
    grant_count = session.scalar(
        select(func.count())
        .select_from(UserRoleGrant)
        .join(User, User.id == UserRoleGrant.user_id)
        .where(
            UserRoleGrant.role == UserRole.SUPER_ADMIN.value,
            User.is_active.is_(True),
            User.id != exclude_user_id,
        )
    )
    return bool(grant_count)


def _is_super_admin(session: Session, user: User) -> bool:
    if user.role == UserRole.SUPER_ADMIN.value:
        return True
    grant = session.scalar(
        select(UserRoleGrant).where(
            UserRoleGrant.user_id == user.id, UserRoleGrant.role == UserRole.SUPER_ADMIN.value
        )
    )
    return grant is not None


def deactivate_user(session: Session, *, actor_user_id: str, target_user_id: str) -> User:
    if actor_user_id == target_user_id:
        raise ValidationError("cannot deactivate your own account")
    user = session.get(User, uuid.UUID(target_user_id))
    if user is None:
        raise NotFoundError(f"user {target_user_id} not found")
    if (
        user.is_active
        and _is_super_admin(session, user)
        and not _has_other_active_super_admin(session, exclude_user_id=user.id)
    ):
        raise ValidationError("cannot deactivate the last active SUPER_ADMIN")
    user.is_active = False
    session.commit()
    return user


def reactivate_user(session: Session, user_id: str) -> User:
    user = session.get(User, uuid.UUID(user_id))
    if user is None:
        raise NotFoundError(f"user {user_id} not found")
    user.is_active = True
    session.commit()
    return user


# Tables holding this account's own client-side activity (as opposed to
# rows that merely *reference* it, like a payment they reviewed or an
# invite they sent someone else) - see delete_user.
_CLIENT_HISTORY_MODELS = (StrategyAssignment, OrderIntent, Mt5Connection, PaymentSubmission)


def delete_user(session: Session, *, actor_user_id: str, target_user_id: str) -> str:
    """Permanently remove a deactivated admin account. Only allowed once the
    account is already deactivated (deactivate_user's own guards - self-action,
    last-active-SUPER_ADMIN - have then already run, and this can never catch
    a live account by surprise).

    Refuses to delete an account that has ever acted as a real client (a
    strategy assignment, MT5 connection, order, or payment submitted in its
    own name) - that's client/trading/financial history, not admin-team
    bookkeeping, and it stays reachable only via deactivation. Where the
    account is merely *referenced* by someone else's record - they reviewed a
    payment, or invited another admin - that reference is kept but
    anonymized (set to NULL) rather than deleting the other row.

    Returns the deleted account's email, for the caller's notification/log.
    """
    if actor_user_id == target_user_id:
        raise ValidationError("cannot delete your own account")
    user = session.get(User, uuid.UUID(target_user_id))
    if user is None:
        raise NotFoundError(f"user {target_user_id} not found")
    if user.is_active:
        raise ValidationError("account must be deactivated before it can be permanently deleted")

    target_id = user.id
    has_client_history = any(
        session.scalar(select(model.id).where(model.user_id == target_id).limit(1)) is not None
        for model in _CLIENT_HISTORY_MODELS
    )
    if has_client_history:
        raise ValidationError(
            "this account has client, trading, or payment history and cannot be permanently "
            "deleted - it stays deactivated"
        )

    email = user.email
    session.execute(
        update(PaymentSubmission)
        .where(PaymentSubmission.reviewed_by == target_id)
        .values(reviewed_by=None)
    )
    session.execute(
        update(AdminInvite).where(AdminInvite.invited_by == target_id).values(invited_by=None)
    )
    session.execute(delete(AdminInvite).where(AdminInvite.user_id == target_id))
    session.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == target_id))
    session.delete(user)
    session.commit()
    return email


def ensure_bootstrap_super_admin(
    session: Session, *, email: str, display_name: str = "Super Admin"
) -> tuple[User, str | None]:
    """Idempotent: called on every production boot (app/main.py's lifespan)
    to guarantee `email` is a SUPER_ADMIN. A no-op once the account already
    holds the role - never re-invites or duplicates rows on a later restart.
    Returns a raw invite token only when a brand-new account was created."""
    email_norm = email.lower()
    user = session.scalar(select(User).where(User.email == email_norm))
    if user is None:
        return invite_or_update_admin(
            session,
            email=email_norm,
            display_name=display_name,
            roles={UserRole.SUPER_ADMIN},
            invited_by=None,
        )
    if _is_super_admin(session, user):
        return user, None
    current_extra = {UserRole(r) for r in extra_roles_for(session, user.id)}
    current_primary = UserRole(user.role)
    # A plain client (role=USER, e.g. this email signed up before being
    # designated the bootstrap admin) contributes no role of its own here -
    # set_user_roles rejects USER as it's not an invitable admin role.
    target_roles = current_extra | {UserRole.SUPER_ADMIN}
    if current_primary is not UserRole.USER:
        target_roles.add(current_primary)
    updated = set_user_roles(session, str(user.id), target_roles)
    return updated, None


def extra_roles_for(session: Session, user_id: uuid.UUID) -> list[str]:
    return list(session.scalars(select(UserRoleGrant.role).where(UserRoleGrant.user_id == user_id)))


def extra_roles_by_user(session: Session, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    if not user_ids:
        return {}
    out: dict[uuid.UUID, list[str]] = {}
    rows: Any = session.execute(
        select(UserRoleGrant.user_id, UserRoleGrant.role).where(UserRoleGrant.user_id.in_(user_ids))
    ).all()
    for user_id, role in rows:
        out.setdefault(user_id, []).append(role)
    return out
