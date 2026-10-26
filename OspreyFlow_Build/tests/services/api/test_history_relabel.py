"""The stored history labels are rewritten to the fixed texts (ADR-124 decision 8), live Postgres.

`InvestigationHistoryStore.connect` runs the rewrite on every start, so a case whose steps were
written with a count or a case id in the label is cleaned the next time the Conduit starts. Each
pattern of decision 8's table is exercised on a label of the shape the old code wrote, the fallback
on a label matching none, a second run must change nothing, and a label that differs from a
pattern's text by one character must not match it (`_` is a single-character wildcard in `LIKE`,
and a pattern that carried one unescaped would match it).

Live: it needs the dev stack's Postgres. Run it as the other Postgres tests in this folder are run
(`test_hotlists.py`): `pytest tests/services/api/test_history_relabel.py`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from services.api.config import PostgresConfig
from services.api.history import InvestigationHistoryStore

#: (what the old code wrote, the label it becomes): decision 8's second table, one row per pattern
#: and one more for the second pattern of "Showed links among the view", with the labels the code
#: really produced (the digits and ids are invented).
OLD_AND_NEW = [
    ("Branched from inv-7c1", "Branched"),
    ("Seeded 12 node(s)", "Seeded"),
    ("Expanded 31 node(s) from 2 seed(s)", "Expanded"),
    ("Showed 5 link(s) among the nodes in view", "Showed links among the view"),
    (
        "Showed the routes within 3 degrees among the selected nodes: 4 link(s), 2 node(s)",
        "Showed links among the view",
    ),
    ("Removed 3 node(s)", "Removed"),
    ("Ran a starter question: 14 node(s)", "Ran a starter question"),
    ("Showed two who share contacts: 6 node(s)", "Showed two who share contacts"),
    ("Opened from alert al-91", "Opened from an alert"),
    ("Showed an ownership structure: 9 node(s)", "Showed an ownership structure"),
    ("Opened an alert: structuring", "Opened an alert"),
    ("Opened an alert: alert", "Opened an alert"),
]

#: Labels that match no pattern: the fallback.
UNMATCHED = [
    "Ran community detection",
    "Expanded HALE, Marcus by one hop",
    "Restored a step",
    "",
]

#: The text of each pattern's literal parts, as `LIKE` sees them (`%` is the one wildcard).
PATTERN_SAMPLES = [
    ("Branched from ", "Branched from inv-7c1"),
    ("Seeded ", "Seeded 12 node(s)"),
    ("Expanded ", "Expanded 31 node(s) from 2 seed(s)"),
    ("Showed ", "Showed 5 link(s) among the nodes in view"),
    ("Showed the routes within ", "Showed the routes within 3 degrees among the selected nodes: x"),
    ("Removed ", "Removed 3 node(s)"),
    ("Ran a starter question: ", "Ran a starter question: 14 node(s)"),
    ("Showed two who share contacts: ", "Showed two who share contacts: 6 node(s)"),
    ("Opened from alert ", "Opened from alert al-91"),
    ("Showed an ownership structure: ", "Showed an ownership structure: 9 node(s)"),
    ("Opened an alert: ", "Opened an alert: structuring"),
]


@pytest.fixture
async def store():
    s = await InvestigationHistoryStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


_run = 0


async def _write(store: InvestigationHistoryStore, labels: list[str]) -> list[str]:
    """Rows with the given labels in a case of their own; their ids, in order."""
    global _run
    _run += 1
    case = f"relabel-{datetime.now(UTC).timestamp()}-{_run}"
    ids = []
    async with store._pool.acquire() as conn:
        for seq, label in enumerate(labels):
            row_id = f"{case}-{seq}"
            ids.append(row_id)
            await conn.execute(
                "INSERT INTO investigation_history "
                "(id, investigation_id, seq, label, created_at, created_by, nodes, edges) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                row_id,
                case,
                seq,
                label,
                datetime.now(UTC),
                "analyst-1",
                json.dumps([]),
                json.dumps([]),
            )
    return ids


async def _labels(store: InvestigationHistoryStore, ids: list[str]) -> list[str]:
    async with store._pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, label FROM investigation_history WHERE id = ANY($1::text[])", ids
        )
    by_id = {r["id"]: r["label"] for r in rows}
    return [by_id[i] for i in ids]


async def test_each_pattern_rewrites_its_old_label(store: InvestigationHistoryStore) -> None:
    ids = await _write(store, [old for old, _ in OLD_AND_NEW])
    await store.relabel()
    assert await _labels(store, ids) == [new for _, new in OLD_AND_NEW]


async def test_a_label_matching_no_pattern_becomes_changed(
    store: InvestigationHistoryStore,
) -> None:
    ids = await _write(store, UNMATCHED)
    await store.relabel()
    assert await _labels(store, ids) == ["Changed"] * len(UNMATCHED)


async def test_a_second_run_changes_nothing(store: InvestigationHistoryStore) -> None:
    ids = await _write(store, [old for old, _ in OLD_AND_NEW] + UNMATCHED)
    await store.relabel()
    first = await _labels(store, ids)
    await store.relabel()
    await store.relabel()
    assert await _labels(store, ids) == first


async def test_a_fixed_label_is_left_alone(store: InvestigationHistoryStore) -> None:
    fixed = [new for _, new in OLD_AND_NEW] + ["Changed"]
    ids = await _write(store, fixed)
    await store.relabel()
    assert await _labels(store, ids) == fixed


@pytest.mark.parametrize(("literal", "sample"), PATTERN_SAMPLES)
async def test_a_label_with_another_character_where_a_pattern_has_text_does_not_match(
    store: InvestigationHistoryStore, literal: str, sample: str
) -> None:
    """Violation caught: a pattern carrying an unescaped `_` (one character of anything) or `%`
    where its text has a letter or a space. Every character of the pattern's own text is replaced
    in turn, by `_` and by `%` as well as by a letter, and none of those labels may be rewritten
    to the pattern's new label: they are all `Changed`."""
    assert sample.startswith(literal)
    mutants = []
    for i, char in enumerate(literal):
        for replacement in ("_", "%", "X"):
            if char != replacement:
                mutants.append(sample[:i] + replacement + sample[i + 1 :])
    ids = await _write(store, mutants)
    await store.relabel()
    assert await _labels(store, ids) == ["Changed"] * len(mutants)


