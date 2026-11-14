"""v0.5.2 step 4's timer (`process/lanes/platform/v052-measure/PLAN.md`): search and suggestions
timed at the Conduit, through its own routes, as the Glass sends them, signed as one principal.

Each query class (suggestions, names, full text, exact identifiers, ...) is sent `warmup + n`
times; the warm-up is discarded and the rest give a p50, p95, p99 and max. A class is judged
against its budget's **failure figure** (ADR-149 Amendment 2's, `BUDGETS`): "met" or "not
met", with why. Three things are never counted as the index's speed, each making its class "not
met" in words: - an answer from the fallback (`source` is not `index`): its speed is today's
search's, not OpenSearch's; - an exact identifier not ranked first, where the query names the
record it must find (`expect_first`); - an error from the Conduit.

A class with no budget is refused rather than measured against nothing.

python -m scripts.measure_search --base https://<the door> --case <id> --queries <file.jsonl> \\
[--n 200] [--warmup 20] > results.json

The bearer token is read from `OSPREY_MEASURE_TOKEN`, never an argument (it would show in the
process list). Queries are made from B's plants (the `truth` column); none is typed by hand."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

#: The accepted budgets (ADR-149 Amendment 2; the orchestrator's decision 8, 14 November 2026), by
#: the query class the timer sends: the p95's budget and failure figure, and M1's second failure
#: figure, any answer over the fallback's 2 s timeout. Held to the amendment's table both ways by
#: `tests/test_measure_search.py`; a run is never given figures of its own.
BUDGETS: dict[str, dict[str, Any]] = {
    "suggest": {"measure": "M1", "budget_ms": 300.0, "fail_ms": 300.0, "any_over_ms": 2000.0},
    "names": {"measure": "M3", "budget_ms": 1000.0, "fail_ms": 2000.0},
    "fulltext": {"measure": "M4", "budget_ms": 1500.0, "fail_ms": 3000.0},
    # M5: every exact identifier first (a correctness figure), timed as the name search it is.
    "exact": {"measure": "M5", "budget_ms": 1000.0, "fail_ms": 2000.0},
    # M6: a drawn node, from the Conduit's write to the index answering it (`measure_lag`).
    "lag": {"measure": "M6", "budget_ms": 5000.0, "fail_ms": 30000.0},
}
#: The classes `measure` sends as queries; `lag` is timed by `measure_lag`, a write then a poll.
QUERY_CLASSES = tuple(sorted(c for c in BUDGETS if c != "lag"))
#: How often M6 asks the search whether the drawn node is there, and how long before it gives up.
LAG_POLL_SECONDS = 0.1
LAG_GIVE_UP_SECONDS = 60.0

#: The classes sent to the suggestion route; every other class goes to the search route.
SUGGEST_CLASSES = frozenset({"suggest"})


def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


def _send(
    base: str, path: str, body: dict[str, Any], token: str
) -> tuple[float, dict[str, Any] | None, str]:
    request = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            data = json.loads(answer.read())
        return (time.perf_counter() - started) * 1000, data, ""
    except (urllib.error.URLError, OSError, ValueError) as error:
        return (time.perf_counter() - started) * 1000, None, f"{type(error).__name__}: {error}"


def _request(case: str, query: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if query["class"] in SUGGEST_CLASSES:
        return f"/v1/investigations/{case}/suggest", {"query": query["query"], "limit": 10}
    body: dict[str, Any] = {"query": query["query"], "page": 1, "page_size": 20}
    for key in ("group", "filters"):
        if key in query:
            body[key] = query[key]
    return f"/v1/investigations/{case}/search", body


def _problem(query: dict[str, Any], answer: dict[str, Any] | None, error: str) -> str:
    if answer is None:
        return f"an error from the Conduit ({error})"
    if query["class"] not in SUGGEST_CLASSES and answer.get("source", "index") != "index":
        return f"answered from the {answer.get('source')} (not the index's speed)"
    expected = query.get("expect_first")
    if expected:
        results = answer.get("results") or []
        first = results[0] if results else {}
        if (
            expected not in first.get("node_ids", [])
            or first.get("match", {}).get("band") != "identifier"
        ):
            return f"{expected} not ranked first as an exact identifier"
    return ""


def measure(
    *,
    base: str,
    case: str,
    token: str,
    queries: Sequence[dict[str, Any]],
    budgets: dict[str, dict[str, Any]] = BUDGETS,
    n: int,
    warmup: int,
) -> dict[str, Any]:
    classes = sorted({q["class"] for q in queries})
    if "lag" in classes:
        raise SystemExit(
            "lag is not a query class: M6 is timed by measure_lag, a write then a poll"
        )
    unbudgeted = [c for c in classes if c not in budgets]
    if unbudgeted:
        raise SystemExit(
            f"no budget for {', '.join(unbudgeted)}: say what it is measured against first"
        )
    out: dict[str, Any] = {"base": base, "case": case, "n": n, "warmup": warmup, "classes": {}}
    for name in classes:
        mine = [q for q in queries if q["class"] == name]
        times: list[float] = []
        problems: list[str] = []
        for i in range(warmup + n):
            query = mine[i % len(mine)]
            path, body = _request(case, query)
            ms, answer, error = _send(base, path, body, token)
            if i < warmup:
                continue
            times.append(ms)
            problem = _problem(query, answer, error)
            if problem:
                problems.append(problem)
        budget = budgets[name]
        p95 = _percentile(times, 0.95)
        why = []
        if p95 > budget["fail_ms"]:
            why.append(f"p95 {p95:.0f} ms over the failure figure, {budget['fail_ms']:.0f} ms")
        over = budget.get("any_over_ms")
        if over is not None and max(times) > over:
            slow = sum(1 for t in times if t > over)
            why.append(f"{slow} of {len(times)} over {over:.0f} ms (max {max(times):.0f} ms)")
        if problems:
            why.append(f"{len(problems)} of {len(times)}: {sorted(set(problems))[0]}")
        out["classes"][name] = {
            "measure": budget.get("measure", ""),
            "n": len(times),
            "p50_ms": round(_percentile(times, 0.50), 1),
            "p95_ms": round(p95, 1),
            "p99_ms": round(_percentile(times, 0.99), 1),
            "max_ms": round(max(times), 1),
            "budget_ms": budget["budget_ms"],
            "fail_ms": budget["fail_ms"],
            "within_budget": p95 <= budget["budget_ms"] and not problems,
            "verdict": "not met" if why else "met",
            "why": "; ".join(why),
        }
    return out


def measure_lag(
    *,
    base: str,
    case: str,
    token: str,
    n: int,
    warmup: int,
    budget: dict[str, Any] | None = None,
    poll_seconds: float = LAG_POLL_SECONDS,
    give_up_seconds: float = LAG_GIVE_UP_SECONDS,
) -> dict[str, Any]:
    """M6, the index feed's lag (ADR-149 Amendment 2): a node drawn on a board through the Conduit
    (`POST .../boards/{board}/items`, the smallest write through the adapter's `upsert_nodes`, so
    through the outbox in its transaction), timed from the request until the case's search answers
    it from the index (`source` "index"), polled every `poll_seconds`. No route says the indexer
    has drained an event, and the analyst sees the search, so the search is the measure. The board
    is made once, outside the clock. Both requests are signed as one principal (a node on a
    private board is visible to its author). A worker's death mid-run hands the indexer's lease
    over after up to 30 s: a run that meets one is not the steady state, and is not to be read as
    M6's figure. The drawn nodes stay in the case, each named `M6 <unique>`."""
    import uuid

    budget = budget or BUDGETS["lag"]
    ms, board, error = _send(base, f"/v1/investigations/{case}/boards", {"name": "M6"}, token)
    if board is None or "id" not in board:
        raise SystemExit(f"M6: no board to draw on ({error or board})")
    times: list[float] = []
    problems: list[str] = []
    for i in range(warmup + n):
        unique = f"m6{uuid.uuid4().hex[:12]}"
        item = {
            "type": "Person",
            "label": f"M6 {unique}",
            "marking": "OFFICIAL",
            "grading": {"source": "B", "intelligence": "2", "handling": "1"},
            "source_note": "M6",
            "x": 0.2,
            "y": 0.3,
            "properties": {"family_name": unique},
        }
        started = time.perf_counter()
        _ms, made, error = _send(
            base, f"/v1/investigations/{case}/boards/{board['id']}/items", item, token
        )
        if made is None or "element_id" not in made:
            problem = f"the draw was refused ({error or made})"
        else:
            problem = _wait_for(base, case, token, unique, made["element_id"], poll_seconds,
                                started + give_up_seconds)  # fmt: skip
        lag = (time.perf_counter() - started) * 1000
        if i < warmup:
            continue
        times.append(lag)
        if problem:
            problems.append(problem)
    p95 = _percentile(times, 0.95)
    why = []
    if p95 > budget["fail_ms"]:
        why.append(f"p95 {p95:.0f} ms over the failure figure, {budget['fail_ms']:.0f} ms")
    if problems:
        why.append(f"{len(problems)} of {len(times)}: {sorted(set(problems))[0]}")
    return {
        "measure": budget.get("measure", "M6"),
        "n": len(times),
        "p50_ms": round(_percentile(times, 0.50), 1),
        "p95_ms": round(p95, 1),
        "max_ms": round(max(times), 1),
        "budget_ms": budget["budget_ms"],
        "fail_ms": budget["fail_ms"],
        "within_budget": p95 <= budget["budget_ms"] and not problems,
        "verdict": "not met" if why else "met",
        "why": "; ".join(why),
    }


