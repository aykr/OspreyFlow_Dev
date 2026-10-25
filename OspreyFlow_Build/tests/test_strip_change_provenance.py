"""`python -m scripts.strip_change_provenance` (ADR-124 decision 11, U10), over the graph and
working-set fakes and a dict-backed Valkey client: one run takes the old link's id out of the
Vault's links (the port method, once for each prefix), out of every case's stored links, and
deletes each delta stream that names one, leaving the access index as it was and a second run with
nothing to do. The same run against a real store is `services/api/test_valkey_store.py`'s case.
"""

from __future__ import annotations

from typing import Any

import pytest
from scripts.strip_change_provenance import StripReport, strip
from services.api.working_set.models import DeltaReplaceEdge
from services.api.working_set.store import _deltas_key  # noqa: PLC2701

from schemas.domain import Edge, SourceRef, Subgraph

from .services.api.working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .services.api.working_set.test_visible_link import edge, node

CHANGE = "manual:change:old-link"
PICTURE = "manual:remove-picture:old-picture"


def _with_sources(link: Edge, *documents: str) -> Edge:
    sources = [
        *link.provenance.sources,
        *(SourceRef(document_id=d, locator="p.1", excerpt_hash="") for d in documents),
    ]
    return link.model_copy(
        update={"provenance": link.provenance.model_copy(update={"sources": sources})}
    )


def _documents(link: Edge) -> list[str]:
    return [s.document_id for s in link.provenance.sources]


class _Valkey:
    """The three calls the script makes: `scan_iter` over the `ws:<case>:edges` keys, `xrange` of a
    stream, `delete`. A stream is a list of (id, {field: payload})."""

    def __init__(self, streams: dict[str, list[str]]) -> None:
        self.streams = {k: list(v) for k, v in streams.items()}
        self.deleted: list[str] = []

    async def scan_iter(self, match: str, count: int = 0) -> Any:
        assert match == "ws:*:edges"
        for case in sorted({k.split(":")[1] for k in self.streams}):
            yield f"ws:{case}:edges".encode()

    async def xrange(self, key: str) -> list[tuple[bytes, dict[bytes, bytes]]]:
        return [
            (f"{n}-0".encode(), {b"json": p.encode()})
            for n, p in enumerate(self.streams.get(key, []), 1)
        ]

    async def delete(self, key: str) -> int:
        self.deleted.append(key)
        return 1 if self.streams.pop(key, None) is not None else 0


def _delta_naming(document: str) -> str:
    old = edge("old", "a", "b")
    new = _with_sources(edge("new", "a", "b"), document)
    return DeltaReplaceEdge(seq=1, old_edge_id=old.id, edge=new).model_dump_json()


async def _world() -> tuple[FakeGraphPort, FakeWorkingSetStore, _Valkey]:
    graph = FakeGraphPort(
        Subgraph(nodes=[], edges=[]),
        graph_edges=[
            _with_sources(edge("v1", "a", "b"), CHANGE),
            _with_sources(edge("v2", "c", "d"), PICTURE),
            _with_sources(edge("v3", "e", "f"), "manual:change"),
        ],
    )
    store = FakeWorkingSetStore()
    for case, links in {
        "case-1": [_with_sources(edge("w1", "a", "b"), CHANGE, PICTURE)],
        "case-2": [_with_sources(edge("w2", "a", "b"), PICTURE), edge("w3", "c", "d")],
        "case-3": [edge("w4", "a", "b")],
    }.items():
        await store.add_nodes(case, [node("a"), node("b"), node("c"), node("d")])
        await store.add_edges(case, links)
    valkey = _Valkey(
        {
            _deltas_key("case-1"): [_delta_naming(CHANGE)],
            _deltas_key("case-2"): [_delta_naming("doc-1")],
            _deltas_key("case-3"): [],
            "ws:case-1:edges": [],
            "ws:case-2:edges": [],
            "ws:case-3:edges": [],
        }
    )
    return graph, store, valkey


async def test_one_run_cleans_the_vault_every_working_set_and_the_streams_that_name_a_link() -> (
    None
):
    graph, store, valkey = await _world()

    report = await strip(graph, valkey, store)

    assert report.vault == {"manual:change:": 1, "manual:remove-picture:": 1}, "each prefix, once"
    assert [(_documents(e)) for e in graph._graph_edges] == [
        ["doc-1"],
        ["doc-1"],
        ["doc-1", "manual:change"],
    ]
    assert _documents(await store.get_edge("case-1", "w1")) == ["doc-1"]  # type: ignore[arg-type]
    assert _documents(await store.get_edge("case-2", "w2")) == ["doc-1"]  # type: ignore[arg-type]
    assert (report.working_set_links, report.working_set_cases) == (2, 2)
    assert valkey.deleted == [_deltas_key("case-1")], "only the stream that named a link"
    assert report.streams_deleted == 1 and report.total == 5


