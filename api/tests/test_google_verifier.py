"""Exercises the real RS256 verification path (PyJWT's `cryptography` backend)
rather than mocking it away. The signup-google/login-google endpoint tests in
test_auth.py stub `verify_google_id_token` entirely - useful for testing the
account logic, but it means they never actually decode a token, so a missing
optional dependency (`cryptography`, needed for RS256) passed CI and only
surfaced as a live 500. These tests sign a real token with a throwaway RSA
key and verify it for real, so that regression can't hide again."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from app.identity import google_verifier
from app.identity.google_verifier import GoogleTokenError, verify_google_id_token

_CLIENT_ID = "test-client-id.apps.googleusercontent.com"


@pytest.fixture
def rsa_keypair() -> tuple[RSAPrivateKey, RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _token(private_key: RSAPrivateKey, **claim_overrides: object) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": "https://accounts.google.com",
        "aud": _CLIENT_ID,
        "sub": "1234567890",
        "email": "jane@example.test",
        "email_verified": True,
        "name": "Jane Doe",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-kid"})


def _stub_jwks(monkeypatch: pytest.MonkeyPatch, public_key: RSAPublicKey) -> None:
    """Skip the real network call to Google's JWKS endpoint - the point of
    this test is the RS256/`cryptography` decode path, not network I/O."""

    class _FakeSigningKey:
        key = public_key

    monkeypatch.setattr(
        google_verifier._jwk_client,
        "get_signing_key_from_jwt",
        lambda _token: _FakeSigningKey(),
    )


def test_verify_accepts_a_real_rs256_token(
    rsa_keypair: tuple[RSAPrivateKey, RSAPublicKey], monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key, public_key = rsa_keypair
    _stub_jwks(monkeypatch, public_key)

    identity = verify_google_id_token(_token(private_key), client_id=_CLIENT_ID)

    assert identity.email == "jane@example.test"
    assert identity.name == "Jane Doe"


def test_verify_lowercases_email(
    rsa_keypair: tuple[RSAPrivateKey, RSAPublicKey], monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key, public_key = rsa_keypair
    _stub_jwks(monkeypatch, public_key)

    identity = verify_google_id_token(
        _token(private_key, email="Jane@Example.TEST"), client_id=_CLIENT_ID
    )

    assert identity.email == "jane@example.test"


def test_verify_rejects_wrong_audience(
    rsa_keypair: tuple[RSAPrivateKey, RSAPublicKey], monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key, public_key = rsa_keypair
    _stub_jwks(monkeypatch, public_key)

    with pytest.raises(GoogleTokenError):
        verify_google_id_token(_token(private_key, aud="someone-elses-app"), client_id=_CLIENT_ID)


def test_verify_rejects_unverified_email(
    rsa_keypair: tuple[RSAPrivateKey, RSAPublicKey], monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key, public_key = rsa_keypair
    _stub_jwks(monkeypatch, public_key)

    with pytest.raises(GoogleTokenError, match="not verified"):
        verify_google_id_token(_token(private_key, email_verified=False), client_id=_CLIENT_ID)


def test_verify_rejects_expired_token(
    rsa_keypair: tuple[RSAPrivateKey, RSAPublicKey], monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key, public_key = rsa_keypair
    _stub_jwks(monkeypatch, public_key)
    now = datetime.now(UTC)

    token = _token(
        private_key,
        iat=int((now - timedelta(hours=2)).timestamp()),
        exp=int((now - timedelta(hours=1)).timestamp()),
    )

    with pytest.raises(GoogleTokenError):
        verify_google_id_token(token, client_id=_CLIENT_ID)


def test_verify_requires_client_id_configured() -> None:
    with pytest.raises(GoogleTokenError, match="not configured"):
        verify_google_id_token("irrelevant", client_id="")
