"""ADR-127 decision 6 and Amendment 5: what a run keeps in the run ledger beside it, and when.

- **At the graph's commit.** A load's record is written to the ledger when its graph transaction
  commits, before the events, the geometry points, the post-commit rules, the resolution jobs and
  the change stream, so a failure in any of those still leaves the record a revert needs
  (`test_a_failure_after_the_commit_leaves_the_record`, one case per stage and per route).
- **Per load.** A pipeline run's branches are each a load of their own, each with its own source;
  a release of held rows is a load of its own with `released_from`, the load that held the rows.
- **The geometry points a load inserted** are recorded, only the ones not already present, and
  before they are inserted, so a failure between the two leaves a ref that is absent (a revert
  removes nothing for it) and never a point nothing records.
- **Held rows carry their `load_id`**, so the revert can discard the ones still pending.
- **No route returns the ids.** The run and release routes answer a view without the id lists
  (rules 3 and 7): `merged_edge_ids` would tell the loader that a link pre-existed whether or not
  they may read it.

Pure: the ledger is a recording fake holding to `RecipeRunStore`'s interface (the store is proved
live in `test_recipe_runs.py`), the graph is the shared stand-in made to merge as the real one does
(`tests/ingest/test_load_record_created_and_merged.py`), and the routes are called as functions with
their collaborators replaced, as `test_recipe_run_path.py` does."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import services.api.app as app_module
import services.api.recipe_run as run_module
from services.api.load_records import LedgerSink, released_from_of, report_view
from services.api.pipeline_run import run_published_pipeline
from services.api.rule_evaluation import PreCommitVerdict, held_rows_for
from services.api.studio_publish import load_with_rules, run_published_recipe

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.analytics import GeometryRecord
from schemas.domain import Handling, HeldRow, Principal, TypologyRule
from schemas.ingest import (
    BranchRunReport,
    LoadRecord,
    LoadReport,
    PipelineGraph,
    PipelineRunReport,
    Recipe,
    StudioRecipeDraft,
    StudioRecipeStatus,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    ValidatingGraph,
    local_staging,
)
from tests.ingest.test_load_record_created_and_merged import (
    LOADER,
    MergingGraph,
    _recipe,
    _row,
)
from tests.ingest.test_studio_run_geometries import (
    MASTS,
    RecordingAnalytics,
    TransactionalGraph,
)
from tests.ingest.test_studio_run_geometries import _draft as _mast_draft
from tests.ingest.test_studio_run_geometries import _recipe as _mast_recipe
from tests.ingest.test_studio_run_geometries import _rows as _mast_rows

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
NOW = datetime(2026, 10, 25, 9, tzinfo=UTC)
SOURCE = Handling(
    classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
)
#: Ids a reader may not be entitled to see. None may appear in a route's response.
SECRET_IDS = ["node-secret-1", "node-secret-2", "edge-secret-1", "edge-secret-2", "edge-secret-3"]


class Ledger:
    """What the run ledger is asked, in order, with its records kept as the store keeps them."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.started: list[dict[str, Any]] = []
        self.records: list[LoadRecord] = []
        self.geometries: dict[str, list[str]] = {}
        self.row_keys: dict[str, list[str]] = {}
        self.rule_writes: list[tuple[str, dict[str, Any]]] = []
        self.uncovered: list[str] = []
        self.failed: list[str] = []
        self.failed_markings: list[Any] = []
        self.finished = 0

    async def start(self, **kwargs: Any) -> str:
        self.calls.append("start")
        self.started.append(kwargs)
        return "run-1"

    async def add_record(
        self,
        run_id: str,
        record: LoadRecord,
        *,
        row_keys: Sequence[str] = (),
        row_key_fingerprint: str = "",
    ) -> None:
        """As `RecipeRunStore.add_record` (decision 5): the keys of the rows the load wrote come
        with the record, which is how the real store keeps them in one transaction."""
        assert run_id == "run-1"
        self.calls.append(f"record:{record.load_id}")
        self.records.append(record)
        self.row_keys[record.load_id] = list(row_keys)

    async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]:
        """As `RecipeRunStore.fingerprints`: no keys kept for the (recipe, case), so none to
        refuse over. A read, not one of the writes `calls` orders."""
        return {}

    async def add_geometries(self, run_id: str, load_id: str, refs: list[str]) -> None:
        self.calls.append(f"geometries:{load_id}")
        self.geometries[load_id] = list(refs)

    async def add_rule_writes(self, run_id: str, load_id: str, **kwargs: Any) -> None:
        self.calls.append(f"rule_writes:{load_id}")
        self.rule_writes.append((load_id, kwargs))

    async def mark_uncovered(self, run_id: str, load_id: str) -> None:
        self.calls.append(f"uncovered:{load_id}")
        self.uncovered.append(load_id)

    async def finish(self, run_id: str, *, report: Any, now: datetime) -> None:
        self.calls.append("finish")
        self.finished += 1

    async def fail(
        self, run_id: str, *, failure: str, now: datetime, markings: Sequence[Any] = ()
    ) -> None:
        self.calls.append("fail")
        self.failed.append(failure)
        self.failed_markings = list(markings)


