"""`scripts.migrate_rules_to_datasets`, offline (`spec/06_DECISIONS.md` ADR-146 decision 3 and
Amendment 6, L2.11): each whole-deployment rule becomes one rule per source dataset in its home case
with the same conditions, and is retired; the dry run writes nothing.

What a mistake would do, and the case that catches it:
- a dry run that writes: `test_a_dry_run_writes_nothing` (red with the real writer handed in);
- a copy with other conditions, in the wrong case or on no dataset, or the original left running:
  `test_one_rule_per_dataset_in_its_home_case_with_the_same_conditions_and_the_original_retired`;
- a rule retired with a dataset left unwatched, or copied beside a running original:
  `test_a_dataset_with_no_home_case_leaves_the_rule_whole_and_running`;
- a rule never approved copied live: `test_a_rule_never_approved_is_copied_as_a_draft`.
"""

from __future__ import annotations

import json
from typing import Any

from scripts.migrate_rules_to_datasets import SourceDataset, WideRule, migrate

SENTENCE = {
    "subject": "Person",
    "conditions": [{"op": "equals", "property": "family_name", "value": "Okafor"}],
    "scope": "deployment",
}


def _rule(status: str = "active") -> WideRule:
    return WideRule(
        id="r-wide", investigation_id="case-admin", owner_id="admin", name="Okafor anywhere",
        params={"typology": "sentence", "pattern_id": "p", "sentence": SENTENCE},
        trigger="post_commit", budget_ms=5000, status=status, version=2,
    )  # fmt: skip


DATASETS = [SourceDataset("ds-a", "Prison records", "home-a"),
            SourceDataset("ds-b", "Custody suites", "home-b")]  # fmt: skip


class _Conn:
    """A connection that keeps what it was asked to run; or refuses to run anything."""

    def __init__(self, *, refuses: bool = False) -> None:
        self.refuses = refuses
        self.ran: list[tuple[str, tuple[Any, ...]]] = []

    def transaction(self) -> Any:
        conn = self

        class _Tx:
            async def __aenter__(self) -> None:
                if conn.refuses:
                    raise AssertionError("a dry run opened a transaction")

            async def __aexit__(self, *exc: object) -> None:
                return None

        return _Tx()

    async def execute(self, sql: str, *args: Any) -> None:
        if self.refuses:
            raise AssertionError(f"a dry run wrote: {sql[:60]}")
        self.ran.append((sql, args))


async def test_a_dry_run_writes_nothing() -> None:
    conn = _Conn(refuses=True)
    report = await migrate([_rule()], DATASETS, conn=conn, write=False)  # type: ignore[arg-type]
    assert report.writes and conn.ran == []
    assert report.retired == ["r-wide"] and len(report.copied) == 2


async def test_one_rule_per_dataset_in_its_home_case_with_the_same_conditions_and_the_original_retired() -> None:
    conn = _Conn()
    report = await migrate([_rule()], DATASETS, conn=conn, write=True)  # type: ignore[arg-type]
    inserts = [args for sql, args in conn.ran if sql.startswith("INSERT INTO typology_rules ")]
    assert [(a[1], a[9], a[7]) for a in inserts] == [("home-a", "ds-a", "active"),
                                                    ("home-b", "ds-b", "active")]  # fmt: skip
    for args in inserts:
        params = json.loads(args[4])
        assert params["sentence"]["conditions"] == SENTENCE["conditions"]
        assert params["sentence"]["scope"] == "this_case"
        assert (args[2], args[3]) == ("admin", "Okafor anywhere")
    (retired,) = [args for sql, args in conn.ran if "SET status = 'retired'" in sql]
    assert (retired[0], retired[2]) == ("r-wide", 3)
    assert report.unplaced == []


async def test_a_dataset_with_no_home_case_leaves_the_rule_whole_and_running() -> None:
    conn = _Conn()
    homeless = [*DATASETS, SourceDataset("ds-c", "No home", None)]
    report = await migrate([_rule()], homeless, conn=conn, write=True)  # type: ignore[arg-type]
    assert conn.ran == [] and report.retired == [] and report.copied == []
    (said,) = report.unplaced
    assert "'No home' (ds-c) has no home case" in said and "left whole and running" in said


async def test_a_rule_never_approved_is_copied_as_a_draft() -> None:
    conn = _Conn()
    await migrate([_rule("pending")], DATASETS, conn=conn, write=True)  # type: ignore[arg-type]
    inserts = [args for sql, args in conn.ran if sql.startswith("INSERT INTO typology_rules ")]
    assert {a[7] for a in inserts} == {"draft"}
    closed = [sql for sql, _ in conn.ran if "SET status = 'rejected'" in sql]
    assert len(closed) == 1


async def test_nothing_to_convert_changes_nothing() -> None:
    conn = _Conn()
    report = await migrate([], DATASETS, conn=conn, write=True)  # type: ignore[arg-type]
    assert conn.ran == [] and report.writes == [] and report.unplaced == []
