"""v052-measure's timer (`scripts/measure_search.py`), held to what it claims before it is trusted
on B's load (rule 15: a timer shown only on a fast server has been exercised, not tested).
Against a stub Conduit that answers the two routes as 3d's frozen shape does
(`SEARCH_RESPONSE_SHAPE.md`), and can be made slow, answer from the fallback, or rank an exact
identifier second: each must turn the class's verdict to "not met"."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from scripts import measure_search


class _Conduit(BaseHTTPRequestHandler):
    delay = 0.0
    source = "index"
    exact_first = True
    seen: list[tuple[str, dict[str, Any], str]] = []
    # M6: how long a drawn node takes to reach the index, whether the draw is refused, and the
    # drawn nodes (their family name, their id, when they were drawn).
    lag = 0.0
    refuse_draw = False
    drawn: dict[str, tuple[str, float]] = {}
    # M10: a world with one hidden record, hid-1 ("Ravenscar Kestral"), which the cleared token
    # sees; `leak` makes the part-cleared answer leak it as an id, its words, or a count, and
    # "unreached" makes the cleared answer miss it (a case that proves nothing).
    leak_world = False
    leak = ""
    # A never-join world: hid-1 is in another dataset, read only in its own case, case-partner.
    partner_only = False
    # M9: OpenSearch stopped (`index_down`), and how the fallback misbehaves: "slow", "silent"
    # (no words), "stuck" (the stop does not take), "never_back" (the start does not).
    index_down = False
    fallback = ""
    # A token's life, as the Conduit meets it: after `expires_after` requests every request is
    # refused with 401, as Keycloak's token is once its `exp` passes (step 4's rerun on d, 14
    # November 2026: the realm's default 300 s, every send after about five minutes refused).
    # `control_fails`: the cleared principal's request answered with this status instead.
    expires_after = 0
    control_fails = 0

    def do_POST(self) -> None:  # noqa: N802 - http.server's name
        if self.path.startswith("/_control/"):  # the stand-in docker's stop and start (M9)
            _Conduit.index_down = self.path.endswith("/stop")
            self.send_response(204)
            self.end_headers()
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.seen.append((self.path, body, self.headers.get("Authorization", "")))
        time.sleep(self.delay)
        if self.expires_after and len(self.seen) > self.expires_after:
            self._refuse(401, {"detail": "the token has expired"})
            return
        if self.control_fails and self.headers.get("Authorization", "").startswith(
            "Bearer cleared-"
        ):
            self._refuse(self.control_fails, {"detail": "the store is unavailable"})
            return
        status = 200
        if self.index_down and self.path.endswith(("/search", "/suggest")):
            answer = self._fallback_answer()
        elif self.leak_world and self.path.endswith(("/search", "/suggest")):
            answer = self._leak_answer(
                self.headers.get("Authorization", "") == "Bearer cleared-unit-fiu",
                str(body.get("query", "")),
            )
        elif self.path.endswith("/suggest"):
            answer: dict[str, Any] = {"nodes": [{"id": "n1"}], "more": False}
        elif self.path.endswith("/boards"):
            status, answer = 201, {"id": "board-1", "name": body["name"]}
        elif self.path.endswith("/items"):
            if self.refuse_draw:
                status, answer = 403, {"detail": "no draw right"}
            else:
                node = f"drawn-{len(self.drawn)}"
                self.drawn[body["properties"]["family_name"]] = (node, time.monotonic())
                status, answer = 201, {"element_id": node, "item_id": f"i-{node}"}
        else:
            hits = [
                {"node_ids": ["exact-1"], "match": {"band": "identifier"}},
                {"node_ids": ["close-1"], "match": {"band": "name_typo"}},
            ]
            found = self.drawn.get(body.get("query", ""))
            if found and time.monotonic() - found[1] >= self.lag:
                hits = [{"node_ids": [found[0]], "match": {"band": "name_exact"}}]
            answer = {
                "source": self.source,
                "limited": self.source != "index",
                "total": len(hits),
                "groups": [],
                "results": hits if self.exact_first else hits[::-1],
                "nodes": [],
            }
        data = json.dumps(answer).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _refuse(self, status: int, answer: dict[str, Any]) -> None:
        data = json.dumps(answer).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _fallback_answer(self) -> dict[str, Any]:
        if self.fallback == "slow":
            time.sleep(0.3)
        silent = self.fallback == "silent"
        if self.path.endswith("/suggest"):
            return {
                "nodes": [{"id": "n1"}],
                "more": False,
                "source": "graph",
                "limited": not silent,
            }
        return {
            "source": "fallback",
            "limited": not silent,
            "limited_reason": None if silent else "Search is limited: names starting with this",
            "total": 1, "groups": [],
            "results": [{"node_ids": ["n1"], "match": {"band": "prefix"}}],
            "nodes": [],
        }  # fmt: skip

    def _leak_answer(self, cleared: bool, query: str) -> dict[str, Any]:
        hidden = cleared and self.leak != "unreached"
        if self.partner_only:
            hidden = hidden and "/investigations/case-partner/" in self.path
        visible = [{"node_ids": ["vis-1"], "match": {"band": "name_exact"}, "passage": []}]
        if self.path.endswith("/suggest"):
            nodes = [{"id": "vis-1", "label": "Kestral"}]
            if hidden or (not cleared and self.leak == "id"):
                nodes.append({"id": "hid-1", "label": "Ravenscar Kestral"})
            return {"nodes": nodes, "more": False}
        results = list(visible)
        if hidden:
            results.append({"node_ids": ["hid-1"], "match": {"band": "name_exact"}, "passage": []})
        elif self.leak == "id":
            results[0] = {**results[0], "node_ids": ["vis-1", "hid-1"]}  # a merged entity
        elif self.leak == "text":
            results[0] = {**results[0], "passage": [{"text": "paid by Ravenscar Holdings"}]}
        total = len(results) + (1 if not cleared and self.leak == "count" else 0)
        return {
            # The search page echoes the query as the real one does (`SearchPageResponse.query`):
            # a case that asks a hidden record's own words gets them back in the echo, which is
            # what the caller sent, not a leak (rules' M10 analysis, 14 November 2026). `echo`
            # stands in for a Conduit that put something else under that key.
            "query": "Ravenscar Holdings" if self.leak == "echo" else query,
            "source": self.source,
            "limited": False,
            "total": total,
            "counts_exact": True,
            "groups": [{"key": "Person", "label": "People", "count": total}],
            "results": results,
            "nodes": [],
        }

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def conduit() -> Iterator[str]:
    _Conduit.delay, _Conduit.source, _Conduit.exact_first, _Conduit.seen = 0.0, "index", True, []
    _Conduit.lag, _Conduit.refuse_draw, _Conduit.drawn = 0.0, False, {}
    _Conduit.leak_world, _Conduit.leak, _Conduit.partner_only = False, "", False
    _Conduit.index_down, _Conduit.fallback = False, ""
    _Conduit.expires_after, _Conduit.control_fails = 0, 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Conduit)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


QUERIES = [
    {"class": "suggest", "query": "kes"},
    {"class": "names", "query": "Kestral"},
    {"class": "exact", "query": "ACC-0001", "expect_first": "exact-1"},
]
BUDGETS = {
    "suggest": {"budget_ms": 300, "fail_ms": 300},
    "names": {"budget_ms": 1000, "fail_ms": 2000},
    "exact": {"budget_ms": 1000, "fail_ms": 2000},
}


def _run(base: str, **overrides: Any) -> dict[str, Any]:
    return measure_search.measure(
        base=base,
        case="case-1",
        token="t0ken",
        queries=QUERIES,
        budgets=BUDGETS,
        n=5,
        warmup=1,
        **overrides,
    )


def test_a_fast_conduit_meets_every_budget_and_the_requests_are_the_glass_s(conduit: str) -> None:
    result = _run(conduit)
    assert {c: r["verdict"] for c, r in result["classes"].items()} == {
        "suggest": "met",
        "names": "met",
        "exact": "met",
    }
    paths = {p for p, _b, _a in _Conduit.seen}
    assert paths == {"/v1/investigations/case-1/suggest", "/v1/investigations/case-1/search"}
    assert all(a == "Bearer t0ken" for _p, _b, a in _Conduit.seen)
    for name in ("p50_ms", "p95_ms", "p99_ms", "max_ms"):
        assert result["classes"]["names"][name] >= 0
    assert result["classes"]["names"]["n"] == 5  # the warm-up discarded


def test_a_slow_suggestion_is_not_met_at_its_failure_figure(conduit: str) -> None:
    _Conduit.delay = 0.35  # over the suggestion's 300 ms
    result = _run(conduit)
    assert result["classes"]["suggest"]["verdict"] == "not met"
    assert result["classes"]["suggest"]["p95_ms"] > 300


def test_an_answer_from_the_fallback_is_never_counted_as_the_index_s(conduit: str) -> None:
    """A fast answer from the fallback is not the index's speed: the class is not met, and says
    why."""
    _Conduit.source = "fallback"
    result = _run(conduit)
    assert result["classes"]["names"]["verdict"] == "not met"
    assert "fallback" in result["classes"]["names"]["why"]


def test_an_exact_identifier_ranked_second_is_not_met(conduit: str) -> None:
    _Conduit.exact_first = False
    result = _run(conduit)
    assert result["classes"]["exact"]["verdict"] == "not met"
    assert "first" in result["classes"]["exact"]["why"]


def test_a_class_with_no_budget_is_refused_rather_than_measured_against_nothing(
    conduit: str,
) -> None:
    with pytest.raises(SystemExit, match="no budget"):
        measure_search.measure(
            base=conduit,
            case="case-1",
            token="t",
            queries=[{"class": "dates", "query": "x"}],
            budgets=BUDGETS,
            n=1,
            warmup=0,
        )


# ---- the accepted budgets (ADR-149 Amendment 2; the orchestrator's decision 8, 14 November 2026)

_DECISIONS = Path(__file__).resolve().parents[1] / "spec/06_DECISIONS.md"


def _ms(text: str) -> float:
    number, unit = re.fullmatch(r"([\d.]+) (ms|s)", text.strip()).groups()  # type: ignore[union-attr]
    return float(number) * (1 if unit == "ms" else 1000)


def _amendment_rows() -> dict[str, dict[str, Any]]:
    """The timed rows of ADR-149 Amendment 2's table, by the query class the timer sends."""
    text = _DECISIONS.read_text(encoding="utf-8")
    start = text.index("### ADR-149, Amendment 2 ")
    end = text.find("\n### ", start + 1)
    section = text[start : end if end > 0 else len(text)]
    rows: dict[str, dict[str, Any]] = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or not re.fullmatch(r"M\d+", cells[0]):
            continue
        timed = re.fullmatch(r"`([a-z]+)`", cells[2])
        if not timed:
            continue
        budget = re.fullmatch(r"≤ ([\d.]+ m?s)", cells[3])
        fail = re.match(r"p95 > ([\d.]+ m?s)(?:, or any over ([\d.]+ m?s))?", cells[4])
        assert budget and fail, line
        row: dict[str, Any] = {
            "measure": cells[0],
            "budget_ms": _ms(budget.group(1)),
            "fail_ms": _ms(fail.group(1)),
        }
        if fail.group(2):
            row["any_over_ms"] = _ms(fail.group(2))
        rows[timed.group(1)] = row
    return rows


