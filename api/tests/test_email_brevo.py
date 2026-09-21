"""BrevoEmailSender - the production backend (Render blocks SMTP ports on
free web services, so mail goes out over HTTPS instead).

Covers the exact wire format Brevo expects, both failure modes, and the
best-effort wrapper that keeps a dead mailbox from failing a request whose
database work has already been committed.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

from app.email import BestEffortEmailSender, BrevoEmailSender, EmailError, get_email_sender
from app.email import brevo as brevo_module


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


def _capture(
    monkeypatch: pytest.MonkeyPatch, response: _FakeResponse | Exception
) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        seen["url"] = url
        seen.update(kwargs)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(brevo_module.httpx, "post", fake_post)
    return seen


def _sender() -> BrevoEmailSender:
    return BrevoEmailSender(
        api_key="test-key", from_name="ProTrixPlus", from_address="protrixplus@gmail.com"
    )


def test_sends_the_request_shape_brevo_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture(monkeypatch, _FakeResponse(201))

    _sender().send(to="client@example.test", subject="Welcome", body_text="temp password: abc")

    assert seen["url"] == "https://api.brevo.com/v3/smtp/email"
    assert seen["headers"]["api-key"] == "test-key"
    assert seen["headers"]["content-type"] == "application/json"
    assert seen["json"] == {
        "sender": {"name": "ProTrixPlus", "email": "protrixplus@gmail.com"},
        "to": [{"email": "client@example.test"}],
        "subject": "Welcome",
        "textContent": "temp password: abc",
    }


def test_html_body_is_only_sent_when_there_is_one(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture(monkeypatch, _FakeResponse(201))

    _sender().send(to="a@b.test", subject="s", body_text="plain", body_html="<p>rich</p>")

    assert seen["json"]["htmlContent"] == "<p>rich</p>"
    assert seen["json"]["textContent"] == "plain"


def test_rejected_send_raises_email_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture(monkeypatch, _FakeResponse(400, '{"message":"sender not valid"}'))

    with pytest.raises(EmailError, match="400"):
        _sender().send(to="a@b.test", subject="s", body_text="t")


def test_network_failure_raises_email_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture(monkeypatch, httpx.ConnectTimeout("timed out"))

    with pytest.raises(EmailError, match="failed to send email"):
        _sender().send(to="a@b.test", subject="s", body_text="t")


def test_best_effort_swallows_the_failure_without_logging_the_body(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _capture(monkeypatch, _FakeResponse(401, "invalid api key"))
    secret = "temp-password-nobody-else-may-see"

    with caplog.at_level(logging.ERROR, logger="api.email"):
        BestEffortEmailSender(_sender()).send(
            to="a@b.test", subject="Your login details", body_text=secret
        )

    assert "email delivery failed" in caplog.text
    assert secret not in caplog.text


def test_factory_builds_a_wrapped_brevo_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROTRIX_EMAIL_BACKEND", "brevo")
    monkeypatch.setenv("PROTRIX_BREVO_API_KEY", "key-from-env")
    get_email_sender.cache_clear()

    sender = get_email_sender()

    assert isinstance(sender, BestEffortEmailSender)
    assert isinstance(sender._inner, BrevoEmailSender)
