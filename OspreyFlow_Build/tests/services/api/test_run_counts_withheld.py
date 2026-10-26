"""Rule 3, ADR-127 Amendment 23 (B2-10a), "Counts the reader cannot see": a run's counts include the
rows it wrote above the source's own marking (R15's include its SECRET link), and Data feeds showed
them to any reader of the source. The engine now reports every distinct marking its rows were
written at, the ledger keeps them (`RecipeRun.markings`), and the two places counts are shown
withhold them from a reader who may not view any one of those markings: `_schedule_run_view` (a
recipe's runs, the schedule panel and Data feeds) and the run route's own `report_view`.

What a mistake would do, and the case that catches it:

- the view ignoring the markings and judging the source alone, so an OFFICIAL reader is shown counts
  that include a SECRET link
  (`test_an_official_reader_is_given_no_counts_when_one_row_was_secret`);
- the view judging the classification only, so a reader of another unit is shown counts that
  include a row under a restricted code of a unit they are not in
  (`test_a_reader_of_another_unit_is_given_no_counts_when_a_row_was_under_a_restricted_code`);
- the view withholding from everyone (`test_a_reader_cleared_for_every_marking_is_given_the_counts`);
- a run written before the column existed behaving differently from before
  (`test_a_run_with_no_recorded_markings_reads_as_the_sources_alone`);
- the ledger not keeping the markings the run reports, or not reading them back
  (`test_finish_hands_the_reports_markings_to_the_ledger`,
  `test_a_ledger_row_reads_its_markings_and_a_null_reads_as_the_source`; the real column is in
  `test_recipe_runs.py`, live);
- a route that builds its answer without the reader
  (`test_every_ledger_route_withholds_counts_for_a_marking_the_reader_may_not_view`,
  `test_the_run_route_and_the_release_route_hand_the_reader_to_the_view`);
- the run route's own answer showing the counts to a loader who may not view every marking
  (`test_the_run_routes_answer_withholds_counts_for_a_marking_the_loader_may_not_view` and its
  pipeline twin), and that answer showing nothing of the withheld run
  (`test_a_withheld_answer_carries_no_count_word_or_branch`)."""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    _schedule_run_view,
    app,
    get_audit,
    get_handling_scheme,
    get_investigations,
    get_principal,
    get_recipe_runs,
    get_studio_recipes,
)
from services.api.load_records import report_view
from services.api import recipe_runs as recipe_runs_module
from services.api.recipe_runs import RecipeRun, RecipeRunStore, _row

from ontology.handling import load_uk_le_scheme
from schemas.domain import Handling, Principal
from schemas.ingest import BranchRunReport, LoadReport, PipelineRunReport, RejectionRecord
from tests.services.api.any_case import AnyCase
from tests.services.api.test_run_ledger_read_side import _Audit, _Recipes

CORE = Path(__file__).resolve().parents[4] / "OspreyFlow_Core"
SCHEME = load_uk_le_scheme()
NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)

OFFICIAL_ROW = Handling(
    classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
)
SECRET_ROW = Handling(
    classification="SECRET", handling_code="P", owning_unit="unit-1", originator="unit-1"
)
#: A row under a restricted code of another unit: OFFICIAL, so only the unit gates it.
OTHER_UNIT_ROW = Handling(
    classification="OFFICIAL", handling_code="R", owning_unit="unit-2", originator="unit-2"
)
SOURCE = Handling(
    classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
)


def reader(clearance: str, unit: str = "unit-1", codes: tuple[str, ...] = ("P", "C")) -> Principal:
    return Principal(
        id=f"reader-{clearance}-{unit}", clearance=clearance, org_unit=unit,
        receivable_handling_codes=list(codes),
        roles=["source_approver", "reports_viewer", "osprey-admin"], datasets=["ds-case"],
    )  # fmt: skip


OFFICIAL_READER = reader("OFFICIAL")
SECRET_READER = reader("SECRET", codes=("P", "C", "R"))
UNIT_2_READER = reader("OFFICIAL", unit="unit-2", codes=("P", "C", "R"))


