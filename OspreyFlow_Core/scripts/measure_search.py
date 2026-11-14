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
from collections.abc import Callable, Iterator, Sequence
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


class TokenRefused(SystemExit):
    """The Conduit refused the token (401): it expired or was never valid. Every figure from here
    would time a refusal, so the run stops and says its figures are void rather than finishing as
    if it had measured (step 4's rerun on d, 14 November 2026: the tokens died at 300 s and M4,
    M3, M1, M6 and M10 ran on, refused)."""


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
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise TokenRefused(
                f"the Conduit refused the token (HTTP 401) on {path}: it has expired or was never "
                "valid, so this run's figures from here are void; the run stops"
            ) from error
        return (time.perf_counter() - started) * 1000, None, f"{type(error).__name__}: {error}"
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
    M6's figure. No route removes a board or its items: the board and the drawn nodes stay in the
    case, each named `M6 <unique>` (ADR-149 Amendment 2 records it)."""
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


def _strings(value: Any) -> Iterator[str]:
    """Every string in an answer, keys and values, at any depth: where an id or word could show."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, inner in value.items():
            yield str(key)
            yield from _strings(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _strings(inner)


def _answer_strings(answer: dict[str, Any], sent: str) -> list[str]:
    """Every string in an answer but its echo of the query sent (`SearchPageResponse.query`): a case
    that asks a hidden record's own words gets them back there, which is what the caller sent, not
    a leak (rules' M10 analysis, 14 November 2026: all 500 leak cases failed on their own echo).
    Only an echo equal to what was sent is left out; anything else under that key is read."""
    if answer.get("query") == sent:
        answer = {k: v for k, v in answer.items() if k != "query"}
    return list(_strings(answer))


#: The share of a file's cases whose control must reach its record on page 1 for M10 to count as
#: measured (the orchestrator's ruling of 14 November 2026, on rules' M10 analysis).
REACHED_AT_LEAST = 0.9


def _leak_request(case: str, leak: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if leak.get("route", "search") == "suggest":
        return f"/v1/investigations/{case}/suggest", {"query": leak["query"], "limit": 10}
    body: dict[str, Any] = {"query": leak["query"], "page": 1, "page_size": 20}
    if "filters" in leak:
        body["filters"] = leak["filters"]
    return f"/v1/investigations/{case}/search", body


def measure_leaks(
    *, base: str, case: str, token: str, controls: dict[str, str], cases: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """M10, the leak test at scale (requirement a; ADR-149 Amendment 2): each case a query, from
    B's plants, that matches a record the part-cleared principal (`token`) may not see. As that
    principal, through the routes the Glass calls, none of its `never_ids` and none of its
    `never_text` (the record's distinguishing words, not ones it shares with visible look-alikes)
    may appear anywhere in the answer: results, merged entities, passages, suggestions, labels or
    filters. Where the truth gives them, `expect_total` and `expect_groups` ({key: count}) must be
    the counts of what they may see. The answer must be the index's. **The control:** the same
    request as the case's control (`controls[case["control"]]`, a principal cleared for SECRET
    with code R in the hidden record's owning unit: a restricted code is read only in its own
    unit, so one principal cannot be the control for every unit; for a never-join case, asked in
    its `partner_case`) must name every `never_ids`, or the case reaches nothing hidden and
    proves nothing: it is reported apart, `indeterminate`, never a pass and never a leak, and the
    file is `unmeasured` unless the controls of at least `REACHED_AT_LEAST` of its cases reach their
    record (the orchestrator's ruling of 14 November 2026). A case whose control is missing, not
    given or answers an error fails, never skipped. The answer's echo of the query sent is not read
    (`_answer_strings`). Pass or fail, not a time: any leak fails M10, whatever share is reached."""
    if not cases:
        raise SystemExit("M10: no leak cases: the test would pass having asked nothing")
    failures: list[str] = []
    indeterminate: list[str] = []
    for i, leak in enumerate(cases):
        name = leak.get("name") or f"case {i + 1} ({leak.get('route', 'search')} {leak['query']!r})"
        path, body = _leak_request(case, leak)
        unit = leak.get("control")
        if unit not in controls:
            failures.append(
                f"{name}: no control token for {unit!r} (given: {', '.join(sorted(controls))}), "
                "so the case proves nothing"
            )
            continue
        # A never-join case's hidden record is in another dataset: its control asks the same query
        # in the partner's own case, which the cleared subject is granted (the orchestrator's
        # ruling (a), 14 November), and the test asks in the measured case.
        control_path = path
        if leak.get("partner_case"):
            control_path, _body = _leak_request(str(leak["partner_case"]), leak)
        _ms, control, error = _send(base, control_path, body, controls[unit])
        seen = set(_strings(control)) if control is not None else set()
        unreached = [n for n in leak["never_ids"] if not any(n in t for t in seen)]
        if control is None:
            failures.append(
                f"{name}: the cleared principal's answer does not name {error}, so "
                "the case reaches nothing hidden and proves nothing"
            )
            continue
        if unreached:
            indeterminate.append(
                f"{name}: the cleared principal's answer does not name {unreached} on page 1, so "
                "the case reaches nothing hidden and proves nothing"
            )
            continue
        _ms, answer, error = _send(base, path, body, token)
        if answer is None:
            failures.append(f"{name}: an error from the Conduit ({error})")
            continue
        if path.endswith("/search") and answer.get("source", "index") != "index":
            failures.append(f"{name}: answered from the {answer.get('source')}, not the index")
            continue
        texts = _answer_strings(answer, leak["query"])
        for node in leak["never_ids"]:
            if any(node in t for t in texts):
                failures.append(f"{name}: the hidden record {node} is in the answer")
        lowered = [t.lower() for t in texts]
        for word in leak.get("never_text", []):
            if any(word.lower() in t for t in lowered):
                failures.append(f"{name}: the hidden record's words {word!r} are in the answer")
        if "expect_total" in leak and answer.get("total") != leak["expect_total"]:
            failures.append(
                f"{name}: total {answer.get('total')}, but they may see {leak['expect_total']}"
            )
        if "expect_groups" in leak:
            groups = {g["key"]: g["count"] for g in answer.get("groups") or []}
            if groups != leak["expect_groups"]:
                failures.append(
                    f"{name}: groups {groups}, but they may see {leak['expect_groups']}"
                )
    reached = len(cases) - len(indeterminate)
    if failures:
        verdict = "not met"
    elif reached < REACHED_AT_LEAST * len(cases):
        verdict = "unmeasured"
    else:
        verdict = "met"
    return {
        "measure": "M10",
        "cases": len(cases),
        "reached": reached,
        "verdict": verdict,
        "failures": failures,
        "indeterminate": indeterminate,
    }


#: M9's figures (ADR-149 Amendment 2): the search service's own timeouts, after which the bar
#: falls back (`services/api/search_service.py`: SEARCH_TIMEOUT, SUGGEST_TIMEOUT).
FALLBACK_WITHIN_MS = {"search": 5000.0, "suggest": 2000.0}
#: How long the index may take to answer again once OpenSearch is back.
RECOVERY_SECONDS = 120.0


def measure_fallback(
    *,
    base: str,
    case: str,
    token: str,
    queries: Sequence[dict[str, Any]],
    stop: Callable[[], None],
    start: Callable[[], None],
    within_ms: dict[str, float] | None = None,
    recovery_seconds: float = RECOVERY_SECONDS,
    poll_seconds: float = 1.0,
) -> dict[str, Any]:
    """M9, the fallback (ADR-149 Amendment 2; the owner's requirement c): OpenSearch stopped
    mid-session (`stop`), each query must answer within its route's timeout, and say so: a search
    from the fallback (`source` "fallback", `limited`, words in `limited_reason`), a suggestion
    from the graph and `limited`. Before the stop, the first query must be the index's (the
    control: a session that never had the index proves nothing). OpenSearch is started again
    (`start`) whatever happens, and the index must answer again within `recovery_seconds`."""
    within = within_ms or FALLBACK_WITHIN_MS
    if not queries:
        raise SystemExit("M9: no queries: the fallback would pass having asked nothing")
    failures: list[str] = []
    timings: list[dict[str, Any]] = []
    first = queries[0]
    path, body = _leak_request(case, {**first, "route": first.get("route", "search")})
    _ms, before, error = _send(base, path, body, token)
    if before is None or before.get("source") not in ("index",):
        answered = error or (before or {}).get("source")
        return {"measure": "M9", "verdict": "not met", "timings": [], "failures": [
            f"before the stop the answer was not the index's ({answered}): a session that never "
            "had the index proves nothing"]}  # fmt: skip
    recovered_s: float | None = None
    try:
        stop()
        for query in queries:
            route = query.get("route", "search")
            path, body = _leak_request(case, {**query, "route": route})
            ms, answer, error = _send(base, path, body, token)
            timings.append({"route": route, "query": query["query"], "ms": round(ms, 1)})
            said = f"{route} {query['query']!r}"
            if answer is None:
                failures.append(f"{said}: an error, not a fallback ({error})")
                continue
            if ms > within[route]:
                failures.append(f"{said}: {ms:.0f} ms, over the {within[route]:.0f} ms timeout")
            if route == "search":
                if answer.get("source") != "fallback":
                    failures.append(
                        f"{said}: answered from the {answer.get('source')}, not the fallback"
                    )
                elif not answer.get("limited") or not (answer.get("limited_reason") or "").strip():
                    failures.append(f"{said}: the fallback did not say so (no limited_reason)")
            elif answer.get("source") == "index" or not answer.get("limited"):
                failures.append(f"{said}: the suggestions did not say they are limited")
    finally:
        start()
    deadline = time.monotonic() + recovery_seconds
    started = time.monotonic()
    while time.monotonic() < deadline:
        path, body = _leak_request(case, {**first, "route": "search"})
        _ms, again, _error = _send(base, path, body, token)
        if again is not None and again.get("source") == "index":
            recovered_s = round(time.monotonic() - started, 1)
            break
        time.sleep(poll_seconds)
    if recovered_s is None:
        failures.append(
            f"the index did not answer again within {recovery_seconds:.0f} s of the start"
        )
    return {
        "measure": "M9",
        "verdict": "not met" if failures else "met",
        "timings": timings,
        "recovered_s": recovered_s,
        "failures": failures,
    }


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
