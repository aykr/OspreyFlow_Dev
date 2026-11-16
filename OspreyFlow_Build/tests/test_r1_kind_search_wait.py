"""R1's check "what it loaded is found" waits for the index (v0.6.0's package test, 16 November
2026).

The search index is written by the indexer a moment after a load (ADR-150), so a search made the
instant the load returns can find nothing. Row 2 of the package test on 0c158b8 failed so: the
check searched at about 06:34:03, the worker's `_bulk` landed at 06:34:04.85, and the same search
read afterwards found the node. The check now asks again every 5 s for up to 60 s, as the alert
check after it already waits for its alert, and fails in the same words if nothing is found.

What a mistake would do, and the case that catches it (rule 12):
- the check searching once, so a load indexed a moment late fails it:
  `test_a_load_indexed_a_moment_later_is_found`;
- the wait passing whatever the index holds, so a load never indexed passes:
  `test_a_load_never_indexed_fails_after_the_wait_in_the_same_words`.

Each runs the real `r1_kind.checks()` through `tests/test_r1_kind_domain_guard.py`'s stand-in door,
whose search answers no node for its first `found_after` searches."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_r1_kind_domain_guard import _Answer, _checks, _Door, _r1_kind


def _waits(monkeypatch: pytest.MonkeyPatch, found_after: int) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(_Door, "found_after", found_after)
    monkeypatch.setattr(_r1_kind().time, "sleep", slept.append)
    return slept


def test_a_load_indexed_a_moment_later_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _waits(monkeypatch, found_after=3)
    _probed, log = _checks(tmp_path, monkeypatch, "opensearch")
    assert "PASS what it loaded is found" in log, log[-400:]
    assert _Door.searches == 4


def test_a_load_never_indexed_fails_after_the_wait_in_the_same_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slept = _waits(monkeypatch, found_after=10**6)
    with pytest.raises(SystemExit, match="check failed: what it loaded is found"):
        _checks(tmp_path, monkeypatch, "opensearch")
    assert "FAIL what it loaded is found" in (tmp_path / "check.log").read_text()
    assert _Door.searches == 12 and sum(slept) <= 60, (_Door.searches, sum(slept))


# ---- change(): the load after the set, found once the index has it (row 5, 16 November 2026) ----------------


class _Search:
    """The door's search alone: `R1AfterTheSet` found after `late` asks, `R1Synthetic` at once."""

    def __init__(self, late: int) -> None:
        self.late, self.asks = late, 0

    def post(self, path: str, headers: dict[str, str] | None = None, json: dict | None = None) -> _Answer:  # type: ignore[type-arg]
        assert path.endswith("/search"), path
        if (json or {}).get("query") == "R1AfterTheSet":
            self.asks += 1
            return _Answer(200, {"nodes": [{"id": "n"}] if self.asks > self.late else []})
        return _Answer(200, {"nodes": [{"id": "s"}]})


def _change(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, late: int) -> tuple[_Search, list[float]]:
    r1 = _r1_kind()
    door, slept = _Search(late), []
    monkeypatch.setattr(r1, "door", lambda: door)
    monkeypatch.setattr(r1, "state", lambda: {"case": "case-1"})
    monkeypatch.setattr(r1, "token", lambda **_: "admin")
    monkeypatch.setattr(r1, "_load_file", lambda *a, **k: 1)
    monkeypatch.setattr(r1, "_source_files", lambda *a, **k: ["r1-people.csv", "r1-after-the-set.csv"])
    monkeypatch.setattr(r1, "record", lambda name: tmp_path / f"{name}.log")
    monkeypatch.setattr(r1.time, "sleep", slept.append)
    r1.change()
    return door, slept


def test_the_change_after_the_set_is_found_once_the_index_has_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Row 5's change() searched once, at once after its load: where search reads the index (ADR-150
    Amendment 3), the load is found a moment later, and the change would read as not taken."""
    door, slept = _change(monkeypatch, tmp_path, late=3)
    assert door.asks == 4 and sum(slept) == 15


def test_a_change_never_indexed_still_stops_in_its_own_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit, match="the change after the set did not take"):
        _change(monkeypatch, tmp_path, late=10**6)