def _sink(ledger: Ledger, **kwargs: Any) -> LedgerSink:
    return LedgerSink(
        ledger,  # type: ignore[arg-type]
        "run-1",
        created_by="loader-1",
        investigation_id="case-1",
        started_at=NOW,
        **kwargs,
    )


def _report(load_id: str, *, created: str = "e-new", merged: str | None = "e-old") -> LoadReport:
    return LoadReport(
        load_id=load_id,
        recipe_id="r",
        recipe_version=2,
        rows_read=3,
        nodes_created=1,
        edges_created=1,
        created_node_ids=[f"n-{load_id}"],
        merged_node_ids=["doc-shared"],
        created_edge_ids=[created],
        merged_edge_ids=[merged] if merged else [],
        touched_edge_ids=[created, *([merged] if merged else [])],
    )


# --- the sink ----------------------------------------------------------------------------------


async def test_a_commit_writes_the_loads_record_with_its_own_source() -> None:
    ledger = Ledger()
    sink = _sink(ledger)
    await sink.committed(_report("load-1"), source="one.csv")
    await sink.committed(_report("load-2", created="e2", merged=None), source="two.csv")
    first, second = ledger.records
    assert (first.load_id, first.source, first.investigation_id) == ("load-1", "one.csv", "case-1")
    assert (second.load_id, second.source) == ("load-2", "two.csv"), "each branch has its own"
    assert first.created_node_ids == ["n-load-1"] and first.merged_node_ids == ["doc-shared"]
    assert first.created_edge_ids == ["e-new"] and first.merged_edge_ids == ["e-old"]
    assert first.events_stamped is True and first.released_from is None
    assert first.created_by == "loader-1" and first.started_at == NOW


async def test_a_release_sinks_records_that_name_where_they_came_from() -> None:
    ledger = Ledger()
    await _sink(ledger, released_from="load-0").committed(_report("load-1"), source="one.csv")
    assert [(r.load_id, r.released_from) for r in ledger.records] == [("load-1", "load-0")]


async def test_the_geometry_refs_a_load_inserted_are_recorded_against_it() -> None:
    ledger = Ledger()
    await _sink(ledger).geometries("load-1", ["g1", "g2"])
    assert ledger.geometries == {"load-1": ["g1", "g2"]}


def _held(load_id: str) -> HeldRow:
    return HeldRow(
        id="h", investigation_id="case-1", recipe_id="r", recipe_version=2, load_id=load_id,
        source="private_cash.csv", row_index=4, row={"a": "b"}, rule_id="rule", reason="x",
        handling=SOURCE, held_at=NOW,
    )  # fmt: skip


def test_held_rows_of_one_load_name_it_and_of_two_loads_are_refused() -> None:
    assert released_from_of([_held("load-1"), _held("load-1")]) == "load-1"
    with pytest.raises(ValueError, match="one load"):
        released_from_of([_held("load-1"), _held("load-0")])


