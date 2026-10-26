"""Rule 3, ADR-127 Amendment 23 (B2-10a): a load's report names every distinct marking its rows were
written at (`LoadReport.markings`), and a pipeline's report the union over its branches, so the
routes that show a run's counts can withhold them from a reader who may not view one of the
markings (`test_run_counts_withheld.py`). What a mistake would do, and the case that catches it:

- the engine reporting the source's marking alone, so R15's SECRET link is not named
  (`test_r15s_report_names_every_marking_its_rows_were_written_at`);
- a marking named twice, or one a row was never written at
  (`test_a_marking_is_named_once_and_only_where_a_row_was_written`);
- the pipeline's union taking one branch, or none
  (`test_the_union_keeps_every_marking_once_in_first_seen_order`,
  `test_a_pipelines_report_is_the_union_over_its_branches` and
  `test_a_two_branch_pipeline_reports_the_union_of_both_branches_markings`);
- the held-rows release, which writes through the same engine, naming none
  (covered by the engine case: both go through `run_recipe`)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from services.api.pipeline_run import run_published_pipeline
from services.api.studio_publish import load_with_rules
from services.ingest.engine import distinct_markings

from adapters.media_objectstore.testing import InMemoryMediaStore
from demo_fixtures import pid_files
from ontology.handling import principal_may_view
from schemas.domain import Handling, Principal
from schemas.ingest import (
    LoadReport,
    PipelineGraph,
    Recipe,
    StudioRecipeDraft,
    StudioRecipeStatus,
)
from tests.ingest.pid_golden_support import (
    CASE,
    LOADER,
    ONTOLOGY,
    SCHEME,
    recipe_for,
    load,
    loaded,
    marking,
    row_marking,
    rows_of,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_load_record_created_and_merged import _recipe, _row
from tests.ingest.test_referenced_in_change_stream import _published
from tests.ingest.test_row_keys import Sink

FILE = "pid_conflicts.csv"
#: Every file the seed loads before R15, in the seed's order (ADR-127 Amendment 23: each golden
#: test's BEFORE is derived from `SEED_ORDER`, never typed): so the markings of the elements R15
#: finds are the seed's.
ORDER = [stage.file for stage in pid_files.SEED_ORDER]
BEFORE = tuple(ORDER[: ORDER.index(FILE)])


def _h(classification: str, unit: str = "unit-1", code: str = "P") -> Handling:
    return Handling(
        classification=classification, handling_code=code, owning_unit=unit, originator=unit
    )


def _with_one_secret_row() -> list[dict[str, str]]:
    """R15's file as written, with its first row's handling columns set to SECRET (the owner dropped
    the plan's own covert link, ADR-120 Amendment 16, so the rule-3 behaviour is tested over a marking
    these tests plant: ADR-127 Amendment 31). Built here; the fixtures are untouched."""
    rows = [dict(r) for r in rows_of(FILE)]
    rows[0] = {**rows[0], "classification": "SECRET"}
    return rows


def _marks(rows: list[dict[str, str]]) -> set[tuple[Any, ...]]:
    return {row_marking(r) for r in rows}


async def test_r15s_report_names_every_marking_its_rows_were_written_at() -> None:
    graph, store, _ = await loaded(*BEFORE)
    rows = _with_one_secret_row()
    report, _events = await load(graph, FILE, Sink(store, CASE), rows=rows)
    assert report.rejections == []
    written = _marks(rows)
    assert {m[0] for m in written} == {"OFFICIAL", "SECRET"}, "the planted SECRET row"
    assert {marking(h) for h in report.markings} == written
    assert report.edges_created > 0


async def test_a_marking_is_named_once_and_only_where_a_row_was_written() -> None:
    graph, store, _ = await loaded(*BEFORE)
    rows = _with_one_secret_row()
    report, _events = await load(graph, FILE, Sink(store, CASE), rows=rows)
    keys = [marking(h) for h in report.markings]
    assert len(keys) == len(set(keys)), "each distinct marking once"
    second, _ = await load(graph, FILE, Sink(store, CASE), "load-2", rows=rows)
    assert second.rows_already_loaded == len(rows)
    # Amendment 26: every row read is marked, written or not. A re-run wrote nothing, yet its counts
    # (`rows_read`, `rows_already_loaded`) include the SECRET row, so it names the same markings.
    assert {marking(h) for h in second.markings} == {marking(h) for h in report.markings}
    assert any(h.classification == "SECRET" for h in second.markings)


def _broken(row: dict[str, str]) -> dict[str, str]:
    return {**row, "nomis_id_a": ""}


async def test_a_rejected_row_is_marked_too() -> None:
    graph, store, _ = await loaded(*BEFORE)
    rows = _with_one_secret_row()
    secret = next(r for r in rows if row_marking(r)[0] == "SECRET")
    official = next(r for r in rows if row_marking(r)[0] == "OFFICIAL")
    report, _events = await load(graph, FILE, Sink(store, CASE), rows=[official, _broken(secret)])
    assert [r.row_index for r in report.rejections] == [1], "the SECRET row was rejected"
    assert {h.classification for h in report.markings} == {"OFFICIAL", "SECRET"}
    assert report.rows_read == 2


async def test_a_rejection_carries_the_marking_of_its_row() -> None:
    graph, store, _ = await loaded(*BEFORE)
    secret = next(r for r in _with_one_secret_row() if row_marking(r)[0] == "SECRET")
    report, _events = await load(graph, FILE, Sink(store, CASE), rows=[_broken(secret)])
    (rejection,) = report.rejections
    assert rejection.marking is not None and rejection.marking.classification == "SECRET"


def test_every_row_read_is_marked_even_when_the_case_already_holds_it() -> None:
    from services.ingest.engine import row_group_keys, resolve_rows_keyed

    recipe = recipe_for(FILE)
    rows = _with_one_secret_row()
    keys = [k for k in row_group_keys(recipe, rows) if k is not None]
    done = resolve_rows_keyed(
        recipe, rows, load_id="l", source=FILE, ontology=ONTOLOGY, scheme=SCHEME,
        already_loaded=frozenset(keys),
    )  # fmt: skip
    assert done.rows_already_loaded == len(rows) and done.staged_rows == []
    assert {marking(h) for h in done.markings} == _marks(rows)
    assert any(h.classification == "SECRET" for h in done.markings)


def test_a_row_whose_marking_cannot_be_resolved_records_the_most_restrictive_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.ingest import engine
    from services.ingest.engine import RowRejected, most_restrictive_markings

    def unresolvable(*args: Any, **kwargs: Any) -> Any:
        raise RowRejected("its elements name different units under a restricted code")

    monkeypatch.setattr(engine, "row_marking", unresolvable)
    recipe = recipe_for(FILE)
    done = engine.resolve_rows_keyed(
        recipe, list(rows_of(FILE))[:3], load_id="l", source=FILE, ontology=ONTOLOGY, scheme=SCHEME
    )
    assert done.markings == most_restrictive_markings(recipe, SCHEME)
    # it withholds from a SECRET reader of any one unit, and from a reader of none
    for unit in ("fenwick-moor-security", "regional-intel-unit", "elsewhere"):
        reader = Principal(
            id="r", clearance="SECRET", org_unit=unit, receivable_handling_codes=["P", "C", "R"]
        )
        assert not all(principal_may_view(h, reader, SCHEME) for h in done.markings), unit


async def test_the_held_content_write_site_records_its_marking() -> None:
    """The holder entity carries its own marking, and the `Document` it holds is written at the same
    one (`_write_held_content`). The holder's site records it first, so no mutation of the second
    site alone is visible here: this proves the marking reaches the report on a load that holds
    content, which is what the second site exists to guarantee if the first is ever skipped."""
    recipe = _recipe(content=True)
    document = recipe.model_dump(by_alias=True)
    document["row_template"]["entities"][0]["handling"] = {"classification": "SECRET"}
    recipe = Recipe.model_validate(document)
    graph = MergingGraph(ONTOLOGY)
    report, _events, _held = await load_with_rules(
        recipe, [_row("SYN-1", "SYN-2", 1, memo="a note")], LOADER, graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY, load_id="l", investigation_scope="case-1", source="private_cash.csv",
        media=InMemoryMediaStore(), rules=None, scheme=SCHEME,
    )  # fmt: skip
    assert [e for e in graph.committed_edges if e.type == "HOLDS"], "a held content link was written"
    assert {h.classification for h in report.markings} == {"OFFICIAL", "SECRET"}


def test_the_union_keeps_every_marking_once_in_first_seen_order() -> None:
    a, b, c = _h("OFFICIAL"), _h("SECRET"), _h("OFFICIAL", unit="unit-2", code="R")
    assert distinct_markings([a, b], [b, c], []) == [a, b, c]
    assert distinct_markings([c], [a]) == [c, a]
    assert distinct_markings() == []
    assert distinct_markings([a, a]) == [a]


async def test_a_pipelines_report_is_the_union_over_its_branches(tmp_path: Path) -> None:
    repo, draft = _published(tmp_path)
    graph = MergingGraph(ONTOLOGY)
    report = await run_published_pipeline(
        draft, LOADER, graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY, scheme=SCHEME, load_id="p-1", investigation_scope="case-1",
        repo_root=repo, recogniser_for=lambda name: None, media=InMemoryMediaStore(),
    )  # fmt: skip
    assert report.branches, "the run had a branch"
    assert report.markings, "and wrote rows"
    assert report.markings == distinct_markings(*(b.report.markings for b in report.branches))


async def test_a_two_branch_pipeline_reports_the_union_of_both_branches_markings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One branch wrote only OFFICIAL rows and the other a SECRET one: the pipeline's counts are
    both branches' together, so its report must name both markings. The branches' runs are stood in
    for (each returns the report the engine would), since a real two-branch run needs two sources;
    the single-branch case above is the real run."""
    official, secret = _h("OFFICIAL"), _h("SECRET")
    by_branch = {"a": [official], "b": [official, secret]}

    async def branch_run(draft: Any, principal: Any, *, load_id: str, **kwargs: Any) -> LoadReport:
        return LoadReport(
            load_id=load_id, recipe_id=draft.recipe_id, recipe_version=draft.version,
            markings=by_branch[load_id.rsplit(":", 1)[1]],
        )  # fmt: skip

    monkeypatch.setattr("services.api.pipeline_run.run_published_recipe", branch_run)
    pipeline = PipelineGraph.model_validate(
        {
            "nodes": [
                {"id": "a", "kind": "source", "label": "A"},
                {"id": "b", "kind": "source", "label": "B"},
            ],
            "edges": [],
        }
    )
    draft = StudioRecipeDraft(  # type: ignore[call-arg]
        recipe_id="two-branches", version=1, status=StudioRecipeStatus.PUBLISHED, label="Two",
        owning_unit="unit-1", created_by="analyst-1", created_at=datetime(2026, 10, 26, tzinfo=UTC),
        pipeline=pipeline,
    )  # fmt: skip
    report = await run_published_pipeline(
        draft, LOADER, graph=MergingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ontology=ONTOLOGY, scheme=SCHEME, load_id="p-2", investigation_scope="case-1",
        repo_root=tmp_path, recogniser_for=lambda name: None, media=InMemoryMediaStore(),
    )  # fmt: skip
    assert [b.source_id for b in report.branches] == ["a", "b"]
    assert report.markings == [official, secret]
