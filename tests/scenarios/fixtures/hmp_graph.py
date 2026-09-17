"""Gives the HMP fixture a graph side — `08_ACCEPTANCE_SCENARIOS.md`
Scenario A, `07_BUILD_PLAN.md` Phase 5. `tests/scenarios/fixtures/hmp.py`'s
own `generate_hmp_events()` stays untouched: its 262 `EventRecord`s and
their statistical shape are already proved correct against a real
`AnalyticsPort` (`test_hmp_fixture_shape.py`), and nothing here changes
that shape — only `source_id`/`target_id`/`edge_id` move from synthetic
placeholder strings to real `GraphPort` ids, exactly what the build plan's
"real Location/Person nodes and PRESENT_AT edges behind its EventRecords"
asks for.

**Why incidents are written directly, not through a seventh recipe.** The
six structural recipes (yards, persons, families, groups, associates,
reports) each earn the recipe engine's `on_match: reference` dedup and
load-ledger stamping. Incidents do not need a new one: `hmp.py`'s
generator already produces the exact, tested statistical shape, and a
recipe-engine path would need `PRESENT_AT` to carry an `item_type`
property it does not have (and should not gain solely to move 262 already-
correct rows through a second pipeline). Calling `GraphPort.upsert_edges`
directly is the documented, sanctioned shape for this
(`01_DOMAIN_MODEL.md` §2.4: `recipe_id`/`recipe_version` are `None` "for
anything written outside a recipe load — a conformance fixture... not a
patched-together special case).

**What is, and is not, verified here.** The principal subject's elevated
incident/report frequency and the relay group's dense internal
`ASSOCIATE_OF` subgraph are real, checked-in-this-module properties of the
generated data (`test_hmp_graph.py`) — not yet proved to make A8's
ranking or A12's Clique Metric come out the claimed way, since neither the
metrics panel's filtering nor `ComputePort` exists yet. Building the data
so those checks have something real to find is this phase's job; running
them is the phase that builds the mechanism.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path

from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe

from conduit_common.identity import new_edge_id
from ports.graph import GraphPort
from schemas.analytics import EventRecord
from schemas.domain import (
    EdgeId,
    EdgeWrite,
    Handling,
    Interval,
    NodeId,
    OntologySchema,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .hmp import HOTSPOT_YARDS, PEAK_HOURS, generate_hmp_events
from .hmp_population import (
    PRINCIPAL_SUBJECT_INDEX,
    PRINCIPAL_SUBJECT_PRISON_NUMBER,
    RELAY_GROUP_INDICES,
    RELAY_GROUP_PRISON_NUMBERS,
    SECOND_SUBJECT_INDEX,
    SECOND_SUBJECT_PRISON_NUMBER,
    TOTAL_PERSONS,
    YARD_LETTERS,
    generate_associate_rows,
    generate_family_rows,
    generate_group_rows,
    generate_persons,
    generate_report_rows,
    person_rows_as_dicts,
    prison_number_for_index,
    yard_rows_as_dicts,
)

FIXTURES = Path(__file__).resolve().parent

INVESTIGATION_SCOPE = "case-hmp-fixture"
_HANDLING = Handling(
    classification="OFFICIAL",
    handling_code="P",
    originator="hmp-hollywood",
    owning_unit="hmp-hollywood",
)

#: Dated before `hmp.py`'s `_WINDOW_START` (2026-01-05) — A10/A11's "the
#: second has prior events outside the current window."
_PRIOR_PERIOD_DATES: tuple[date, ...] = (
    date(2025, 12, 10), date(2025, 12, 17), date(2025, 12, 22), date(2025, 12, 29),
)
#: A non-hotspot yard — the prior events are about continuity, not the
#: hotspot finding.
PRIOR_PERIOD_YARD = "E"


@dataclass(frozen=True)
class HmpGraphResult:
    yard_node_ids: dict[str, NodeId]  # yard letter -> Location NodeId
    person_node_ids: dict[str, NodeId]  # prison_number -> Person NodeId
    principal_subject_id: NodeId
    second_subject_id: NodeId
    relay_group_ids: tuple[NodeId, ...]
    current_window_events: list[EventRecord]  # hmp.py's 262, with real graph ids
    prior_period_events: list[EventRecord]  # the second subject's, dated before the window


def _source_ref(label: str) -> SourceRef:
    return SourceRef(document_id="hmp-fixture", locator=label, excerpt_hash="")


def _provenance(label: str) -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED, sources=[_source_ref(label)], first_seen=datetime.now(UTC),
    )


async def _run_structural_recipes(
    *,
    graph: GraphPort,
    ontology: OntologySchema,
    principal: Principal,
    load_id_prefix: str,
    investigation_scope: str = INVESTIGATION_SCOPE,
) -> None:
    """One transaction *per chunk*, committed before the next one starts —
    never one shared transaction across all six recipes, and never one
    single transaction for a whole large recipe either.

    **Why between recipes.** `GraphPort.find_node` (confirmed empirically,
    not assumed) does not see a write made earlier in the same still-open
    transaction, and every recipe from `hmp_persons_recipe.yaml` onward
    resolves an already-created entity by `on_match: reference`, which
    calls `find_node` internally (`services/ingest/engine.py`'s
    `_write_entity`). Sharing one transaction across all six would not
    raise — `on_match: reference` falls back to *creating* a new node when
    the lookup misses — so the failure mode is a silent duplicate
    population, not an error.

    **Why chunked within the two largest recipes.** Measured, not assumed:
    a single ~400-row (persons) or ~229-row (reports) transaction reliably
    triggered `"Error in execution in lock"` on ArcadeDB commit on this
    host (`docs/SESSION_HANDOVER.md`'s documented heap-pressure territory,
    reached here by data volume rather than concurrent DDL). Batches of
    `_CHUNK_SIZE` rows keep every single transaction's write volume in the
    range every other fixture in this build already runs at without
    incident."""
    persons = generate_persons()
    recipes_and_rows = [
        ("hmp_yards_recipe.yaml", yard_rows_as_dicts(), "hmp-fixture:yards"),
        ("hmp_persons_recipe.yaml", person_rows_as_dicts(persons), "hmp-fixture:persons"),
        ("hmp_families_recipe.yaml", generate_family_rows(persons), "hmp-fixture:families"),
        ("hmp_groups_recipe.yaml", generate_group_rows(persons), "hmp-fixture:groups"),
        ("hmp_associates_recipe.yaml", generate_associate_rows(persons), "hmp-fixture:associates"),
        ("hmp_reports_recipe.yaml", generate_report_rows(persons), "hmp-fixture:reports"),
    ]
    for recipe_file, rows, source in recipes_and_rows:
        recipe = load_recipe(FIXTURES / recipe_file)
        for chunk_index, chunk in enumerate(_chunked(rows, _CHUNK_SIZE)):
            tx = await graph.begin_transaction()
            try:
                report, _events = await run_recipe(
                    recipe, chunk, graph=graph, ontology=ontology, tx=tx, principal=principal,
                    load_id=f"{load_id_prefix}-{recipe.id}-{chunk_index}",
                    investigation_scope=investigation_scope, source=f"{source}:chunk-{chunk_index}",
                )
            except Exception:
                await graph.rollback_transaction(tx)
                raise
            if report.rejections:
                await graph.rollback_transaction(tx)
                raise AssertionError(f"{recipe_file} rejected rows: {report.rejections}")
            await graph.commit_transaction(tx)


_CHUNK_SIZE = 40


def _chunked(rows: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)] or [[]]


async def _upsert_edges_in_chunks(
    graph: GraphPort, writes: list[EdgeWrite],
) -> list[EdgeId]:
    """`_run_structural_recipes`'s docstring explains why: keep every
    single transaction's write volume down. Returns ids in the same order
    as `writes`, across all chunks."""
    edge_ids: list[EdgeId] = []
    for i in range(0, len(writes), _CHUNK_SIZE):
        chunk = writes[i : i + _CHUNK_SIZE]
        tx = await graph.begin_transaction()
        try:
            edge_ids.extend(await graph.upsert_edges(chunk, tx))
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)
    return edge_ids


async def _lookup_yard_ids(graph: GraphPort, principal: Principal) -> dict[str, NodeId]:
    async def _one(letter: str) -> tuple[str, NodeId]:
        node = await graph.find_node("Location", "site_ref", f"yard-{letter.lower()}", principal)
        assert node is not None, f"yard {letter} was not created by hmp_yards_recipe.yaml"
        return letter, node.id

    pairs = await asyncio.gather(*(_one(letter) for letter in YARD_LETTERS))
    return dict(pairs)


async def _lookup_person_ids(graph: GraphPort, principal: Principal) -> dict[str, NodeId]:
    async def _one(prison_number: str) -> tuple[str, NodeId]:
        node = await graph.find_node("Person", "prison_number", prison_number, principal)
        assert node is not None, f"{prison_number} was not created by hmp_persons_recipe.yaml"
        return prison_number, node.id

    prison_numbers = [prison_number_for_index(i) for i in range(TOTAL_PERSONS)]
    pairs = await asyncio.gather(*(_one(p) for p in prison_numbers))
    return dict(pairs)


def _assign_incident_persons(events: list[EventRecord]) -> list[int]:
    """Deterministic, exact partitioning — `hmp.py`'s own "built as an
    exact multiset, not weighted coin-flips" philosophy, applied to who
    the incident belongs to rather than to yard/weekday/hour. Hotspot
    *and* peak-hour incidents go mostly to the principal subject (A8:
    "the principal subject ranks first"); the rest of that intersection,
    and a share of hotspot-only incidents, round-robin across the relay
    group (spread across multiple yards — "passing items between cells");
    everything else goes to the general population."""
    excluded = set(RELAY_GROUP_INDICES) | {PRINCIPAL_SUBJECT_INDEX, SECOND_SUBJECT_INDEX}
    general_pool = [i for i in range(TOTAL_PERSONS) if i not in excluded]

    hotspot_peak_positions = [
        i for i, e in enumerate(events)
        if e.properties["yard"] in HOTSPOT_YARDS and e.occurred_at.hour in PEAK_HOURS
    ]
    hotspot_only_positions = [
        i for i, e in enumerate(events)
        if e.properties["yard"] in HOTSPOT_YARDS and e.occurred_at.hour not in PEAK_HOURS
    ]
    hotspot_positions = set(hotspot_peak_positions) | set(hotspot_only_positions)
    other_positions = [i for i in range(len(events)) if i not in hotspot_positions]

    assignment: list[int | None] = [None] * len(events)

    principal_share = max(1, round(len(hotspot_peak_positions) * 0.6))
    for j, pos in enumerate(hotspot_peak_positions):
        if j < principal_share:
            assignment[pos] = PRINCIPAL_SUBJECT_INDEX
        else:
            assignment[pos] = RELAY_GROUP_INDICES[(j - principal_share) % len(RELAY_GROUP_INDICES)]

    relay_share = max(1, round(len(hotspot_only_positions) * 0.3))
    for j, pos in enumerate(hotspot_only_positions):
        if j < relay_share:
            assignment[pos] = RELAY_GROUP_INDICES[j % len(RELAY_GROUP_INDICES)]
        else:
            assignment[pos] = general_pool[(j - relay_share) % len(general_pool)]

    for j, pos in enumerate(other_positions):
        assignment[pos] = general_pool[j % len(general_pool)]

    assert all(a is not None for a in assignment)
    return assignment  # type: ignore[return-value]


def _prior_period_events(investigation_scope: str = INVESTIGATION_SCOPE) -> list[EventRecord]:
    # id/source/target below are placeholders — build_hmp_graph() replaces
    # all three with the real graph ids once the second subject and the
    # yard Location exist, the same substitution current_window_events
    # applies to hmp.py's own placeholder ids.
    events: list[EventRecord] = []
    for i, incident_date in enumerate(_PRIOR_PERIOD_DATES):
        events.append(
            EventRecord(
                event_id=f"hmp-prior-incident-{i:04d}",
                edge_id=f"hmp-prior-edge-{i:04d}",
                edge_type="PRESENT_AT",
                source_id=f"hmp-prior-subject-{i:04d}",
                target_id=f"hmp-prior-location-{PRIOR_PERIOD_YARD}",
                occurred_at=datetime.combine(incident_date, time(hour=14, minute=0), tzinfo=UTC),
                properties={"yard": PRIOR_PERIOD_YARD, "item_type": "tobacco"},
                investigation_scope=investigation_scope,
                handling=_HANDLING,
            )
        )
    return events


async def build_hmp_graph(
    *, graph: GraphPort, ontology: OntologySchema, principal: Principal,
    load_id_prefix: str = "load-hmp",
    investigation_scope: str = INVESTIGATION_SCOPE,
) -> HmpGraphResult:
    """Manages its own transactions throughout — see
    `_run_structural_recipes`'s docstring for why a single transaction
    passed in by the caller cannot work here. Every write this function
    makes is committed by the time it returns; a caller never needs to
    (and cannot usefully) wrap this call in its own transaction.

    `investigation_scope` defaults to this fixture's own constant, exactly
    as every existing test that doesn't pass it already expects — but a
    live seed against a real, analyst-created investigation
    (`scripts/seed_hmp_fixture.py`, `07_BUILD_PLAN.md` Phase 5 Checkpoint
    2) needs its events tagged with *that* investigation's own id instead,
    since `EventFilter.investigation_scope` is what every analytics query
    actually filters on."""
    await _run_structural_recipes(
        graph=graph, ontology=ontology, principal=principal, load_id_prefix=load_id_prefix,
        investigation_scope=investigation_scope,
    )
    yard_ids = await _lookup_yard_ids(graph, principal)
    person_ids = await _lookup_person_ids(graph, principal)

    current_events = generate_hmp_events(investigation_scope=investigation_scope)
    assignment = _assign_incident_persons(current_events)

    def _person_index_to_id(index: int) -> NodeId:
        return person_ids[prison_number_for_index(index)]

    # Chunked commits again, the same reason as `_run_structural_recipes`'s
    # own — no `find_node` lookups happen in this phase (every id needed is
    # already resolved above), so chunking here is purely about keeping
    # each transaction's write volume down, not about read-your-own-writes.
    current_writes = [
        EdgeWrite(
            id=new_edge_id(),
            type="PRESENT_AT",
            source=_person_index_to_id(person_index),
            target=yard_ids[event.properties["yard"]],
            interval=Interval(valid_from=event.occurred_at, valid_to=event.occurred_at),
            occurrences=1,
            provenance=_provenance(f"incident row {i}"),
            handling=_HANDLING,
            created_by=principal.id,
            created_at=datetime.now(UTC),
        )
        for i, (event, person_index) in enumerate(zip(current_events, assignment, strict=True))
    ]
    current_edge_ids = await _upsert_edges_in_chunks(graph, current_writes)
    current_window_events = [
        event.model_copy(
            update={
                "source_id": _person_index_to_id(person_index),
                "target_id": yard_ids[event.properties["yard"]],
                "edge_id": edge_id,
            }
        )
        for event, person_index, edge_id in zip(
            current_events, assignment, current_edge_ids, strict=True
        )
    ]

    second_subject_id = person_ids[SECOND_SUBJECT_PRISON_NUMBER]
    prior_events_placeholder = _prior_period_events(investigation_scope)
    prior_writes = [
        EdgeWrite(
            id=new_edge_id(),
            type="PRESENT_AT",
            source=second_subject_id,
            target=yard_ids[PRIOR_PERIOD_YARD],
            interval=Interval(valid_from=event.occurred_at, valid_to=event.occurred_at),
            occurrences=1,
            provenance=_provenance(f"prior-period row {i}"),
            handling=_HANDLING,
            created_by=principal.id,
            created_at=datetime.now(UTC),
        )
        for i, event in enumerate(prior_events_placeholder)
    ]
    prior_edge_ids = await _upsert_edges_in_chunks(graph, prior_writes)
    prior_period_events = [
        event.model_copy(
            update={
                "source_id": second_subject_id,
                "target_id": yard_ids[PRIOR_PERIOD_YARD],
                "edge_id": edge_id,
            }
        )
        for event, edge_id in zip(prior_events_placeholder, prior_edge_ids, strict=True)
    ]

    return HmpGraphResult(
        yard_node_ids=yard_ids,
        person_node_ids=person_ids,
        principal_subject_id=person_ids[PRINCIPAL_SUBJECT_PRISON_NUMBER],
        second_subject_id=second_subject_id,
        relay_group_ids=tuple(person_ids[p] for p in RELAY_GROUP_PRISON_NUMBERS),
        current_window_events=current_window_events,
        prior_period_events=prior_period_events,
    )