def _run(markings: list[Handling] | None) -> RecipeRun:
    fields: dict[str, Any] = {} if markings is None else {"markings": markings}
    return RecipeRun(
        run_id="run-1", recipe_id="recipe-1", recipe_version=1, investigation_id="inv-1",
        trigger="manual", slot=None, run_as="loader-1", source=SOURCE, started_at=NOW,
        finished_at=NOW, outcome="succeeded", rows_read=1_200, nodes_created=0,
        nodes_referenced=40, edges_created=311, rows_rejected=0, rows_held=0, load_id="load-1",
        failure=None, source_file="pid_conflicts.csv|9|1", **fields,
    )  # fmt: skip


def _counts_shown(view: Any) -> bool:
    return (view.rows_read, view.edges_created) == (1_200, 311) and view.withheld is False


def _counts_withheld(view: Any) -> bool:
    return (
        view.withheld is True
        and view.rows_read is None
        and view.nodes_created is None
        and view.nodes_referenced is None
        and view.edges_created is None
        and view.rows_rejected is None
        and view.rows_held is None
        and view.load_id is None
        and view.file is None
    )


# --- the ledger's view (`_schedule_run_view`) ----------------------------------------------------


def test_an_official_reader_is_given_no_counts_when_one_row_was_secret() -> None:
    run = _run([OFFICIAL_ROW, SECRET_ROW])
    assert _counts_withheld(_schedule_run_view(run, OFFICIAL_READER, SCHEME))


def test_a_reader_of_another_unit_is_given_no_counts_when_a_row_was_under_a_restricted_code() -> None:
    run = _run([OFFICIAL_ROW, OTHER_UNIT_ROW])
    # unit-1 reads the source, and every row's classification, but not unit-2's restricted code
    assert OFFICIAL_READER.clearance == "OFFICIAL"
    assert _counts_withheld(_schedule_run_view(run, OFFICIAL_READER, SCHEME))
    assert _counts_withheld(_schedule_run_view(run, reader("SECRET", codes=("P", "C", "R")), SCHEME))
    # the unit the code names reads it
    assert _counts_shown(_schedule_run_view(run, UNIT_2_READER, SCHEME))


def test_a_reader_cleared_for_every_marking_is_given_the_counts() -> None:
    run = _run([OFFICIAL_ROW, SECRET_ROW])
    assert _counts_shown(_schedule_run_view(run, SECRET_READER, SCHEME))
    both = _run([OFFICIAL_ROW, SECRET_ROW, OTHER_UNIT_ROW])
    assert _counts_withheld(_schedule_run_view(both, SECRET_READER, SCHEME))
    cleared = reader("SECRET", unit="unit-2", codes=("P", "C", "R"))
    # unit-2 is not unit-1: the SECRET row is open to its clearance, the restricted code to its unit
    assert _counts_shown(_schedule_run_view(both, cleared, SCHEME))


def test_a_run_with_no_recorded_markings_reads_as_the_sources_alone() -> None:
    run = _run(None)
    assert run.markings == [SOURCE]
    assert _counts_shown(_schedule_run_view(run, OFFICIAL_READER, SCHEME))
    source_secret = run.model_copy(
        update={"source": SECRET_ROW, "markings": [SECRET_ROW]}
    )
    assert _counts_withheld(_schedule_run_view(source_secret, OFFICIAL_READER, SCHEME))


def test_the_source_is_still_judged_when_the_markings_are_all_open() -> None:
    run = _run([OFFICIAL_ROW]).model_copy(update={"source": SECRET_ROW})
    assert _counts_withheld(_schedule_run_view(run, OFFICIAL_READER, SCHEME))


def test_a_run_that_wrote_nothing_is_judged_by_its_source() -> None:
    run = _run([])
    assert _counts_shown(_schedule_run_view(run, OFFICIAL_READER, SCHEME))


# --- every ledger route ----------------------------------------------------------------------------


