"""Working-set storage — `docs/03_CONDUIT_MIDDLEWARE.md` §4: "One Valkey
hash per investigation holding the node and edge set in a compact binary
encoding, plus a capped stream of deltas for reconnect. TTL of 24 hours on
idle."

`WorkingSetStorage` is a `Protocol` so `WorkingSetService`'s own logic —
the cap check, the projection, the reconnect gap detection — can be
exercised in tests against a fast in-memory fake
(`tests/services/api/working_set/fakes.py`) without a live Valkey, the
same reasoning `GraphPort` is a `Protocol` rather than a concrete class.
`ValkeyWorkingSetStore` is the one real implementation this phase ships.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Protocol

import msgpack
from valkey.asyncio import Valkey

from conduit_common.valkey_compat import reply as _reply
from schemas.domain import Edge, EdgeId, Node, NodeId

from .models import WorkingSetDelta, decode_delta

#: `03_CONDUIT_MIDDLEWARE.md` §4: "TTL of 24 hours on idle". Refreshed on
#: every mutating call — `_touch_ttl` — so an active investigation never
#: expires mid-session; only one nobody has touched in a day does.
IDLE_TTL_SECONDS = 24 * 60 * 60

#: Approximate cap on the capped delta stream (`~` trim, not exact — Valkey
#: trims to *approximately* this many entries for O(1) trimming rather than
#: an exact count that would need a full scan). A client that has missed
#: more than this many deltas gets a gap and resnapshots regardless, so the
#: approximation costs nothing the protocol doesn't already handle.
DELTA_STREAM_MAXLEN = 2000


class WorkingSetStorage(Protocol):
    async def source_fidelity_nodes(self, investigation_id: str) -> dict[NodeId, Node]: ...
    async def source_fidelity_edges(self, investigation_id: str) -> dict[EdgeId, Edge]: ...

    async def node_ids(self, investigation_id: str) -> set[NodeId]:
        """Ids only, not the full node payload — the cheap check `expand`
        and `seed` need to tell a genuinely new node from one already in
        the working set, without paying for every stored property on
        every call."""
        ...

    async def edge_ids(self, investigation_id: str) -> set[EdgeId]: ...
    async def add_nodes(self, investigation_id: str, nodes: Sequence[Node]) -> None: ...
    async def add_edges(self, investigation_id: str, edges: Sequence[Edge]) -> None: ...
    async def remove_nodes(self, investigation_id: str, node_ids: Sequence[NodeId]) -> None: ...

    async def remove_edges(self, investigation_id: str, edge_ids: Sequence[EdgeId]) -> None:
        """`remove_nodes` alone lets an edge outlive the node it once
        needed — harmless for ordinary `DELETE /nodes` (`_project`'s
        endpoint check already excludes an edge whose endpoint is gone
        from every *projected* read), but `WorkingSetService.restore`
        needs the store's edge set to exactly match a target step's, not
        merely a superset of it: an edge added *after* a step was
        recorded, between two nodes both still present at that step,
        would otherwise survive a restore to it. This is that direct
        removal path."""
        ...

    async def node_count(self, investigation_id: str) -> int: ...
    async def edge_count(self, investigation_id: str) -> int: ...
    async def next_seq(self, investigation_id: str) -> int: ...
    async def current_seq(self, investigation_id: str) -> int: ...
    async def append_delta(self, investigation_id: str, delta: WorkingSetDelta) -> None: ...

    async def deltas_after(
        self, investigation_id: str, since_seq: int
    ) -> list[WorkingSetDelta] | None:
        """`None` means `since_seq` has fallen off the capped stream (or
        nothing has ever been recorded for this investigation) — the
        caller's signal to resnapshot rather than patch
        (`03_CONDUIT_MIDDLEWARE.md` §3.2)."""
        ...

    async def clear(self, investigation_id: str) -> None:
        """Test/branch support — drops every key for `investigation_id`.
        Never called from the ordinary read/expand path."""
        ...

    async def get_threshold(self, investigation_id: str) -> float | None:
        """`None` means no `PUT /v1/resolution/threshold` has ever run for this investigation —
        the caller's signal to use `services/resolve/projection.py`'s `DEFAULT_THRESHOLD`
        (Balanced, 0.95) rather than a stored value (`01_DOMAIN_MODEL.md` §4's three detents)."""
        ...

    async def set_threshold(self, investigation_id: str, tau: float) -> None: ...


def _node_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:nodes"


def _edge_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:edges"


def _seq_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:seq"


def _deltas_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:deltas"


def _threshold_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:threshold"


class ValkeyWorkingSetStore:
    """`docs/03_CONDUIT_MIDDLEWARE.md` §4/§7 — the `ws:{investigation_id}`
    layer. Nodes and edges live in a hash, msgpack-encoded per
    `Node`/`Edge`'s own JSON-mode shape (`model_dump(mode="json")`,
    `model_validate`) — binary, but still the exact model, not a bespoke
    wire format to keep in sync by hand. The delta stream is a genuine
    Valkey Stream, `XADD`ed with an *explicit* ID of `f"{seq}-0"` rather
    than an autogenerated timestamp-based one: `seq` is already the
    protocol's own monotonic sequence number
    (`03_CONDUIT_MIDDLEWARE.md` §3.2), and reusing it as the stream ID is
    what makes `XRANGE (since_seq-0 +` — everything strictly after what
    the client last acknowledged — a single, cheap lookup instead of a
    scan-and-filter."""

    def __init__(self, client: Valkey) -> None:
        self._client = client

    async def _touch_ttl(self, investigation_id: str) -> None:
        pipe = self._client.pipeline()
        for key in (
            _node_key(investigation_id),
            _edge_key(investigation_id),
            _seq_key(investigation_id),
            _deltas_key(investigation_id),
            _threshold_key(investigation_id),
        ):
            pipe.expire(key, IDLE_TTL_SECONDS)
        await _reply(pipe.execute())

    async def source_fidelity_nodes(self, investigation_id: str) -> dict[NodeId, Node]:
        raw = await _reply(self._client.hgetall(_node_key(investigation_id)))
        return {
            node_id.decode(): Node.model_validate(msgpack.unpackb(blob, raw=False))
            for node_id, blob in raw.items()
        }

    async def source_fidelity_edges(self, investigation_id: str) -> dict[EdgeId, Edge]:
        raw = await _reply(self._client.hgetall(_edge_key(investigation_id)))
        return {
            edge_id.decode(): Edge.model_validate(msgpack.unpackb(blob, raw=False))
            for edge_id, blob in raw.items()
        }

    async def node_ids(self, investigation_id: str) -> set[NodeId]:
        raw = await _reply(self._client.hkeys(_node_key(investigation_id)))
        return {key.decode() for key in raw}

    async def edge_ids(self, investigation_id: str) -> set[EdgeId]:
        raw = await _reply(self._client.hkeys(_edge_key(investigation_id)))
        return {key.decode() for key in raw}

    async def add_nodes(self, investigation_id: str, nodes: Sequence[Node]) -> None:
        if not nodes:
            return
        mapping = {
            node.id: msgpack.packb(node.model_dump(mode="json"), use_bin_type=True)
            for node in nodes
        }
        await _reply(self._client.hset(_node_key(investigation_id), mapping=mapping))
        await self._touch_ttl(investigation_id)

    async def add_edges(self, investigation_id: str, edges: Sequence[Edge]) -> None:
        if not edges:
            return
        mapping = {
            edge.id: msgpack.packb(edge.model_dump(mode="json"), use_bin_type=True)
            for edge in edges
        }
        await _reply(self._client.hset(_edge_key(investigation_id), mapping=mapping))
        await self._touch_ttl(investigation_id)

    async def remove_nodes(self, investigation_id: str, node_ids: Sequence[NodeId]) -> None:
        if not node_ids:
            return
        await _reply(self._client.hdel(_node_key(investigation_id), *node_ids))
        await self._touch_ttl(investigation_id)

    async def remove_edges(self, investigation_id: str, edge_ids: Sequence[EdgeId]) -> None:
        if not edge_ids:
            return
        await _reply(self._client.hdel(_edge_key(investigation_id), *edge_ids))
        await self._touch_ttl(investigation_id)

    async def node_count(self, investigation_id: str) -> int:
        return int(await _reply(self._client.hlen(_node_key(investigation_id))))

    async def edge_count(self, investigation_id: str) -> int:
        return int(await _reply(self._client.hlen(_edge_key(investigation_id))))

    async def next_seq(self, investigation_id: str) -> int:
        seq = int(await _reply(self._client.incr(_seq_key(investigation_id))))
        await self._touch_ttl(investigation_id)
        return seq

    async def current_seq(self, investigation_id: str) -> int:
        value = await _reply(self._client.get(_seq_key(investigation_id)))
        return int(value) if value is not None else 0

    async def append_delta(self, investigation_id: str, delta: WorkingSetDelta) -> None:
        stream_id = f"{delta.seq}-0"
        await _reply(
            self._client.xadd(
                _deltas_key(investigation_id),
                {"json": delta.model_dump_json()},
                id=stream_id,
                maxlen=DELTA_STREAM_MAXLEN,
                approximate=True,
            )
        )
        await self._touch_ttl(investigation_id)

    async def deltas_after(
        self, investigation_id: str, since_seq: int
    ) -> list[WorkingSetDelta] | None:
        current = await self.current_seq(investigation_id)
        if since_seq >= current:
            return []
        entries = await _reply(
            self._client.xrange(_deltas_key(investigation_id), min=f"({since_seq}-0", max="+")
        )
        if not entries:
            return None  # everything since `since_seq` has been trimmed
        oldest_seq = int(entries[0][0].decode().split("-", 1)[0])
        if oldest_seq != since_seq + 1:
            return None  # a gap: something between since_seq+1 and oldest_seq-1 was trimmed
        deltas: list[WorkingSetDelta] = []
        for _stream_id, fields in entries:
            payload = fields[b"json"].decode()
            deltas.append(decode_delta(json.loads(payload)))
        return deltas

    async def clear(self, investigation_id: str) -> None:
        await _reply(
            self._client.delete(
                _node_key(investigation_id),
                _edge_key(investigation_id),
                _seq_key(investigation_id),
                _deltas_key(investigation_id),
                _threshold_key(investigation_id),
            )
        )

    async def get_threshold(self, investigation_id: str) -> float | None:
        value = await _reply(self._client.get(_threshold_key(investigation_id)))
        return float(value) if value is not None else None

    async def set_threshold(self, investigation_id: str, tau: float) -> None:
        await _reply(self._client.set(_threshold_key(investigation_id), str(tau)))
        await self._touch_ttl(investigation_id)