def test_the_timer_s_budgets_are_the_amendment_s_both_ways() -> None:
    """The figures the timer judges by are ADR-149 Amendment 2's table, row for row: a figure
    changed on one side alone, a class timed with no row, or a row no class times, is red."""
    assert measure_search.BUDGETS == _amendment_rows()


def test_the_run_judges_against_the_accepted_budgets_with_no_file_of_its_own(
    conduit: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No `--budgets` file: a run cannot be judged against a laxer figure than the accepted."""
    queries = tmp_path / "q.jsonl"
    queries.write_text("\n".join(json.dumps(q) for q in QUERIES))
    monkeypatch.setenv("OSPREY_MEASURE_TOKEN", "t0ken")
    code = measure_search.main(
        [
            "--base",
            conduit,
            "--case",
            "case-1",
            "--queries",
            str(queries),
            "--n",
            "3",
            "--warmup",
            "1",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["classes"]["suggest"]["fail_ms"] == measure_search.BUDGETS["suggest"]["fail_ms"]
    assert result["classes"]["suggest"]["measure"] == "M1"
    with pytest.raises(SystemExit):
        measure_search.main(
            ["--base", conduit, "--case", "c", "--queries", str(queries), "--budgets", "lax.json"]
        )


def test_one_suggestion_over_two_seconds_is_not_met_whatever_the_p95(conduit: str) -> None:
    """M1's second failure figure: any answer over 2 s (the fallback's timeout), though the p95
    is within budget, is not met."""
    slow_once = {"first": True}
    original = _Conduit.do_POST

    def do_post(self: _Conduit) -> None:
        if self.path.endswith("/suggest") and slow_once["first"] and len(_Conduit.seen) > 3:
            slow_once["first"] = False
            time.sleep(2.1)
        original(self)

    _Conduit.do_POST = do_post  # type: ignore[method-assign]
    try:
        result = measure_search.measure(
            base=conduit, case="case-1", token="t", queries=QUERIES[:1],
            budgets=measure_search.BUDGETS, n=40, warmup=1,
        )  # fmt: skip
    finally:
        _Conduit.do_POST = original  # type: ignore[method-assign]
    suggest = result["classes"]["suggest"]
    assert suggest["p95_ms"] < 300 and suggest["max_ms"] > 2000
    assert suggest["verdict"] == "not met" and "2000 ms" in suggest["why"]


def test_full_text_is_sent_to_the_search_route_and_judged_at_m4(conduit: str) -> None:
    result = measure_search.measure(
        base=conduit, case="case-1", token="t",
        queries=[{"class": "fulltext", "query": "harbour", "filters": {"dataset": "d1"}}],
        budgets=measure_search.BUDGETS, n=2, warmup=0,
    )  # fmt: skip
    assert result["classes"]["fulltext"]["fail_ms"] == 3000
    assert {p for p, _b, _a in _Conduit.seen} == {"/v1/investigations/case-1/search"}


# ---- the live gate itself (tests/perf/test_search_budget_live.py), run as step 6 runs it

_LIVE = Path(__file__).resolve().parent / "perf/test_search_budget_live.py"


def _run_live(
    tmp_path: Path, base: str | None, extra: dict[str, str] | None = None, only: str = ""
) -> subprocess.CompletedProcess[str]:
    import sys

    queries = tmp_path / "queries.jsonl"
    queries.write_text(
        "\n".join(
            json.dumps(q)
            for q in [
                *QUERIES,
                {"class": "fulltext", "query": "harbour", "filters": {"dataset": "d1"}},
            ]
        )
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("OSPREY_MEASURE_")}
    if base is not None:
        env |= {
            "OSPREY_MEASURE_BASE": base,
            "OSPREY_MEASURE_CASE": "case-1",
            "OSPREY_MEASURE_TOKEN": "t0ken",
            "OSPREY_MEASURE_QUERIES": str(queries),
            "OSPREY_MEASURE_N": "3",
            "OSPREY_MEASURE_LAG_N": "2",
            "OSPREY_MEASURE_WARMUP": "1",
        }
    env["PYTHONPYCACHEPREFIX"] = str(tmp_path / "pyc")
    env |= extra or {}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfs", str(_LIVE)]
        + (["-k", only] if only else []),
        cwd=_LIVE.parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_the_live_gate_passes_a_conduit_within_every_failure_figure(
    conduit: str, tmp_path: Path
) -> None:
    done = _run_live(tmp_path, conduit)
    assert done.returncode == 0, done.stdout[-2000:]
    assert "5 passed, 2 skipped" in done.stdout  # M9 and M10: not named


def test_the_live_gate_fails_a_suggestion_over_its_failure_figure(
    conduit: str, tmp_path: Path
) -> None:
    """Rule 15: the gate shown red, at the real call site (the file step 6 runs), for M1 alone."""
    _Conduit.delay = 0.35
    done = _run_live(tmp_path, conduit)
    assert done.returncode != 0
    assert "FAILED" in done.stdout and "M1-suggest" in done.stdout
    assert "over the failure figure" in done.stdout


def test_the_live_gate_is_skipped_with_its_reason_where_no_stack_is_named(tmp_path: Path) -> None:
    done = _run_live(tmp_path, None)
    assert done.returncode == 0 and "7 skipped" in done.stdout
    assert "no B-sized stack named" in done.stdout


def test_the_live_gate_fails_a_class_its_queries_file_leaves_out(
    conduit: str, tmp_path: Path
) -> None:
    """A named stack whose queries hold no full-text query fails M4, never passes it unmeasured."""
    done = _run_live(tmp_path, conduit)
    assert "5 passed" in done.stdout  # the control: every class present
    (tmp_path / "queries.jsonl").write_text("\n".join(json.dumps(q) for q in QUERIES))
    import sys

    env = {k: v for k, v in os.environ.items() if not k.startswith("OSPREY_MEASURE_")} | {
        "OSPREY_MEASURE_BASE": conduit, "OSPREY_MEASURE_CASE": "case-1",
        "OSPREY_MEASURE_TOKEN": "t",
        "OSPREY_MEASURE_QUERIES": str(tmp_path / "queries.jsonl"),
        "OSPREY_MEASURE_N": "2", "OSPREY_MEASURE_LAG_N": "2",
        "OSPREY_MEASURE_WARMUP": "0", "PYTHONPYCACHEPREFIX": str(tmp_path / "pyc"),
    }  # fmt: skip
    again = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfs", str(_LIVE)],
        cwd=_LIVE.parents[2], env=env, capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert again.returncode != 0 and "M4-fulltext" in again.stdout and "unmeasured" in again.stdout


# ---- M6, the feed's lag (measure_lag)

_LAG = {"measure": "M6", "budget_ms": 150.0, "fail_ms": 250.0}


def test_a_drawn_node_answered_from_the_index_in_time_meets_m6(conduit: str) -> None:
    _Conduit.lag = 0.05
    result = measure_lag_run(conduit, budget=_LAG)
    assert result["verdict"] == "met", result["why"]
    assert result["n"] == 3 and result["p50_ms"] >= 50
    paths = [p for p, _b, _a in _Conduit.seen]
    assert paths.count("/v1/investigations/case-1/boards") == 1, (
        "the board made once, outside the clock"
    )
    assert paths.count("/v1/investigations/case-1/boards/board-1/items") == 4  # one warm-up
    item = next(b for p, b, _a in _Conduit.seen if p.endswith("/items"))
    assert item["type"] == "Person" and item["label"] == f"M6 {item['properties']['family_name']}"
    searched = {b["query"] for p, b, _a in _Conduit.seen if p.endswith("/search")}
    assert searched == set(_Conduit.drawn)
    assert all(a == "Bearer t0ken" for _p, _b, a in _Conduit.seen), "one principal throughout"


def test_a_lag_over_the_failure_figure_is_not_met(conduit: str) -> None:
    _Conduit.lag = 0.4
    result = measure_lag_run(conduit, budget=_LAG)
    assert result["verdict"] == "not met" and "over the failure figure" in result["why"]


def test_the_fallback_answering_the_node_is_never_the_index_s(conduit: str) -> None:
    _Conduit.source = "fallback"
    result = measure_lag_run(conduit, budget=_LAG, give_up_seconds=0.3)
    assert result["verdict"] == "not met" and "not searchable from the index" in result["why"]


def test_a_refused_draw_is_not_met(conduit: str) -> None:
    _Conduit.refuse_draw = True
    result = measure_lag_run(conduit, budget=_LAG)
    assert result["verdict"] == "not met" and "refused" in result["why"]


def test_lag_is_not_sent_as_a_query(conduit: str) -> None:
    with pytest.raises(SystemExit, match="measure_lag"):
        measure_search.measure(
            base=conduit, case="case-1", token="t", queries=[{"class": "lag", "query": "x"}],
            n=1, warmup=0,
        )  # fmt: skip


def measure_lag_run(base: str, **overrides: Any) -> dict[str, Any]:
    return measure_search.measure_lag(
        base=base, case="case-1", token="t0ken", n=3, warmup=1, poll_seconds=0.01, **overrides
    )


def test_the_live_gate_fails_m6_when_no_drawn_node_reaches_the_index(
    conduit: str, tmp_path: Path
) -> None:
    _Conduit.refuse_draw = True
    done = _run_live(tmp_path, conduit)
    assert done.returncode != 0 and "FAILED" in done.stdout and "M6 lag" in done.stdout
    assert "4 passed" in done.stdout, "the query classes are not M6's"


# ---- M10, the leak test at scale (measure_leaks)

LEAKS = [
    {
        "name": "a hidden namesake",
        "control": "unit-fiu",
        "route": "search",
        "query": "Kestral",
        "never_ids": ["hid-1"],
        "never_text": ["Ravenscar"],
        "expect_total": 1,
        "expect_groups": {"Person": 1},
    },
    {
        "name": "a hidden namesake's prefix",
        "control": "unit-fiu",
        "route": "suggest",
        "query": "kes",
        "never_ids": ["hid-1"],
    },
]


#: One cleared control per R-owning unit (the orchestrator's ruling, 14 November 2026): only
#: unit-fiu's sees hid-1, as only a principal of a restricted record's own unit may.
CONTROLS = {"unit-fiu": "cleared-unit-fiu", "unit-border": "cleared-unit-border"}


def _leaks(base: str) -> dict[str, Any]:
    _Conduit.leak_world = True
    return measure_search.measure_leaks(
        base=base, case="case-1", token="part", controls=CONTROLS, cases=LEAKS
    )


def test_nothing_hidden_seen_or_counted_meets_m10(conduit: str) -> None:
    result = _leaks(conduit)
    assert result["verdict"] == "met", result["failures"]
    tokens = {(p, a) for p, _b, a in _Conduit.seen}
    assert ("/v1/investigations/case-1/search", "Bearer cleared-unit-fiu") in tokens, "the control"
    assert not any(a == "Bearer cleared-unit-border" for _p, a in tokens), "only the case's own"
    assert ("/v1/investigations/case-1/suggest", "Bearer part") in tokens


@pytest.mark.parametrize(
    ("leak", "said"),
    [
        ("id", "hid-1 is in the answer"),
        ("text", "'Ravenscar' are in the answer"),
        ("count", "total 2, but they may see 1"),
    ],
)
def test_a_hidden_record_seen_or_counted_fails_m10(conduit: str, leak: str, said: str) -> None:
    _Conduit.leak = leak
    result = _leaks(conduit)
    assert result["verdict"] == "not met"
    assert any(said in f for f in result["failures"]), result["failures"]


def test_a_case_the_cleared_principal_cannot_reach_is_indeterminate_never_a_pass(
    conduit: str,
) -> None:
    """The orchestrator's ruling of 14 November 2026 on rules' M10 analysis: a control that
    answers without naming its record on page 1 is reported apart, as indeterminate, never a pass
    and never a leak; under 90% reached, the file is unmeasured."""
    _Conduit.leak = "unreached"
    result = _leaks(conduit)
    assert result["verdict"] == "unmeasured", result
    assert result["failures"] == [], "an unreached case is not a leak"
    assert len(result["indeterminate"]) == 2 and result["reached"] == 0
    assert all("proves nothing" in f for f in result["indeterminate"])


def _cases(n: int, unreached: int) -> list[dict[str, Any]]:
    """`n` copies of the first case, the last `unreached` of them asked of a control in another
    unit, which answers without the hidden record (it cannot read it)."""
    return [
        {
            **LEAKS[0],
            "name": f"case {i}",
            **({"control": "unit-border"} if i >= n - unreached else {}),
        }
        for i in range(n)
    ]


@pytest.mark.parametrize(
    ("unreached", "verdict"), [(0, "met"), (1, "met"), (2, "unmeasured"), (10, "unmeasured")]
)
def test_m10_is_measured_only_when_90_percent_of_the_controls_reach_their_record(
    conduit: str, unreached: int, verdict: str
) -> None:
    _Conduit.leak_world = True
    result = measure_search.measure_leaks(
        base=conduit, case="case-1", token="part", controls=CONTROLS, cases=_cases(10, unreached)
    )
    assert result["verdict"] == verdict, result
    assert len(result["indeterminate"]) == unreached and result["reached"] == 10 - unreached
    assert result["failures"] == []


def test_a_leak_fails_m10_whatever_share_of_the_controls_is_reached(conduit: str) -> None:
    _Conduit.leak_world, _Conduit.leak = True, "text"
    result = measure_search.measure_leaks(
        base=conduit, case="case-1", token="part", controls=CONTROLS, cases=_cases(10, 5)
    )
    assert result["verdict"] == "not met" and len(result["failures"]) == 5, result


def test_a_case_that_asks_the_hidden_words_is_not_failed_by_the_query_s_own_echo(
    conduit: str,
) -> None:
    """Rules' M10 analysis, 14 November 2026: every leak case asked its hidden document's own
    title, which was its `never_text`, and the search page's echo of the query was read as the
    words leaking, so all 500 failed. The echo is what the caller sent."""
    _Conduit.leak_world = True
    case = {**LEAKS[0], "query": "Ravenscar Kestral", "never_text": ["Ravenscar"]}
    result = measure_search.measure_leaks(
        base=conduit, case="case-1", token="part", controls=CONTROLS, cases=[case]
    )
    assert result["verdict"] == "met", result
    _Conduit.leak = "text"  # and the same words elsewhere in the answer still fail it
    result = measure_search.measure_leaks(
        base=conduit, case="case-1", token="part", controls=CONTROLS, cases=[case]
    )
    assert any("'Ravenscar' are in the answer" in f for f in result["failures"]), result


def test_words_under_the_query_key_that_are_not_the_query_sent_still_fail(conduit: str) -> None:
    _Conduit.leak_world, _Conduit.leak = True, "echo"
    result = _leaks(conduit)
    assert any("'Ravenscar' are in the answer" in f for f in result["failures"]), result


def test_a_fallback_answer_is_not_the_index_s_for_m10(conduit: str) -> None:
    _Conduit.source = "fallback"
    result = _leaks(conduit)
    assert any("not the index" in f for f in result["failures"])


def test_no_leak_cases_is_refused(conduit: str) -> None:
    with pytest.raises(SystemExit, match="asked nothing"):
        measure_search.measure_leaks(
            base=conduit, case="c", token="part", controls=CONTROLS, cases=[]
        )


def _run_live_m10(conduit: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    _Conduit.leak_world = True
    leaks = tmp_path / "leaks.jsonl"
    leaks.write_text("\n".join(json.dumps(c) for c in LEAKS))
    extra = {
        "OSPREY_MEASURE_PART_TOKEN": "part",
        "OSPREY_MEASURE_CONTROLS": json.dumps(CONTROLS),
        "OSPREY_MEASURE_LEAKS": str(leaks),
    }
    return _run_live(tmp_path, conduit, extra, only="m10")


def test_the_live_gate_passes_m10_when_nothing_hidden_shows(conduit: str, tmp_path: Path) -> None:
    done = _run_live_m10(conduit, tmp_path)
    assert done.returncode == 0 and "1 passed" in done.stdout, done.stdout[-1500:]
    asked = {a for p, _b, a in _Conduit.seen if p.startswith("/v1/investigations/case-1/")}
    assert asked == {"Bearer part", "Bearer cleared-unit-fiu"}, (
        "asked as m10-part, never the measure"
    )


def test_the_live_gate_fails_m10_on_a_leak(conduit: str, tmp_path: Path) -> None:
    """Rule 15 at the real call site: the file step 6 runs, red for a hidden id in a merged
    entity."""
    _Conduit.leak = "id"
    done = _run_live_m10(conduit, tmp_path)
    assert (
        done.returncode != 0
        and "M10 not met" in done.stdout
        and "hid-1 is in the answer" in done.stdout
    )


def test_the_live_gate_fails_an_unmeasured_m10_saying_how_many_reached(
    conduit: str, tmp_path: Path
) -> None:
    """Rule 15 at the real call site: indeterminate cases are never a pass."""
    _Conduit.leak = "unreached"
    done = _run_live_m10(conduit, tmp_path)
    assert done.returncode != 0, done.stdout[-1500:]
    assert "M10 unmeasured, 0 of 2 controls reached" in done.stdout, done.stdout[-1500:]


@pytest.mark.parametrize(
    ("control", "said"),
    [
        ("unit-covert", "no control token for 'unit-covert'"),
        (None, "no control token for None"),
    ],
)
def test_a_case_whose_control_is_not_given_fails_never_skips(
    conduit: str, control: str | None, said: str
) -> None:
    _Conduit.leak_world = True
    if control:
        case = {**LEAKS[0], "control": control}
    else:
        case = {k: v for k, v in LEAKS[0].items() if k != "control"}
    result = measure_search.measure_leaks(
        base=conduit, case="case-1", token="part", controls=CONTROLS, cases=[case]
    )
    assert result["verdict"] == "not met" and len(result["failures"]) == 1
    assert said in result["failures"][0] and "proves nothing" in result["failures"][0]


def _never_join(conduit: str, **case: Any) -> dict[str, Any]:
    _Conduit.leak_world = _Conduit.partner_only = True
    leak = {"name": "a partner in another dataset", "control": "unit-fiu", "route": "search",
            "query": "Kestral", "never_ids": ["hid-1"], **case}  # fmt: skip
    return measure_search.measure_leaks(
        base=conduit, case="case-1", token="part", controls=CONTROLS, cases=[leak]
    )


def test_a_never_join_case_s_control_asks_in_the_partner_s_case(conduit: str) -> None:
    """The orchestrator's ruling (a): the partner is read only in its own case, so the control
    asks there, and the test asks in the measured case."""
    result = _never_join(conduit, partner_case="case-partner")
    assert result["verdict"] == "met", result["failures"]
    asked = [(p, a) for p, _b, a in _Conduit.seen]
    assert ("/v1/investigations/case-partner/search", "Bearer cleared-unit-fiu") in asked
    assert ("/v1/investigations/case-1/search", "Bearer part") in asked
    assert ("/v1/investigations/case-partner/search", "Bearer part") not in asked


def test_a_never_join_case_without_its_partner_case_proves_nothing(conduit: str) -> None:
    result = _never_join(conduit)
    assert result["verdict"] == "unmeasured" and result["failures"] == [], result
    assert "proves nothing" in result["indeterminate"][0]


def test_a_never_join_partner_merged_into_the_answer_fails(conduit: str) -> None:
    _Conduit.leak = "id"
    result = _never_join(conduit, partner_case="case-partner")
    assert any("hid-1 is in the answer" in f for f in result["failures"]), result["failures"]


# ---- M9, the fallback (measure_fallback)

_M9_QUERIES = [{"route": "search", "query": "Kestral"}, {"route": "suggest", "query": "kes"}]
_M9_WITHIN = {"search": 250.0, "suggest": 250.0}


def _m9(conduit: str) -> tuple[dict[str, Any], list[str]]:
    calls: list[str] = []

    def stop() -> None:
        calls.append("stop")
        if _Conduit.fallback != "stuck":
            _Conduit.index_down = True

    def start() -> None:
        calls.append("start")
        if _Conduit.fallback != "never_back":
            _Conduit.index_down = False

    result = measure_search.measure_fallback(
        base=conduit, case="case-1", token="t", queries=_M9_QUERIES, stop=stop, start=start,
        within_ms=_M9_WITHIN, recovery_seconds=0.5, poll_seconds=0.05,
    )  # fmt: skip
    return result, calls


def test_the_fallback_answers_in_time_and_says_so_then_the_index_returns(conduit: str) -> None:
    result, calls = _m9(conduit)
    assert result["verdict"] == "met", result["failures"]
    assert calls == ["stop", "start"] and result["recovered_s"] is not None
    assert [t["route"] for t in result["timings"]] == ["search", "suggest"]


@pytest.mark.parametrize(
    ("fallback", "said"),
    [
        ("slow", "over the 250 ms timeout"),
        ("silent", "did not say so"),
        ("stuck", "answered from the index, not the fallback"),
        ("never_back", "did not answer again"),
    ],
)
def test_a_fallback_late_silent_or_absent_or_an_index_never_back_fails_m9(
    conduit: str, fallback: str, said: str
) -> None:
    _Conduit.fallback = fallback
    result, calls = _m9(conduit)
    assert result["verdict"] == "not met"
    assert any(said in f for f in result["failures"]), result["failures"]
    assert calls[-1] == "start", "OpenSearch started again whatever happened"


def test_a_session_that_never_had_the_index_proves_nothing(conduit: str) -> None:
    _Conduit.index_down = True
    result, calls = _m9(conduit)
    assert result["verdict"] == "not met" and "proves nothing" in result["failures"][0]
    assert calls == [], "nothing stopped when there was nothing to stop"


def test_opensearch_is_started_again_when_the_check_itself_fails(conduit: str) -> None:
    calls: list[str] = []

    def stop() -> None:
        calls.append("stop")
        raise RuntimeError("docker stop failed")

    with pytest.raises(RuntimeError):
        measure_search.measure_fallback(
            base=conduit, case="case-1", token="t", queries=_M9_QUERIES, stop=stop,
            start=lambda: calls.append("start"), within_ms=_M9_WITHIN,
        )  # fmt: skip
    assert calls == ["stop", "start"]


def _run_live_m9(conduit: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """The live file's M9 case as step 4 runs it, its `docker stop` and `docker start` a stand-in
    on PATH that stops and starts the stub's index (never a real container)."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "docker").write_text(
        "#!/bin/sh\n"
        f"exec curl -s -o /dev/null -X POST -H 'Content-Length: 0' {conduit}/_control/$1\n"
    )
    (bin_ / "docker").chmod(0o755)
    extra = {"OSPREY_MEASURE_STOP_OPENSEARCH": "osprey-test-x-opensearch",
             "PATH": f"{bin_}:{os.environ['PATH']}"}  # fmt: skip
    done = _run_live(tmp_path, conduit, extra, only="m9")
    if "local_docker_guard" in done.stdout:
        # On this machine the guard refuses any docker call, the stand-in's too: the server's
        # make test runs these (where the stand-in on PATH is what `docker` finds).
        pytest.skip("a server-only test: the live M9 case calls the docker CLI (its stand-in here)")
    return done


