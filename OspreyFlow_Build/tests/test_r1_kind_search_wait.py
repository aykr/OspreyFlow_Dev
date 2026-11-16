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

from tests.test_r1_kind_domain_guard import _checks, _Door, _r1_kind


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
