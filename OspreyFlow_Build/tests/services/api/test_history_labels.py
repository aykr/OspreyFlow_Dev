"""History labels are fixed text (ADR-124 decision 8): no number, no name, one per write site.

A label is shown to anyone who can see the case, and it is stored with an unfiltered snapshot, so
a label that said how many nodes a step added, or which case or alert it came from, would be a
figure for the case's contents that the reader may not be entitled to (rules 3 and 7). The labels
are constants in `services/api/history_labels.py`; the sites of `app.py` name them and compute
nothing.

Pure: it parses `app.py` and imports a constants module, and opens no connection.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from services.api import history_labels
from services.api.history import RELABEL_SQL

APP = Path(__file__).resolve().parents[4] / "OspreyFlow_Core" / "services" / "api" / "app.py"

#: Decision 8's table, site by site: the function in `app.py` that records a step, and its label.
SITES = {
    "branch_investigation": "Branched",
    "branch_investigation_by_filter": "Branched",
    "seed": "Seeded",
    "expand": "Expanded",
    "links_among_route": "Showed links among the view",
    "remove_nodes": "Removed",
    "explore_starter_run_route": "Ran a starter question",
    "shared_pair_canvas_route": "Showed two who share contacts",
    "jump_alert_route": "Opened from an alert",
    "ownership_canvas": "Showed an ownership structure",
    "alert_canvas": "Opened an alert",
}


def _fixed_labels() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(history_labels).items()
        if name.isupper() and isinstance(value, str)
    }


def _recording_calls() -> list[tuple[str, ast.Call]]:
    """Every call of `_record_history_step` in `app.py` with the function it is in."""
    tree = ast.parse(APP.read_text())
    found: list[tuple[str, ast.Call]] = []
    for function in ast.walk(tree):
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "_record_history_step"
                ):
                    found.append((function.name, node))
    return found


def test_the_fixed_texts_are_decision_8s_table_and_the_fallback() -> None:
    assert set(SITES.values()) | {"Changed"} == set(_fixed_labels().values())
    assert history_labels.CHANGED == "Changed"
    assert history_labels.FIXED_LABELS == set(SITES.values())


@pytest.mark.parametrize("text", sorted(set(SITES.values()) | {"Changed"}))
def test_no_label_holds_a_digit_or_a_placeholder(text: str) -> None:
    """Violation caught: a label with a count in it, or with a slot for one."""
    assert not re.search(r"\d|[{}%]|\(s\)", text), text


def test_every_write_site_is_in_the_table_and_no_site_is_missing() -> None:
    """Violation caught (rule 12): a history-writing site added without a label in decision 8's
    table, or one the table lists that stopped writing. The walk is over `app.py`'s own calls."""
    sites = [name for name, _ in _recording_calls()]
    assert sorted(sites) == sorted(SITES)


@pytest.mark.parametrize("site", sorted(SITES))
def test_a_write_site_names_a_constant_and_computes_nothing(site: str) -> None:
    """Violation caught: a site writing an interpolated label (an f-string, a format, a
    concatenation, a literal of its own), which could carry a number, an id or a name. The `label`
    argument must be a bare name from `history_labels`, whose text is the table's."""
    (call,) = [c for name, c in _recording_calls() if name == site]
    (label,) = [k.value for k in call.keywords if k.arg == "label"]
    assert isinstance(label, ast.Name), f"{site}: label is {ast.dump(label)[:80]}"
    assert label.id in _fixed_labels(), f"{site}: {label.id} is not in history_labels"
    assert _fixed_labels()[label.id] == SITES[site]


def test_the_store_records_only_through_the_one_helper() -> None:
    """Violation caught: a route that calls `history.record_step` itself and so skips the sites'
    check above."""
    tree = ast.parse(APP.read_text())
    callers = {
        function.name
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "record_step"
    }
    assert callers == {"_record_history_step"}


def test_the_site_check_catches_an_interpolated_label() -> None:
    """Violation caught (rule 15, shown able to fail): the same inspection over a planted site that
    interpolates, in the shape the real sites had (`f"Seeded {len(...)} node(s)"`)."""
    planted = ast.parse(
        "async def seed():\n"
        "    await _record_history_step(a, b, label=f'Seeded {len(x)} node(s)', principal=p)\n"
    )
    (call,) = [
        n
        for n in ast.walk(planted)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_record_history_step"
    ]
    (label,) = [k.value for k in call.keywords if k.arg == "label"]
    assert not isinstance(label, ast.Name)


def test_no_pattern_of_the_table_has_an_underscore_of_its_own() -> None:
    """Violation caught: a pattern with a `_` in it, a single-character wildcard in `LIKE` that
    would match a label with any character there. Decision 8's patterns are plain words and spaces
    with `%` for the part that varied, so there is nothing to escape and `_` can only be a mistake.
    Pure: it reads the statement's text, which the live test (`test_history_relabel.py`) runs."""
    patterns = re.findall(r"LIKE '([^']*)'", RELABEL_SQL)
    assert len(patterns) == 11
    assert not [p for p in patterns if "_" in p]


class _Conn:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        return self.rows


class _Acquire:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _Conn:
        return self.conn

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Pool:
    """Stands in for the `asyncpg` pool: `list_steps` only acquires and fetches rows."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.conn = _Conn(rows)

    def acquire(self) -> _Acquire:
        return _Acquire(self.conn)


async def test_list_steps_returns_a_label_that_is_not_fixed_as_changed() -> None:
    """Violation caught: a rolling upgrade, where an old instance still writes numbered labels
    after a new one's migration has run. Whatever is stored, the listing shows only fixed text, so
    a count or a case id in a stored label never reaches the reader. A fixed label is unchanged."""
    from datetime import UTC, datetime

    from services.api.history import InvestigationHistoryStore

    when = datetime(2026, 1, 1, tzinfo=UTC)
    stored = [
        "Seeded 12 node(s)",
        "Branched from inv-7c1",
        "Opened an alert: structuring",
        "",
        "Seeded",
        "Showed links among the view",
        "Changed",
    ]
    rows = [{"id": f"s{i}", "label": label, "created_at": when} for i, label in enumerate(stored)]
    store = InvestigationHistoryStore(_Pool(rows))  # type: ignore[arg-type]

    listed = await store.list_steps("case-1")

    assert [s.label for s in listed] == [
        "Changed",
        "Changed",
        "Changed",
        "Changed",
        "Seeded",
        "Showed links among the view",
        "Changed",
    ]
    assert [s.id for s in listed] == [f"s{i}" for i in range(len(stored))]
