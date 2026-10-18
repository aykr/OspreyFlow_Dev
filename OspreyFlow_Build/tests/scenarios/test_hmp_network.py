"""The HMP pack's prison intelligence network (`06_DECISIONS.md` ADR-117,
`packages/demo_fixtures/hmp_network.py`): the plan's shape, without a store.

Each test names the story element it protects, since a demonstration walks straight to it: the
principal's cell history, the shared number, the shared payer, the third-party visitor, the call
surge before the finds, the SECRET conflict. The first test checks every node and link against the
deployment ontology, so a property the store would refuse fails here and not in front of an
audience; the last ones check nothing in the plan could be a real identifier (rule 9).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime

from demo_fixtures.hmp_network import (
    COORDINATOR,
    COORDINATOR_PHONE,
    NETWORK_END,
    SECRET_CONFLICT,
    SHARED_ACCOUNT,
    SURGE_START,
    P,
    R,
    plan_network,
    prisoner,
)
from ontology.packs import load_deployment_ontology
from ontology.validation import validate_edge_endpoints, validate_properties


def _type_of(key: str, node_types: dict[str, str]) -> str:
    return "Person" if key.startswith("prisoner:") else node_types[key]


def test_every_node_and_link_is_one_the_deployment_ontology_accepts() -> None:
    ontology = load_deployment_ontology()
    plan = plan_network()
    node_types = {n.key: n.type for n in plan.nodes}
    for node in plan.nodes:
        entity = ontology.entity_type(node.type)
        assert entity is not None, node.type
        validate_properties(entity, node.properties)
    for edge in plan.edges:
        edge_type = ontology.edge_type(edge.type)
        assert edge_type is not None, edge.type
        validate_properties(edge_type, edge.properties)
        validate_edge_endpoints(
            edge_type,
            source_type=_type_of(edge.source, node_types),
            target_type=_type_of(edge.target, node_types),
        )
        assert (edge.interval is not None) or not edge_type.temporal or edge.type in {
            "USES", "HOLDS_ACCOUNT"
        }, f"{edge.type} is temporal and has no interval"


def test_the_plan_is_the_same_every_time() -> None:
    first, second = plan_network(), plan_network()
    assert [(n.key, n.properties) for n in first.nodes] == [
        (n.key, n.properties) for n in second.nodes
    ]
    assert [(e.type, e.source, e.target, e.events) for e in first.edges] == [
        (e.type, e.source, e.target, e.events) for e in second.edges
    ]


def test_every_link_type_a_prison_analyst_filters_by_is_present() -> None:
    types = Counter(e.type for e in plan_network().edges)
    for name in ("SHARED_CELL_WITH", "CO_DEFENDANT_OF", "IN_CONFLICT_WITH", "VISITED",
                 "ROLE_IN", "COMMUNICATED_WITH", "TRANSACTED"):
        assert types[name] > 0, f"no {name} link"


def test_the_principal_has_the_long_cell_history() -> None:
    mates = {
        e.target if e.source == prisoner(P) else e.source
        for e in plan_network().edges
        if e.type == "SHARED_CELL_WITH" and prisoner(P) in (e.source, e.target)
    }
    assert len(mates) >= 14


def test_the_principal_and_three_relay_members_call_one_outside_number() -> None:
    plan = plan_network()
    pin_owner = {e.target: e.source for e in plan.edges if e.type == "USES"}
    callers = {
        pin_owner[e.source]
        for e in plan.edges
        if e.type == "COMMUNICATED_WITH" and e.target == COORDINATOR_PHONE
    }
    assert prisoner(P) in callers
    assert len(callers & {prisoner(i) for i in R}) == 3


def test_one_outside_account_pays_the_principal_and_two_relay_members() -> None:
    plan = plan_network()
    holder = {e.target: e.source for e in plan.edges if e.type == "HOLDS_ACCOUNT"}
    payees = {
        holder[e.target]
        for e in plan.edges
        if e.type == "TRANSACTED" and e.source == SHARED_ACCOUNT
    }
    assert prisoner(P) in payees
    assert len(payees & {prisoner(i) for i in R}) == 2


def test_the_coordinator_visits_the_principal_in_person_and_a_relay_member_by_video() -> None:
    visits = {
        (e.target, e.properties["channel"])
        for e in plan_network().edges
        if e.type == "VISITED" and e.source == COORDINATOR
    }
    assert (prisoner(P), "in_person") in visits
    assert any(t in {prisoner(i) for i in R} and c == "video" for t, c in visits)


def test_calls_to_the_coordinator_surge_before_the_finds() -> None:
    calls = [
        ev.at
        for e in plan_network().edges
        if e.type == "COMMUNICATED_WITH" and e.target == COORDINATOR_PHONE
        for ev in e.events
    ]
    surge = datetime.combine(SURGE_START, datetime.min.time(), tzinfo=UTC)
    assert sum(at >= surge for at in calls) / len(calls) > 0.6


def test_one_conflict_is_secret_and_it_is_the_principal_s() -> None:
    secret = [e for e in plan_network().edges if e.classification == "SECRET"]
    assert [(e.type, e.source, e.target) for e in secret] == [
        ("IN_CONFLICT_WITH", prisoner(SECRET_CONFLICT[0]), prisoner(SECRET_CONFLICT[1]))
    ]


def test_finds_fall_in_the_incident_window_and_involve_the_relay_group() -> None:
    plan = plan_network()
    finds = [n for n in plan.nodes if n.type == "Incident" and n.properties["category"] == "find"]
    assert len(finds) >= 10
    for find in finds:
        at = datetime.fromisoformat(find.properties["occurred_at"])
        assert at.date() <= NETWORK_END and at.year == 2026
    holders = {
        e.source for e in plan.edges
        if e.type == "ROLE_IN" and e.properties["role"] == "found in possession"
    }
    assert holders <= {prisoner(i) for i in R}


def test_every_link_with_events_has_one_summarised_edge_per_occurrence_count() -> None:
    for edge in plan_network().edges:
        assert edge.occurrences == max(1, len(edge.events))


def test_no_identifier_could_be_a_real_one() -> None:
    """Rule 9: drama-range phone numbers, never-issued `QQ` National Insurance numbers, the
    fixture's own prison numbers and a fictional bank."""
    plan = plan_network()
    for node in plan.nodes:
        props = node.properties
        if "e164" in props:
            assert re.fullmatch(r"\+447700900\d{3}", props["e164"]), props["e164"]
        if "nino" in props:
            assert props["nino"].startswith("QQ"), props["nino"]
        if node.type == "Account":
            assert props["institution"] in {"Fictional Bank", "HMP Hollywood private cash"}
    assert all(
        re.fullmatch(r"prisoner:\d+", e.source) or not e.source.startswith("prisoner")
        for e in plan.edges
    )


