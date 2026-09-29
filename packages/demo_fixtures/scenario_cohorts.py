"""Scenario B's person layer — the cohorts B4–B8 walk through, and B15's device legs.

**Promoted from `tests/scenarios/test_phase8_exit_criterion_end_to_end.py` in round 13cb, on that
file's own terms.** Its docstring said of `_seed_cohort`/`_seed_handle_cohort`: *"disclosed as
test-local construction, not a dedicated fixture module, because no other test needs this shape
yet; if a second test ever does, promoting it to `tests/scenarios/fixtures/` is the right move
then, not speculative work now."* Owner ruling R8 created that second consumer —
`scripts/seed_scenarios.py` has to seed a rendered deployment with the same shape, because R8's
bar is that every acceptance row is performable through the analyst's own door.

**Why this matters more than tidiness.** The two tiers must seed the *same* graph, or the
over-the-wire test and the in-process test are proving different things while both reporting
green. That is the defect shape round 13bf spent itself removing from connector availability —
one fact, expressed in two places, drifting. Here the fact is "what Scenario B's cohorts look
like", and there is now one statement of it.

**Pure generators, no writes.** These return `Node`/`Edge` values and nothing else, the same shape
`fixture_corp.py` uses, so each consumer supplies its own `NodeWrite`/`EdgeWrite` envelope
(`created_by`, `load_id`, the transaction). The in-process test writes through a
`GraphArcadeDBAdapter` it already holds; the seeder writes through the deployment's own adapter
with a seed `load_id`. Neither needs the other's machinery.

**Ids are minted per call, never fixed literals.** The original's reasoning holds and is the
reason to keep it: a fixed id collides with a previous run's leftovers in the shared, persistent
`ospreyflow` database, and the failure reads as a mysterious duplicate rather than as a stale
fixture. `run_token` lets a caller pin the token when it needs to name the nodes it just made.

**The token is the ULID's *tail*, and the original's `new_id()[:8]` was wrong.** A ULID's leading
characters encode its timestamp, so every id minted in the same millisecond shares them —
measured, not reasoned: three successive `new_id()` calls gave `01M3J9XW` three times for `[:8]`
and three distinct values for `[-8:]`. The test-local original got away with it by minting one
token per test run; a seeder that builds two cohorts back to back would have written the *same*
ids twice and the second write would have silently upserted over the first, leaving one cohort
where the fixture claims two — a B4/B5 that passes while proving nothing.
`test_ids_are_minted_per_call_so_reruns_do_not_collide` is what caught it and is what fails if it
returns.

Rule 9: synthetic only. The phone numbers below are Ofcom's 07700 900000–900999 drama range,
which exists for exactly this purpose and is never a real subscriber.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from conduit_common.identity import new_edge_id, new_id
from demo_fixtures.seizure_record import (
    HANDSET_IMEI_NORMALISED,
    SIM_A_IMSI_NORMALISED,
    SIM_B_IMSI_NORMALISED,
)
from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Node,
    Provenance,
    ProvenanceState,
    SourceRef,
)

#: Ofcom's reserved drama range (07700 900000–900999). `cdr.py` deliberately does *not* use it —
#: a msisdn normaliser rejects it as invalid, and B1's point is normalisation. Here the numbers
#: are only identity, never parsed for validity, so the reserved range is the correct choice and
#: the two fixtures differ for a stated reason rather than by accident.
_DRAMA_PREFIX = "+447700900"

#: Named once so a consumer can attribute what it reads back to this module.
_CREATED_BY = "scenario-cohort-fixture"


def _stable_digest(text: str) -> int:
    """A digest that is the same in every process — `hash()` is not.

    Python randomises `hash()` for `str` per interpreter (PYTHONHASHSEED), so the original
    test-local `abs(hash(run))` produced a different number every process. That was harmless while
    one process both generated and wrote the fixture. It is **not** harmless now: the seeder writes
    these nodes in the deployment's own container and the over-the-wire test has to *find* them
    afterwards, in a different process. With `hash()` the two would disagree about which number
    the cohort uses, and the test would look for an endpoint that was never written.

    Measured, not assumed — `abs(hash("scenarios")) % 900` gave 674 and then 514 in two successive
    interpreters. `crc32` is stable by specification, which is the only property wanted here; it
    is not used for anything security-bearing.
    """
    return zlib.crc32(text.encode("utf-8"))


def _handling(owning_unit: str = "unit-1", classification: str = "OFFICIAL") -> Handling:
    return Handling(
        classification=classification,
        handling_code="P",
        originator="fixture",
        owning_unit=owning_unit,
    )


def _provenance(label: str) -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="fixture", locator=label, excerpt_hash="")],
        first_seen=datetime.now(UTC),
    )


#: Fixture elements are written outside a recipe load, so `load_id`/`recipe_*` stay `None` — the
#: same posture `fixture_corp.py` takes, and what ADR-018 expects for a fixture rather than a load.
def _audit() -> AuditStub:
    return AuditStub(created_at=datetime.now(UTC), created_by=_CREATED_BY)


def _person(node_id: str, family_name: str, given_names: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={
            "family_name": family_name,
            "given_names": given_names,
            "date_of_birth": "1985-01-01",
        },
        provenance=_provenance(f"person:{node_id}"),
        handling=_handling(),
        audit=_audit(),
    )


def _endpoint(node_id: str, value_normalised: str, endpoint_kind: str) -> Node:
    return Node(
        id=node_id,
        type="Endpoint",
        properties={
            "value_raw": value_normalised,
            "value_normalised": value_normalised,
            "endpoint_kind": endpoint_kind,
        },
        provenance=_provenance(f"endpoint:{node_id}"),
        handling=_handling(),
        audit=_audit(),
    )


def _edge(edge_type: str, source: str, target: str) -> Edge:
    return Edge(
        id=new_edge_id(),
        type=edge_type,
        source=source,
        target=target,
        provenance=_provenance(f"edge:{source}->{target}"),
        handling=_handling(),
        audit=_audit(),
    )


@dataclass
class Cohort:
    """One cohort and the ids a caller needs to name afterwards.

    `person_ids` is what a working set is seeded with; `shared_id` is what B5's "one hop out"
    is expected to discover. Returning both is the difference between a test that asserts the
    shape it built and one that has to go looking for it.
    """

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    person_ids: list[str] = field(default_factory=list)
    endpoint_ids: list[str] = field(default_factory=list)
    shared_id: str = ""


def generate_cohort(
    *, shared_endpoint_id: str, prefix: str, count: int = 4, run_token: str | None = None
) -> Cohort:
    """**B4/B5.** `count` `Person`s, each with their own personal `Endpoint`, each of those one
    hop from `shared_endpoint_id` via `COMMUNICATED_WITH`.

    That is B4/B5's own two-step description made concrete: seed the working set with the people,
    expand to their own endpoints, expand once more, and the one endpoint common to all of them
    is what surfaces. The shape is deliberately minimal — four people, four endpoints, one shared
    target — because a denser graph would let B5 succeed by accident.
    """
    run = run_token or new_id()[-8:]
    # A per-cohort block inside the drama range, so two cohorts in one database never collide on
    # a number and then appear — correctly, and uselessly — to share an endpoint.
    block = _stable_digest(run) % 900
    person_ids = [f"{prefix}-{run}-person-{i}" for i in range(count)]
    endpoint_ids = [f"{prefix}-{run}-endpoint-{i}" for i in range(count)]

    nodes: list[Node] = [
        _person(pid, f"Cohort{prefix}", f"Member{i}") for i, pid in enumerate(person_ids)
    ]
    nodes += [
        _endpoint(eid, f"{_DRAMA_PREFIX}{(block + i) % 1000:03d}", "msisdn")
        for i, eid in enumerate(endpoint_ids)
    ]
    edges = [
        _edge("USES", pid, eid) for pid, eid in zip(person_ids, endpoint_ids, strict=True)
    ]
    edges += [_edge("COMMUNICATED_WITH", eid, shared_endpoint_id) for eid in endpoint_ids]

    return Cohort(
        nodes=nodes,
        edges=edges,
        person_ids=person_ids,
        endpoint_ids=endpoint_ids,
        shared_id=shared_endpoint_id,
    )


def generate_handle_cohort(
    *, prefix: str, count: int = 4, run_token: str | None = None
) -> Cohort:
    """**B7.** `count` `Person`s sharing one messaging-handle `Endpoint`
    (`endpoint_kind="handle"`) — B7's own literal, "a shared messaging handle is common to that
    cohort".

    The same construction as `generate_cohort` but landing on a handle rather than a number,
    which is what makes B8 meaningful: a handle and an `e164` number share no lexical space, so
    the edge between them is asserted rather than scored (`08_ACCEPTANCE_SCENARIOS.md` B8, citing
    ADR-024).
    """
    run = run_token or new_id()[-8:]
    handle_id = f"{prefix}-{run}-handle"
    person_ids = [f"{prefix}-{run}-person-{i}" for i in range(count)]

    nodes: list[Node] = [_endpoint(handle_id, f"@{prefix}-{run}-handle", "handle")]
    nodes += [_person(pid, f"Cohort{prefix}", f"Member{i}") for i, pid in enumerate(person_ids)]
    edges = [_edge("USES", pid, handle_id) for pid in person_ids]

    return Cohort(
        nodes=nodes, edges=edges, person_ids=person_ids, shared_id=handle_id
    )


@dataclass
class DeviceLegs:
    """B15's handset and its two SIMs, plus the ids to pivot on."""

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    handset_id: str = ""
    sim_ids: list[str] = field(default_factory=list)


