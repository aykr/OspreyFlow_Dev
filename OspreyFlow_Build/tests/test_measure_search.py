"""v052-measure's timer (`scripts/measure_search.py`), held to what it claims before it is trusted
on B's load (rule 15: a timer shown only on a fast server has been exercised, not tested).
Against a stub Conduit that answers the two routes as 3d's frozen shape does
(`SEARCH_RESPONSE_SHAPE.md`), and can be made slow, answer from the fallback, or rank an exact
identifier second: each must turn the class's verdict to "not met"."""

from __future__ import annotations

import json
import re
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

    def do_POST(self) -> None:  # noqa: N802 - http.server's name
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.seen.append((self.path, body, self.headers.get("Authorization", "")))
        time.sleep(self.delay)
        if self.path.endswith("/suggest"):
            answer: dict[str, Any] = {"nodes": [{"id": "n1"}], "more": False}
        else:
            hits = [
                {"node_ids": ["exact-1"], "match": {"band": "identifier"}},
                {"node_ids": ["close-1"], "match": {"band": "name_typo"}},
            ]
            answer = {
                "source": self.source,
                "limited": self.source != "index",
                "total": 2,
                "groups": [],
                "results": hits if self.exact_first else hits[::-1],
                "nodes": [],
            }
        data = json.dumps(answer).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def conduit() -> Iterator[str]:
    _Conduit.delay, _Conduit.source, _Conduit.exact_first, _Conduit.seen = 0.0, "index", True, []
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
