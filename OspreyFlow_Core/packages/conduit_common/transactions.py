"""One helper for the Conduit's transaction guards (ADR-127 Amendment 21)."""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


async def rollback_keeping_failure(graph: Any, tx: Any) -> None:
    """Rolls `tx` back from inside an `except BaseException:` guard. A rollback that itself raises
    (the session already expired: ArcadeDB's 404) must not replace the exception being handled,
    least of all a `CancelledError`, which the caller's cancellation depends on reaching its own
    caller: the rollback's failure is logged, and the guard's own `raise` re-raises the original."""
    try:
        await graph.rollback_transaction(tx)
    except Exception as failure:  # noqa: BLE001 - logged; the original exception is re-raised
        _log.warning("rolling back transaction %s failed: %r", tx, failure)