def test_held_rows_carry_the_load_id_of_the_load_that_held_them() -> None:
    rule = TypologyRule.model_construct(id="rule-1")
    verdict = PreCommitVerdict(hold={1: (rule, "no verdict"), 3: (rule, "no verdict")})
    held = held_rows_for(
        verdict,
        [{"a": str(i)} for i in range(5)],
        row_numbers=None,
        investigation_id="case-1",
        recipe_id="r",
        recipe_version=2,
        load_id="load-9",
        source="private_cash.csv",
        handling=SOURCE,
        dataset_id=None,
    )
    assert [h.row_index for h in held] == [1, 3]
    assert {h.load_id for h in held} == {"load-9"}


# --- when the record is written ----------------------------------------------------------------


async def test_the_record_is_written_at_the_graph_commit_and_before_anything_after_it() -> None:
    graph = MergingGraph(ONTOLOGY)
    seen: list[tuple[int, str]] = []

    class Sink:
        async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]:
            return {}

        async def committed(self, report: LoadReport, *, source: str) -> None:
            seen.append((graph.commits, report.load_id))

        async def geometries(self, load_id: str, refs: Any) -> None:
            raise AssertionError("no points here")

    await load_with_rules(
        _recipe(),
        [_row("SYN-1", "SYN-2", 1)],
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id="load-1",
        investigation_scope="case-1",
        source="private_cash.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
        sink=Sink(),
    )
    assert seen == [(1, "load-1")], "called once, after the commit"


def _write_published(tmp_path: Path, recipe: Recipe, rows: list[dict[str, str]]) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "recipes").mkdir(parents=True, exist_ok=True)
    (repo / "recipes" / f"{recipe.id}.yaml").write_text(
        recipe.model_dump_json(by_alias=True), encoding="utf-8"
    )
    source = tmp_path / f"{recipe.id}.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return repo, source


def _draft(recipe: Recipe, source: Path, **extra: Any) -> StudioRecipeDraft:
    return StudioRecipeDraft(
        recipe_id=recipe.id, version=1, status=StudioRecipeStatus.PUBLISHED, label=recipe.label,
        connector_profile="generic-csv", source_location=str(source), owning_unit="unit-1",
        created_by="analyst-1", created_at=NOW, git_path=f"recipes/{recipe.id}.yaml", **extra,
    )  # fmt: skip


