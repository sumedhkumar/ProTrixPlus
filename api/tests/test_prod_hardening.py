"""Startup guard in app/main.py's lifespan: production must not boot with the
placeholder (or otherwise weak) dev_jwt_secret - every session token is
signed with it, so a known/short secret lets anyone forge a SUPER_ADMIN
token."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def _boot(monkeypatch: pytest.MonkeyPatch, *, secret: str) -> None:
    monkeypatch.setenv("PROTRIX_APP_ENV", "prod")
    monkeypatch.setenv("PROTRIX_DEV_IDENTITY_ENABLED", "false")
    monkeypatch.setenv("PROTRIX_DEV_JWT_SECRET", secret)
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app):
        pass


def test_prod_boot_rejects_placeholder_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(RuntimeError, match="dev_jwt_secret"):
        _boot(monkeypatch, secret="dev-only-not-a-real-secret-change-me")


def test_prod_boot_rejects_short_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(RuntimeError, match="dev_jwt_secret"):
        _boot(monkeypatch, secret="too-short")


def test_prod_boot_accepts_strong_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _boot(monkeypatch, secret="a" * 40)  # does not raise
