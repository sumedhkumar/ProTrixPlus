from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.routers.marketplace import Mt5CredentialInput


def test_metaapi_enrollment_is_rejected_until_an_adapter_exists() -> None:
    with pytest.raises(ValidationError, match="MetaApi enrollment execution is not configured"):
        Mt5CredentialInput(
            login="123456",
            password="not-a-real-password",
            server="Example-Demo",
            transport="METAAPI",
        )