def test_the_seed_s_marker_incident_is_one_the_plan_writes() -> None:
    """`seed_hmp_fixture` takes `FIRST_INCIDENT_REF` in a store to mean the network is there, and
    writes nothing. Catches the marker naming an incident the plan never writes: a second run would
    then write the whole network again."""
    from demo_fixtures.hmp_network import FIRST_INCIDENT_REF

    refs = [n.properties["incident_ref"] for n in plan_network().nodes if n.type == "Incident"]
    assert refs[0] == FIRST_INCIDENT_REF


def test_the_prison_is_where_its_yards_are() -> None:
    """Catches the network's visits and incidents drawn at a different place from the fixture's own
    yard incidents (`hmp.py`): the map would show one prison in two places."""
    from demo_fixtures.hmp import _YARD_COORDINATES
    from demo_fixtures.hmp_network import PRISON_POINT

    lats = [lat for lat, _ in _YARD_COORDINATES.values()]
    lons = [lon for _, lon in _YARD_COORDINATES.values()]
    assert min(lats) <= PRISON_POINT[0] <= max(lats)
    assert min(lons) <= PRISON_POINT[1] <= max(lons)


def test_an_account_is_named_after_the_person_who_holds_it() -> None:
    """Catches an account's display name naming someone other than its holder — the demonstration
    reads the name aloud while pointing at the holder."""
    plan = plan_network()
    people = {n.key: n.properties for n in plan.nodes if n.type == "Person"}
    names = {n.key: n.properties["name"] for n in plan.nodes if n.type == "Account"}
    for edge in plan.edges:
        if edge.type == "HOLDS_ACCOUNT" and edge.source in people:
            holder = people[edge.source]
            assert holder["family_name"].title() in names[edge.target], (edge.target, holder)