async def test_the_access_index_is_the_same_after_the_rewrite() -> None:
    """A body's provenance is not in its signature, so the counted index must not move."""
    graph, store, valkey = await _world()
    before = {c: await store.access_counts(c) for c in ("case-1", "case-2", "case-3")}

    await strip(graph, valkey, store)

    for case, was in before.items():
        now = await store.access_counts(case)
        assert (now.signatures, now.node_counts, now.edge_counts) == (
            was.signatures,
            was.node_counts,
            was.edge_counts,
        ), case


async def test_a_second_run_changes_nothing_and_reports_zero() -> None:
    graph, store, valkey = await _world()
    await strip(graph, valkey, store)
    deleted = list(valkey.deleted)

    again = await strip(graph, valkey, store)

    assert again.total == 0 and again.vault == {"manual:change:": 0, "manual:remove-picture:": 0}
    assert valkey.deleted == deleted, "a second run deletes no stream"


async def test_the_report_totals_what_changed() -> None:
    assert StripReport().total == 0
    assert StripReport(vault={"a": 2}, working_set_links=3, streams_deleted=1).total == 6


# --- the rewrite is conditional: a link a running Conduit changed is not brought back -------------


def _strip_old_entry(link: Edge) -> Edge | None:
    kept = [s for s in link.provenance.sources if not s.document_id.startswith("manual:change:")]
    if len(kept) == len(link.provenance.sources):
        return None
    return link.model_copy(
        update={"provenance": link.provenance.model_copy(update={"sources": kept})}
    )


async def _case_of_three() -> FakeWorkingSetStore:
    store = FakeWorkingSetStore()
    await store.add_nodes("c", [node("a"), node("b")])
    await store.add_edges(
        "c",
        [
            _with_sources(edge("l1", "a", "b"), CHANGE),
            _with_sources(edge("l2", "a", "b"), CHANGE),
            edge("l3", "a", "b"),
        ],
    )
    return store


async def test_a_link_removed_between_the_read_and_the_write_is_not_brought_back() -> None:
    """Violation caught: the script reads a case's links, a running Conduit removes one (a node's
    removal, a restore's reconcile), and an upsert of what was read puts it back with no delta.
    The others are rewritten; the removed one stays removed and is reported as skipped."""
    store = await _case_of_three()

    async def conduit_removes_l2(case: str) -> None:
        await store.remove_edges(case, ["l2"])

    store._between_read_and_write = conduit_removes_l2

    result = await store.rewrite_edges_if_unchanged("c", _strip_old_entry)

    assert (result.rewritten, result.skipped) == (1, 1)
    assert sorted(await store.edge_ids("c")) == ["l1", "l3"]
    assert _documents(await store.get_edge("c", "l1")) == ["doc-1"]  # type: ignore[arg-type]


async def test_a_link_replaced_between_the_read_and_the_write_keeps_the_newer_body() -> None:
    """The newer body was written by the running Conduit, so it is not the body that was read and
    it is left exactly as it is."""
    store = await _case_of_three()
    newer = edge("l2", "a", "b").model_copy(update={"occurrences": 9})

    async def conduit_replaces_l2(case: str) -> None:
        await store.add_edges(case, [newer])

    store._between_read_and_write = conduit_replaces_l2

    result = await store.rewrite_edges_if_unchanged("c", _strip_old_entry)

    assert (result.rewritten, result.skipped) == (1, 1)
    assert await store.get_edge("c", "l2") == newer


async def test_with_nothing_changed_underneath_every_link_that_needs_it_is_rewritten() -> None:
    store = await _case_of_three()
    counts = await store.access_counts("c")

    result = await store.rewrite_edges_if_unchanged("c", _strip_old_entry)

    assert (result.rewritten, result.skipped) == (2, 0)
    after = await store.access_counts("c")
    assert (after.signatures, after.node_counts, after.edge_counts) == (
        counts.signatures,
        counts.node_counts,
        counts.edge_counts,
    )
    again = await store.rewrite_edges_if_unchanged("c", _strip_old_entry)
    assert (again.rewritten, again.skipped) == (0, 0)


async def test_a_rewrite_that_would_move_the_index_is_refused() -> None:
    """The conditional write leaves the access entry alone, so a replacement with another handling,
    dataset or end is refused before anything is written."""
    store = await _case_of_three()

    def raise_marking(link: Edge) -> Edge:
        return link.model_copy(
            update={"handling": link.handling.model_copy(update={"classification": "SECRET"})}
        )

    with pytest.raises(ValueError):
        await store.rewrite_edges_if_unchanged("c", raise_marking)
    for moved in ({"source": "b"}, {"datasets": ["other"]}):
        with pytest.raises(ValueError):
            await store.rewrite_edges_if_unchanged(
                "c", lambda link, m=moved: link.model_copy(update=m)
            )
