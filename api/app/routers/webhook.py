"""POST /webhook/tradingview - the signal ingress.

Order of operations is deliberate:

1. authorize (shared-secret header)   -> 401 if wrong, nothing touched
2. parse JSON with Decimal floats     -> 400 if not JSON
3. strict schema validation           -> 422, nothing written
4. durable write of signal + outbox   -> committed BEFORE we return
5. only then: 202 (new) / 200 (dup)
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from protrix_contracts.envelope import EnvelopeValidationError
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import tradingview_path_authorized, webhook_authorized
from app.services.ingest import SignalConflictError, accept_signal

log = logging.getLogger("api.webhook")
router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/tradingview", dependencies=[Depends(webhook_authorized)])
async def ingest_tradingview(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return await _ingest(request, response, db, normalize_tradingview=False)


@router.post(
    "/tradingview/{webhook_token}",
    dependencies=[Depends(tradingview_path_authorized)],
)
async def ingest_tradingview_alert(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Direct TradingView ingress authenticated by the URL path secret."""
    return await _ingest(request, response, db, normalize_tradingview=True)


async def _ingest(
    request: Request,
    response: Response,
    db: Session,
    *,
    normalize_tradingview: bool,
) -> dict[str, Any]:
    raw = await request.body()
    try:
        # parse_float=Decimal: never let a wire number become a binary float.
        payload = json.loads(raw or b"", parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid JSON: {exc.msg}"
        ) from exc

    if normalize_tradingview and isinstance(payload, dict):
        payload = _normalize_tradingview_payload(payload)

    try:
        result = accept_signal(db, payload)
    except EnvelopeValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": exc.errors},
        ) from exc
    except SignalConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    response.status_code = status.HTTP_200_OK if result.duplicate else status.HTTP_202_ACCEPTED
    return {
        "accepted": True,
        "duplicate": result.duplicate,
        "signal_id": result.signal_id,
        "signal_row_id": result.signal_row_id,
        "payload_hash": result.payload_hash,
    }


def _normalize_tradingview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize TradingView strategy placeholders to the frozen wire contract.

    ``order_id`` is accepted as a convenience alias, not part of the frozen
    envelope (which has ``additionalProperties: false``): TradingView's alert
    editor sometimes mis-lints a message where two ``{{...}}`` placeholders
    are concatenated in the same string (e.g.
    ``"{{strategy.order.id}}-{{timenow}}"``), so the recommended alert
    template sends ``order_id`` and ``event_time_utc`` as separate
    single-placeholder fields and we combine them into ``signal_id`` here -
    always popped before the payload reaches validate_envelope.
    """
    normalized = dict(payload)
    order_id = normalized.pop("order_id", None)
    if order_id is not None and "signal_id" not in normalized:
        normalized["signal_id"] = f"{order_id}-{normalized.get('event_time_utc', '')}"
    action = normalized.get("action")
    if isinstance(action, str) and action.lower() in {"buy", "sell"}:
        normalized["action"] = action.upper()
    timeframe = normalized.get("timeframe")
    if isinstance(timeframe, str) and timeframe.isdigit():
        normalized["timeframe"] = f"{timeframe}m"
    return normalized