class _RunsWithAHighRow:
    async def for_recipe(self, recipe_id: str, *, limit: int = 50) -> list[RecipeRun]:
        return [_run([OFFICIAL_ROW, SECRET_ROW])][:limit]


@pytest.fixture
def client() -> Any:
    app.dependency_overrides[get_studio_recipes] = _Recipes
    app.dependency_overrides[get_recipe_runs] = _RunsWithAHighRow
    app.dependency_overrides[get_audit] = _Audit
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    yield TestClient(app)
    app.dependency_overrides.clear()


ROUTES = [
    "/v1/investigations/inv-1/ingest/recipes/recipe-1/runs",
    "/v1/admin/schedules/recipe-1/runs",
    "/v1/investigations/inv-1/data-feeds",
]


def _first(path: str, body: Any) -> dict[str, Any]:
    run = body[0]["last_run"] if path.endswith("data-feeds") else body[0]
    assert isinstance(run, dict)
    return run


@pytest.mark.parametrize("path", ROUTES)
def test_every_ledger_route_withholds_counts_for_a_marking_the_reader_may_not_view(
    client: Any, path: str
) -> None:
    app.dependency_overrides[get_principal] = lambda: OFFICIAL_READER
    response = client.get(path)
    assert response.status_code == 200, response.text
    run = _first(path, response.json())
    assert run["withheld"] is True
    assert run["rows_read"] is None and run["edges_created"] is None


@pytest.mark.parametrize("path", ROUTES)
def test_every_ledger_route_shows_counts_to_a_reader_cleared_for_every_marking(
    client: Any, path: str
) -> None:
    """The run's own source is OFFICIAL and one row was SECRET: a SECRET reader of the same unit
    is shown the counts, so the routes do not withhold from everyone."""
    app.dependency_overrides[get_principal] = lambda: SECRET_READER
    response = client.get(path)
    assert response.status_code == 200, response.text
    run = _first(path, response.json())
    assert run["withheld"] is False and run["rows_read"] == 1_200 and run["edges_created"] == 311


# --- the run route's own answer (`report_view`) ------------------------------------------------------


def _report(markings: list[Handling]) -> LoadReport:
    return LoadReport(
        load_id="load-1", recipe_id="recipe-1", recipe_version=1, rows_read=1_200,
        nodes_referenced=40, edges_created=311, rows_held=2, rule_notes=["a note"],
        rejections=[RejectionRecord(row_index=4, reason="no date", sample="")],
        markings=markings,
    )  # fmt: skip


def _pipeline(branch_markings: list[list[Handling]]) -> PipelineRunReport:
    branches = [
        BranchRunReport(source_id=f"s{i}", source_label=f"Source {i}", report=_report(m))
        for i, m in enumerate(branch_markings)
    ]
    union = [h for m in branch_markings for h in m]
    return PipelineRunReport(
        load_id="run-1", recipe_id="recipe-1", recipe_version=1, rows_read=1_200,
        edges_created=311, branches=branches, markings=list({_key(h): h for h in union}.values()),
    )  # fmt: skip


def _key(handling: Handling) -> str:
    return handling.model_dump_json()


def test_the_run_routes_answer_withholds_counts_for_a_marking_the_loader_may_not_view() -> None:
    view = report_view(_report([OFFICIAL_ROW, SECRET_ROW]), OFFICIAL_READER, SCHEME)
    assert view.withheld is True
    assert (view.rows_read, view.nodes_referenced, view.edges_created, view.rows_held) == (0, 0, 0, 0)
    assert view.rejections == [] and view.rule_notes == []
    shown = report_view(_report([OFFICIAL_ROW, SECRET_ROW]), SECRET_READER, SCHEME)
    assert shown.withheld is False and (shown.rows_read, shown.edges_created) == (1_200, 311)
    assert shown.rows_held == 2 and len(shown.rejections) == 1


def test_a_reader_of_another_unit_is_given_no_counts_in_the_run_routes_answer() -> None:
    report = _report([OFFICIAL_ROW, OTHER_UNIT_ROW])
    assert report_view(report, OFFICIAL_READER, SCHEME).withheld is True
    assert report_view(report, UNIT_2_READER, SCHEME).withheld is False