def test_the_live_gate_passes_m9_when_the_fallback_says_so(conduit: str, tmp_path: Path) -> None:
    done = _run_live_m9(conduit, tmp_path)
    assert done.returncode == 0 and "1 passed" in done.stdout, done.stdout[-1500:]
    assert _Conduit.index_down is False, "OpenSearch started again"


def test_the_live_gate_fails_m9_when_the_fallback_is_silent(conduit: str, tmp_path: Path) -> None:
    _Conduit.fallback = "silent"
    done = _run_live_m9(conduit, tmp_path)
    assert done.returncode != 0 and "M9:" in done.stdout and "did not say so" in done.stdout
    assert _Conduit.index_down is False


# --- a token that dies mid-run (step 4's rerun on d, 14 November 2026) ---------------------------


def test_a_token_refused_mid_run_stops_the_measure_and_says_its_figures_are_void(
    conduit: str,
) -> None:
    """Rule 15: the fake models the Conduit's refusal of an expired token, not only its grant.
    Before, a 401 was one more slow error and the class reported as measured."""
    _Conduit.expires_after = 4
    with pytest.raises(measure_search.TokenRefused) as stopped:
        _run(conduit)
    said = str(stopped.value)
    assert "401" in said and "void" in said, said
    assert len(_Conduit.seen) == 5, "stopped at the first refusal, not measured on"


