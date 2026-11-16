"""`index_wait`: the closing-pass cases wait for the search index, and say how long they waited
(ADR-150 Amendment 3; v0.6.0's package test row 4).

What a mistake would do, and the case that catches it (rule 12):
- a search made once, so a write the index takes a moment to reach is missed:
  `test_a_write_the_index_takes_a_moment_to_reach_is_found`;
- a wait with no bound, or one that hides a write never indexed:
  `test_a_write_never_indexed_is_not_found_after_the_bound`;
- a refused search waited on: `test_a_refused_search_is_answered_at_once`;
- a read after a redraw made before the index settles, which could miss a duplicate written late:
  `test_a_late_duplicate_is_seen_by_the_settled_read`;
- the wait not recorded: each case reads the record's line."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.scenarios import index_wait


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _Answer:
    def __init__(self, status: int, nodes: list[dict[str, Any]]) -> None:
        self.status_code, self._nodes = status, nodes

    def json(self) -> dict[str, Any]:
        return {"nodes": self._nodes}


def _index(answers: list[list[str]], status: int = 200) -> Any:
    """A search whose nth ask answers the nth list of ids (the last one from then on)."""
    asked = []

    def post(path: str, json: dict[str, Any]) -> _Answer:
        asked.append(json)
        ids = answers[min(len(asked) - 1, len(answers) - 1)]
        return _Answer(status, [{"id": i} for i in ids])

    post.asked = asked  # type: ignore[attr-defined]
    return post


@pytest.fixture
def waits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    kept = tmp_path / "waits.log"
    monkeypatch.setenv("OSPREY_SEARCH_WAITS", str(kept))
    return kept


def test_a_write_the_index_takes_a_moment_to_reach_is_found(waits: Path) -> None:
    clock, post = _Clock(), _index([[], [], [], ["cell"]])
    answer = index_wait.search_until(post, "/v1/search", {"query": "q"}, what="the cell",
                                     clock=clock, sleep=clock.sleep)  # fmt: skip
    assert answer.json()["nodes"] == [{"id": "cell"}] and len(post.asked) == 4
    assert waits.read_text() == "the cell: found after 3.0 s\n"


def test_a_write_never_indexed_is_not_found_after_the_bound(waits: Path) -> None:
    clock, post = _Clock(), _index([[]])
    answer = index_wait.search_until(post, "/v1/search", {"query": "q"}, what="the number",
                                     clock=clock, sleep=clock.sleep)  # fmt: skip
    assert answer.json()["nodes"] == [] and clock.now == index_wait.BOUND
    assert waits.read_text() == "the number: not found after 30.0 s\n"


def test_a_refused_search_is_answered_at_once(waits: Path) -> None:
    clock, post = _Clock(), _index([[]], status=403)
    answer = index_wait.search_until(post, "/v1/search", {"query": "q"}, what="refused",
                                     clock=clock, sleep=clock.sleep)  # fmt: skip
    assert answer.status_code == 403 and len(post.asked) == 1 and clock.now == 0.0


def test_a_late_duplicate_is_seen_by_the_settled_read(waits: Path) -> None:
    clock, post = _Clock(), _index([["c1"], ["c1"], ["c1"], ["c1", "c1-dup"]])
    nodes = index_wait.settled(post, "/v1/search", {"query": "q"}, what="after the redraw",
                               clock=clock, sleep=clock.sleep)  # fmt: skip
    assert [n["id"] for n in nodes] == ["c1", "c1-dup"]
    assert waits.read_text() == "after the redraw: settled (2) after 8.0 s\n"
