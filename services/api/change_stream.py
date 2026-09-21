"""The corpus-wide change stream — `06_DECISIONS.md` ADR-037's amendment: "Ingest, the corpus-wide
resolution trigger (ADR-025), and manual assertion (B11's mechanism) all publish to one change
stream; a monitor evaluates against that stream, not against ingest alone." Phase 7 Stage 6a's own
foundation-only scope: this module is the publish/read mechanism itself, wired to its three
producers — it is deliberately not a scheduler and has no consumer-group/worker loop of its own
(`worker.py`'s own `JobWorker` is that shape, for job dispatch, not this). Nothing in this stage
watches the stream continuously; a future monitor evaluator (Stage 6b/6c) is the first real
consumer, and reads it the same way `read_since` below already proves is possible.

**One Valkey Stream, `changes:corpus`, not a second piece of infrastructure** — the same
`XADD`/`valkey_compat.reply` shape `services/api/jobs.py::JobQueue.submit` already uses, per the
amendment's own "the natural substrate is the same Valkey-Streams mechanism ADR-025's own job
queue already uses... a second stream, not a second piece of infrastructure."

**What a change stream entry carries.** `source` (one of `"ingest"`, `"resolution"`,
`"manual_assertion"`), the node/edge ids the write touched, and `recorded_at`. Deliberately thin —
this stage builds no pattern-matching consumer, so the entry does not try to pre-encode what a
future monitor's own
`PatternQuery` might need to filter on beyond what each producer already has for free; a consumer
that needs more (entity types touched, say) re-fetches via `GraphPort` from the ids given, the same
"re-verify from the authoritative source, never trust a cached shape" discipline every access-
control path in this codebase already follows.

**What this still misses, checked directly rather than assumed — ADR-037's own amendment already
did this analysis and it is not repeated here, only pointed at**: a match created by deletion does
not exist as a possible gap in this system as built (no hard-delete on `GraphPort`, no negation in
`PatternQuery`) — see ADR-037's own "What the change delta still misses" section for the full
two-part argument (supersession is itself a write this stream already captures; a pattern language
with no "must not exist" clause cannot have a match newly created by removal). The only thing this
stream cannot yet prove it captures is a producer nobody has wired it to — currently exactly three,
matching ADR-037's own accepted list, no more and no fewer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from valkey.asyncio import Valkey

from conduit_common.valkey_compat import reply

ChangeSource = Literal["ingest", "resolution", "manual_assertion"]

_STREAM_KEY = "changes:corpus"


class ChangeStreamEntry(BaseModel):
    entry_id: str
    source: ChangeSource
    node_ids: list[str]
    edge_ids: list[str]
    recorded_at: datetime


def _decode(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


class ChangeStreamWriter:
    """The one place any producer appends to the corpus-wide change stream — `publish` is called
    from `app.py`'s ingest-run route, `services/resolve/trigger.py::run_resolution_for_entity_type`
    and `services/api/working_set/service.py::_manual_assertion`, never duplicated inline at each
    call site."""

    def __init__(self, client: Valkey) -> None:
        self._client = client

    async def publish(
        self,
        source: ChangeSource,
        *,
        node_ids: list[str] | None = None,
        edge_ids: list[str] | None = None,
    ) -> str | None:
        """No-op (returns `None`) when a producer's own write touched nothing — an ingest run that
        created zero nodes, a resolution pass that wrote zero `SAME_AS` edges — the same "nothing
        happened, nothing to publish" discipline `submit_post_ingest_resolution_jobs` already
        applies to its own `report.nodes_created == 0` check, not a special case invented here."""
        node_ids = node_ids or []
        edge_ids = edge_ids or []
        if not node_ids and not edge_ids:
            return None
        fields = {
            "source": source,
            "node_ids": ",".join(node_ids),
            "edge_ids": ",".join(edge_ids),
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        entry_id = await reply(self._client.xadd(_STREAM_KEY, fields))
        return _decode(entry_id)

    async def read_since(
        self, *, after_id: str = "-", count: int = 1000
    ) -> list[ChangeStreamEntry]:
        """A plain `XRANGE`, not a consumer group — this stage builds no scheduled consumer, only
        proves the mechanism a future one will read from. `after_id="-"` (the default) reads from
        the stream's own start; a real consumer would track and pass its own last-seen id, the same
        cursor discipline `ListNodesPage.next_cursor` already establishes elsewhere in this
        codebase, not invented fresh here."""
        start = "-" if after_id == "-" else f"({after_id}"
        raw = await reply(self._client.xrange(_STREAM_KEY, min=start, max="+", count=count))
        entries: list[ChangeStreamEntry] = []
        for entry_id, fields in raw:
            decoded = {_decode(k): _decode(v) for k, v in fields.items()}
            entries.append(
                ChangeStreamEntry(
                    entry_id=_decode(entry_id),
                    source=decoded["source"],  # type: ignore[arg-type]
                    node_ids=[n for n in decoded["node_ids"].split(",") if n],
                    edge_ids=[e for e in decoded["edge_ids"].split(",") if e],
                    recorded_at=decoded["recorded_at"],  # type: ignore[arg-type]
                )
            )
        return entries


__all__ = ["ChangeSource", "ChangeStreamEntry", "ChangeStreamWriter"]
