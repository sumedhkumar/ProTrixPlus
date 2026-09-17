from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal

import pytest

from app.config import Settings
from app.payments import RazorpayError, RazorpayGateway, usd_to_subunits


def _gateway() -> RazorpayGateway:
    return RazorpayGateway(
        Settings(razorpay_key_id="rzp_test_example", razorpay_key_secret="test-secret")
    )


def test_checkout_signature_is_server_verified() -> None:
    signature = hmac.new(b"test-secret", b"order_123|pay_123", hashlib.sha256).hexdigest()
    gateway = _gateway()
    assert gateway.verify_checkout_signature(
        order_id="order_123", payment_id="pay_123", signature=signature
    )
    assert not gateway.verify_checkout_signature(
        order_id="order_123", payment_id="pay_other", signature=signature
    )


def test_usd_amounts_require_exact_cents() -> None:
    assert usd_to_subunits(Decimal("100.00")) == 10000
    with pytest.raises(RazorpayError):
        usd_to_subunits(Decimal("0"))
    with pytest.raises(RazorpayError):
        usd_to_subunits(Decimal("1.001"))
