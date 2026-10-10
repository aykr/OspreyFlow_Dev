"""The pure half of the typology-rule evaluator (`06_DECISIONS.md` ADR-109 phase A).

What a mistake would do, and the case that catches it:

- a rule that fires where it should not (rule 15: a fixture models refusals, not only grants) —
  each typology has a fires case and a refuses case built from the same flows, one parameter apart;
- a flow read from an event that is not a money movement, or with no amount, would invent a
  transaction (`test_only_transacted_events_with_an_amount_become_flows`);
- an alert raised on flows that were already there before this load would re-alert old findings
  (`test_a_hit_counts_only_when_it_cites_an_event_of_this_load`);
- a pre-commit rule judging an incoming event its deployer cannot see would disclose that event
  through the alert (rule 3) — `handling_readable` mirrors the adapters' access predicate on both
  axes (`test_handling_readable_*`);
- an alert node marked lower than something it references would let a reader learn that
  referent exists (rule 3) — `test_the_alert_node_takes_the_highest_handling_of_its_referents`, and
  where no single marking can be safe it is withheld
  (`test_no_alert_marking_when_restricted_referents_belong_to_different_units`);
- the same finding alerted twice (`test_the_same_finding_has_the_same_signature`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from services.api.rule_evaluation import (
    alert_handling,
    context_window,
    flows_from_events,
    handling_readable,
    hit_signature,
    hits_citing,
    run_typology,
)

from ontology.handling import load_uk_le_scheme
from schemas.analytics import EventRecord
from schemas.domain import (
    CircularFlowParams,
    Handling,
    Principal,
    RapidMovementParams,
    StructuringParams,
)

SCHEME = load_uk_le_scheme()
T0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _handling(classification: str = "OFFICIAL", code: str = "P", unit: str = "unit-1") -> Handling:
    return Handling(
        classification=classification, handling_code=code, originator=unit, owning_unit=unit
    )


def _event(
    event_id: str,
    source: str,
    target: str,
    amount: object,
    at: datetime,
    *,
    edge_type: str = "TRANSACTED",
    handling: Handling | None = None,
) -> EventRecord:
    properties = {} if amount is None else {"amount": amount}
    return EventRecord(
        event_id=event_id,
        edge_id=f"edge-{source}-{target}",
        edge_type=edge_type,
        source_id=source,
        target_id=target,
        occurred_at=at,
        properties=properties,
        investigation_scope="case-1",
        handling=handling or _handling(),
    )


def _deposits(count: int, amount: float, *, every: timedelta = timedelta(hours=6)) -> list:
    return flows_from_events(
        [_event(f"d{i}", "mule", "hub", amount, T0 + every * i) for i in range(count)]
    )


# --- flows ------------------------------------------------------------------


def test_only_transacted_events_with_an_amount_become_flows() -> None:
    flows = flows_from_events(
        [
            _event("e1", "a", "b", 9500.0, T0),
            _event("e2", "a", "b", "9600", T0),  # a number as text, as a CSV gives it
            _event("e3", "a", "b", None, T0),  # no amount: not a movement of value
            _event("e4", "a", "b", "n/a", T0),  # not a number
            _event("e5", "a", "b", 100.0, T0, edge_type="COMMUNICATED_WITH"),
        ]
    )
    assert [(f.ref, f.amount) for f in flows] == [("e1", 9500.0), ("e2", 9600.0)]


def test_context_window_follows_each_typologys_own_parameter() -> None:
    assert context_window(
        StructuringParams(threshold=10_000, window_days=7, minimum_count=3)
    ) == timedelta(days=7)
    assert context_window(RapidMovementParams(within_hours=48, keep_fraction=0.8)) == timedelta(
        hours=48
    )
    assert context_window(CircularFlowParams(max_hops=4, window_days=30)) == timedelta(days=30)


# --- each typology: fires, and refuses -------------------------------------


def test_structuring_fires_on_sub_threshold_deposits_summing_past_it() -> None:
    hits = run_typology(
        StructuringParams(threshold=10_000, window_days=7, minimum_count=3), _deposits(4, 9_500)
    )
    assert [h.typology for h in hits] == ["structuring"]
    assert set(hits[0].refs) == {"d0", "d1", "d2", "d3"}


def test_structuring_refuses_when_the_deposits_are_too_few() -> None:
    assert (
        run_typology(
            StructuringParams(threshold=10_000, window_days=7, minimum_count=5),
            _deposits(4, 9_500),
        )
        == []
    )


def test_structuring_refuses_deposits_spread_wider_than_the_window() -> None:
    assert (
        run_typology(
            StructuringParams(threshold=10_000, window_days=1, minimum_count=3),
            _deposits(4, 9_500, every=timedelta(days=2)),
        )
        == []
    )


def _pass_through(out_amount: float, gap: timedelta) -> list:
    return flows_from_events(
        [
            _event("in", "payer", "conduit", 50_000, T0),
            _event("out", "conduit", "offshore", out_amount, T0 + gap),
        ]
    )


def test_rapid_movement_fires_when_most_of_it_leaves_within_the_window() -> None:
    hits = run_typology(
        RapidMovementParams(within_hours=24, keep_fraction=0.8),
        _pass_through(48_000, timedelta(hours=3)),
    )
    assert [(h.typology, h.subject, set(h.refs)) for h in hits] == [
        ("rapid_movement", "conduit", {"in", "out"})
    ]


def test_rapid_movement_refuses_when_too_little_leaves() -> None:
    assert (
        run_typology(
            RapidMovementParams(within_hours=24, keep_fraction=0.8),
            _pass_through(10_000, timedelta(hours=3)),
        )
        == []
    )


def test_rapid_movement_refuses_when_it_leaves_after_the_window() -> None:
    assert (
        run_typology(
            RapidMovementParams(within_hours=24, keep_fraction=0.8),
            _pass_through(48_000, timedelta(hours=30)),
        )
        == []
    )


def _ring(*, close: bool) -> list:
    events = [
        _event("r1", "a", "b", 20_000, T0),
        _event("r2", "b", "c", 19_500, T0 + timedelta(hours=1)),
    ]
    if close:
        events.append(_event("r3", "c", "a", 19_000, T0 + timedelta(hours=2)))
    return flows_from_events(events)


def test_circular_flow_fires_when_value_returns_to_its_origin() -> None:
    hits = run_typology(CircularFlowParams(max_hops=4, window_days=30), _ring(close=True))
    assert hits and all(h.typology == "circular_flow" for h in hits)
    assert set(hits[0].refs) == {"r1", "r2", "r3"}


def test_circular_flow_refuses_an_open_chain() -> None:
    assert run_typology(CircularFlowParams(max_hops=4, window_days=30), _ring(close=False)) == []


def test_circular_flow_refuses_a_ring_longer_than_its_hops() -> None:
    assert run_typology(CircularFlowParams(max_hops=2, window_days=30), _ring(close=True)) == []


# --- what counts as this load's finding ------------------------------------


def test_a_hit_counts_only_when_it_cites_an_event_of_this_load() -> None:
    hits = run_typology(
        StructuringParams(threshold=10_000, window_days=7, minimum_count=3), _deposits(4, 9_500)
    )
    assert hits_citing(hits, {"d3"}) == hits
    assert hits_citing(hits, {"unrelated"}) == []


def test_the_same_finding_has_the_same_signature() -> None:
    params = StructuringParams(threshold=10_000, window_days=7, minimum_count=3)
    (first,) = run_typology(params, _deposits(4, 9_500))
    (again,) = run_typology(params, list(reversed(_deposits(4, 9_500))))
    assert hit_signature("rule-1", first) == hit_signature("rule-1", again)
    assert hit_signature("rule-1", first) != hit_signature("rule-2", first)


# --- access: the predicate, and the alert's marking ------------------------

OFFICIAL_UNIT_1 = Principal(id="p1", clearance="OFFICIAL", org_unit="unit-1")


def test_handling_readable_refuses_a_classification_above_the_clearance() -> None:
    assert handling_readable(SCHEME, OFFICIAL_UNIT_1, _handling("OFFICIAL"))
    assert not handling_readable(SCHEME, OFFICIAL_UNIT_1, _handling("SECRET"))


def test_handling_readable_refuses_a_restricted_code_the_principal_cannot_receive() -> None:
    restricted = _handling(code="R", unit="unit-1")
    assert not handling_readable(SCHEME, OFFICIAL_UNIT_1, restricted)
    receiver = OFFICIAL_UNIT_1.model_copy(update={"receivable_handling_codes": ["R"]})
    assert handling_readable(SCHEME, receiver, restricted)
    # Receivable, but another unit's: still refused, as the adapters refuse it.
    assert not handling_readable(SCHEME, receiver, _handling(code="R", unit="unit-2"))


def test_handling_readable_refuses_an_unknown_clearance() -> None:
    stranger = OFFICIAL_UNIT_1.model_copy(update={"clearance": "NOT-A-LEVEL"})
    assert not handling_readable(SCHEME, stranger, _handling("PUBLIC"))


def test_the_alert_node_takes_the_highest_handling_of_its_referents() -> None:
    marking = alert_handling(
        SCHEME, [_handling("OFFICIAL"), _handling("SECRET", code="C"), _handling("PUBLIC")]
    )
    assert marking is not None
    assert marking.classification == "SECRET"
    assert marking.handling_code == "C"
    # Whoever cannot read every referent cannot read the alert.
    assert not handling_readable(SCHEME, OFFICIAL_UNIT_1, marking)


def test_no_alert_marking_when_restricted_referents_belong_to_different_units() -> None:
    assert (
        alert_handling(SCHEME, [_handling(code="R", unit="unit-1"), _handling(unit="unit-2")])
        is None
    )
    assert alert_handling(SCHEME, []) is None


@pytest.mark.parametrize("unit", ["unit-1", "unit-2"])
def test_one_units_restricted_referents_keep_their_unit(unit: str) -> None:
    marking = alert_handling(SCHEME, [_handling(code="R", unit=unit), _handling(code="R", unit=unit)])
    assert marking is not None
    assert (marking.handling_code, marking.owning_unit) == ("R", unit)


def test_one_transaction_loaded_twice_is_read_once_as_its_first_event() -> None:
    from services.api.rule_evaluation import one_per_transaction

    first = _event("01A", "mule", "hub", 9_500, T0)
    again = _event("01B", "mule", "hub", 9_500, T0)  # the same export, re-run
    other = _event("01C", "mule", "hub", 9_500, T0 + timedelta(hours=1))
    chosen = one_per_transaction([again, other, first])
    assert sorted(e.event_id for e in chosen.values()) == ["01A", "01C"]
