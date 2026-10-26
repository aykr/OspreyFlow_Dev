"""`python -m scripts.revert_load <load_id> --reverted-by <principal id>` (ADR-127 decision 6).

No store is needed: the script's own logic (what it says and which exit code it gives) is `run`,
called here with the revert's collaborators replaced; the revert itself is proved in
`tests/ingest/test_revert_load.py`. What a mistake would do, and the case that catches it:

- the script that connects on import, so a test or a tool importing it opens a store
  (`test_importing_the_script_opens_nothing`);
- no `--reverted-by`, which would record nobody in the ledger and the audit trail
  (`test_the_reverting_principal_is_required`);
- a refusal printed with the ids of what the load merged into, to whoever ran it
  (`test_a_refusal_names_the_reason_and_no_id_unless_asked`);
- a failure part way reported as success, or with nothing said of what was done
  (`test_a_failure_part_way_says_what_was_done_and_to_run_it_again`)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from scripts import revert_load as script
from services.ingest.load_revert import (
    LoadReverted,
    Refusal,
    RevertIncomplete,
    RevertRefused,
    RevertResult,
)

from schemas.domain import Principal

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


class _Graph:
    """The two reads `--show-ids` filters through: what `viewer` can read among the ids asked."""

    def __init__(self, readable_nodes: set[str], readable_links: set[str]) -> None:
        self.readable_nodes, self.readable_links = readable_nodes, readable_links
        self.asked: list[tuple[str, list[str], Principal]] = []

    async def get_nodes(self, ids: Any, principal: Principal) -> list[Any]:
        self.asked.append(("nodes", list(ids), principal))
        return [SimpleNamespace(id=i) for i in sorted(set(ids) & self.readable_nodes)]

    async def get_edges(self, ids: Any, principal: Principal) -> list[Any]:
        self.asked.append(("links", list(ids), principal))
        return [SimpleNamespace(id=i) for i in sorted(set(ids) & self.readable_links)]


VIEWER = Principal(id="operator-1", clearance="OFFICIAL", org_unit="unit-1")


def _run(
    outcome: Any,
    *,
    show_ids: bool = False,
    viewer: Principal | None = None,
    graph: _Graph | None = None,
) -> tuple[int, str]:
    lines: list[str] = []
    called: list[str] = []

    async def revert(
        load_id: str, *, reverted_by: str, deps: object, now: datetime
    ) -> RevertResult:
        called.append(load_id)
        assert (load_id, reverted_by, now) == ("load-1", "operator-1", NOW)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    code = asyncio.run(
        script.run(
            "load-1",
            reverted_by="operator-1",
            deps=SimpleNamespace(graph=graph or _Graph(set(), set())),  # type: ignore[arg-type]
            now=NOW,
            show_ids=show_ids,
            viewer=viewer,
            say=lines.append,
            revert=revert,  # type: ignore[arg-type]
        )
    )
    if code == 64:
        assert called == [], "refused before anything was reverted"
    return code, "\n".join(lines)


def _done(load_id: str) -> LoadReverted:
    return LoadReverted(
        load_id=load_id, nodes=4, links=3, events=120, geometries=2, held_rows=1, alerts=1
    )


def test_a_revert_that_finishes_reports_each_load_in_order_and_exits_zero() -> None:
    code, text = _run(
        RevertResult(reverted=[_done("rel-2"), _done("load-1")], already_reverted=["rel-1"])
    )
    assert code == 0
    assert text.index("rel-2") < text.index("load-1")
    assert "4 node(s)" in text and "3 link(s)" in text and "120 event(s)" in text
    assert "rel-1" in text and "already" in text


def _merged_refusal() -> RevertRefused:
    return RevertRefused(
        [
            Refusal("load-1", "merged_links", 3, ("link-ok", "link-hidden-1", "link-hidden-2")),
            Refusal("load-1", "merged_nodes", 2, ("doc-ok", "doc-hidden")),
        ]
    )


def test_a_refusal_names_the_reason_and_no_id_unless_asked() -> None:
    code, text = _run(_merged_refusal())
    assert code == 1
    assert "merged into 3 link(s)" in text and "nothing was changed" in text
    assert "link-ok" not in text and "doc-ok" not in text and "--show-ids" in text


def test_show_ids_prints_only_the_ids_the_reverting_principal_can_read() -> None:
    graph = _Graph(readable_nodes={"doc-ok"}, readable_links={"link-ok"})
    code, text = _run(_merged_refusal(), show_ids=True, viewer=VIEWER, graph=graph)
    assert code == 1
    assert "link-ok" in text and "doc-ok" in text
    assert "hidden" not in text, "an id the principal cannot read is not printed"
    assert "2 more" in text and "1 more" in text, "the rest stay a count"
    assert {(kind, who.id) for kind, _, who in graph.asked} == {
        ("links", "operator-1"),
        ("nodes", "operator-1"),
    }, "read through the graph as the principal, not by a filter of our own"


def test_show_ids_with_nothing_readable_prints_no_id_and_says_how_many() -> None:
    graph = _Graph(set(), set())
    code, text = _run(_merged_refusal(), show_ids=True, viewer=VIEWER, graph=graph)
    assert code == 1 and "ok" not in text.replace("nothing", "") and "3 more" in text


def test_show_ids_is_refused_when_the_principal_cannot_be_resolved() -> None:
    """Without a clearance and unit to read as, there is no filter to apply, so no id is shown and
    the revert is not run: refused before it starts, because a refusal comes after nothing."""
    code, text = _run(_merged_refusal(), show_ids=True, viewer=None)
    assert code == 64
    assert "--clearance" in text and "--org-unit" in text
    assert "link-ok" not in text


def test_a_failure_part_way_says_what_was_done_and_to_run_it_again() -> None:
    incomplete = RevertIncomplete(
        done=[_done("rel-1")],
        failed_load_id="load-1",
        failed_step="events",
        cause=RuntimeError("the analytics store is down"),
    )
    code, text = _run(incomplete)
    assert code == 2
    assert "rel-1" in text and "load-1" in text and "events" in text
    assert "the analytics store is down" in text and "again" in text


def test_the_reverting_principal_is_required() -> None:
    with pytest.raises(SystemExit):
        script.build_parser().parse_args(["load-1"])
    args = script.build_parser().parse_args(["load-1", "--reverted-by", "operator-1"])
    assert (args.load_id, args.reverted_by, args.show_ids) == ("load-1", "operator-1", False)
    assert script.viewer_from(args) is None
    args = script.build_parser().parse_args(["load-1", "--reverted-by", "o", "--show-ids"])
    assert args.show_ids is True


def test_importing_the_script_opens_nothing() -> None:
    """`main` builds the connections; the module itself must not, or importing it (as this test
    does) would need every store."""
    assert callable(script.main) and callable(script.run)


def test_the_principal_is_built_from_the_arguments_as_the_seed_scripts_do() -> None:
    parse = script.build_parser().parse_args
    args = parse(
        ["x", "--reverted-by", "op", "--show-ids", "--clearance", "SECRET", "--org-unit", "unit-9"]
    )
    viewer = script.viewer_from(args)
    assert viewer is not None
    assert (viewer.id, viewer.clearance, viewer.org_unit, viewer.datasets) == (
        "op", "SECRET", "unit-9", None,
    )  # fmt: skip
    args = parse(
        ["x", "--reverted-by", "op", "--clearance", "OFFICIAL", "--org-unit", "u",
         "--dataset", "enron", "--receivable-code", "R"]
    )  # fmt: skip
    viewer = script.viewer_from(args)
    assert viewer is not None
    assert (viewer.datasets, viewer.receivable_handling_codes) == (["enron"], ["R"])
    # One of the two missing is no principal at all.
    assert script.viewer_from(parse(["x", "--reverted-by", "op", "--clearance", "SECRET"])) is None
    assert script.viewer_from(parse(["x", "--reverted-by", "op", "--org-unit", "u"])) is None


def test_what_was_left_is_said_as_a_count_and_no_id_is_printed() -> None:
    done = LoadReverted(
        load_id="load-1", nodes=3, links=2, events=9, geometries=1, held_rows=0, alerts=0,
        geometries_kept=2, nodes_left_alone=1, left_alone_node_ids=("secret-node",),
    )  # fmt: skip
    code, text = _run(RevertResult(reverted=[done]))
    assert code == 0
    assert "1 node(s) left alone" in text and "2 point(s) kept" in text
    assert "secret-node" not in text


def test_the_two_new_refusals_are_worded_without_an_id() -> None:
    refusals = RevertRefused(
        [
            Refusal("load-1", "merged_into_by_later_load", 2),
            Refusal("load-1", "rests_on_by_live_links", 3),
        ]
    )
    code, text = _run(refusals)
    assert code == 1 and "a later load merged into 2 element(s)" in text
    assert "3 live link(s) outside it rest on nodes it created" in text


def test_the_script_says_its_clearance_is_self_declared_and_it_is_never_routed_through_the_conduit() -> (
    None
):
    """`--clearance` is whatever the operator types, so the `--show-ids` filter is a courtesy, not
    access control: the script must never be reachable from a route."""
    doc = " ".join((script.__doc__ or "").split())
    assert "self-declared" in doc
    assert "never be routed through the Conduit" in doc


def test_the_working_sets_and_the_alerts_citing_events_are_reported_in_counts() -> None:
    done = LoadReverted(
        load_id="load-1", nodes=3, links=2, events=9, geometries=1, held_rows=0, alerts=1,
        alerts_citing_events=4, cases=2,
    )  # fmt: skip
    code, text = _run(RevertResult(reverted=[done]))
    assert code == 0
    assert "2 working set(s) cleared" in text
    assert "4 alert(s) citing its events closed" in text


def test_the_script_reaches_the_working_sets_the_history_and_the_caches_directly() -> None:
    """It runs outside the Conduit, so it builds the working-set reach itself: the store on Valkey,
    the stored history, and the cache clear, all handed to the revert (`RevertDeps`). That
    construction is `build_revert_deps`, which the Prison Intelligence seed's reset shares
    (ADR-127 Amendment 23: factored out, not copied)."""
    import inspect

    source = inspect.getsource(script.build_revert_deps)
    for needed in (
        "ValkeyWorkingSetStore",
        "WorkingSetReverter",
        "invalidate_every_cache",
    ):
        assert needed in source, needed
    assert "working_sets=" in source and "invalidate_caches=" in source
    assert "InvestigationHistoryStore" in inspect.getsource(script._main)
    assert "build_revert_deps(" in inspect.getsource(script._main), "the script uses its own"


def test_the_shared_construction_hands_every_store_it_is_given_to_the_revert() -> None:
    """`build_revert_deps` wires what it is given and opens nothing of its own: each store lands in
    its own field, and the cache clear and the working-set reach are built over the Valkey given."""
    marks = {
        name: object()
        for name in ("graph", "analytics", "ledger", "held_rows", "alerts", "audit", "history")
    }
    valkey = SimpleNamespace(marker="valkey")
    deps = script.build_revert_deps(
        scheme=object(), valkey=valkey, **marks  # type: ignore[arg-type]
    )
    assert deps.graph is marks["graph"] and deps.analytics is marks["analytics"]
    assert deps.ledger is marks["ledger"] and deps.held_rows is marks["held_rows"]
    assert deps.alerts is marks["alerts"] and deps.audit is marks["audit"]
    assert type(deps.working_sets).__name__ == "WorkingSetReverter"
    assert callable(deps.invalidate_caches)


def test_the_script_says_a_revert_should_run_with_the_conduit_quiet() -> None:
    doc = " ".join((script.__doc__ or "").split())
    assert "Quiesce the Conduit" in doc
    assert "DuckDB engine that is required" in doc
    assert "With ClickHouse it is advised" in doc
