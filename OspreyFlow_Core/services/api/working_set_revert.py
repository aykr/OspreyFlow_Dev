"""A revert's reach into the Conduit's stores, from outside the Conduit (ADR-127 decision 6).

`scripts/revert_load.py` is its own process, so it cannot call the Conduit's running services; it
reaches the working-set store, the stored history and Pub/Sub directly, as
`scripts/strip_change_provenance.py` does. `WorkingSetService` runs outside the Conduit: it needs a
graph, a store and a scheme, and `remove_reverted` uses only the store.

`WorkingSetReverter.remove` removes the load's elements from every case holding them
(`WorkingSetService.remove_reverted`), publishes each case's stored removal on that case's channel
so every Conduit instance holding a socket projects it for its reader (`notify.publish_delta`: the
stored form, with the record, never a sent form), and takes the elements out of every stored history
step. It is idempotent: a second call finds nothing held, publishes nothing, and the history
scrub changes nothing.

**Not the clearance of anyone.** It removes the load's own elements; no reader's clearance applies.
What each connected reader is sent is decided per reader by the projection, from the record.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from valkey.asyncio import Valkey

from .notify import publish_delta
from .working_set.service import WorkingSetService


class HistoryScrub(Protocol):
    async def remove_elements(self, node_ids: Sequence[str], edge_ids: Sequence[str]) -> int: ...


class WorkingSetReverter:
    def __init__(self, service: WorkingSetService, valkey: Valkey, history: HistoryScrub) -> None:
        self._service = service
        self._valkey = valkey
        self._history = history

    async def remove(
        self, node_ids: Sequence[str], edge_ids: Sequence[str], *, final_pass: bool = False
    ) -> int:
        """The number of cases that held any of the ids. Every case's removal is stored before any
        is published, so a socket that resynchronises on a published message finds the stores
        already clean. `final_pass` (the revert's second run, last before its mark) does the same
        work: it finds only what a Conduit left running added back since the first."""
        removals = await self._service.remove_reverted(node_ids, edge_ids)
        for removal in removals:
            await publish_delta(self._valkey, removal.investigation_id, removal.delta)
        await self._history.remove_elements(node_ids, edge_ids)
        return len(removals)
