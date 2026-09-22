"""ExecutionAdapter interface + the DTOs that cross it.

Deliberately transport-shaped, not domain-shaped: a ``MetaApiExecutionAdapter``
will implement exactly this Protocol. Protrixplus keeps all eligibility, sizing
and risk logic on its side of this line.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

Side = Literal["BUY", "SELL"]
PlaceStatus = Literal["ACKNOWLEDGED", "REJECTED"]


class ExecutionTimeout(Exception):
    """The transport did not return in time. The order may or may not have
    reached the broker - state is UNKNOWN and must be reconciled, never blindly
    re-sent."""


@dataclass(frozen=True)
class OrderIntentDTO:
    client_order_id: str
    account_ref: str
    symbol: str
    side: Side
    volume: Decimal
    action: str
    command_target: str
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    position_ref: str | None = None
    close_fraction: Decimal | None = None
    # Only used by the mock adapter to resolve a CLOSE/MODIFY against the
    # right previously-opened position - the real mt5 adapter ignores these
    # (it rejects every non-ENTRY action until real broker position lookup
    # exists).
    user_id: str | None = None
    strategy_key: str | None = None
    strategy_version: str | None = None


@dataclass(frozen=True)
class PlaceResult:
    ticket_id: str
    deal_id: str
    status: PlaceStatus
    raw: dict[str, str]
    # Set by the mock adapter on a successful ENTRY placement so the caller
    # can persist it onto the Execution row; None everywhere else.
    entry_price: Decimal | None = None


@dataclass(frozen=True)
class BrokerPosition:
    client_order_id: str
    ticket_id: str
    deal_id: str
    symbol: str
    volume: Decimal
    side: Side
    status: str


@runtime_checkable
class ExecutionAdapter(Protocol):
    name: str

    def place(self, order: OrderIntentDTO) -> PlaceResult:
        """Submit an order. Raises :class:`ExecutionTimeout` on a lost response."""
        ...

    def sync_positions(self, account_ref: str) -> list[BrokerPosition]:
        """Return current broker positions/deals for reconciliation."""
        ...