def test_a_report_that_names_no_marking_is_shown_as_before() -> None:
    assert report_view(_report([]), OFFICIAL_READER, SCHEME).withheld is False


def test_the_run_routes_answer_for_a_pipeline_withholds_on_the_union_of_its_branches() -> None:
    """One branch wrote only OFFICIAL rows; the other wrote a SECRET one. The run's counts include
    both, so the pipeline's answer, and the OFFICIAL branch's own numbers within it, are withheld."""
    pipeline = _pipeline([[OFFICIAL_ROW], [OFFICIAL_ROW, SECRET_ROW]])
    view = report_view(pipeline, OFFICIAL_READER, SCHEME)
    assert view.withheld is True and (view.rows_read, view.edges_created) == (0, 0)
    assert view.branches == [] and view.extracts == [] and view.enriches == []
    assert report_view(pipeline, SECRET_READER, SCHEME).withheld is False
    assert len(report_view(pipeline, SECRET_READER, SCHEME).branches) == 2


def test_a_withheld_answer_carries_no_count_word_or_branch() -> None:
    text = report_view(_report([SECRET_ROW]), OFFICIAL_READER, SCHEME).model_dump_json()
    assert "1200" not in text and "311" not in text and "no date" not in text and "a note" not in text
    pipeline = report_view(_pipeline([[SECRET_ROW]]), OFFICIAL_READER, SCHEME).model_dump_json()
    assert "Source 0" not in pipeline and "s0" not in pipeline


# --- the routes hand the reader to the view ----------------------------------------------------------


def test_the_run_route_and_the_release_route_hand_the_reader_to_the_view() -> None:
    """Rule 12: the sentence is about the routes, so the test reads them. Every call of
    `report_view` in the application names the reader and the handling scheme; a call with one
    argument is a route that shows counts to whoever asked."""
    tree = ast.parse((CORE / "services/api/app.py").read_text())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "report_view"
    ]
    assert len(calls) == 2, "the run route and the release route"
    for call in calls:
        assert len(call.args) + len(call.keywords) == 3, ast.dump(call)


# --- the ledger store keeps and reads the markings (pure: the pool is a stand-in) ---------------------


class _Conn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    async def execute(self, sql: str, *args: Any) -> None:
        self.executed.append((sql, args))


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    def acquire(self) -> Any:
        conn = self.conn

        class _Acquired:
            async def __aenter__(self) -> _Conn:
                return conn

            async def __aexit__(self, *exc: Any) -> None:
                return None

        return _Acquired()


async def test_finish_hands_the_reports_markings_to_the_ledger() -> None:
    conn = _Conn()
    store = RecipeRunStore(_Pool(conn), "postgres://nowhere")  # type: ignore[arg-type]
    await store.finish("run-1", report=_report([OFFICIAL_ROW, SECRET_ROW]), now=NOW)
    ((sql, args),) = conn.executed
    assert "row_markings" in sql
    kept = json.loads(args[-1])
    assert [Handling.model_validate(m) for m in kept] == [OFFICIAL_ROW, SECRET_ROW]
    pipeline = _pipeline([[OFFICIAL_ROW], [SECRET_ROW]])
    await store.finish("run-2", report=pipeline, now=NOW)
    assert [Handling.model_validate(m) for m in json.loads(conn.executed[-1][1][-1])] == [
        OFFICIAL_ROW,
        SECRET_ROW,
    ]


def _record(markings: Any) -> dict[str, Any]:
    """A `recipe_runs` row as asyncpg hands it back (JSONB as text), with the column under test."""
    return {
        "run_id": "run-1", "recipe_id": "recipe-1", "recipe_version": 1,
        "investigation_id": "inv-1", "trigger": "manual", "slot": None, "run_as": "loader-1",
        "source_handling": SOURCE.model_dump_json(), "started_at": NOW, "finished_at": NOW,
        "outcome": "succeeded", "rows_read": 5, "nodes_created": 0, "nodes_referenced": 0,
        "edges_created": 5, "rows_rejected": 0, "rows_held": 0, "load_id": "load-1",
        "failure": None, "source_file": None, "row_markings": markings,
    }  # fmt: skip