class FailingAnalytics:
    """The analytics store failing at one named stage, after the graph has committed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage

    async def load_events(self, records: Any) -> None:
        if self.stage == "events":
            raise RuntimeError("the analytics store is down")

    async def get_geometries(self, *args: Any, **kwargs: Any) -> list[GeometryRecord]:
        return []

    async def load_geometries(self, records: Any) -> None:
        if self.stage == "geometries":
            raise RuntimeError("the analytics store is down")


@pytest.mark.parametrize("stage", ["events"])
async def test_a_failure_after_the_commit_leaves_the_record(tmp_path: Path, stage: str) -> None:
    """The events are the first thing a run does after its graph commit; the record must already
    be in the ledger when they fail."""
    recipe = _recipe()
    repo, source = _write_published(
        tmp_path, recipe, [_row("SYN-1", "SYN-2", 1), _row("SYN-3", "SYN-4", 2)]
    )
    ledger = Ledger()
    with pytest.raises(RuntimeError, match="analytics store is down"):
        await run_published_recipe(
            _draft(recipe, source),
            LOADER,
            graph=MergingGraph(ONTOLOGY),  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            load_id="load-1",
            investigation_scope="case-1",
            repo_root=repo,
            analytics=FailingAnalytics(stage),  # type: ignore[arg-type]
            media=InMemoryMediaStore(),
            scheme=SCHEME,
            sink=_sink(ledger),
        )
    (record,) = ledger.records
    assert record.load_id == "load-1" and len(record.created_edge_ids) == 2
    assert record.source == str(source)


async def test_the_geometry_points_a_load_inserted_are_recorded_before_they_are_inserted(
    tmp_path: Path,
) -> None:
    """Only the points not already present are the load's: a ref another load put there is not
    this load's to remove. They are recorded first, so a failure inserting them leaves refs that
    are absent (a revert removes nothing for them), never points that nothing records."""
    recipe = _mast_recipe()
    repo, source = _write_published(tmp_path, recipe, _mast_rows())
    first_point = __import__("services.ingest.geometries", fromlist=["point_geometries"]).point_geometries(
        recipe, _mast_rows()
    )[0]
    already = RecordingAnalytics(already=[first_point])
    ledger = Ledger()
    await run_published_recipe(
        _mast_draft(source),
        LOADER,
        graph=TransactionalGraph(),  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id="load-1",
        investigation_scope="case-1",
        repo_root=repo,
        analytics=already,  # type: ignore[arg-type]
        sink=_sink(ledger),
    )
    assert len(already.geometries) == len(MASTS)
    assert ledger.geometries["load-1"] == [
        g.geometry_ref for g in already.geometries if g.geometry_ref != first_point.geometry_ref
    ]
    assert ledger.calls.index("geometries:load-1") > ledger.calls.index("record:load-1")

    failing = Ledger()
    with pytest.raises(RuntimeError):
        await run_published_recipe(
            _mast_draft(source),
            LOADER,
            graph=TransactionalGraph(),  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            load_id="load-2",
            investigation_scope="case-1",
            repo_root=repo,
            analytics=FailingAnalytics("geometries"),  # type: ignore[arg-type]
            sink=_sink(failing),
        )
    assert len(failing.geometries["load-2"]) == len(MASTS), "recorded before the insert failed"


async def test_a_pipeline_whose_second_branch_raises_keeps_the_first_branchs_record(
    tmp_path: Path,
) -> None:
    graph_nodes = [
        {"id": "domain", "kind": "domain_model", "label": "Domain", "config": {"pack": "pole"}},
        {"id": "source", "kind": "source", "label": "One", "config": {}},
        {"id": "profile", "kind": "profile", "label": "Profile", "config": {}},
        {"id": "map", "kind": "map", "label": "Map", "config": {}},
        {"id": "load", "kind": "load", "label": "Load", "config": {}},
        {"id": "source-b", "kind": "source", "label": "Two",
         "config": {"source_location": str(tmp_path / "missing.csv")}},
        {"id": "source-b-load", "kind": "load", "label": "Load", "config": {}},
    ]  # fmt: skip
    edges = [
        {"source": "domain", "target": "source"}, {"source": "source", "target": "profile"},
        {"source": "profile", "target": "map"}, {"source": "map", "target": "load"},
        {"source": "domain", "target": "source-b"}, {"source": "source-b", "target": "source-b-load"},
    ]  # fmt: skip
    recipe = _recipe().model_copy(
        update={"pipeline": PipelineGraph.model_validate({"nodes": graph_nodes, "edges": edges})}
    )
    repo, source = _write_published(tmp_path, recipe, [_row("SYN-1", "SYN-2", 1)])
    ledger = Ledger()
    with pytest.raises(Exception):  # noqa: B017, PT011 - the missing file's own error
        await run_published_pipeline(
            _draft(recipe, source),
            LOADER,
            graph=MergingGraph(ONTOLOGY),  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            scheme=SCHEME,
            load_id="run",
            investigation_scope="case-1",
            repo_root=repo,
            recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
            media=InMemoryMediaStore(),
            sink=_sink(ledger),
        )
    assert [r.load_id for r in ledger.records] == ["run:source"]
    assert ledger.records[0].source == str(source)


# --- the routes --------------------------------------------------------------------------------


def _deps_namespace() -> Any:
    return SimpleNamespace(recipe_runs=Ledger())


async def test_a_run_that_fails_after_the_commit_keeps_its_record_and_is_marked_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = Ledger()
    deps = SimpleNamespace(recipe_runs=ledger)

    async def execute(deps: Any, *, sink: Any, **kwargs: Any) -> Any:
        await sink.committed(_report("load-1"), source="one.csv")
        raise RuntimeError("a post-commit stage failed")

    monkeypatch.setattr(run_module, "_execute_recipe_run", execute)
    recipe = _draft(_recipe(), Path("one.csv"), handling=SOURCE.model_dump())
    with pytest.raises(RuntimeError, match="post-commit"):
        await run_module.run_recipe_as(
            deps,  # type: ignore[arg-type]
            principal=LOADER,
            recipe=recipe,
            investigation_id="case-1",
            source_location=None,
            trigger="manual",
        )
    assert ledger.calls == ["start", "record:load-1", "fail"]
    assert ledger.records[0].investigation_id == "case-1"


def _published_recipe() -> StudioRecipeDraft:
    return _draft(_recipe(), Path("one.csv"), handling=SOURCE.model_dump())


async def test_the_run_route_answers_a_view_with_no_id_from_the_loads_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    single = _report("load-1").model_copy(
        update={"created_node_ids": SECRET_IDS[:2], "touched_edge_ids": SECRET_IDS[2:],
                "created_edge_ids": SECRET_IDS[2:3], "merged_edge_ids": SECRET_IDS[3:]}
    )  # fmt: skip
    pipeline = PipelineRunReport(
        load_id="run", recipe_id="r", recipe_version=2, nodes_created=1, created_node_ids=SECRET_IDS[:2],
        touched_edge_ids=SECRET_IDS[2:],
        branches=[BranchRunReport(source_id="s", source_label="One", report=single)],
    )  # fmt: skip
    for report in (single, pipeline):

        async def fake_run(deps: Any, **kwargs: Any) -> Any:
            return report

        monkeypatch.setattr(app_module, "run_recipe_as", fake_run)
        names = [f.name for f in __import__("dataclasses").fields(app_module.RecipeRunDeps)]
        route_args = {
            "graph": 1, "ontology": 1, "analytics": 1, "media": 1, "repo_root": 1, "audit": 1,
            "jobs": 1, "valkey": 1, "handling_scheme": 1, "config": 1, "hotlists_store": 1,
            "monitors_store": 1, "patterns_store": 1, "alerts_store": 1, "principal_resolver": 1,
            "extraction_candidates": 1, "recogniser_for": 1, "online_geocode": 1,
            "typology_rules": 1, "held_rows": 1, "screening_lists": 1, "compute": 1,
            "kyc_expiries": 1, "recipe_runs": 1,
        }  # fmt: skip
        assert names  # the dependency list is what `RecipeRunDeps` declares
        result = await app_module.run_studio_recipe(
            investigation=SimpleNamespace(id="case-1"),  # type: ignore[arg-type]
            recipe=object(),  # type: ignore[arg-type]
            principal=LOADER,
            body=SimpleNamespace(source_location=None),  # type: ignore[arg-type]
            **route_args,  # type: ignore[arg-type]
        )
        text = result.model_dump_json()
        for secret in SECRET_IDS:
            assert secret not in text
        for word in ("created_node_ids", "touched_edge_ids", "created_edge_ids", "merged_edge_ids",
                     "merged_node_ids"):  # fmt: skip
            assert word not in text
        assert result.load_id == report.load_id and result.nodes_created == report.nodes_created


def test_the_view_keeps_every_count_and_each_branchs_own_numbers() -> None:
    view = report_view(_report("load-1"), LOADER, SCHEME)
    assert (view.rows_read, view.nodes_created, view.edges_created) == (3, 1, 1)
    pipeline = report_view(
        PipelineRunReport(
            load_id="run", recipe_id="r", recipe_version=2, rows_read=7,
            branches=[BranchRunReport(source_id="s", source_label="One", report=_report("run:s"))],
        ),
        LOADER, SCHEME,
    )  # fmt: skip
    assert pipeline.rows_read == 7 and pipeline.branches[0].report.load_id == "run:s"
    assert pipeline.branches[0].report.nodes_created == 1


class _Held:
    def __init__(self, held: list[HeldRow]) -> None:
        self.held = held
        self.decided: list[str] = []

    async def get_authorized(self, held_id: str, investigation_id: str, principal: Any) -> HeldRow:
        return self.held[0]

    async def decide_for_reader(self, ids: Any, case: str, principal: Any, **kwargs: Any) -> list[HeldRow]:
        self.decided.extend(ids)
        return self.held


class _Audit:
    async def record(self, **kwargs: Any) -> None:
        return None


async def _release(
    monkeypatch: pytest.MonkeyPatch, ledger: Ledger, release: Any
) -> Any:
    async def rule_gate(*args: Any, **kwargs: Any) -> Any:
        return object()

    monkeypatch.setattr(app_module, "release_held_rows", release)
    monkeypatch.setattr(app_module, "_rule_gate", rule_gate)
    monkeypatch.setattr(app_module, "load_published_recipe", lambda *a, **k: object())
    held = _Held([_held("load-0")])
    return await app_module.release_held_rows_route(
        investigation=SimpleNamespace(id="case-1"),  # type: ignore[arg-type]
        recipe=_published_recipe().model_copy(update={"git_path": "recipes/x.yaml"}),
        principal=LOADER,
        body=SimpleNamespace(ids=["h"], reason=None),  # type: ignore[arg-type]
        graph=1, ontology=1, analytics=1, media=1, repo_root=1,  # type: ignore[arg-type]
        audit=_Audit(),  # type: ignore[arg-type]
        valkey=1, handling_scheme=SCHEME, alerts_store=1, principal_resolver=1,  # type: ignore[arg-type]
        typology_rules=1, held_rows=held, screening_lists=1, compute=1,  # type: ignore[arg-type]
        kyc_expiries=1, patterns_store=1, recipe_runs=ledger,  # type: ignore[arg-type]
    )  # fmt: skip


async def test_a_release_starts_its_ledger_run_first_and_its_response_holds_no_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = Ledger()
    report = _report("load-1").model_copy(
        update={"created_node_ids": SECRET_IDS[:2], "merged_edge_ids": SECRET_IDS[3:]}
    )

    async def release(held: Any, recipe: Any, reviewer: Any, *, sink: Any, **kwargs: Any) -> Any:
        ledger.calls.append("release")
        await sink.committed(report, source="private_cash.csv")
        return report

    result = await _release(monkeypatch, ledger, release)
    assert ledger.calls == ["start", "release", "record:load-1", "finish"]
    assert ledger.started[0]["trigger"] == "release" and ledger.started[0]["run_as"] == "loader-1"
    assert [(r.load_id, r.released_from) for r in ledger.records] == [("load-1", "load-0")]
    text = result.model_dump_json()
    assert not [secret for secret in SECRET_IDS if secret in text]
    assert "merged_edge_ids" not in text


async def test_a_release_that_fails_after_its_commit_leaves_the_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = Ledger()

    async def release(held: Any, recipe: Any, reviewer: Any, *, sink: Any, **kwargs: Any) -> Any:
        await sink.committed(_report("load-1"), source="private_cash.csv")
        raise RuntimeError("a post-commit stage failed")

    with pytest.raises(RuntimeError, match="post-commit"):
        await _release(monkeypatch, ledger, release)
    assert ledger.calls == ["start", "record:load-1", "fail"]
    assert ledger.records[0].released_from == "load-0"


async def test_a_release_gives_the_load_its_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    """`release_held_rows` is what loads the held rows; the sink must reach the load it makes, or
    the release's record would wait for the route to finish (and be lost with a failure)."""
    import services.api.rule_holds as rule_holds

    seen: dict[str, Any] = {}

    async def fake_load(*args: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return _report("load-1"), [], frozenset()

    async def post_commit(events: Any, **kwargs: Any) -> list[str]:
        return []

    monkeypatch.setattr(rule_holds, "load_with_rules", fake_load)
    rules = SimpleNamespace(investigation_id="case-1", scheme=SCHEME, post_commit=post_commit,
                            last_written=())  # fmt: skip
    sink = object()
    await rule_holds.release_held_rows(
        [_held("load-0").model_copy(update={"recipe_id": "private-cash", "recipe_version": 1})],
        _recipe(),
        LOADER,
        graph=1,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        analytics=None,
        media=None,
        rules=rules,  # type: ignore[arg-type]
        load_id="load-1",
        sink=sink,  # type: ignore[arg-type]
    )
    assert seen["sink"] is sink


async def test_the_sink_tells_the_ledger_what_rules_wrote_and_what_no_record_covers() -> None:
    ledger = Ledger()
    sink = _sink(ledger)
    await sink.rule_writes("load-1", node_ids=["alert"], created_edge_ids=["l1"], merged_edge_ids=[])
    await sink.uncovered("load-1")
    assert ledger.rule_writes == [
        ("load-1", {"node_ids": ["alert"], "created_edge_ids": ["l1"], "merged_edge_ids": []})
    ]
    assert ledger.uncovered == ["load-1"]


# --- writes no record covers: a pipeline's extract and enrich stages -----------------------------


def _staged_pipeline(tmp_path: Path) -> tuple[Recipe, Path, Path]:
    nodes = [
        {"id": "domain", "kind": "domain_model", "label": "Domain", "config": {"pack": "pole"}},
        {"id": "source", "kind": "source", "label": "One", "config": {}},
        {"id": "profile", "kind": "profile", "label": "Profile", "config": {}},
        {"id": "map", "kind": "map", "label": "Map", "config": {}},
        {"id": "load", "kind": "load", "label": "Load", "config": {}},
        {"id": "extract", "kind": "extract", "label": "Extract", "config": {}},
        {"id": "extract-load", "kind": "load", "label": "Load", "config": {}},
        {"id": "enrich", "kind": "enrich", "label": "Enrich", "config": {}},
        {"id": "enrich-load", "kind": "load", "label": "Load", "config": {}},
        {"id": "source-b", "kind": "source", "label": "Two", "config": {}},
        {"id": "source-b-load", "kind": "load", "label": "Load", "config": {}},
    ]  # fmt: skip
    edges = [
        {"source": "domain", "target": "source"}, {"source": "source", "target": "profile"},
        {"source": "profile", "target": "map"}, {"source": "map", "target": "load"},
        {"source": "map", "target": "extract"}, {"source": "extract", "target": "extract-load"},
        {"source": "map", "target": "enrich"}, {"source": "enrich", "target": "enrich-load"},
        {"source": "domain", "target": "source-b"}, {"source": "source-b", "target": "source-b-load"},
    ]  # fmt: skip
    second = tmp_path / "two.csv"
    nodes[-2]["config"] = {"source_location": str(second)}
    recipe = _recipe().model_copy(
        update={"pipeline": PipelineGraph.model_validate({"nodes": nodes, "edges": edges})}
    )
    repo, first = _write_published(tmp_path, recipe, [_row("SYN-1", "SYN-2", 1)])
    with second.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_row("a", "b", 1)))
        writer.writeheader()
        writer.writerow(_row("SYN-5", "SYN-6", 2))
    return recipe, repo, first