def test_a_token_refused_mid_run_stops_m10_rather_than_reading_as_reaching_nothing(
    conduit: str,
) -> None:
    _Conduit.expires_after = 1
    with pytest.raises(measure_search.TokenRefused):
        _leaks(conduit)


def test_a_control_that_errs_says_its_error_not_the_ids_it_did_not_name(conduit: str) -> None:
    """Before, a failed control request listed every hidden id as unnamed and hid the error."""
    _Conduit.control_fails = 500
    result = _leaks(conduit)
    assert result["verdict"] == "not met"
    assert all("500" in f for f in result["failures"]), result["failures"]
    assert not any("hid-1" in f for f in result["failures"]), result["failures"]


def test_the_live_gate_stops_the_whole_run_on_a_refused_token(conduit: str, tmp_path: Path) -> None:
    """A run whose results are void must not report as finished: the first 401 ends the session
    (pytest.exit), so no later case measures on and no later result file is written."""
    _Conduit.expires_after = 2
    results = tmp_path / "results"
    done = _run_live(tmp_path, conduit, {"OSPREY_MEASURE_RESULTS": str(results)})
    said = done.stdout + done.stderr
    assert done.returncode != 0, said
    assert "401" in said and "void" in said, said[-2000:]
    assert " passed" not in said.splitlines()[-1], said[-600:]
    assert not results.exists() or not list(results.iterdir()), "no result written past it"
    assert len(_Conduit.seen) == 3, f"no case sent anything past the refusal: {len(_Conduit.seen)}"