def test_a_ledger_row_reads_its_markings_and_a_null_reads_as_the_source() -> None:
    kept = json.dumps([OFFICIAL_ROW.model_dump(mode="json"), SECRET_ROW.model_dump(mode="json")])
    assert _row(_record(kept)).markings == [OFFICIAL_ROW, SECRET_ROW]  # type: ignore[arg-type]
    assert _row(_record(None)).markings == [SOURCE]  # type: ignore[arg-type]
    assert _row(_record("[]")).markings == []  # type: ignore[arg-type]
    assert "row_markings" in recipe_runs_module._COLUMNS


# --- Amendment 26: a rejected row's content, an unreadable marking, an unfinished run ------------------


def _rejecting(markings: list[Handling | None]) -> LoadReport:
    return LoadReport(
        load_id="load-1", recipe_id="recipe-1", recipe_version=1, rows_read=3,
        rejections=[
            RejectionRecord(row_index=i, reason="no date", sample=f"{{'secret': 'row-{i}'}}", marking=m)
            for i, m in enumerate(markings)
        ],
        markings=[OFFICIAL_ROW],
    )  # fmt: skip


def test_a_rejected_secret_rows_sample_is_withheld_from_an_official_loader() -> None:
    report = _rejecting([OFFICIAL_ROW, SECRET_ROW, None])
    view = report_view(report, OFFICIAL_READER, SCHEME)
    assert view.withheld is False, "the run's own markings are all open to this reader"
    by_row = {r.row_index: r for r in view.rejections}
    assert by_row[0].sample == "{'secret': 'row-0'}" and by_row[2].sample == "{'secret': 'row-2'}"
    assert by_row[1].sample != "{'secret': 'row-1'}" and "withheld" in by_row[1].sample
    assert by_row[1].reason == "no date" and by_row[1].row_index == 1, "the cause and number stay"
    assert "row-1" not in view.model_dump_json()
    assert all(r.marking is None for r in view.rejections), "a marking is not the reader's to see"
    shown = report_view(report, SECRET_READER, SCHEME)
    assert {r.row_index: r.sample for r in shown.rejections}[1] == "{'secret': 'row-1'}"


def test_a_reader_of_another_unit_has_a_restricted_rows_sample_withheld() -> None:
    view = report_view(_rejecting([OTHER_UNIT_ROW]), OFFICIAL_READER, SCHEME)
    assert "withheld" in view.rejections[0].sample and "row-0" not in view.model_dump_json()
    assert report_view(_rejecting([OTHER_UNIT_ROW]), UNIT_2_READER, SCHEME).rejections[0].sample


def test_a_pipelines_branch_rejections_are_masked_too() -> None:
    branch = BranchRunReport(source_id="s", source_label="One", report=_rejecting([SECRET_ROW]))
    pipeline = PipelineRunReport(
        load_id="run", recipe_id="recipe-1", recipe_version=1, branches=[branch],
        rejections=list(branch.report.rejections), markings=[OFFICIAL_ROW],
    )  # fmt: skip
    text = report_view(pipeline, OFFICIAL_READER, SCHEME).model_dump_json()
    assert "row-0" not in text and "withheld" in text


def test_an_unknown_stored_marking_withholds_that_run_and_lists_the_rest() -> None:
    unknown = Handling(
        classification="OFFICIAL", handling_code="Z", owning_unit="unit-1", originator="unit-1"
    )
    unknown_class = Handling(
        classification="TOP-DRAWER", handling_code="P", owning_unit="unit-1", originator="unit-1"
    )
    for bad in (unknown, unknown_class):
        views = [
            _schedule_run_view(run, OFFICIAL_READER, SCHEME)
            for run in (_run([OFFICIAL_ROW, bad]), _run([OFFICIAL_ROW]))
        ]
        assert _counts_withheld(views[0]) and _counts_shown(views[1]), bad
    assert report_view(_report([unknown]), OFFICIAL_READER, SCHEME).withheld is True