def _wait_for(
    base: str, case: str, token: str, unique: str, node: str, poll: float, deadline: float
) -> str:
    """'' once the index answers `node` for `unique`; else what was wrong. A fallback answer,
    even holding the node, is not the index's, and the polling goes on."""
    body = {"query": unique, "page": 1, "page_size": 20}
    while time.perf_counter() < deadline:
        _ms, answer, _error = _send(base, f"/v1/investigations/{case}/search", body, token)
        if answer is not None and answer.get("source", "index") == "index":
            if any(node in hit.get("node_ids", []) for hit in answer.get("results") or []):
                return ""
        time.sleep(poll)
    return "not searchable from the index in time"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.measure_search", description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument(
        "--queries",
        required=True,
        help="JSON lines: {class, query, [expect_first, group, filters]}",
    )
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    args = parser.parse_args(argv)
    token = os.environ.get("OSPREY_MEASURE_TOKEN", "")
    if not token:
        parser.error(
            "OSPREY_MEASURE_TOKEN is not set: the principal's bearer token, from the environment"
        )
    with open(args.queries, encoding="utf-8") as handle:
        queries = [json.loads(line) for line in handle if line.strip()]
    result = measure(
        base=args.base,
        case=args.case,
        token=token,
        queries=queries,
        n=args.n,
        warmup=args.warmup,
    )
    json.dump(result, sys.stdout, indent=2)
    print()
    return 0 if all(c["verdict"] == "met" for c in result["classes"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
