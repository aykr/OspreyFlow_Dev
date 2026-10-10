"""AML typology rules (`06_DECISIONS.md` ADR-108 phase D, ruling Q3): structuring, rapid
movement and circular flows as pure rules on our own engine's transaction shape — never a
copyleft dependency. A hit is a suggestion with the transactions that make it, for a person to
judge (rule 5); nothing here writes anything.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.ingest.typologies import MoneyFlow, circular_flows, rapid_movement, structuring

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def flow(source: str, target: str, amount: float, hours: float = 0.0, ref: str = "") -> MoneyFlow:
    return MoneyFlow(
        source=source,
        target=target,
        amount=amount,
        at=T0 + timedelta(hours=hours),
        ref=ref or f"{source}->{target}@{hours}",
    )


def test_structuring_finds_sub_threshold_amounts_that_sum_past_it() -> None:
    flows = [
        flow("a", "bank", 9_500, 0),
        flow("a", "bank", 9_200, 20),
        flow("a", "bank", 9_800, 40),
    ]
    hits = structuring(flows, threshold=10_000, window=timedelta(days=3), minimum_count=3)
    assert len(hits) == 1
    assert hits[0].typology == "structuring"
    assert set(hits[0].refs) == {f.ref for f in flows}
    assert "28,500" in hits[0].words and "10,000" in hits[0].words


def test_structuring_ignores_amounts_at_or_over_the_threshold() -> None:
    flows = [flow("a", "bank", 10_000, 0), flow("a", "bank", 9_000, 1), flow("a", "bank", 9_000, 2)]
    assert structuring(flows, threshold=10_000, window=timedelta(days=3), minimum_count=3) == []


def test_structuring_respects_the_window() -> None:
    flows = [
        flow("a", "bank", 9_500, 0),
        flow("a", "bank", 9_500, 100),
        flow("a", "bank", 9_500, 200),
    ]
    assert structuring(flows, threshold=10_000, window=timedelta(days=1), minimum_count=3) == []


def test_rapid_movement_finds_money_passing_straight_through() -> None:
    flows = [flow("x", "mule", 20_000, 0, "in"), flow("mule", "y", 19_500, 2, "out")]
    hits = rapid_movement(flows, within=timedelta(hours=6), keep_fraction=0.8)
    assert len(hits) == 1
    assert hits[0].typology == "rapid_movement"
    assert set(hits[0].refs) == {"in", "out"}


def test_rapid_movement_ignores_a_slow_or_partial_pass() -> None:
    slow = [flow("x", "mule", 20_000, 0, "in"), flow("mule", "y", 19_500, 48, "out")]
    assert rapid_movement(slow, within=timedelta(hours=6), keep_fraction=0.8) == []
    partial = [flow("x", "mule", 20_000, 0, "in"), flow("mule", "y", 3_000, 1, "out")]
    assert rapid_movement(partial, within=timedelta(hours=6), keep_fraction=0.8) == []


def test_a_circular_flow_is_found_and_a_chain_is_not() -> None:
    cycle = [flow("a", "b", 5_000, 0), flow("b", "c", 4_900, 1), flow("c", "a", 4_800, 2)]
    hits = circular_flows(cycle, max_hops=4)
    assert len(hits) == 1
    assert hits[0].typology == "circular_flow"
    assert len(hits[0].refs) == 3
    chain = [flow("a", "b", 5_000, 0), flow("b", "c", 4_900, 1), flow("c", "d", 4_800, 2)]
    assert circular_flows(chain, max_hops=4) == []