def test_extract_stage_counts_are_withheld_on_the_same_rule() -> None:
    from schemas.ingest import ExtractStageReport

    stage = ExtractStageReport(node_id="x", library="stanza", output="review_queue",
                               documents_read=4, markings=[SECRET_ROW])  # fmt: skip
    branch = BranchRunReport(source_id="s", source_label="One", report=_report([OFFICIAL_ROW]))
    pipeline = PipelineRunReport(
        load_id="run", recipe_id="recipe-1", recipe_version=1, branches=[branch], extracts=[stage],
        markings=[OFFICIAL_ROW, SECRET_ROW],
    )  # fmt: skip
    view = report_view(pipeline, OFFICIAL_READER, SCHEME)
    assert view.withheld is True and view.extracts == []
    assert len(report_view(pipeline, SECRET_READER, SCHEME).extracts) == 1


async def test_a_failure_stores_the_markings_the_run_had_reached() -> None:
    conn = _Conn()
    store = RecipeRunStore(_Pool(conn), "postgres://nowhere")  # type: ignore[arg-type]
    await store.fail("run-1", failure="boom", now=NOW, markings=[OFFICIAL_ROW, SECRET_ROW])
    ((sql, args),) = conn.executed
    assert "row_markings" in sql
    assert [Handling.model_validate(m) for m in json.loads(args[-1])] == [OFFICIAL_ROW, SECRET_ROW]
    await store.fail("run-2", failure="boom", now=NOW)
    assert conn.executed[-1][1][-1] is None, "nothing committed: the source's alone, as a running run"


def test_a_failed_run_that_committed_a_secret_branch_withholds() -> None:
    failed = _run([OFFICIAL_ROW, SECRET_ROW]).model_copy(
        update={"outcome": "failed", "failure": "the stage failed"}
    )
    view = _schedule_run_view(failed, OFFICIAL_READER, SCHEME)
    assert view.withheld is True and view.failure is None


def test_an_unresolvable_rows_sample_is_withheld_from_every_reader_whatever_their_unit() -> None:
    """The unit a stand-in marking would name can be created by an administrator, so a mask judged
    by unit alone fails: this reader has the top clearance, every code, and is in that very unit."""
    from services.ingest.engine import UNRESOLVED_UNIT

    rejection = RejectionRecord(
        row_index=0, reason="no date", sample="{'secret': 'row-0'}", sample_unreadable=True,
        marking=SECRET_ROW.model_copy(
            update={"handling_code": "R", "owning_unit": UNRESOLVED_UNIT, "originator": UNRESOLVED_UNIT}
        ),
    )  # fmt: skip
    insider = reader("SECRET", unit=UNRESOLVED_UNIT, codes=("P", "C", "R"))
    report = LoadReport(
        load_id="l", recipe_id="r", recipe_version=1, rejections=[rejection], markings=[OFFICIAL_ROW]
    )
    view = report_view(report, insider, SCHEME)
    assert "withheld" in view.rejections[0].sample and "row-0" not in view.model_dump_json()
    assert view.rejections[0].row_index == 0 and view.rejections[0].reason == "no date"


async def test_the_engine_flags_an_unresolvable_rows_rejection_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.ingest import engine
    from services.ingest.engine import RowRejected

    from tests.ingest.pid_golden_support import SCHEME as PID_SCHEME
    from tests.ingest.pid_golden_support import recipe_for, rows_of

    def unresolvable(*args: Any, **kwargs: Any) -> Any:
        raise RowRejected("units conflict")

    monkeypatch.setattr(engine, "row_marking", unresolvable)
    recipe = recipe_for("pid_conflicts.csv")
    broken = {**rows_of("pid_conflicts.csv")[0], "nomis_id_a": ""}
    done = engine.resolve_rows_keyed(recipe, [broken], load_id="l", source="s", scheme=PID_SCHEME)
    assert [r.sample_unreadable for r in done.rejections] == [True]
