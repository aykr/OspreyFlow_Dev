"""The `scenarios` seed dataset writes what the acceptance rows need — round 13cb.

Owner ruling R8 makes this load-bearing: every acceptance row must be performable through the
analyst's own door on a rendered deployment, and this seeder is what puts the data there. If it
writes the wrong shape, the over-the-wire rows fail four layers downstream with a message about a
missing node, and nothing points back here.

`build_everything()` is separated from the writing precisely so this can be asserted without a
database. The writing itself is already covered — `upsert_nodes`/`upsert_edges` by the graph
conformance suite, and the seed *plumbing* (Conduit stopped, one-shot container, `scripts/` and
`tests/` mounted) by `tests/harness/`.
"""

from __future__ import annotations

from collections import Counter

import duckdb
from scripts.seed_scenarios import (
    SCENARIOS_TOKEN,
    SEIZURE_DATE,
    SHARED_ENDPOINT_ID,
    SHARED_ENDPOINT_VALUE,
    build_everything,
    build_sighting_events,
    load_sighting_events,
)

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from ontology.handling import load_uk_le_scheme
from schemas.analytics import EventFilter, SightingRequest
from schemas.domain import Interval, Principal


def test_b4_b5_the_cohort_converges_on_the_shared_endpoint() -> None:
    nodes, edges, landmarks = build_everything()
    by_id = {n.id: n for n in nodes}

    assert SHARED_ENDPOINT_ID in by_id, "the endpoint B4/B5 converge on was not seeded"
    assert by_id[SHARED_ENDPOINT_ID].properties["value_normalised"] == SHARED_ENDPOINT_VALUE

    people = list(landmarks["cohort_person_ids"])
    assert len(people) == 4

    uses = {(e.source, e.target) for e in edges if e.type == "USES"}
    comms = {(e.source, e.target) for e in edges if e.type == "COMMUNICATED_WITH"}
    for person in people:
        own = [t for s, t in uses if s == person]
        assert len(own) == 1, f"{person} should have exactly one personal endpoint, got {own}"
        assert (own[0], SHARED_ENDPOINT_ID) in comms, (
            f"{person}'s endpoint is not one hop from the shared endpoint, so B5 finds nothing"
        )


def test_b7_the_handle_cohort_shares_one_handle() -> None:
    nodes, edges, landmarks = build_everything()
    handle_id = str(landmarks["handle_id"])
    by_id = {n.id: n for n in nodes}

    assert by_id[handle_id].properties["endpoint_kind"] == "handle"
    users = {e.source for e in edges if e.type == "USES" and e.target == handle_id}
    assert users == set(landmarks["handle_cohort_person_ids"])


def test_b8_seeds_no_same_as_edge() -> None:
    """**The row this seeder deliberately does not seed**, and the reason is a decision record.

    ADR-024: a link between identifier systems with no lexical resemblance "is a direct, asserted
    write, not a probabilistic match". `08_ACCEPTANCE_SCENARIOS.md` B8 says the edge is "asserted
    at score 1.0". So the `SAME_AS` is the *analyst's* act, made over the wire, and seeding one
    here would pre-make the very thing B8 exists to watch an analyst do — a walkthrough that
    passes by finding what the fixture already put there.
    """
    _, edges, _ = build_everything()
    assert not [e for e in edges if e.type == "SAME_AS"], (
        "the seeder wrote a SAME_AS; B8's edge must be asserted by the analyst over the wire"
    )


def test_b15_the_seeder_holds_the_pre_swap_state_only() -> None:
    """**One SIM, not two — corrected in round 13cdb.**

    13cb seeded both, which made B13 impossible: `08_ACCEPTANCE_SCENARIOS.md` B13 ingests "the
    **later** seizure record", and the swap is what that record reveals. With both SIMs already in
    the graph the ingest created nothing, produced no change entry, and the hotlist never fired —
    found by B13 failing against a graph that looked entirely correct.
    """
    nodes, edges, landmarks = build_everything()
    handset = str(landmarks["handset_id"])
    sims = list(landmarks["sim_ids"])
    by_id = {n.id: n for n in nodes}

    assert by_id[handset].type == "Device", "the handset is a Device; imei is not an endpoint_kind"
    assert len(sims) == 1, (
        f"the seeder holds the pre-swap state and must seed one SIM, not {len(sims)} — seeding "
        "the swapped SIM leaves B13's ingest with nothing to create and no alert fires"
    )
    assert by_id[sims[0]].properties["endpoint_kind"] == "imsi"

    paired = {(e.source, e.target) for e in edges if e.type == "PAIRED_WITH"}
    assert paired == {(sims[0], handset)}


