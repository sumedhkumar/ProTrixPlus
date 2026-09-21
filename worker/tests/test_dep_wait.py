"""_safe_netloc must never leak credentials into a log line.

The dependency-wait log names the endpoint that refused a connection so an
operator can tell postgres from redis, and localhost from a real host. Both
URLs carry passwords - Upstash hands out `rediss://default:<pw>@host:6379` and
Render's DATABASE_URL embeds one too - so a regression here would write a
production secret straight into the deploy log.
"""

from __future__ import annotations

from app.main import _safe_netloc

PASSWORD = "sup3r-s3cret-pw"


def test_strips_user_and_password() -> None:
    url = f"rediss://default:{PASSWORD}@fond-kite-12345.upstash.io:6379"
    assert _safe_netloc(url) == "fond-kite-12345.upstash.io:6379"


def test_password_never_appears_for_any_supported_url() -> None:
    urls = [
        f"rediss://default:{PASSWORD}@host.upstash.io:6379",
        f"redis://:{PASSWORD}@127.0.0.1:6379/0",
        f"postgresql+psycopg://protrix:{PASSWORD}@dpg-abc123.oregon-postgres.render.com:5432/protrix",
    ]
    for url in urls:
        assert PASSWORD not in _safe_netloc(url)


def test_url_without_credentials_is_unchanged() -> None:
    assert _safe_netloc("redis://localhost:6379/0") == "localhost:6379"


def test_url_without_explicit_port_omits_the_port() -> None:
    assert _safe_netloc("rediss://default:pw@host.upstash.io") == "host.upstash.io"


def test_postgres_url_keeps_the_dialect_host() -> None:
    url = "postgresql+psycopg://protrix:pw@db.internal:5432/protrix"
    assert _safe_netloc(url) == "db.internal:5432"


def test_malformed_url_does_not_raise() -> None:
    # An out-of-range port makes urlparse.port raise ValueError - the wait loop
    # is already in a failure path here, so it must degrade, not crash.
    assert _safe_netloc("redis://host:99999/0") == "<unparseable url>"


def test_empty_url_does_not_raise() -> None:
    assert _safe_netloc("") == "<no host>"
