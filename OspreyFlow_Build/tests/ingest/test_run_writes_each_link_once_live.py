"""ADR-127 Amendment 19 against a real ArcadeDB, rules 3 and 4: a run that combines its writes keeps
apart what ADR-102 Amendment 3 keeps apart, and the store's own access filter then reads each link
to the principals it is for. Needs the dev stack's ArcadeDB, like the rest of `tests/ingest` (it
runs under `make test-all`; `make test` ignores the folder). The stand-in cannot show this: it has
no access filter, and `CountingStore` no merge of a real store's.

- A pair written at OFFICIAL and at SECRET is two links, and a principal without SECRET sees one,
  counting only the OFFICIAL rows
  (`test_a_pair_at_two_classifications_is_two_links_one_seen_without_secret`). Catches a combiner
  that keys on the pair alone, which would raise the link to SECRET and hide it from the reader the
  first rows were for, and show them a degree it should not.
- Two rows of one classification under a restricted code, for different owning units, are two
  links, and each unit reads only its own
  (`test_a_restricted_pair_for_two_units_is_two_links_each_read_by_its_unit`). Catches a combiner
  that keys on classification alone, which would hand one unit's rows to the other.

Each is run combined, and the same rows run per row, which must read the same."""

from __future__ import annotations

import itertools
from contextlib import nullcontext
from typing import Any

from services.api.studio_publish import load_with_rules

from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_node_id, now_utc
from schemas.domain import (
    ExpandRequest,
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.ingest.combined_run_support import (
    BASE,
    audience_recipe,
    audience_row,
    per_row,
)
from tests.ingest.pid_golden_support import ONTOLOGY, SCHEME
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)

LOADER = Principal(
    id="loader-1", clearance="SECRET", org_unit="unit-1", receivable_handling_codes=["R"]
)
OFFICIAL_READER = Principal(id="reader-o", clearance="OFFICIAL", org_unit="unit-1")
SECRET_READER = Principal(id="reader-s", clearance="SECRET", org_unit="unit-1")
UNIT_1 = Principal(
    id="reader-u1", clearance="OFFICIAL", org_unit="unit-1", receivable_handling_codes=["R"]
)
UNIT_2 = Principal(
    id="reader-u2", clearance="OFFICIAL", org_unit="unit-2", receivable_handling_codes=["R"]
)


