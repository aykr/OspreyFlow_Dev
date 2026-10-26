"""`python -m scripts.close_paysim_instants --written-before <ISO time> --run-by <principal id>`
(ADR-127 decision 11, the operator step it needs).

Before decision 11 the PaySim seeder stored its `TRANSACTED` links with no end, meaning an instant;
from it, a missing end is a span still open. The script closes those links at their start, and
**only those**: other links with no end are open on purpose (the PID's `HELD_AT`, `PRESENT_AT` and
`PASSES_ITEMS_TO` while custody or presence is current, ADR-120 Amendment 9; an end an analyst
cleared through the link-change form; another recipe's `TRANSACTED`). Pure here: the store is a
recording fake that accepts only the statements the script is meant to send and refuses any other,
and any parameter named by a reserved word (rule 15); the live proof against ArcadeDB is in
`tests/adapters/graph_arcadedb/test_datasets_index.py`. What a mistake would do, and the case that
catches it:

- a PID custody span closed (`test_a_pid_held_at_span_is_left_open`);
- an open end an analyst recorded closed
  (`test_a_link_an_analyst_changed_is_left_open`);
- another recipe's `TRANSACTED` closed
  (`test_a_transacted_link_of_another_source_is_left_open`), or one that merely cites PaySim among
  other sources (`test_a_link_that_cites_other_sources_too_is_left_open`);
- a cutoff left out or with no zone (`test_the_cutoff_and_the_principal_are_required`,
  `test_a_cutoff_with_no_zone_is_refused`);
- a link written after the cutoff closed, or one with no readable creation time closed or lost from
  the count (`test_a_paysim_link_written_after_the_cutoff_is_left_open`,
  `test_a_link_with_no_readable_creation_time_is_left_open_and_counted_on_its_own`);
- a dry run that writes, a rerun that changes anything
  (`test_a_dry_run_counts_and_writes_nothing`, `test_a_rerun_closes_nothing_more`);
- a reverted or superseded link closed, or a read that forgot to leave them out
  (`test_the_read_leaves_out_reverted_and_superseded_links_and_those_already_closed`);
- an id in the summary (`test_the_summary_is_counts_only`);
- the script connecting on import (`test_importing_the_script_opens_nothing`)."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

import pytest
from scripts import close_paysim_instants as script

from adapters.graph_arcadedb.naming import physical_type_name
from ontology.loader import load_default_ontology
from tests.adapters.graph_arcadedb.edge_store import refuse_reserved_parameters

ONTOLOGY = load_default_ontology()
CUTOFF = datetime(2026, 3, 1, tzinfo=UTC)
OLD, NEW = "2026-01-05T00:00:00Z", "2026-04-01T00:00:00Z"
START = "2026-01-02T09:00:00Z"
PAYSIM = ["paysim-dataset"]


def _link(
    link_id: str,
    *,
    sources: list[str] | None = None,
    created: Any = OLD,
    valid_to: str | None = None,
) -> dict[str, Any]:
    return {
        "id": link_id,
        "sources": sources if sources is not None else PAYSIM,
        "audit": {"created_at": created},
        "interval": {"valid_from": START, "valid_to": valid_to},
        "valid_from": START,
        "valid_to": valid_to,
        "reverted": False,
        "superseded_by": None,
    }


class _Store:
    """Holds the links of one type and answers the script's statements as the real store would for
    these rows; any other statement, or a reserved-word parameter, is refused."""

    def __init__(self, label: str, links: list[dict[str, Any]]) -> None:
        self.label, self.links = label, links
        self.sent: list[str] = []

    async def sql(
        self, command: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[dict[str, Any]]:
        self.sent.append(command)
        refuse_reserved_parameters(command)
        params = params or {}
        if command.startswith("SELECT name FROM schema:types"):
            return [{"name": self.label}]
        select = re.match(
            r"SELECT id, interval, audit\.created_at AS created, "
            r"provenance\.sources\.document_id AS sources FROM `(\w+)` ",
            command,
        )
        if select:
            assert select.group(1) == self.label
            rows = [
                link
                for link in sorted(self.links, key=lambda x: x["id"])
                if link["id"] > params["last_id"]
                and link["interval"]["valid_to"] is None
                and not link["reverted"]
                and link["superseded_by"] is None
                and "paysim-dataset" in link["sources"]
            ]
            return [
                {
                    "id": r["id"],
                    "interval": r["interval"],
                    "created": r["audit"]["created_at"],
                    "sources": r["sources"],
                }
                for r in rows[: script.PAGE]
            ]
        update = re.fullmatch(
            r"UPDATE `(\w+)` SET interval = :new_interval, valid_to = valid_from WHERE id = :id",
            command,
        )
        if update:
            for link in self.links:
                if link["id"] == params["id"]:
                    link["interval"] = params["new_interval"]
                    link["valid_to"] = link["valid_from"]
            return []
        raise AssertionError(f"unexpected SQL: {command}")


def _store(links: list[dict[str, Any]]) -> _Store:
    return _Store(physical_type_name("TRANSACTED"), links)


def _run(store: _Store, *, dry_run: bool = False, changed: set[str] | None = None) -> script.Counts:
    return asyncio.run(
        script.close_paysim_instants(
            store,  # type: ignore[arg-type]
            cutoff=CUTOFF,
            dry_run=dry_run,
            ontology=ONTOLOGY,
            changed_link_ids=changed or set(),
        )
    )


def _get(store: _Store, link_id: str) -> dict[str, Any]:
    return next(link for link in store.links if link["id"] == link_id)


def _ended(link: dict[str, Any]) -> bool:
    return link["valid_to"] is not None and link["interval"]["valid_to"] is not None


def test_the_cutoff_and_the_principal_are_required() -> None:
    parser = script.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--run-by", "operator-1"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--written-before", "2026-03-01T00:00:00Z"])
    args = parser.parse_args(["--written-before", "2026-03-01T00:00:00Z", "--run-by", "operator-1"])
    assert args.dry_run is False and args.run_by == "operator-1"


def test_a_cutoff_with_no_zone_is_refused() -> None:
    assert script.parse_cutoff("2026-03-01T00:00:00Z") == CUTOFF
    assert script.parse_cutoff("2026-03-01T01:00:00+01:00") == CUTOFF
    with pytest.raises(ValueError, match="zone"):
        script.parse_cutoff("2026-03-01T00:00:00")
    with pytest.raises(ValueError):
        script.parse_cutoff("last Tuesday")


def test_a_paysim_transacted_link_with_no_end_is_closed_at_its_start() -> None:
    store = _store([_link("a-paysim")])
    counts = _run(store)
    link = _get(store, "a-paysim")
    assert link["interval"] == {"valid_from": START, "valid_to": START}
    assert link["valid_to"] == link["valid_from"]
    assert counts.closed == 1


def test_a_pid_held_at_span_is_left_open() -> None:
    """The PID writes `HELD_AT` open for current custody: not a `TRANSACTED` link, and not PaySim's.
    The fake holds only `TRANSACTED` (the script reads no other type), so it is shown by what the
    script asks for: one type, `TRANSACTED`, and no other."""
    store = _store([_link("a-paysim")])
    _run(store)
    reads = [c for c in store.sent if c.startswith("SELECT id, interval")]
    assert reads and all(f"`{physical_type_name('TRANSACTED')}`" in c for c in reads)
    assert not any(physical_type_name(name) in " ".join(store.sent) for name in (
        "HELD_AT", "PRESENT_AT", "PASSES_ITEMS_TO"
    ))  # fmt: skip
    assert script.LINK_TYPE == "TRANSACTED"


def test_a_transacted_link_of_another_source_is_left_open() -> None:
    store = _store([_link("a-aml", sources=["aml_transactions.csv"])])
    counts = _run(store)
    assert not _ended(_get(store, "a-aml")) and counts.closed == 0


def test_a_link_that_cites_other_sources_too_is_left_open() -> None:
    store = _store([_link("a-mixed", sources=["paysim-dataset", "aml_transactions.csv"])])
    counts = _run(store)
    assert not _ended(_get(store, "a-mixed")) and counts.closed == 0


def test_a_link_an_analyst_changed_is_left_open() -> None:
    """A change through the link-change route is a successor carrying the original's sources; it is
    known by its id in `link_changes`, and an end an analyst cleared stays open."""
    store = _store([_link("a-changed"), _link("b-seeded")])
    counts = _run(store, changed={"a-changed"})
    assert not _ended(_get(store, "a-changed"))
    assert _ended(_get(store, "b-seeded"))
    assert counts.closed == 1 and counts.left_open_changed_by_an_analyst == 1


def test_a_paysim_link_written_after_the_cutoff_is_left_open() -> None:
    store = _store([_link("a-new", created=NEW)])
    counts = _run(store)
    assert not _ended(_get(store, "a-new"))
    assert counts.left_open_after_cutoff == 1 and counts.closed == 0


def test_a_link_with_no_readable_creation_time_is_left_open_and_counted_on_its_own() -> None:
    store = _store(
        [_link("a-none", created=None), _link("b-garbled", created="last spring"), _link("c-ok")]
    )
    counts = _run(store)
    assert not _ended(_get(store, "a-none")) and not _ended(_get(store, "b-garbled"))
    assert _ended(_get(store, "c-ok"))
    assert counts.left_open_no_creation_time == 2
    assert counts.left_open_after_cutoff == 0 and counts.closed == 1
    assert "no creation time: 2" in script.describe(counts)


def test_a_dry_run_counts_and_writes_nothing() -> None:
    store = _store([_link("a-paysim"), _link("b-new", created=NEW)])
    before = [dict(link) for link in store.links]
    counts = _run(store, dry_run=True)
    assert counts.closed == 1 and counts.dry_run is True
    assert store.links == before
    assert not any(command.startswith("UPDATE") for command in store.sent)


def test_a_rerun_closes_nothing_more() -> None:
    store = _store([_link("a-paysim"), _link("b-new", created=NEW)])
    first = _run(store)
    after_first = [dict(link) for link in store.links]
    second = _run(store)
    assert first.closed == 1 and second.closed == 0
    assert store.links == after_first


def test_the_read_leaves_out_reverted_and_superseded_links_and_those_already_closed() -> None:
    """The fake filters on its own account; this pins that the script's statement asks for it, and
    for the PaySim marker."""
    store = _store([_link("a-paysim")])
    _run(store)
    select = next(command for command in store.sent if command.startswith("SELECT id, interval"))
    assert "interval.valid_to IS NULL" in select
    assert "reverted" in select and "superseded_by IS NULL" in select
    assert "CONTAINS 'paysim-dataset'" in select
    assert "ORDER BY id" in select


def test_the_summary_is_counts_only() -> None:
    store = _store([_link("a-paysim"), _link("b-new", created=NEW)])
    counts = _run(store)
    text = script.describe(counts)
    for link in store.links:
        assert link["id"] not in text
    assert "closed 1" in text


def test_importing_the_script_opens_nothing() -> None:
    import importlib

    importlib.reload(script)  # a reload that opened a store would fail here with no stack
    assert callable(script.main)
