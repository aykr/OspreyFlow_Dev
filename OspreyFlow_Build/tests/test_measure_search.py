"""v052-measure's timer (`scripts/measure_search.py`), held to what it claims before it is trusted
on B's load (rule 15: a timer shown only on a fast server has been exercised, not tested).
Against a stub Conduit that answers the two routes as 3d's frozen shape does
(`SEARCH_RESPONSE_SHAPE.md`), and can be made slow, answer from the fallback, or rank an exact
identifier second: each must turn the class's verdict to "not met"."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
