"""Waiting for the search index (ADR-150 Amendment 3, the owner's ruling of 16 November 2026).

Where search reads OpenSearch (the poc and cloud-platform shapes), the index follows a write
through ADR-150's outbox, drained in batches by the indexer: a search made at once after a load or
a drawn grid may not find it yet. v0.6.0's package test (row 4 on 0b51705) found the closing-pass
cases searching at once and failing, the writes landing seconds later. So these ask again until
the index has it, up to a bound, and record how long each waited (the file `OSPREY_SEARCH_WAITS`
names), so the lag is measured on every run rather than assumed. Held by
`tests/scenarios/test_index_wait.py`."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

#: The longest a search waits for the index, and how often it asks.
BOUND, EVERY = 30.0, 1.0


def record(what: str, waited: float, outcome: str) -> None:
    """One line in the run's record of waits, where the run names one."""
    named = os.environ.get("OSPREY_SEARCH_WAITS")
    if named:
        with open(named, "a", encoding="utf-8") as kept:
            kept.write(f"{what}: {outcome} after {waited:.1f} s\n")


def search_until(
    post: Callable[..., Any], path: str, body: dict[str, Any], *, what: str,
    holds: Callable[[list[dict[str, Any]]], bool] = bool,
    clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """The search's answer once its nodes hold what `holds` asks (any node, by default), or the
    last answer when the bound passes or the search is refused: the caller's own assertion then
    says why."""
    start = clock()
    while True:
        answer = post(path, json=body)
        found = answer.status_code == 200 and holds(answer.json()["nodes"])
        if found or answer.status_code != 200 or clock() - start >= BOUND:
            record(what, clock() - start, "found" if found else "not found")
            return answer
        sleep(EVERY)


def settled(
    post: Callable[..., Any], path: str, body: dict[str, Any], *, what: str, quiet: float = 5.0,
    clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """The search's nodes once they have stayed the same for `quiet` seconds (up to the bound):
    after a write that should change nothing, a read made at once would see the index before the
    write reached it, and prove nothing."""
    start = clock()
    last = post(path, json=body).json()["nodes"]
    same_since = clock()
    while clock() - same_since < quiet and clock() - start < BOUND:
        sleep(EVERY)
        now = post(path, json=body).json()["nodes"]
        if [n["id"] for n in now] != [n["id"] for n in last]:
            last, same_since = now, clock()
    record(what, clock() - start, f"settled ({len(last)})")
    return last
