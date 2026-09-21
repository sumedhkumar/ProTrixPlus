"""TradingView alert-config catalog + changelog (Feature 1).

An "alert" here is admin-authored in ProTrixPlus, then pasted into
TradingView's own alert dialog - TradingView has no API that pushes
alert-created/edited events back to us, only live BUY/SELL webhook signals
(see app/services/ingest.py). Every field change is diffed against the
previous value and recorded as one ``AuditEvent`` row per changed field
(entity_type="alert") - the existing insert-only audit table, not a new one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from protrix_contracts.db.models import Alert, AuditEvent, Strategy
from sqlalchemy import select
from sqlalchemy.orm import Session

_TRACKED_FIELDS = ("name", "symbol", "lot_size", "timeframe")


class NotFoundError(Exception):
    pass


def _alert_dict(a: Alert) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "strategy_id": str(a.strategy_id) if a.strategy_id else None,
        "name": a.name,
        "symbol": a.symbol,
        "lot_size": format(a.lot_size, "f"),
        "timeframe": a.timeframe,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
    }


def _field_value(a: Alert, field: str) -> str:
    value = getattr(a, field)
    return format(value, "f") if isinstance(value, Decimal) else str(value)


def admin_list_alerts(session: Session) -> list[dict[str, Any]]:
    stmt = select(Alert).order_by(Alert.created_at)
    return [_alert_dict(a) for a in session.scalars(stmt).all()]


@dataclass
class AlertInput:
    name: str
    symbol: str
    lot_size: Decimal
    timeframe: str


def admin_create_alert(session: Session, body: AlertInput, *, actor: str) -> dict[str, Any]:
    alert = Alert(
        name=body.name, symbol=body.symbol, lot_size=body.lot_size, timeframe=body.timeframe
    )
    session.add(alert)
    session.flush()
    session.add(
        AuditEvent(
            event_type="alert.created",
            entity_type="alert",
            entity_id=str(alert.id),
            actor=actor,
            data={"name": alert.name, "symbol": alert.symbol},
        )
    )
    session.commit()
    session.refresh(alert)
    return _alert_dict(alert)


def admin_update_alert(
    session: Session, alert_id: str, *, actor: str, **fields: Any
) -> dict[str, Any]:
    alert = session.get(Alert, uuid.UUID(alert_id))
    if alert is None:
        raise NotFoundError(f"alert {alert_id} not found")

    for field in _TRACKED_FIELDS:
        if field not in fields or fields[field] is None:
            continue
        new_value = fields[field]
        old_repr = _field_value(alert, field)
        if getattr(alert, field) == new_value:
            continue
        setattr(alert, field, new_value)
        new_repr = _field_value(alert, field)
        session.add(
            AuditEvent(
                event_type="alert.field_changed",
                entity_type="alert",
                entity_id=str(alert.id),
                actor=actor,
                data={"field": field, "old_value": old_repr, "new_value": new_repr},
            )
        )

    session.commit()
    session.refresh(alert)
    return _alert_dict(alert)


def admin_get_alert_changelog(session: Session, alert_id: str) -> list[dict[str, Any]]:
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.entity_type == "alert", AuditEvent.entity_id == alert_id)
        .order_by(AuditEvent.created_at.desc())
    )
    return [
        {
            "event_type": e.event_type,
            "actor": e.actor,
            "data": e.data,
            "created_at": e.created_at.isoformat(),
        }
        for e in session.scalars(stmt).all()
    ]


def admin_bundle_alerts_into_strategy(
    session: Session, strategy_id: str, alert_ids: list[str], *, actor: str
) -> list[dict[str, Any]]:
    strategy = session.get(Strategy, uuid.UUID(strategy_id))
    if strategy is None:
        raise NotFoundError(f"strategy {strategy_id} not found")

    alerts = []
    for alert_id in alert_ids:
        alert = session.get(Alert, uuid.UUID(alert_id))
        if alert is None:
            raise NotFoundError(f"alert {alert_id} not found")
        alert.strategy_id = strategy.id
        alerts.append(alert)

    session.add(
        AuditEvent(
            event_type="strategy.alerts_bundled",
            entity_type="strategy",
            entity_id=str(strategy.id),
            actor=actor,
            data={"alert_ids": alert_ids},
        )
    )
    session.commit()
    for alert in alerts:
        session.refresh(alert)
    return [_alert_dict(a) for a in alerts]
