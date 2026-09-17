"""Minimal Razorpay REST boundary.

All amount calculation and fulfillment stays in Protrixplus. This module only
creates/fetches provider objects and verifies provider signatures.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings


class RazorpayError(RuntimeError):
    pass


@dataclass(frozen=True)
class RazorpayOrder:
    order_id: str
    amount_subunits: int
    currency: str


def usd_to_subunits(amount: Decimal) -> int:
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded != amount or rounded <= 0:
        raise RazorpayError("Razorpay USD amounts must be positive cents")
    return int(rounded * 100)


class RazorpayGateway:
    def __init__(self, settings: Settings) -> None:
        self._key_id = settings.razorpay_key_id
        self._key_secret = settings.razorpay_key_secret.get_secret_value()
        self._webhook_secret = settings.razorpay_webhook_secret.get_secret_value()

    @property
    def configured(self) -> bool:
        return bool(self._key_id and self._key_secret)

    @property
    def public_key_id(self) -> str:
        return self._key_id

    def create_order(
        self, *, amount_usd: Decimal, receipt: str, notes: dict[str, str]
    ) -> RazorpayOrder:
        amount = usd_to_subunits(amount_usd)
        data = self._request(
            "POST",
            "/orders",
            {"amount": amount, "currency": "USD", "receipt": receipt, "notes": notes},
        )
        try:
            return RazorpayOrder(
                order_id=str(data["id"]),
                amount_subunits=int(data["amount"]),
                currency=str(data["currency"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RazorpayError("invalid create-order response") from exc

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return self._request("GET", f"/payments/{payment_id}", None)

    def verify_checkout_signature(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        if not self._key_secret:
            raise RazorpayError("Razorpay is not configured")
        expected = hmac.new(
            self._key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str | None) -> bool:
        if not self._webhook_secret or not signature:
            return False
        expected = hmac.new(self._webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not self.configured:
            raise RazorpayError("Razorpay test or live credentials are not configured")
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        auth = base64.b64encode(f"{self._key_id}:{self._key_secret}".encode()).decode()
        request = Request(
            f"https://api.razorpay.com/v1{path}",
            data=body,
            method=method,
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed provider base URL
                decoded = json.loads(response.read().decode())
        except HTTPError as exc:
            raise RazorpayError(f"Razorpay returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RazorpayError("Razorpay request failed") from exc
        if not isinstance(decoded, dict):
            raise RazorpayError("invalid Razorpay response")
        return decoded
