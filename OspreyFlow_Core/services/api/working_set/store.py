"""Working-set storage — `spec/03_CONDUIT_MIDDLEWARE.md` §4: "One Valkey
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
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

import msgpack
from valkey.asyncio import Valkey
from valkey.exceptions import ResponseError, WatchError

from conduit_common.valkey_compat import reply as _reply
from schemas.domain import Edge, EdgeId, Node, NodeId

from .access_index import (
    ABSENT,
    AccessCounts,
    AccessEntries,
    CountedIndex,
    adjacency_member,
    adjacency_prefix,
    build_counted_index,
    decode_edge_entry,
    decode_signature,
    encode_edge_entry,
    encode_signature,
    signature_id,
    signature_of,
    split_adjacency_member,
    split_triple_key,
    triple_key,
)
from .access_scripts import ADD_EDGES, ADD_NODES, REMOVE_EDGES, REMOVE_NODES
from .models import WorkingSetDelta, decode_delta, lacks_record

_log = logging.getLogger(__name__)

#: How many times a rebuild of the access index starts over when a write lands while it is reading
#: (`ValkeyWorkingSetStore._rebuild_access_index`).
_REBUILD_ATTEMPTS = 5

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

    async def access_counts(self, investigation_id: str) -> AccessCounts:
        """What a reader's figures are computed from, without reading a body or an element (ADR-124
        Amendment 4): the signatures by key, how many nodes carry each, and how many links carry
        each (link, source end, target end) triple, with the epoch and versions they were read at.
        Kept by every method that writes bodies, in the same transaction, so it equals what the
        bodies say; `build_counted_index` is the oracle. Small whatever the case holds, and never
        sent anywhere: it is the service's own input."""
        ...

    async def access_entries(
        self, investigation_id: str, node_ids: Sequence[NodeId], edge_ids: Sequence[EdgeId]
    ) -> AccessEntries:
        """The entries of the named ids only: each stored node's signature key, each stored link's
        (signature key, source, target), and the signature key of those links' stored ends. What the
        membership of a request's ids is judged by, and what says which of them are stored. The
        result carries the epoch the entries were read at: a request compares it with the epoch of
        the counts it judges them by, since a rebuild that renumbers the signatures replaces it."""
        ...

    async def adjacent_edge_ids(
        self, investigation_id: str, node_ids: Sequence[NodeId]
    ) -> dict[NodeId, list[EdgeId]]:
        """The stored links at each of these nodes, whether or not the node is stored: what a node
        that is about to arrive would complete."""
        ...

    async def stored_node_signatures(self, investigation_id: str) -> dict[NodeId, str]:
        """Every stored node's signature key. For a case whose reader's view is known to be small
        and whose nodes must be named (`expand`'s links among); not for a count."""
        ...

    async def node_ids(self, investigation_id: str) -> set[NodeId]:
        """Ids only, not the full node payload — the cheap check `expand`
        and `seed` need to tell a genuinely new node from one already in
        the working set, without paying for every stored property on
        every call."""
        ...

    async def edge_ids(self, investigation_id: str) -> set[EdgeId]: ...

    async def get_edge(self, investigation_id: str, edge_id: EdgeId) -> Edge | None:
        """One link by id, source fidelity, or `None` when this investigation's working set does
        not hold it. A single hash lookup — link notes ask this on every read and write, and
        loading the whole edge set to answer it would grow with the case."""
        ...

    async def get_node(self, investigation_id: str, node_id: NodeId) -> Node | None:
        """One node by id, source fidelity, or `None` — the other half of `get_edge`'s question
        (does each end of the link stand in the working set?)."""
        ...

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
        (`03_CONDUIT_MIDDLEWARE.md` §3.2). It is also `None` when any delta after `since_seq` is a
        removal or a replacement stored without the record of what it removed (`lacks_record`,
        written before ADR-124 decision 4): none can be projected for a reader, so the reader is
        sent a full snapshot."""
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


def _access_nodes_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:access_nodes"


def _access_edges_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:access_edges"


def _access_signatures_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:access_signatures"


def _meta_key(investigation_id: str) -> str:
    """The scalars of the access index as fields of one hash (`sig_counter`, `sigs_version`,
    `version`, `epoch`, `self_links`), so that they are lost together and a reader's check sees
    it."""
    return f"ws:{investigation_id}:access_meta"


def _sig_numbers_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:sig_numbers"


def _node_counts_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:node_counts"


def _edge_counts_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:edge_counts"


def _adjacency_key(investigation_id: str) -> str:
    return f"ws:{investigation_id}:adjacency"


def _script_keys(investigation_id: str) -> list[str]:
    """The thirteen keys every script takes, in the order `access_scripts.py` documents."""
    return [
        _node_key(investigation_id),
        _edge_key(investigation_id),
        _access_nodes_key(investigation_id),
        _access_edges_key(investigation_id),
        _access_signatures_key(investigation_id),
        _sig_numbers_key(investigation_id),
        _meta_key(investigation_id),
        _node_counts_key(investigation_id),
        _edge_counts_key(investigation_id),
        _adjacency_key(investigation_id),
        _seq_key(investigation_id),
        _deltas_key(investigation_id),
        _threshold_key(investigation_id),
    ]


def _derived_keys(investigation_id: str) -> list[str]:
    """What the index derives from the bodies: a rebuild replaces these and keeps the signature
    tables and the scalars (it only appends to them)."""
    return [
        _access_nodes_key(investigation_id),
        _access_edges_key(investigation_id),
        _node_counts_key(investigation_id),
        _edge_counts_key(investigation_id),
        _adjacency_key(investigation_id),
    ]


def _index_keys(investigation_id: str) -> list[str]:
    """Every key of the access index, for `clear` and the TTL."""
    return [
        *_derived_keys(investigation_id),
        _access_signatures_key(investigation_id),
        _sig_numbers_key(investigation_id),
        _meta_key(investigation_id),
    ]


#: The most elements one script takes. A branch or a restore writes tens of thousands; each chunk is
#: its own script and leaves the bodies and the index consistent, so none holds Valkey for the
#: length of the whole.
_SCRIPT_CHUNK = 1_000


def _epoch_text(raw: bytes | None) -> str:
    return raw.decode() if raw else ""


def _chunks(items: Sequence[Any]) -> list[Sequence[Any]]:
    return [items[i : i + _SCRIPT_CHUNK] for i in range(0, len(items), _SCRIPT_CHUNK)]


class ValkeyWorkingSetStore:
    """`spec/03_CONDUIT_MIDDLEWARE.md` §4/§7 — the `ws:{investigation_id}`
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
        #: How many times the access index was found not to cover its bodies and was rebuilt: a
        #: case written before the index existed, or an index that lost something. Never expected
        #: to move on a deployment that has run for a day; each is also logged.
        self.access_index_rebuilds = 0
        #: Called between the rebuild's read of the bodies and its write, with the case id. Only a
        #: test sets it, to land a write in that gap.
        self._between_rebuild_read_and_write: Callable[[str], Awaitable[None]] | None = None
        #: Called after each write script, with its name and how many elements it took. Only a
        #: test sets it, to look at the store between chunks.
        self._after_script: Callable[[str, int], Awaitable[None]] | None = None
        #: Every write script run: (name, elements, seconds). What the benchmark reads the longest
        #: single script from, and what a test reads the chunk sizes from.
        self.script_runs: list[tuple[str, int, float]] = []
        self._scripts: dict[str, Any] = {}

    async def _run_once(
        self, name: str, source: str, investigation_id: str, args: list[Any], elements: int
    ) -> None:
        script = self._scripts.get(name)
        if script is None:
            script = self._scripts[name] = self._client.register_script(source)
        started = time.monotonic()
        await _reply(
            script(
                keys=_script_keys(investigation_id),
                args=[IDLE_TTL_SECONDS, uuid.uuid4().hex, *args],
            )
        )
        self.script_runs.append((name, elements, time.monotonic() - started))
        if self._after_script is not None:
            await self._after_script(name, elements)

    async def _run(
        self, name: str, source: str, investigation_id: str, args: list[Any], elements: int
    ) -> None:
        """One write script (`access_scripts.py`): the bodies, the counts, the entries and the
        adjacency in one atomic step, the version counted up, every key's TTL refreshed, so that
        nothing follows it. A script that finds the index damaged stops and says so: the index is
        rebuilt from the bodies, and the chunk runs again (once: a second refusal is raised)."""
        try:
            await self._run_once(name, source, investigation_id, args, elements)
        except ResponseError as error:
            if "access index damaged" not in str(error):
                raise
            _log.warning(
                "a write to %s found the access index damaged (%s)", investigation_id, error
            )
            await self._rebuild_access_index(investigation_id)
            await self._run_once(name, source, investigation_id, args, elements)

    async def _touch_ttl(self, investigation_id: str) -> None:
        pipe = self._client.pipeline()
        for key in (
            _node_key(investigation_id),
            _edge_key(investigation_id),
            _seq_key(investigation_id),
            _deltas_key(investigation_id),
            _threshold_key(investigation_id),
            *_index_keys(investigation_id),
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

    async def access_counts(self, investigation_id: str) -> AccessCounts:
        """The counts as stored, read in one transaction with what they should cover. Every way the
        index can lose something is noticed here by a check that reads no element, and the index is
        then rebuilt from the bodies (`_rebuild_access_index`), once, logged and counted:

        - the entries and the counts of nodes (and of links) add up to the bodies;
        - every signature a count names has a definition, and the definitions, the numbers and
          the counters agree (`sig_counter == sigs_version == HLEN(sig_defs) == HLEN(sig_numbers)`);
        - the adjacency holds two members for every link and one for a link at a single node
          (`ZCARD == 2 * links - self_links`);
        - a case that holds anything has an epoch.

        A case written before the index existed (a deployment upgraded under a live case, its
        24-hour keys not yet expired) has bodies and no counts, so the first check fails. What keeps
        the counts equal to the bodies is that every write is one script with its entries
        (`access_scripts.py`); `build_counted_index` is what the consistency tests hold them to.
        None of this is a defence against eviction: that is the deployment's `noeviction`."""
        pipe = self._client.pipeline(transaction=True)
        pipe.hlen(_node_key(investigation_id))
        pipe.hlen(_edge_key(investigation_id))
        pipe.hlen(_access_nodes_key(investigation_id))
        pipe.hlen(_access_edges_key(investigation_id))
        pipe.hgetall(_access_signatures_key(investigation_id))
        pipe.hlen(_sig_numbers_key(investigation_id))
        pipe.hgetall(_node_counts_key(investigation_id))
        pipe.hgetall(_edge_counts_key(investigation_id))
        pipe.hgetall(_meta_key(investigation_id))
        pipe.zcard(_adjacency_key(investigation_id))
        (
            node_bodies,
            edge_bodies,
            node_entries,
            edge_entries,
            raw_signatures,
            number_count,
            raw_node_counts,
            raw_edge_counts,
            raw_meta,
            adjacency_size,
        ) = await _reply(pipe.execute())
        signatures = {k.decode(): decode_signature(v) for k, v in raw_signatures.items()}
        node_counts = {k.decode(): int(v) for k, v in raw_node_counts.items()}
        edge_counts = {split_triple_key(k.decode()): int(v) for k, v in raw_edge_counts.items()}
        meta = {k.decode(): v.decode() for k, v in raw_meta.items()}
        counter = int(meta.get("sig_counter", 0))
        named = set(node_counts) | {
            key for triple in edge_counts for key in triple if key != ABSENT
        }
        holds_something = node_bodies + edge_bodies + len(signatures) > 0
        if (
            not node_bodies == node_entries == sum(node_counts.values())
            or not edge_bodies == edge_entries == sum(edge_counts.values())
            or not named <= set(signatures)
            or not len(signatures) == number_count == counter == int(meta.get("sigs_version", 0))
            or adjacency_size != 2 * edge_entries - int(meta.get("self_links", 0))
            or (holds_something and not meta.get("epoch"))
        ):
            return await self._rebuild_access_index(investigation_id)
        return AccessCounts(
            epoch=meta.get("epoch", ""),
            version=int(meta.get("version", 0)),
            sigs_version=int(meta.get("sigs_version", 0)),
            signatures=signatures,
            node_counts=node_counts,
            edge_counts=edge_counts,
        )

    async def _rebuild_access_index(self, investigation_id: str) -> AccessCounts:
        """The index from the bodies, written in place of whatever was there, and safe against a
        write landing meanwhile: the body hashes, the signature tables and the scalars are
        `WATCH`ed, so a write between the read and the write of the index makes the transaction
        fail and the rebuild start over (`_REBUILD_ATTEMPTS` times, then it raises: an index
        nothing can settle is not served).

        **Signature numbers are never changed.** A reader may hold a number (a readable set kept for
        it, a script running alongside), and another signature given it would be judged as the
        first. When the tables are whole (the definitions, the numbers and the counters agree) the
        rebuild keeps every number and only appends the signatures the bodies have and the tables
        lack, and keeps the epoch. When they are not, nothing that was kept about their numbers
        can be trusted: they are numbered afresh and the epoch is replaced, which is a new key for
        everything keyed by it."""
        keys = (
            _node_key(investigation_id),
            _edge_key(investigation_id),
            _access_signatures_key(investigation_id),
            _sig_numbers_key(investigation_id),
            _meta_key(investigation_id),
        )
        for attempt in range(_REBUILD_ATTEMPTS):
            async with self._client.pipeline(transaction=True) as pipe:
                try:
                    await _reply(pipe.watch(*keys))
                    raw_nodes = await _reply(pipe.hgetall(keys[0]))
                    raw_edges = await _reply(pipe.hgetall(keys[1]))
                    defs = await _reply(pipe.hgetall(keys[2]))
                    kept = {
                        k.decode(): v.decode()
                        for k, v in (await _reply(pipe.hgetall(keys[3]))).items()
                    }
                    meta = {
                        k.decode(): v.decode()
                        for k, v in (await _reply(pipe.hgetall(keys[4]))).items()
                    }
                    index = build_counted_index(
                        {
                            nid.decode(): Node.model_validate(msgpack.unpackb(blob, raw=False))
                            for nid, blob in raw_nodes.items()
                        },
                        {
                            eid.decode(): Edge.model_validate(msgpack.unpackb(blob, raw=False))
                            for eid, blob in raw_edges.items()
                        },
                    )
                    if self._between_rebuild_read_and_write is not None:
                        await self._between_rebuild_read_and_write(investigation_id)
                    counter = int(meta.get("sig_counter", 0))
                    whole = (
                        len(defs) == len(kept) == counter == int(meta.get("sigs_version", 0))
                        and sorted(kept.values(), key=int)
                        == [str(n) for n in range(1, counter + 1)]
                        and {k.decode() for k in defs} == set(kept.values())
                    )
                    numbers = dict(kept) if whole else {}
                    appended = 0
                    for sid in sorted(index.signatures):
                        if sid not in numbers:
                            counter = len(numbers) + 1 if not whole else counter + 1
                            numbers[sid] = str(counter)
                            appended += 1
                    pipe.multi()  # type: ignore[no-untyped-call]
                    pipe.delete(*_derived_keys(investigation_id))
                    if not whole:
                        pipe.delete(*keys[2:5])
                    if numbers:
                        pipe.hset(_sig_numbers_key(investigation_id), mapping=numbers)
                        pipe.hset(
                            _access_signatures_key(investigation_id),
                            mapping={
                                numbers[sid]: encode_signature(sig)
                                for sid, sig in index.signatures.items()
                            },
                        )
                    meta_key = _meta_key(investigation_id)
                    if whole:
                        pipe.hset(meta_key, "sig_counter", str(counter))
                        pipe.hincrby(meta_key, "sigs_version", appended)
                        pipe.hsetnx(meta_key, "epoch", uuid.uuid4().hex)
                    else:
                        pipe.hset(
                            meta_key,
                            mapping={
                                "sig_counter": counter,
                                "sigs_version": counter,
                                "epoch": uuid.uuid4().hex,
                            },
                        )
                    pipe.hset(meta_key, "self_links", str(index.self_links))
                    pipe.hincrby(meta_key, "version", 1)
                    if index.nodes:
                        pipe.hset(
                            _access_nodes_key(investigation_id),
                            mapping={nid: numbers[sid] for nid, sid in index.nodes.items()},
                        )
                    if index.edges:
                        pipe.hset(
                            _access_edges_key(investigation_id),
                            mapping={
                                eid: encode_edge_entry(numbers[sid], source, target)
                                for eid, (sid, source, target) in index.edges.items()
                            },
                        )
                    if index.node_counts:
                        pipe.hset(
                            _node_counts_key(investigation_id),
                            mapping={numbers[sid]: n for sid, n in index.node_counts.items()},
                        )
                    if index.edge_counts:
                        pipe.hset(
                            _edge_counts_key(investigation_id),
                            mapping={
                                triple_key(
                                    numbers[e],
                                    numbers.get(a, ABSENT),
                                    numbers.get(b, ABSENT),
                                ): n
                                for (e, a, b), n in index.edge_counts.items()
                            },
                        )
                    if index.adjacency:
                        pipe.zadd(
                            _adjacency_key(investigation_id),
                            {adjacency_member(n, e): 0 for n, e in index.adjacency},
                        )
                    await _reply(pipe.execute())
                except WatchError:
                    _log.info(
                        "access index rebuild for %s interrupted by a write (attempt %d)",
                        investigation_id,
                        attempt + 1,
                    )
                    continue
            self.access_index_rebuilds += 1
            _log.warning(
                "the access index of %s did not cover its bodies and was rebuilt "
                "(%d nodes, %d links; rebuild number %d in this process)",
                investigation_id,
                len(index.nodes),
                len(index.edges),
                self.access_index_rebuilds,
            )
            await self._touch_ttl(investigation_id)
            return await self.access_counts(investigation_id)
        raise RuntimeError(
            f"the access index of {investigation_id} could not be rebuilt: writes kept landing"
        )

    async def access_entries(
        self, investigation_id: str, node_ids: Sequence[NodeId], edge_ids: Sequence[EdgeId]
    ) -> AccessEntries:
        """The entries of the named ids, with the epoch they were read at. The epoch is read in the
        same transaction as the entries (and again with the ends of the links, which are a second
        read), so that a caller can tell that a rebuild which renumbered the signatures landed
        between its read of the counts and this one: a number in these entries then names
        another signature than the table it holds does. Epochs that differ between the two reads
        are returned as one that matches nothing."""
        meta = _meta_key(investigation_id)
        pipe = self._client.pipeline(transaction=True)
        pipe.hget(meta, "epoch")
        if node_ids:
            pipe.hmget(_access_nodes_key(investigation_id), list(node_ids))
        if edge_ids:
            pipe.hmget(_access_edges_key(investigation_id), list(edge_ids))
        read = await _reply(pipe.execute())
        epoch = _epoch_text(read[0])
        found = iter(read[1:])
        nodes: dict[NodeId, str] = {}
        edges: dict[EdgeId, tuple[str, NodeId, NodeId]] = {}
        if node_ids:
            nodes = {
                i: v.decode() for i, v in zip(node_ids, next(found), strict=True) if v is not None
            }
        if edge_ids:
            edges = {
                i: decode_edge_entry(v)
                for i, v in zip(edge_ids, next(found), strict=True)
                if v is not None
            }
        wanted = sorted({n for _, source, target in edges.values() for n in (source, target)})
        ends = dict(nodes)
        missing = [n for n in wanted if n not in ends]
        if missing:
            again = self._client.pipeline(transaction=True)
            again.hget(meta, "epoch")
            again.hmget(_access_nodes_key(investigation_id), missing)
            second_epoch, found_ends = await _reply(again.execute())
            if _epoch_text(second_epoch) != epoch:
                epoch = f"{epoch}->{_epoch_text(second_epoch)}"
            ends.update(
                {i: v.decode() for i, v in zip(missing, found_ends, strict=True) if v is not None}
            )
        return AccessEntries(nodes, edges, {n: ends[n] for n in wanted if n in ends}, epoch)

    async def adjacent_edge_ids(
        self, investigation_id: str, node_ids: Sequence[NodeId]
    ) -> dict[NodeId, list[EdgeId]]:
        """The stored links at each of these nodes, whether or not the node is stored (the
        adjacency is kept for both): one range per node, sent together."""
        if not node_ids:
            return {}
        pipe = self._client.pipeline(transaction=False)
        for node_id in node_ids:
            prefix = adjacency_prefix(node_id)
            pipe.zrangebylex(
                _adjacency_key(investigation_id), b"[" + prefix, b"[" + prefix + b"\xff"
            )
        found = await _reply(pipe.execute())
        return {
            node_id: [member[len(adjacency_prefix(node_id)) :].decode() for member in members]
            for node_id, members in zip(node_ids, found, strict=True)
        }

    async def stored_node_signatures(self, investigation_id: str) -> dict[NodeId, str]:
        raw = await _reply(self._client.hgetall(_access_nodes_key(investigation_id)))
        return {k.decode(): v.decode() for k, v in raw.items()}

    async def read_counted_index(self, investigation_id: str) -> CountedIndex:
        """Everything the index holds as the keys hold it, read directly and keyed by full
        signature id: for the consistency tests, which compare it with `build_counted_index`.
        Reads whatever is stored, without rebuilding."""
        client = self._client
        nodes = await _reply(client.hgetall(_access_nodes_key(investigation_id)))
        edges = await _reply(client.hgetall(_access_edges_key(investigation_id)))
        defs = await _reply(client.hgetall(_access_signatures_key(investigation_id)))
        node_counts = await _reply(client.hgetall(_node_counts_key(investigation_id)))
        edge_counts = await _reply(client.hgetall(_edge_counts_key(investigation_id)))
        members = await _reply(client.zrange(_adjacency_key(investigation_id), 0, -1))
        meta = await _reply(client.hgetall(_meta_key(investigation_id)))
        signatures = {k.decode(): decode_signature(v) for k, v in defs.items()}
        ids = {key: signature_id(sig) for key, sig in signatures.items()}

        def sid(key: str) -> str:
            return ABSENT if key == ABSENT else ids[key]

        index = CountedIndex(signatures={ids[k]: sig for k, sig in signatures.items()})
        index.nodes = {k.decode(): sid(v.decode()) for k, v in nodes.items()}
        for k, v in edges.items():
            key, source, target = decode_edge_entry(v)
            index.edges[k.decode()] = (sid(key), source, target)
        index.node_counts = {sid(k.decode()): int(v) for k, v in node_counts.items()}
        for k, v in edge_counts.items():
            e, a, b = split_triple_key(k.decode())
            index.edge_counts[(sid(e), sid(a), sid(b))] = int(v)
        for member in members:
            index.adjacency.add(split_adjacency_member(member))
        index.self_links = int(meta.get(b"self_links", 0))
        return index

    async def node_ids(self, investigation_id: str) -> set[NodeId]:
        raw = await _reply(self._client.hkeys(_node_key(investigation_id)))
        return {key.decode() for key in raw}

    async def edge_ids(self, investigation_id: str) -> set[EdgeId]:
        raw = await _reply(self._client.hkeys(_edge_key(investigation_id)))
        return {key.decode() for key in raw}

    async def get_edge(self, investigation_id: str, edge_id: EdgeId) -> Edge | None:
        blob = await _reply(self._client.hget(_edge_key(investigation_id), edge_id))
        if blob is None:
            return None
        return Edge.model_validate(msgpack.unpackb(blob, raw=False))

    async def get_node(self, investigation_id: str, node_id: NodeId) -> Node | None:
        blob = await _reply(self._client.hget(_node_key(investigation_id), node_id))
        if blob is None:
            return None
        return Node.model_validate(msgpack.unpackb(blob, raw=False))

    async def add_nodes(self, investigation_id: str, nodes: Sequence[Node]) -> None:
        for chunk in _chunks(nodes):
            args: list[Any] = []
            for node in chunk:
                signature = signature_of(node.handling, node.datasets)
                args += [
                    node.id,
                    msgpack.packb(node.model_dump(mode="json"), use_bin_type=True),
                    signature_id(signature),
                    encode_signature(signature),
                ]
            await self._run("add_nodes", ADD_NODES, investigation_id, args, len(chunk))

    async def add_edges(self, investigation_id: str, edges: Sequence[Edge]) -> None:
        for chunk in _chunks(edges):
            args: list[Any] = []
            for edge in chunk:
                signature = signature_of(edge.handling, edge.datasets)
                args += [
                    edge.id,
                    msgpack.packb(edge.model_dump(mode="json"), use_bin_type=True),
                    signature_id(signature),
                    encode_signature(signature),
                    edge.source,
                    edge.target,
                ]
            await self._run("add_edges", ADD_EDGES, investigation_id, args, len(chunk))

    async def remove_nodes(self, investigation_id: str, node_ids: Sequence[NodeId]) -> None:
        for chunk in _chunks(node_ids):
            await self._run("remove_nodes", REMOVE_NODES, investigation_id, list(chunk), len(chunk))

    async def remove_edges(self, investigation_id: str, edge_ids: Sequence[EdgeId]) -> None:
        for chunk in _chunks(edge_ids):
            await self._run("remove_edges", REMOVE_EDGES, investigation_id, list(chunk), len(chunk))

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
        if any(lacks_record(d) for d in deltas):
            return None  # a removal stored before it carried its record: a full snapshot instead
        return deltas

    async def clear(self, investigation_id: str) -> None:
        await _reply(
            self._client.delete(
                _node_key(investigation_id),
                _edge_key(investigation_id),
                _seq_key(investigation_id),
                _deltas_key(investigation_id),
                _threshold_key(investigation_id),
                *_index_keys(investigation_id),
            )
        )

    async def get_threshold(self, investigation_id: str) -> float | None:
        value = await _reply(self._client.get(_threshold_key(investigation_id)))
        return float(value) if value is not None else None

    async def set_threshold(self, investigation_id: str, tau: float) -> None:
        await _reply(self._client.set(_threshold_key(investigation_id), str(tau)))
        await self._touch_ttl(investigation_id)