def test_b16_b18_the_sightings_are_an_ordered_track_around_the_seizure_date() -> None:
    """B17 brushes "to the seizure date" and B18 plots "an ordered track".

    **The time is on the `PRESENT_AT` edge's interval, not on an `Event` node.** `Event` declares
    no properties in the ontology and `validate_properties` refuses undeclared ones — a first
    attempt minted `Event` nodes with `occurred_at` and was rejected by name. `PRESENT_AT` is
    declared `temporal: true`, which is where "when the device was here" belongs.
    """
    nodes, edges, landmarks = build_everything()
    by_id = {n.id: n for n in nodes}

    sightings = [e for e in edges if e.type == "PRESENT_AT"]
    assert len(sightings) >= 3, "too few sightings to render as a track"

    moments = [e.interval.valid_from for e in sightings]
    assert all(m is not None for m in moments), (
        "a sighting carries no time, so it cannot be brushed"
    )
    assert moments == sorted(moments), "the sightings are not in time order, so B18 has no track"
    assert len(set(moments)) == len(moments), "simultaneous sightings cannot animate under playback"

    for moment in moments:
        assert moment.date() == SEIZURE_DATE.date(), (
            f"sighting at {moment} is not on the seizure date, so B17's brush finds nothing"
        )

    handset = str(landmarks["handset_id"])
    assert all(e.source == handset for e in sightings), (
        "the sightings are not attached to the seized handset, so pivoting on it finds no track"
    )
    assert all(by_id[e.target].type == "Location" for e in sightings)


def test_every_location_carries_a_geometry_reference() -> None:
    """Without `geometry_ref` nothing renders on the map, and B17/B18 are map rows."""
    nodes, _, _ = build_everything()
    for node in (n for n in nodes if n.type == "Location"):
        assert node.properties.get("geometry_ref"), f"{node.id} has no geometry_ref"
        assert node.properties.get("name"), f"{node.id} has no name"


def test_seeding_twice_produces_identical_elements() -> None:
    """A rendered deployment can be seeded more than once. With a pinned token the second seed
    upserts the same ids rather than accumulating a second, parallel cohort — which would make
    B5's "the one endpoint shared by all four" quietly false."""
    first_nodes, first_edges, first_landmarks = build_everything()
    second_nodes, _, second_landmarks = build_everything()

    assert [n.id for n in first_nodes] == [n.id for n in second_nodes]
    assert first_landmarks == second_landmarks
    # Edge ids are minted fresh, but the pairs they connect must not move.
    assert {(e.type, e.source, e.target) for e in first_edges} == {
        (e.type, e.source, e.target) for e in build_everything()[1]
    }


def test_the_pinned_token_is_what_the_over_the_wire_test_will_look_for() -> None:
    """The coupling, stated. The over-the-wire rows address seeded elements by these names; a
    change here without a change there fails downstream with no pointer back."""
    _, _, landmarks = build_everything()
    assert SCENARIOS_TOKEN == "scenarios"
    assert str(landmarks["handset_id"]).endswith(SCENARIOS_TOKEN + "-handset")
    assert str(landmarks["handle_id"]).endswith(SCENARIOS_TOKEN + "-handle")


def test_nothing_outside_the_reserved_drama_range_is_written() -> None:
    """`CLAUDE.md` rule 9 at the seeder boundary — this is the module that writes into a real
    deployment, so it is the right place to assert it rather than to assume the fixture did."""
    nodes, _, _ = build_everything()
    for node in (n for n in nodes if n.type == "Endpoint"):
        kind = node.properties["endpoint_kind"]
        value = node.properties["value_normalised"]
        if kind == "msisdn":
            assert value.startswith("+44770090"), f"{value} is not in the reserved drama range"
        elif kind == "handle":
            assert value.startswith("@")
        else:
            assert kind in {"imei", "imsi"}, kind
            assert value.isdigit(), value


def test_the_seed_counts_are_what_the_rows_need() -> None:
    """A single assertion of the whole shape, so an accidental change is visible as a number
    rather than only as a downstream failure."""
    nodes, edges, _ = build_everything()
    assert dict(Counter(n.type for n in nodes)) == {
        "Endpoint": 8,
        "Device": 1,
        "Person": 8,
        "Location": 4,
    }
    assert dict(Counter(e.type for e in edges)) == {
        "USES": 8,
        "COMMUNICATED_WITH": 4,
        "PAIRED_WITH": 1,
        "PRESENT_AT": 4,
    }