async def test_list_steps_shows_changed_for_an_old_label_written_after_the_relabel(
    store: InvestigationHistoryStore,
) -> None:
    """A rolling upgrade: an old instance writes a numbered label after this one's relabel ran.
    The raw row is inserted after `relabel()`; the listing must show "Changed" for it and leave a
    fixed label alone."""
    await store.relabel()
    ids = await _write(store, ["Seeded 12 node(s)", "Seeded"])
    async with store._pool.acquire() as conn:
        case = await conn.fetchval(
            "SELECT investigation_id FROM investigation_history WHERE id=$1", ids[0]
        )
    listed = await store.list_steps(case)
    assert [s.label for s in listed] == ["Changed", "Seeded"]


# --- ADR-127 decision 6, B2-4c2: a revert takes a load's elements out of every stored step -----------


async def test_a_revert_removes_its_elements_and_the_links_at_them_from_every_stored_step(
    store: InvestigationHistoryStore,
) -> None:
    """A step is a full snapshot of the bodies at that moment. A revert leaves none of its
    elements in any case's steps, nor a link ending at one of its nodes; every other element, and
    the order of the rest, is as it was. Restore re-reads the Vault, so a reverted body would not
    come back, but the stored bodies are not kept either. Idempotent: a second call changes nothing."""
    from services.api.history import HistoryStep  # noqa: F401 (the shape get_step returns)

    from schemas.domain import Edge, Node
    from tests.services.api.working_set.test_visible_link import edge, node

    case_a, case_b = (
        f"case-a-{datetime.now(UTC).timestamp()}",
        f"case-b-{datetime.now(UTC).timestamp()}",
    )

    async def step(case: str, nodes: list[Node], edges: list[Edge], seq: int) -> str:
        made = await store.record_step(
            case, seq=seq, label="Seeded", created_by="analyst-1", nodes=nodes, edges=edges
        )
        return made.id

    nodes = [node("r1"), node("r-secret", "SECRET"), node("k1"), node("k2")]
    edges = [edge("re1", "r1", "k1"), edge("hang", "r1", "k2"), edge("ke", "k1", "k2")]
    a1 = await step(case_a, nodes, edges, 1)
    a2 = await step(case_a, [node("k1")], [], 2)
    b1 = await step(case_b, [node("r-secret", "SECRET"), node("k2")], [], 1)

    changed = await store.remove_elements(["r1", "r-secret"], ["re1"])
    assert changed >= 2
    first = await store.get_step(case_a, a1)
    assert [n.id for n in first.nodes] == ["k1", "k2"], "order kept"
    assert [e.id for e in first.edges] == ["ke"], "the named link and the link at r1 are gone"
    assert [n.id for n in (await store.get_step(case_a, a2)).nodes] == ["k1"]
    assert [n.id for n in (await store.get_step(case_b, b1)).nodes] == ["k2"]
    assert await store.remove_elements(["r1", "r-secret"], ["re1"]) == 0
    assert await store.remove_elements([], []) == 0
