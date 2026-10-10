"""AML typology rules (`06_DECISIONS.md` ADR-108 phase D, ruling Q3): structuring, rapid movement
and circular flows, as pure rules over the engine's own transaction shape — chosen over the
copyleft AML libraries the licence register refuses (CoreNLP GPLv3, Jube AGPL) and the unverifiable
commercial one. A hit is a **suggestion** carrying the transactions that make it, for a person to
judge (rule 5); nothing here writes to any store.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class MoneyFlow:
    """One movement of value, as a loaded `TRANSACTED` link reads: ends, amount, when, and the
    reference a hit cites."""

    source: str
    target: str
    amount: float
    at: datetime
    ref: str


@dataclass(frozen=True)
class TypologyHit:
    typology: str
    #: The account (or pair) the pattern centres on.
    subject: str
    #: The refs of the flows that make the pattern — every one, so a reviewer sees the whole case.
    refs: tuple[str, ...]
    #: The finding in words a reviewer can act on.
    words: str


def structuring(
    flows: list[MoneyFlow],
    *,
    threshold: float,
    window: timedelta,
    minimum_count: int,
) -> list[TypologyHit]:
    """Several sub-threshold amounts from one source to one target, inside the window, summing
    past the threshold — the classic splitting of one reportable movement into unreportable ones.
    An amount at or over the threshold is not structuring; it was reportable as it stood."""
    hits: list[TypologyHit] = []
    by_pair: dict[tuple[str, str], list[MoneyFlow]] = defaultdict(list)
    for f in flows:
        if f.amount < threshold:
            by_pair[(f.source, f.target)].append(f)
    for (source, target), pair_flows in sorted(by_pair.items()):
        ordered = sorted(pair_flows, key=lambda f: f.at)
        start = 0
        best: list[MoneyFlow] = []
        for end in range(len(ordered)):
            while ordered[end].at - ordered[start].at > window:
                start += 1
            inside = ordered[start : end + 1]
            if len(inside) >= minimum_count and sum(f.amount for f in inside) > threshold:
                if len(inside) > len(best):
                    best = inside
        if best:
            total = sum(f.amount for f in best)
            hits.append(
                TypologyHit(
                    typology="structuring",
                    subject=f"{source}->{target}",
                    refs=tuple(f.ref for f in best),
                    words=(
                        f"{len(best)} movements from {source} to {target}, each below "
                        f"{threshold:,.0f}, sum to {total:,.0f} within "
                        f"{window.days} day(s) — a reportable amount moved unreportably"
                    ),
                )
            )
    return hits


def rapid_movement(
    flows: list[MoneyFlow],
    *,
    within: timedelta,
    keep_fraction: float,
) -> list[TypologyHit]:
    """Money in and straight back out of an account: an outgoing movement within the window of an
    incoming one, carrying at least `keep_fraction` of it — the account is a conduit, not a home."""
    hits: list[TypologyHit] = []
    incoming: dict[str, list[MoneyFlow]] = defaultdict(list)
    for f in flows:
        incoming[f.target].append(f)
    for out in sorted(flows, key=lambda f: f.at):
        for arrived in incoming.get(out.source, []):
            gap = out.at - arrived.at
            if timedelta(0) <= gap <= within and out.amount >= keep_fraction * arrived.amount:
                hours = gap.total_seconds() / 3600
                hits.append(
                    TypologyHit(
                        typology="rapid_movement",
                        subject=out.source,
                        refs=(arrived.ref, out.ref),
                        words=(
                            f"{arrived.amount:,.0f} arrived at {out.source} and "
                            f"{out.amount:,.0f} left within {hours:.1f} hour(s) — "
                            "the account is a pass-through"
                        ),
                    )
                )
    return hits


def circular_flows(flows: list[MoneyFlow], *, max_hops: int) -> list[TypologyHit]:
    """Value returning to where it started within `max_hops` movements, each later than the one
    before — layering that goes nowhere but around."""
    onward: dict[str, list[MoneyFlow]] = defaultdict(list)
    for f in flows:
        onward[f.source].append(f)
    hits: list[TypologyHit] = []
    seen_cycles: set[frozenset[str]] = set()

    def walk(origin: str, at: str, path: list[MoneyFlow]) -> None:
        if len(path) > max_hops:
            return
        for step in onward.get(at, []):
            if path and step.at <= path[-1].at:
                continue
            taken = [*path, step]
            if step.target == origin and len(taken) >= 2:
                cycle = frozenset(f.ref for f in taken)
                if cycle not in seen_cycles:
                    seen_cycles.add(cycle)
                    hits.append(
                        TypologyHit(
                            typology="circular_flow",
                            subject=origin,
                            refs=tuple(f.ref for f in taken),
                            words=(
                                f"value left {origin} and returned to it over "
                                f"{len(taken)} movements — layering in a circle"
                            ),
                        )
                    )
                continue
            if len(taken) < max_hops and step.target not in {f.source for f in taken}:
                walk(origin, step.target, taken)

    for start in sorted({f.source for f in flows}):
        walk(start, start, [])
    return hits
