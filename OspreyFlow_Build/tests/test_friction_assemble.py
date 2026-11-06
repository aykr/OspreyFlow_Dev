"""`tools/friction_assemble.py` (ADR-142 decision 5): lanes' friction fragments become rows of the
build plan's friction log at merge.

Rule 15: the target is a copy of the real `process/07_BUILD_PLAN.md` (whose rows sit after the
"Standing rules" section, not under the heading), and every fragment is the shape a lane writes:
`process/friction/<yyyy-mm-dd>-<lane>-<slug>.md`, one row, ending "Hash: recorded at merge."
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tools import friction_assemble
from tools.friction_assemble import BUILD_PLAN, PLACEHOLDER, FragmentError, assemble

MERGE = "4e5f6a7"


def _row(date: str, what: str, commit: str = PLACEHOLDER) -> str:
    return f"| {date} | Built (planted) | {what} | Done. | Tests passed. {commit} |"


@pytest.fixture
def tree(tmp_path: Path) -> tuple[Path, Path]:
    friction = tmp_path / "friction"
    friction.mkdir()
    (friction / "README.md").write_text("# Friction fragments\n\n" + _row("2026-01-01", "x") + "\n")
    plan = tmp_path / "07_BUILD_PLAN.md"
    shutil.copy(BUILD_PLAN, plan)
    return friction, plan


def _fragment(friction: Path, name: str, *rows: str) -> Path:
    path = friction / name
    path.write_text("".join(f"{r}\n" for r in rows))
    return path


def _appended(plan: Path) -> list[str]:
    before = BUILD_PLAN.read_text(encoding="utf-8").split("\n")
    after = plan.read_text(encoding="utf-8").split("\n")
    return [line for line in after if line not in before]


def test_fragments_become_rows_in_date_order_after_the_last_row(tree) -> None:
    friction, plan = tree
    _fragment(friction, "2026-11-08-glass-later.md", _row("2026-11-08", "later"))
    _fragment(friction, "2026-11-07-studio-earlier.md", _row("2026-11-07", "earlier"))
    assemble(MERGE, friction, plan)
    assert _appended(plan) == [
        _row("2026-11-07", "earlier", f"{MERGE}."),
        _row("2026-11-08", "later", f"{MERGE}."),
    ]
    lines = plan.read_text(encoding="utf-8").split("\n")
    old_last = max(
        i for i, line in enumerate(BUILD_PLAN.read_text(encoding="utf-8").split("\n"))
        if line.startswith("| 20")
    )
    assert lines[old_last + 1] == _row("2026-11-07", "earlier", f"{MERGE}.")
    assert (friction / "README.md").exists()


@pytest.mark.parametrize("rows", [2, 0])
def test_a_fragment_with_two_rows_or_none_is_refused_and_nothing_is_written(tree, rows) -> None:
    friction, plan = tree
    good = _fragment(friction, "2026-11-07-studio-good.md", _row("2026-11-07", "good"))
    bad = _fragment(
        friction, "2026-11-07-case-bad.md", *[_row("2026-11-07", f"r{i}") for i in range(rows)]
    )
    with pytest.raises(FragmentError, match=f"holds {rows} friction-log rows"):
        assemble(MERGE, friction, plan)
    assert plan.read_bytes() == BUILD_PLAN.read_bytes()
    assert good.exists() and bad.exists()


def test_a_hash_already_filled_is_never_overwritten(tree) -> None:
    friction, plan = tree
    _fragment(friction, "2026-11-07-case-filled.md", _row("2026-11-07", "filled", "0ed30d1."))
    assemble(MERGE, friction, plan)
    assert _appended(plan) == [_row("2026-11-07", "filled", "0ed30d1.")]


def test_the_fragments_are_removed_only_after_the_table_is_written(tree, monkeypatch) -> None:
    friction, plan = tree
    fragment = _fragment(friction, "2026-11-07-studio-one.md", _row("2026-11-07", "one"))

    def fail(*_args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(friction_assemble.os, "replace", fail)
    with pytest.raises(OSError):
        assemble(MERGE, friction, plan)
    assert fragment.exists()
    assert plan.read_bytes() == BUILD_PLAN.read_bytes()


def test_a_row_of_the_wrong_width_or_date_is_refused(tree) -> None:
    friction, plan = tree
    _fragment(friction, "2026-11-07-glass-narrow.md", "| 2026-11-07 | Built | three cells only |")
    with pytest.raises(FragmentError, match="not five"):
        assemble(MERGE, friction, plan)
    (friction / "2026-11-07-glass-narrow.md").unlink()
    _fragment(friction, "2026-11-07-glass-misdated.md", _row("2026-11-09", "misdated"))
    with pytest.raises(FragmentError, match="not dated 2026-11-07"):
        assemble(MERGE, friction, plan)
