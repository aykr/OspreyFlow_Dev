"""The working set's access index — what the caps and previews need of the stored set, as counts.

ADR-124 decision 2 counts the caps and the previews over the reader's projected view of the stored
set. Computing that from the bodies read and validated every one of them (3.2 s of a 3.4 s preview
at 50,000 nodes and 100,000 links); computing it from a full per-element index still loaded every
element on every change (1.1 s at 50,000 nodes and 250,000 links). Nothing the caps need is the
whole set. Every use is a **count** (the reader's visible nodes and links) or the **membership of a
few named ids** (what a request would add). The store keeps both, beside the bodies, maintained in
the transaction of each write.

**Signatures.** What `ontology.handling.principal_may_read` is given for one element: its
classification, handling code, owning unit, originator and datasets. A case has few distinct ones,
however many elements share them, so each is stored once under a short per-case number (its *key*)
and everything else refers to the number. Which signatures a reader may read is judged over this
small table alone.

**What is kept.**

- `node_counts`: signature key -> the number of stored nodes with it;
- `edge_counts`: (link's signature, source end's signature, target end's signature) -> the number of
  stored links, where an end's signature is `ABSENT` when that node is not stored. A link is in a
  reader's view exactly when all three are readable, and `ABSENT` never is: this is `_project`'s
  rule that a link counts only when it and both its ends are readable;
- per element, its signature (a link's with its two ends), for the membership of a few ids;
- an adjacency of node -> its stored links, kept whether or not the node is stored, which is what
  lets a node's arrival, removal or change of signature move the triples of the links at it.

**Not a second source of truth.** It is derived from the bodies on every write, and
`build_counted_index` is the oracle the consistency and equivalence tests hold every store to. It
never reaches the wire: nothing here is a model a route or a delta carries.

**Its epoch and version.** A store keeps an `epoch` (one token for the life of a case's keys, new
after a `clear` or an expiry), a `version` (counted up in the transaction of every write) and a
`sigs_version` (counted up when a signature is first stored). Signature keys restart after a
`clear`, so what is kept about a case's signatures is good for one `(epoch, sigs_version)` only.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from schemas.domain import Edge, EdgeId, Handling, Node, NodeId

#: The signature of an end that is not stored. Never a signature key (those are numbers), never
#: readable.
ABSENT = "absent"


@dataclass(frozen=True)
class AccessSignature:
    """The access fields of one element: what `principal_may_read` is given."""

    classification: str
    handling_code: str
    owning_unit: str
    originator: str
    datasets: tuple[str, ...]

    def handling(self) -> Handling:
        return Handling(
            classification=self.classification,
            handling_code=self.handling_code,
            owning_unit=self.owning_unit,
            originator=self.originator,
        )


def signature_of(handling: Handling, datasets: list[str]) -> AccessSignature:
    return AccessSignature(
        classification=handling.classification,
        handling_code=handling.handling_code,
        owning_unit=handling.owning_unit,
        originator=handling.originator,
        datasets=tuple(sorted(set(datasets))),
    )


def signature_id(signature: AccessSignature) -> str:
    """A stable id for a signature, the same in every process and every run: the full SHA-256
    digest in hex, so that two signatures never share one. The store maps it to the short per-case
    key everything else refers to."""
    return hashlib.sha256(encode_signature(signature)).hexdigest()


def encode_signature(signature: AccessSignature) -> bytes:
    return json.dumps(
        [
            signature.classification,
            signature.handling_code,
            signature.owning_unit,
            signature.originator,
            list(signature.datasets),
        ]
    ).encode()


def decode_signature(blob: bytes) -> AccessSignature:
    classification, handling_code, owning_unit, originator, datasets = json.loads(blob)
    return AccessSignature(classification, handling_code, owning_unit, originator, tuple(datasets))


def _led(part: str) -> bytes:
    """A part of a key led by its length *in bytes* (the scripts count bytes, `#`), so that a
    non-ASCII id is the length the script reads."""
    raw = part.encode()
    return str(len(raw)).encode() + b":" + raw


def _unled(blob: bytes) -> tuple[str, bytes]:
    colon = blob.index(b":")
    length = int(blob[:colon])
    return blob[colon + 1 : colon + 1 + length].decode(), blob[colon + 1 + length :]


def encode_edge_entry(sig_key: str, source: NodeId, target: NodeId) -> bytes:
    """A link's entry, each of the first two parts led by its length, so that any id can be put in
    it and no character is reserved."""
    return _led(sig_key) + _led(source) + target.encode()


def decode_edge_entry(blob: bytes) -> tuple[str, NodeId, NodeId]:
    sig_key, rest = _unled(blob)
    source, target = _unled(rest)
    return sig_key, source, target.decode()


def adjacency_member(node_id: NodeId, edge_id: EdgeId) -> bytes:
    """One member of the adjacency (a sorted set the store ranges over by prefix): the node's id
    led by its length, then the link's. No other node's members share the prefix."""
    return _led(node_id) + edge_id.encode()


def adjacency_prefix(node_id: NodeId) -> bytes:
    return _led(node_id)


def split_adjacency_member(member: bytes) -> tuple[NodeId, EdgeId]:
    node_id, edge_id = _unled(member)
    return node_id, edge_id.decode()


def triple_key(edge_sig: str, source_sig: str, target_sig: str) -> str:
    """The field a store counts links under."""
    return f"{edge_sig},{source_sig},{target_sig}"


def split_triple_key(key: str) -> tuple[str, str, str]:
    edge_sig, source_sig, target_sig = key.split(",")
    return edge_sig, source_sig, target_sig


@dataclass(frozen=True)
class AccessCounts:
    """What a reader's figures are computed from: the signatures by key and the two counts, with
    the epoch and versions they were read at. Small whatever the case holds."""

    epoch: str
    version: int
    sigs_version: int
    signatures: Mapping[str, AccessSignature]
    node_counts: Mapping[str, int]
    edge_counts: Mapping[tuple[str, str, str], int]


@dataclass(frozen=True)
class AccessEntries:
    """The entries of some named ids, for the membership of what a request would add: each node's
    signature key, each link's (signature key, source, target), and the signature key of the end
    nodes of those links that are stored."""

    nodes: Mapping[NodeId, str]
    edges: Mapping[EdgeId, tuple[str, NodeId, NodeId]]
    ends: Mapping[NodeId, str]
    #: The case's epoch as the entries were read. A signature number means what it meant only
    #: within one epoch (a rebuild that renumbers replaces it), so a request compares this with
    #: the epoch of the signature table it judges them by.
    epoch: str = ""


@dataclass
class CountedIndex:
    """Everything the store keeps, keyed by the full signature id rather than the store's per-case
    keys, so that two stores (or a store and the bodies) can be compared whatever numbers each gave
    the signatures. `build_counted_index` makes it from bodies; `IndexState` and the Valkey store
    each maintain it incrementally."""

    signatures: dict[str, AccessSignature] = field(default_factory=dict)
    nodes: dict[NodeId, str] = field(default_factory=dict)
    edges: dict[EdgeId, tuple[str, NodeId, NodeId]] = field(default_factory=dict)
    node_counts: dict[str, int] = field(default_factory=dict)
    edge_counts: dict[tuple[str, str, str], int] = field(default_factory=dict)
    adjacency: set[tuple[NodeId, EdgeId]] = field(default_factory=set)
    #: How many stored links have the same node at both ends: the adjacency holds one member for
    #: such a link and two for any other, which is what its size is checked against.
    self_links: int = 0


def build_counted_index(nodes: Mapping[NodeId, Node], edges: Mapping[EdgeId, Edge]) -> CountedIndex:
    """The index the bodies say it should be: the oracle, and what a store rebuilds from when the
    index it holds does not cover its bodies (a case written before the index existed)."""
    index = CountedIndex()
    node_counts: Counter[str] = Counter()
    edge_counts: Counter[tuple[str, str, str]] = Counter()
    for node_id, node in nodes.items():
        signature = signature_of(node.handling, node.datasets)
        sid = signature_id(signature)
        index.signatures[sid] = signature
        index.nodes[node_id] = sid
        node_counts[sid] += 1
    for edge_id, edge in edges.items():
        signature = signature_of(edge.handling, edge.datasets)
        sid = signature_id(signature)
        index.signatures[sid] = signature
        index.edges[edge_id] = (sid, edge.source, edge.target)
        index.adjacency.add((edge.source, edge_id))
        index.adjacency.add((edge.target, edge_id))
        index.self_links += edge.source == edge.target
    for sid, source, target in index.edges.values():
        edge_counts[(sid, index.nodes.get(source, ABSENT), index.nodes.get(target, ABSENT))] += 1
    index.node_counts = dict(node_counts)
    index.edge_counts = dict(edge_counts)
    return index


def counted_index_differences(actual: CountedIndex, expected: CountedIndex) -> list[str]:
    """How `actual` differs from `expected`, in words; empty when it does not. A store may keep a
    signature no element holds any more (the table is not pruned), so only the signatures an
    element names are compared."""
    found: list[str] = []
    if actual.nodes != expected.nodes:
        found.append(
            "node entries differ: "
            f"{sorted(set(actual.nodes.items()) ^ set(expected.nodes.items()))[:5]}"
        )
    if actual.edges != expected.edges:
        found.append(
            "link entries differ: "
            f"{sorted(set(actual.edges.items()) ^ set(expected.edges.items()))[:5]}"
        )
    if actual.node_counts != expected.node_counts:
        found.append(f"node counts {actual.node_counts} != {expected.node_counts}")
    if actual.edge_counts != expected.edge_counts:
        found.append(
            "link counts differ: "
            f"{sorted(set(actual.edge_counts.items()) ^ set(expected.edge_counts.items()))[:5]}"
        )
    if actual.adjacency != expected.adjacency:
        found.append(f"adjacency differs: {sorted(actual.adjacency ^ expected.adjacency)[:5]}")
    if actual.self_links != expected.self_links:
        found.append(f"self links {actual.self_links} != {expected.self_links}")
    named = set(expected.nodes.values()) | {sid for sid, _, _ in expected.edges.values()}
    for sid in named:
        if actual.signatures.get(sid) != expected.signatures[sid]:
            found.append(f"signature {sid[:8]} missing or wrong")
    return found


class IndexState:
    """The index kept incrementally in Python, with the semantics of the Valkey store's scripts:
    what the in-memory fake keeps, and the model the scripts are written to. A node's arrival,
    removal or change of signature moves the triples of the links at it; a link's replacement takes
    its old triple out. Keyed by full signature id."""

    def __init__(self) -> None:
        self.index = CountedIndex()
        #: The adjacency as node -> links, beside `index.adjacency` (pairs, which is what the
        #: oracle builds): finding a node's links is a lookup, not a scan.
        self._adjacent: dict[NodeId, set[EdgeId]] = {}
        self.epoch = ""
        self.version = 0
        self.sigs_version = 0

    def _triple(self, edge_id: EdgeId) -> tuple[str, str, str]:
        sid, source, target = self.index.edges[edge_id]
        nodes = self.index.nodes
        return (sid, nodes.get(source, ABSENT), nodes.get(target, ABSENT))

    def _bump(self, counts: dict, key: object, delta: int) -> None:  # type: ignore[type-arg]
        counts[key] = counts.get(key, 0) + delta
        if counts[key] == 0:
            del counts[key]

    def _incident(self, node_id: NodeId) -> list[EdgeId]:
        return list(self._adjacent.get(node_id, ()))

    def _remember(self, sid: str, signature: AccessSignature) -> None:
        if sid not in self.index.signatures:
            self.sigs_version += 1
        self.index.signatures[sid] = signature

    def set_node(self, node_id: NodeId, sid: str, signature: AccessSignature) -> None:
        self._remember(sid, signature)
        old = self.index.nodes.get(node_id)
        if old == sid:
            return
        incident = self._incident(node_id)
        for edge_id in incident:
            self._bump(self.index.edge_counts, self._triple(edge_id), -1)
        if old is not None:
            self._bump(self.index.node_counts, old, -1)
        self.index.nodes[node_id] = sid
        self._bump(self.index.node_counts, sid, 1)
        for edge_id in incident:
            self._bump(self.index.edge_counts, self._triple(edge_id), 1)

    def remove_node(self, node_id: NodeId) -> None:
        old = self.index.nodes.get(node_id)
        if old is None:
            return
        incident = self._incident(node_id)
        for edge_id in incident:
            self._bump(self.index.edge_counts, self._triple(edge_id), -1)
        self._bump(self.index.node_counts, old, -1)
        del self.index.nodes[node_id]
        for edge_id in incident:
            self._bump(self.index.edge_counts, self._triple(edge_id), 1)

    def set_edge(
        self, edge_id: EdgeId, sid: str, signature: AccessSignature, source: NodeId, target: NodeId
    ) -> None:
        self._remember(sid, signature)
        if edge_id in self.index.edges:
            self.remove_edge(edge_id)
        self.index.edges[edge_id] = (sid, source, target)
        self.index.self_links += source == target
        for end in (source, target):
            self.index.adjacency.add((end, edge_id))
            self._adjacent.setdefault(end, set()).add(edge_id)
        self._bump(self.index.edge_counts, self._triple(edge_id), 1)

    def remove_edge(self, edge_id: EdgeId) -> None:
        if edge_id not in self.index.edges:
            return
        self._bump(self.index.edge_counts, self._triple(edge_id), -1)
        _, source, target = self.index.edges.pop(edge_id)
        self.index.self_links -= source == target
        for end in (source, target):
            self.index.adjacency.discard((end, edge_id))
            if end in self._adjacent:
                self._adjacent[end].discard(edge_id)
                if not self._adjacent[end]:
                    del self._adjacent[end]

    def written(self, epoch_token: str) -> None:
        """What every write does at its end: the version counts up, and the case has an epoch."""
        self.version += 1
        if not self.epoch:
            self.epoch = epoch_token

    def counts(self) -> AccessCounts:
        """The figures' inputs, keyed by full signature id (the fake has no short keys)."""
        return AccessCounts(
            epoch=self.epoch,
            version=self.version,
            sigs_version=self.sigs_version,
            signatures=dict(self.index.signatures),
            node_counts=dict(self.index.node_counts),
            edge_counts=dict(self.index.edge_counts),
        )

    def adjacent(self, node_ids: list[NodeId]) -> dict[NodeId, list[EdgeId]]:
        return {n: sorted(self._adjacent.get(n, ())) for n in node_ids}

    def entries(self, node_ids: list[NodeId], edge_ids: list[EdgeId]) -> AccessEntries:
        nodes = {i: self.index.nodes[i] for i in node_ids if i in self.index.nodes}
        edges = {i: self.index.edges[i] for i in edge_ids if i in self.index.edges}
        ends = {
            n: self.index.nodes[n]
            for _, source, target in edges.values()
            for n in (source, target)
            if n in self.index.nodes
        }
        return AccessEntries(nodes, edges, ends, self.epoch)