def _existing_node(value: str) -> NodeWrite:
    """A handle already in the store at the base marking, as an earlier load left it, so the run
    finds it by reference and the links under test are the only thing it writes."""
    now = now_utc()
    return NodeWrite(
        id=new_node_id(),
        type="Endpoint",
        properties={"value_raw": value, "value_normalised": value, "endpoint_kind": "handle"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="earlier", locator="row 1", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling.model_validate(BASE),
        created_by="loader-1",
        created_at=now,
    )


async def _written(adapter: Any, rows: list[dict[str, str]], *, combine: bool) -> tuple[str, str]:
    """The two handles in a fresh store, then `rows` loaded through the recipe, combined or per
    row. Returns the handles' ids."""
    tx = await adapter.begin_transaction()
    a, b = await adapter.upsert_nodes([_existing_node("ZA1234ZZ"), _existing_node("ZB5678ZZ")], tx)
    await adapter.commit_transaction(tx)
    with per_row() if not combine else nullcontext():
        report, _events, _held = await load_with_rules(
            audience_recipe(),
            rows,
            LOADER,
            graph=adapter,
            ontology=ONTOLOGY,
            load_id="load-live",
            investigation_scope="case-1",
            source="pairs.csv",
            media=InMemoryMediaStore(),
            rules=None,
            scheme=SCHEME,
        )
    assert report.rejections == [], report.rejections
    return a, b


async def _seen(adapter: Any, reader: Principal, a: str, b: str) -> list[tuple[str, int, int]]:
    """What a reader is given of the pair: each link's classification, its occurrences, and the
    degree of the first handle as the reader counts it."""
    links = await adapter.edges_among([a, b], reader)
    degree = (await adapter.neighbourhood_stats(a, reader)).degree
    return sorted((e.handling.classification, e.occurrences, degree) for e in links)


async def test_a_pair_at_two_classifications_is_two_links_one_seen_without_secret() -> None:
    rows = [audience_row(), audience_row(classification="SECRET"), audience_row(), audience_row()]
    for combine in (True, False):
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as adapter:
            a, b = await _written(adapter, rows, combine=combine)
            links = await adapter.edges_among([a, b], SECRET_READER)
            assert sorted((e.handling.classification, e.occurrences) for e in links) == [
                ("OFFICIAL", 3),
                ("SECRET", 1),
            ], f"two links, one for each audience (combined: {combine})"
            assert sorted(e.audit.revision for e in links) == [1, 3]
            assert await _seen(adapter, OFFICIAL_READER, a, b) == [("OFFICIAL", 3, 1)], (
                "the reader without SECRET sees one link, counting only the OFFICIAL rows, and "
                "a degree of one"
            )
            subgraph = await adapter.expand(ExpandRequest(node_ids=[a], depth=1), OFFICIAL_READER)
            assert len(subgraph.edges) == 1


async def test_a_restricted_pair_for_two_units_is_two_links_each_read_by_its_unit() -> None:
    mark_1 = {"handling_code": "R", "originator": "unit-1", "owning_unit": "unit-1"}
    mark_2 = {"handling_code": "R", "originator": "unit-2", "owning_unit": "unit-2"}
    rows = [audience_row(**mark_1), audience_row(**mark_2), audience_row(**mark_1)]
    for combine in (True, False):
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as adapter:
            a, b = await _written(adapter, rows, combine=combine)
            for reader, unit, occurrences in ((UNIT_1, "unit-1", 2), (UNIT_2, "unit-2", 1)):
                links = await adapter.edges_among([a, b], reader)
                assert [(e.handling.owning_unit, e.occurrences) for e in links] == [
                    (unit, occurrences)
                ], f"{unit} reads its own rows and no other unit's (combined: {combine})"


async def test_a_combined_run_reads_back_what_a_run_per_row_leaves_on_a_real_store() -> None:
    """The amendment's equivalence, once on a real ArcadeDB: three handles, links between each pair
    written by several rows at two markings, each row with its own time and duration, and a second
    load that merges into the links the first left. Read back by a principal cleared for
    everything, every link's marking, occurrences, revision, source rows, interval and properties
    are the same combined and per row, and so is every event, with the link it names. Catches a
    combined write that the real adapter merges differently from the same rows one at a time."""
    clock = itertools.count()

    def rows_between(a: str, b: str, count: int, **marking: str) -> list[dict[str, str]]:
        return [
            {
                **audience_row(**marking),
                "from": a,
                "to": b,
                "duration": str(10 + next(clock)),
                "at": f"2026-03-{1 + next(clock) % 27:02d}T10:00:00+00:00",
            }
            for _ in range(count)
        ]

    first = [
        *rows_between("ZA1234ZZ", "ZB5678ZZ", 3),
        *rows_between("ZB5678ZZ", "ZC9012ZZ", 2),
        *rows_between("ZA1234ZZ", "ZB5678ZZ", 1, classification="SECRET"),
        *rows_between("ZA1234ZZ", "ZC9012ZZ", 1),
    ]
    second = [
        *rows_between("ZA1234ZZ", "ZB5678ZZ", 2),
        *rows_between("ZB5678ZZ", "ZC9012ZZ", 1, classification="SECRET"),
    ]
    found: list[tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]] = []
    for combine in (True, False):
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as adapter:
            tx = await adapter.begin_transaction()
            ids = await adapter.upsert_nodes(
                [_existing_node(v) for v in ("ZA1234ZZ", "ZB5678ZZ", "ZC9012ZZ")], tx
            )
            await adapter.commit_transaction(tx)
            events: list[Any] = []
            for load_id, rows in (("load-1", first), ("load-2", second)):
                with per_row() if not combine else nullcontext():
                    report, load_events, _held = await load_with_rules(
                        audience_recipe(),
                        rows,
                        LOADER,
                        graph=adapter,
                        ontology=ONTOLOGY,
                        load_id=load_id,
                        investigation_scope="case-1",
                        source="pairs.csv",
                        media=InMemoryMediaStore(),
                        rules=None,
                        scheme=SCHEME,
                    )
                assert report.rejections == [], report.rejections
                events.extend(load_events)
            links = await adapter.edges_among(ids, SECRET_READER)
            names = dict(zip(ids, ("ZA1234ZZ", "ZB5678ZZ", "ZC9012ZZ"), strict=True))
            by_id = {e.id: e for e in links}
            found.append(
                (
                    sorted(
                        (
                            names[e.source],
                            names[e.target],
                            e.handling.classification,
                            e.occurrences,
                            e.audit.revision,
                            [s.locator for s in e.provenance.sources],
                            e.interval.model_dump(mode="json") if e.interval else None,
                            e.properties,
                        )
                        for e in links
                    ),
                    sorted(
                        (
                            names[ev.source_id],
                            names[ev.target_id],
                            ev.occurred_at,
                            ev.duration_s,
                            by_id[ev.edge_id].handling.classification,
                            by_id[ev.edge_id].occurrences,
                        )
                        for ev in events
                    ),
                )
            )
    (combined_links, combined_events), (reference_links, reference_events) = found
    assert len(combined_links) == 5, "three pairs, two of them at two classifications"
    assert len(combined_events) == len(first) + len(second)
    assert combined_links == reference_links
    assert combined_events == reference_events
