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
with no "must not exist" clause cannot have a match newly created by removal). **This dependency is
recorded at its own two source locations, not only here** — `01_DOMAIN_MODEL.md` §2.4 (`GraphPort`'s
own no-hard-delete statement) and §8.1 (`PatternQuery`'s own schema, where negation's absence is
checked directly) each carry a pointer back to ADR-037 stating precisely what breaks, and naming
the test that would need to exist, if either absence is ever removed — read there, not re-derived
here, if you are the one adding a hard-delete method or a negation clause. The only thing this
stream cannot yet prove it captures is a producer nobody has wired it to — currently exactly three,
matching ADR-037's own accepted list, no more and no fewer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel
from valkey.asyncio import Valkey

from conduit_common.valkey_compat import reply

ChangeSource = Literal["ingest", "resolution", "manual_assertion"]

_STREAM_KEY = "changes:corpus"

#: How many entries `publish` keeps (`XADD MAXLEN ~`). Valkey runs `noeviction`, so an uncapped
#: stream grows until writes fail, and an ingest entry carries every node a run touched; nothing
#: reads an entry after the fact (evaluation runs with the entry in hand, `read_since` has no caller
#: outside tests), so old ones are of no use. 900, not 1,000: an approximate trim keeps up to one
#: macro node (100 entries by default) over the cap, so the stream never exceeds `READ_SINCE_COUNT`
#: and a read from its start always reaches the newest entry.
CHANGE_STREAM_MAXLEN = 900

#: `read_since`'s default window.
READ_SINCE_COUNT = 1000


class ChangeStreamEntry(BaseModel):
    entry_id: str
    source: ChangeSource
    node_ids: list[str]
    edge_ids: list[str]
    #: Phase 7 Stage 6c — a best-effort audit-shaped hint (`schemas.domain.Alert.investigation_id`'s
    #: own docstring has the full reasoning), never an access-control scope. `None` for a producer
    #: with no single investigation in scope (the resolution trigger).
    investigation_id: str | None = None
    recorded_at: datetime


def _decode(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


class _Touched(Protocol):
    created_node_ids: list[str]
    referenced_node_ids: list[str]


def touched_node_ids(report: _Touched) -> list[str]:
    """The nodes an ingest run's entry names (ADR-127 decision 7(a)): those the run created, then
    those it matched by reference, each once. A hotlist or a monitor is shown what a run *touched*:
    a hotlisted number the run linked to, having been written by an earlier load, is as much its
    business as one it wrote. What the case's rules wrote into the load (`rule_node_ids`) is in
    neither list and stays out (decision 6). The entry is internal: its consumers re-fetch each id
    through the access-filtered port and show a reader nothing it cannot read."""
    return list(dict.fromkeys([*report.created_node_ids, *report.referenced_node_ids]))


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
        investigation_id: str | None = None,
    ) -> ChangeStreamEntry | None:
        """No-op (returns `None`) when a producer's own write touched nothing — an ingest run that
        created zero nodes, a resolution pass that wrote zero `SAME_AS` edges — the same "nothing
        happened, nothing to publish" discipline `submit_post_ingest_resolution_jobs` already
        applies to its own `report.nodes_created == 0` check, not a special case invented here.

        Returns the entry actually written (Stage 6c: the caller needs it in hand to trigger
        synchronous evaluation against exactly what was published, not a second `read_since` round
        trip to reconstruct it) rather than only the bare entry id 6a returned."""
        node_ids = node_ids or []
        edge_ids = edge_ids or []
        if not node_ids and not edge_ids:
            return None
        recorded_at = datetime.now(UTC)
        fields = {
            "source": source,
            "node_ids": ",".join(node_ids),
            "edge_ids": ",".join(edge_ids),
            "investigation_id": investigation_id or "",
            "recorded_at": recorded_at.isoformat(),
        }
        added = self._client.xadd(
            _STREAM_KEY, fields, maxlen=CHANGE_STREAM_MAXLEN, approximate=True
        )
        entry_id = _decode(await reply(added))
        return ChangeStreamEntry(
            entry_id=entry_id,
            source=source,
            node_ids=node_ids,
            edge_ids=edge_ids,
            investigation_id=investigation_id,
            recorded_at=recorded_at,
        )

    async def read_since(
        self, *, after_id: str = "-", count: int = READ_SINCE_COUNT
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
                    investigation_id=decoded.get("investigation_id") or None,
                    recorded_at=decoded["recorded_at"],  # type: ignore[arg-type]
                )
            )
        return entries


__all__ = ["ChangeSource", "ChangeStreamEntry", "ChangeStreamWriter"]