async def _run_staged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, extract: list[str], edges: list[str], online: int
) -> Ledger:
    import services.api.pipeline_run as pipeline_run
    from schemas.ingest import EnrichStageReport, ExtractStageReport

    async def extract_stage(node: Any, **kwargs: Any) -> Any:
        return ExtractStageReport(node_id=node.id, library="stanza", output="inferred_graph"), extract

    async def enrich_stage(node: Any, **kwargs: Any) -> Any:
        return EnrichStageReport(node_id=node.id, geocoder="local_gazetteer", matched_online=online), edges

    monkeypatch.setattr(pipeline_run, "_run_extract_stage", extract_stage)
    monkeypatch.setattr(pipeline_run, "_run_enrich_stage", enrich_stage)
    recipe, repo, first = _staged_pipeline(tmp_path)
    ledger = Ledger()
    await run_published_pipeline(
        _draft(recipe, first),
        LOADER,
        graph=MergingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        scheme=SCHEME,
        load_id="run",
        investigation_scope="case-1",
        repo_root=repo,
        recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
        media=InMemoryMediaStore(),
        sink=_sink(ledger),
    )
    assert [r.load_id for r in ledger.records] == ["run:source", "run:source-b"]
    return ledger


async def test_an_extract_stage_that_wrote_nodes_marks_only_the_branch_that_fed_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = await _run_staged(tmp_path, monkeypatch, extract=["inferred-node"], edges=[], online=0)
    assert ledger.uncovered == ["run:source"], "source-b feeds neither stage"