def test_a15_one_node_is_marked_consult_originator() -> None:
    """**A15's export block needs something to block on** — round 13cdc.

    `08_ACCEPTANCE_SCENARIOS.md` A15: "Items marked consult-originator block the export by name."
    No seeded population carried `sanitisation_code: "S2"`, so that clause had never been walked
    on a deployment; REPORT-13b recorded it as the reason A15 was only "partly" over the wire.

    **It is in this population and not Fixture Corp's**, because ADR-035 §C5's re-measured
    resolution scores are computed from Fixture Corp and adding a node there moves them.
    """
    nodes, _, landmarks = build_everything()
    by_id = {n.id: n for n in nodes}

    marked = [n for n in nodes if n.handling.sanitisation_code == "S2"]
    assert len(marked) == 1, f"expected exactly one consult-originator node, got {len(marked)}"
    assert marked[0].id == landmarks["consult_originator_node_id"]

    # **S2 is the consult-originator code in the scheme, not by assumption.**
    scheme = load_uk_le_scheme()
    assert scheme.sanitisation_codes["S2"].consult_originator is True

    # Readable like any other node: `sanitisation_code` never gates a read, and A15 is about the
    # *export* boundary. A node the analyst could not see would prove the wrong thing.
    node = by_id[landmarks["consult_originator_node_id"]]
    assert node.handling.classification == "OFFICIAL"
    assert node.properties["value_normalised"] == landmarks["consult_originator_value"]


def test_fixture_corps_population_is_untouched_by_this_seeder() -> None:
    """ADR-035 §C5's scores are computed from Fixture Corp. This seeder must not add to it —
    the brief for round 13cdc says so, and `test_fixture_corp_shape.py` is what would fail."""
    nodes, _, _ = build_everything()
    assert not [n for n in nodes if n.id.startswith("corp-")], (
        "the scenarios seeder is writing Fixture Corp nodes, which would move ADR-035 §C5's "
        "re-measured resolution scores"
    )


async def test_b18_the_seeded_sightings_are_the_ones_the_glass_trail_reads() -> None:
    """**B18's trail, through the function the Glass actually calls — round 13cde.**

    The Glass's snail trail is `POST /v1/analytics/sightings`, which is `AnalyticsPort.
    list_sightings` over the analytics store's `events` rows. This seeder used to write the
    sightings only as graph `PRESENT_AT` edges, so the over-the-wire B18 case (which reads the
    graph) passed while the Glass, reading the analytics store, drew nothing — measured in a real
    browser: the request carried the right entity, scope and window and came back `[]`. Two
    tiers were measuring two different populations.

    `EventRecord`'s own docstring says an event is "one occurrence of" a summarised graph edge, so
    each sighting is both, tied by `edge_id`. This case asserts the property the Glass depends on:
    the seeded rows come back through `list_sightings`, filtered **exactly as `App.tsx` filters**
    (`buildEventFilter(scope, window, [selectedNode.id])` — the handset, the seizure day), for a
    principal shaped like the demo analyst's token. Seeding twice must not double the track.
    """
    nodes, edges, landmarks = build_everything()
    scope = "inv-under-test"
    handset = str(landmarks["handset_id"])
    events = build_sighting_events(edges, investigation_scope=scope)

    present_at = {e.id: e for e in edges if e.type == "PRESENT_AT"}
    assert {ev.edge_id for ev in events} == set(present_at), (
        "every sighting edge needs exactly one occurrence in the analytics store, tied by edge_id"
    )

    con = duckdb.connect(":memory:")
    scheme = load_uk_le_scheme()
    assert await load_sighting_events(con, scheme, events) == len(events)
    assert await load_sighting_events(con, scheme, events) == 0, (
        "a second seed wrote the sightings again; re-seeding must not double the track"
    )

    day = SEIZURE_DATE.replace(hour=0)
    request = SightingRequest(
        filter=EventFilter(
            investigation_scope=scope,
            window=Interval(valid_from=day, valid_to=day.replace(day=day.day + 1)),
            node_ids=[handset],
        )
    )
    demo_analyst = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
    track = await AnalyticsDuckDBAdapter(con, scheme).list_sightings(request, demo_analyst)

    assert len(track) == len(present_at), (
        f"the Glass's own sightings request returns {len(track)} of {len(present_at)} seeded "
        "sightings — the trail it draws is not the track this seeder wrote"
    )
    assert [s.occurred_at for s in track] == sorted(
        e.interval.valid_from for e in present_at.values()
    )
