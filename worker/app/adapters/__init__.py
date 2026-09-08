"""Execution transport adapters.

``ExecutionAdapter`` is the seam a real MetaApi.cloud client drops into later
(see docs/adr/ADR-001). Only :class:`~app.adapters.mock.MockExecutionAdapter`
exists today; its request/response shapes mirror what a MetaApi client returns
(broker ticket ids, deal ids, a position/deal sync list).
"""

from app.adapters.base import (
    BrokerPosition,
    ExecutionAdapter,
    ExecutionTimeout,
    OrderIntentDTO,
    PlaceResult,
)
from app.adapters.mock import MockExecutionAdapter

__all__ = [
    "BrokerPosition",
    "ExecutionAdapter",
    "ExecutionTimeout",
    "OrderIntentDTO",
    "PlaceResult",
    "MockExecutionAdapter",
]