def generate_device_legs(
    *, run_token: str | None = None, include_swapped_sim: bool = True
) -> DeviceLegs:
    """**B15.** One handset with two SIM `Endpoint`s `PAIRED_WITH` it — the SIM-swap shape, where
    "both SIMs link to one device" is *one traversal*, not a special case.

    **The handset is a `Device`, not an `Endpoint`, and the identifiers come from
    `seizure_record.py` rather than being invented here.** Both corrections came from the
    ontology refusing a first attempt: `endpoint_kind` is an enum of
    `msisdn|imsi|email|handle|iban|card` and `imei` is not among them, because an IMEI names a
    handset and `Device` carries it as its own identifier. `PAIRED_WITH` is declared
    `Endpoint -> Device`, which is the same statement made in the edge model.

    Reusing `seizure_record.py`'s constants matters beyond tidiness: B13 ingests that record and
    B15 pivots on the device it names. If this module minted its own IMEI, the ingest and the
    pivot would land on two different handsets that both look right, and B15 would pass against a
    device no seizure record ever mentioned.

    ADR-024 is why these are `PAIRED_WITH` writes rather than resolution output: an E.164 number
    and a 3GPP subscriber identity "name the same SIM by a carrier/HLR record's own say-so, with
    no lexical resemblance a comparison function could ever" use.

    **`include_swapped_sim=False` leaves the second SIM out, and that is what a *seeder* wants.**
    `08_ACCEPTANCE_SCENARIOS.md` B13 ingests "the **later** seizure record"; the swap is what that
    record reveals. Round 13cb seeded both SIMs, which quietly made B13 impossible: the ingest had
    nothing left to create, so no change entry was produced, so the hotlist never fired — found by
    B13 failing with an empty alert list against a correct-looking graph. The seeded state is
    therefore the *earlier* one — a handset with the SIM that was in it before the swap — and the
    ingest supplies the rest.
    """
    run = run_token or new_id()[-8:]
    handset_id = f"seizure-{run}-handset"
    sim_a_id = f"seizure-{run}-sim-a"
    sim_b_id = f"seizure-{run}-sim-b"

    nodes = [
        Node(
            id=handset_id,
            type="Device",
            properties={"imei": HANDSET_IMEI_NORMALISED},
            provenance=_provenance("seizure-record:handset"),
            handling=_handling(),
            audit=_audit(),
        ),
        _endpoint(sim_a_id, SIM_A_IMSI_NORMALISED, "imsi"),
    ]
    edges = [_edge("PAIRED_WITH", sim_a_id, handset_id)]
    sim_ids = [sim_a_id]

    if include_swapped_sim:
        nodes.append(_endpoint(sim_b_id, SIM_B_IMSI_NORMALISED, "imsi"))
        edges.append(_edge("PAIRED_WITH", sim_b_id, handset_id))
        sim_ids.append(sim_b_id)

    return DeviceLegs(nodes=nodes, edges=edges, handset_id=handset_id, sim_ids=sim_ids)


__all__ = [
    "Cohort",
    "DeviceLegs",
    "generate_cohort",
    "generate_device_legs",
    "generate_handle_cohort",
]
