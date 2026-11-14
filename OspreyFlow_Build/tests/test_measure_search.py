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

    def do_POST(self) -> None:  # noqa: N802 - http.server's name
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.seen.append((self.path, body, self.headers.get("Authorization", "")))
        time.sleep(self.delay)
        status = 200
        if self.leak_world and self.path.endswith(("/search", "/suggest")):
            answer = self._leak_answer(
                self.headers.get("Authorization", "") == "Bearer cleared-unit-fiu"
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

    def _leak_answer(self, cleared: bool) -> dict[str, Any]:
        hidden = cleared and self.leak != "unreached"
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
    _Conduit.leak_world, _Conduit.leak = False, ""
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
    assert "5 passed, 1 skipped" in done.stdout  # M10: no leak cases named


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
    assert done.returncode == 0 and "6 skipped" in done.stdout
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


def test_a_case_the_cleared_principal_cannot_reach_proves_nothing_and_fails(conduit: str) -> None:
    _Conduit.leak = "unreached"
    result = _leaks(conduit)
    assert result["verdict"] == "not met"
    assert all("proves nothing" in f for f in result["failures"]) and len(result["failures"]) == 2


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
    extra = {"OSPREY_MEASURE_CONTROLS": json.dumps(CONTROLS), "OSPREY_MEASURE_LEAKS": str(leaks)}
    return _run_live(tmp_path, conduit, extra, only="m10")


def test_the_live_gate_passes_m10_when_nothing_hidden_shows(conduit: str, tmp_path: Path) -> None:
    done = _run_live_m10(conduit, tmp_path)
    assert done.returncode == 0 and "1 passed" in done.stdout, done.stdout[-1500:]


def test_the_live_gate_fails_m10_on_a_leak(conduit: str, tmp_path: Path) -> None:
    """Rule 15 at the real call site: the file step 6 runs, red for a hidden id in a merged
    entity."""
    _Conduit.leak = "id"
    done = _run_live_m10(conduit, tmp_path)
    assert (
        done.returncode != 0 and "M10:" in done.stdout and "hid-1 is in the answer" in done.stdout
    )


@pytest.mark.parametrize(
    ("control", "said"),
    [
        ("unit-border", "does not name ['hid-1']"),  # another unit's control cannot see it
        ("unit-covert", "no control token for 'unit-covert'"),
        (None, "no control token for None"),
    ],
)
def test_a_case_whose_control_cannot_name_its_record_fails_never_skips(
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