async def test_an_enrich_stage_that_wrote_links_or_online_points_marks_its_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    links = await _run_staged(tmp_path / "a", monkeypatch, extract=[], edges=["same-as"], online=0)
    assert links.uncovered == ["run:source"]
    points = await _run_staged(tmp_path / "b", monkeypatch, extract=[], edges=[], online=2)
    assert points.uncovered == ["run:source"]


async def test_stages_that_wrote_nothing_mark_no_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = await _run_staged(tmp_path, monkeypatch, extract=[], edges=[], online=0)
    assert ledger.uncovered == []
    assert ledger.records[0].uncovered_writes is False


def test_a_record_reads_as_fully_covered_until_a_stage_says_otherwise() -> None:
    assert LoadRecord.model_validate(
        {"load_id": "l", "recipe_id": "r", "recipe_version": 1, "source": "s",
         "started_at": "2026-01-01T00:00:00Z", "created_by": "u"}
    ).uncovered_writes is False  # fmt: skip


async def test_the_change_stream_entry_does_not_carry_a_rules_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stream and the monitors it feeds were told the elements a recipe wrote. A rule's alert,
    its links and what a finding writes beside it are the load's (its record has them) but are not
    new ingest nodes: the entry is made from `created_node_ids` and `touched_edge_ids`, which the
    rules' writes do not enter."""
    published: dict[str, Any] = {}

    class Writer:
        def __init__(self, valkey: Any) -> None: ...

        async def publish(self, kind: str, **kwargs: Any) -> None:
            published.update(kwargs)

    report = _report("load-1").model_copy(
        update={
            "created_node_ids": ["n-recipe"],
            "touched_edge_ids": ["e-recipe"],
            "rule_node_ids": ["alert-node"],
            "rule_created_edge_ids": ["alert-link"],
            "rule_merged_edge_ids": ["old-link"],
        }
    )

    async def run_published(*args: Any, **kwargs: Any) -> LoadReport:
        return report

    async def nothing(*args: Any, **kwargs: Any) -> Any:
        return None

    async def rules(*args: Any, **kwargs: Any) -> Any:
        return None

    monkeypatch.setattr(run_module, "ChangeStreamWriter", Writer)
    monkeypatch.setattr(run_module, "run_published_recipe", run_published)
    monkeypatch.setattr(run_module, "_rule_gate", rules)
    monkeypatch.setattr(run_module, "_evaluate_watches_best_effort", nothing)
    monkeypatch.setattr(run_module.resolution_trigger_module, "submit_post_ingest_resolution_jobs", nothing)
    deps = SimpleNamespace(
        handling_scheme=SCHEME, valkey=object(), audit=_Audit(), graph=1, ontology=1, analytics=1,
        media=1, recipe_repo_root=1, jobs=1, config=SimpleNamespace(post_ingest_resolution=True),
        hotlists_store=1, monitors_store=1,
        patterns_store=1, alerts_store=1, principal_resolver=1, extraction_candidates=1,
        recogniser_for=1, online_geocode=1, typology_rules=1, held_rows=1, screening_lists=1,
        compute=1, kyc_expiries=1, recipe_runs=1,
    )  # fmt: skip
    await run_module._execute_recipe_run(
        deps,  # type: ignore[arg-type]
        principal=LOADER,
        recipe=_published_recipe(),
        investigation_id="case-1",
        source_location=None,
        trigger="manual",
        sink=_sink(Ledger()),
    )
    assert published["node_ids"] == ["n-recipe"]
    assert published["edge_ids"] == ["e-recipe"]


async def test_a_failed_run_stores_the_markings_of_the_loads_that_committed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Amendment 26: a run that fails after a branch committed SECRET rows has counts that include
    them; the ledger keeps the markings it reached, so the listing withholds them."""
    ledger = Ledger()
    deps = SimpleNamespace(recipe_runs=ledger)
    secret = Handling(classification="SECRET", handling_code="P", originator="u", owning_unit="u")

    async def execute(deps: Any, *, sink: Any, **kwargs: Any) -> Any:
        await sink.committed(_report("load-1").model_copy(update={"markings": [secret]}), source="a.csv")
        raise RuntimeError("a later stage failed")

    monkeypatch.setattr(run_module, "_execute_recipe_run", execute)
    recipe = _draft(_recipe(), Path("one.csv"), handling=SOURCE.model_dump())
    with pytest.raises(RuntimeError):
        await run_module.run_recipe_as(
            deps, principal=LOADER, recipe=recipe, investigation_id="case-1",  # type: ignore[arg-type]
            source_location=None, trigger="manual",
        )  # fmt: skip
    assert ledger.failed_markings == [secret]
