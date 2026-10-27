"""ADR-127 Amendment 23 (B2-10a), "The recipes", "What it refuses first": the seed's method on
`StudioRecipeStore` enters a committed recipe as published only after the checks a publish and a run
make. They are pure, so they are asserted here with a store that has no connection at all: a method
that reached the database before refusing would fail on the missing pool, never on the refusal.

What a mistake would do, and the case that catches it:

- a recipe the rules refuse entered anyway
  (`test_a_recipe_the_rules_refuse_is_refused_before_anything_is_written`);
- an element that loosens the source's marking entered anyway
  (`test_a_recipe_that_loosens_the_sources_marking_is_refused`);
- a pin that is not the ontology's, entered anyway
  (`test_a_recipe_pinned_to_another_pack_version_is_refused`,
  `test_a_recipe_with_no_pins_for_the_packs_it_writes_is_refused`);
- a pin the recipe's own types do not call for (`test_pins_that_differ_from_the_packs_it_writes_are_refused`);
- a recipe made against another ontology (`test_a_recipe_made_against_another_ontology_is_refused`);
- the committed recipes themselves failing a refusal they must pass
  (`test_every_committed_pid_recipe_but_the_reports_passes_every_refusal`)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from services.api.studio_map import HandlingLoosenedError
from services.api.studio_recipes import (
    SeededRecipeNoLegalBasis,
    SeededRecipePinsDiffer,
    StudioRecipeStore,
    check_seeded_recipe,
)
from services.ingest.engine import StaleRecipeError
from services.ingest.recipe_loader import load_recipe
from services.ingest.recipe_rules import RecipeRuleError

from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.ingest import (
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    Recipe,
)

FIXTURES = Path(__file__).resolve().parents[4] / "OspreyFlow_Core/packages/demo_fixtures"
ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
NOW = datetime(2026, 10, 26, 9, tzinfo=UTC)
#: Every committed PID recipe the seed enters; the reports recipe is entered by the fallback command.
SEEDED = sorted(
    p.name for p in FIXTURES.glob("pid_*_recipe.yaml") if p.name != "pid_intel_reports_recipe.yaml"
)


def recipe(name: str = "pid_conflicts_recipe.yaml") -> Recipe:
    return load_recipe(FIXTURES / name)


def offline_store() -> StudioRecipeStore:
    """A store with no pool: any use of the database raises `AttributeError`."""
    return StudioRecipeStore(None)  # type: ignore[arg-type]


async def enter(rec: Recipe) -> Any:
    return await offline_store().enter_published_for_seed(
        rec, source_location="uploaded/prison-intelligence/x.csv", git_path="recipes/x.yaml",
        dataset_id="prison-intelligence", owning_unit="verify", published_by="osprey-demo-engineer",
        now=NOW, ontology=ONTOLOGY, scheme=SCHEME,
    )  # fmt: skip


def test_the_committed_recipes_are_the_seventeen_less_the_reports_recipe() -> None:
    assert len(SEEDED) == 16 and "pid_report_incidents_recipe.yaml" in SEEDED


@pytest.mark.parametrize("name", SEEDED)
def test_every_committed_pid_recipe_but_the_reports_passes_every_refusal(name: str) -> None:
    check_seeded_recipe(recipe(name), ONTOLOGY, SCHEME)


async def test_a_recipe_the_rules_refuse_is_refused_before_anything_is_written() -> None:
    rec = recipe()
    broken = rec.model_copy(deep=True)
    broken.row_template.edges[0].type = "NO_SUCH_LINK"
    with pytest.raises(RecipeRuleError):
        await enter(broken)


async def test_a_recipe_that_loosens_the_sources_marking_is_refused() -> None:
    rec = recipe()
    loosened = rec.model_copy(deep=True)
    assert loosened.defaults.handling["classification"] == "OFFICIAL"
    loosened.row_template.entities[0].handling = {"classification": "PUBLIC"}
    with pytest.raises(HandlingLoosenedError):
        await enter(loosened)


async def test_a_recipe_pinned_to_another_pack_version_is_refused() -> None:
    rec = recipe()
    assert rec.pack_versions == {"niem": ONTOLOGY.packs["niem"]}
    stale = rec.model_copy(update={"pack_versions": {"niem": ONTOLOGY.packs["niem"] + 1}})
    with pytest.raises(StaleRecipeError):
        await enter(stale)


async def test_a_recipe_with_no_pins_for_the_packs_it_writes_is_refused() -> None:
    with pytest.raises(StaleRecipeError):
        await enter(recipe().model_copy(update={"pack_versions": None}))
    with pytest.raises(StaleRecipeError):
        await enter(recipe().model_copy(update={"pack_versions": {}}))


async def test_pins_that_differ_from_the_packs_it_writes_are_refused() -> None:
    """A pin the engine ignores (a pack the recipe neither names nor writes) is still a pin the
    publish would never have stamped: the pins are exactly `pack_versions_for`."""
    rec = recipe()
    extra = rec.model_copy(update={"pack_versions": {**(rec.pack_versions or {}), "fibo": 1}})
    with pytest.raises(SeededRecipePinsDiffer) as refused:
        await enter(extra)
    assert rec.id in str(refused.value)


async def test_a_recipe_made_against_another_ontology_is_refused() -> None:
    other = recipe().model_copy(update={"ontology_version": ONTOLOGY.version + 1})
    with pytest.raises(StaleRecipeError):
        await enter(other)


async def test_a_recipe_with_no_legal_basis_is_refused() -> None:
    """Connect requires one, and a row without it is not `ready_for_profile` (Amendment 25)."""
    rec = recipe()
    assert rec.defaults.legal_basis
    for blank in (None, "", "   "):
        stripped = rec.model_copy(deep=True)
        stripped.defaults.legal_basis = blank
        with pytest.raises(SeededRecipeNoLegalBasis):
            await enter(stripped)


async def test_a_recipe_that_passes_gets_as_far_as_the_database() -> None:
    """The control for every case above: with nothing refused, the method does reach the pool, which
    this store does not have. Without it, a method that refused everything would pass them all."""
    with pytest.raises(AttributeError):
        await enter(recipe())


# --- `restore_to_draft` writes the pipeline it is given (ADR-127 Amendment 25) ----------------------
# Pure: a connection stand-in records the statements. The rows, the status flips and the transaction
# are proved live in `test_studio_recipes_store.py`.


class _Tx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> None:
        return None


class _RestoreConn:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def transaction(self) -> _Tx:
        return _Tx()

    async def execute(self, sql: str, *args: Any) -> None:
        self.executed.append((sql, args))

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any]:
        return self.row


class _RestorePool:
    def __init__(self, conn: _RestoreConn) -> None:
        self.conn = conn

    def acquire(self) -> _Tx:
        conn = self.conn

        class _Acquired(_Tx):
            async def __aenter__(self) -> Any:  # type: ignore[override]
                return conn

        return _Acquired()


def _previous_row(pipeline: Any) -> dict[str, Any]:
    import json

    entered = recipe()
    return {
        "recipe_id": "r9", "version": 3, "status": "published", "label": "Reports",
        "content": json.dumps({
            "connector_profile": "generic-csv", "source_location": "uploaded/x.csv",
            "handling": {"classification": "OFFICIAL", "handling_code": "P",
                         "originator": "u", "owning_unit": "u"},
            "legal_basis": "Synthetic demonstration data",
            "row_template": entered.row_template.model_dump(by_alias=True),
            "unmapped_fields": [], "pipeline": pipeline, "deduplicate": None,
        }),
        "owning_unit": "u", "created_by": "a", "created_at": NOW, "verified_at": NOW,
        "ontology_version": 17, "pack_versions": None, "git_path": "recipes/r9.yaml",
        "published_by": "a", "published_at": NOW, "schedule_cron": None, "schedule_watch": None,
        "dataset_id": "prison-intelligence",
    }  # fmt: skip


def _starting() -> PipelineGraph:
    return PipelineGraph(
        nodes=[
            PipelineNode(id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="Domain model",
                         config={"pack": "niem"}),
            PipelineNode(id="source", kind=PipelineNodeKind.SOURCE, label="Reports",
                         config={"connector_profile": "generic-csv", "source_location": "x.csv"}),
        ],
        edges=[PipelineEdge(source="domain", target="source")],
    )  # fmt: skip


def test_restore_to_draft_takes_the_pipeline_as_a_required_argument() -> None:
    import inspect

    parameter = inspect.signature(StudioRecipeStore.restore_to_draft).parameters["pipeline"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize("previous", [None, "other"], ids=["none-before", "another-before"])
async def test_the_restored_draft_is_written_with_the_given_pipeline_and_never_the_previous(
    previous: str | None,
) -> None:
    import json

    other = None if previous is None else _starting().model_copy(deep=True)
    if other is not None:
        other.nodes[1].config["source_location"] = "elsewhere.csv"
    conn = _RestoreConn(
        _previous_row(None if other is None else other.model_dump(by_alias=True, mode="json"))
    )
    store = StudioRecipeStore(_RestorePool(conn))  # type: ignore[arg-type]
    await store.restore_to_draft(
        "r9", created_by="w", owning_unit="verify", now=NOW, pipeline=_starting()
    )
    inserts = [a for sql, a in conn.executed if sql.startswith("INSERT")]
    assert len(inserts) == 1
    content = json.loads(inserts[0][4])
    assert content["pipeline"] == _starting().model_dump(by_alias=True)
    assert content["row_template"] is None and content["unmapped_fields"] == []
    assert content["deduplicate"] is None
    assert inserts[0][1] == 4, "the next version"
    assert any("superseded" in str(a) or "superseded" in sql for sql, a in conn.executed)


# --- "the same content" is the whole row (ADR-127 Amendment 26) -------------------------------------


def _row_as_entered() -> dict[str, Any]:
    import json

    from services.api.studio_recipes import _seeded_content

    rec = recipe()
    return {
        "label": rec.label,
        "content": json.dumps(_seeded_content(rec, "x.csv")),
        "pack_versions": json.dumps(rec.pack_versions or {}),
        "ontology_version": rec.ontology_version,
        "dataset_id": "prison-intelligence",
        "owning_unit": "verify",
        "git_path": "recipes/x.yaml",
        "status": "published",
    }


def _differences(row: dict[str, Any]) -> list[str]:
    from services.api.studio_recipes import _seeded_content, _seeded_row_differences

    rec = recipe()
    return _seeded_row_differences(
        row,  # type: ignore[arg-type]
        label=rec.label, content=_seeded_content(rec, "x.csv"), pack_versions=rec.pack_versions or {},
        ontology_version=rec.ontology_version, dataset_id="prison-intelligence",
        owning_unit="verify", git_path="recipes/x.yaml",
    )  # fmt: skip


def test_a_row_that_is_what_entering_writes_differs_in_nothing() -> None:
    assert _differences(_row_as_entered()) == []


@pytest.mark.parametrize(
    ("column", "stale"),
    [
        ("label", "Another label"),
        ("content", "{}"),
        ("pack_versions", '{"niem": 2}'),
        ("ontology_version", 15),
        ("dataset_id", "another-dataset"),
        ("owning_unit", "another-unit"),
        ("git_path", "recipes/elsewhere.yaml"),
        ("status", "flagged"),
    ],
)
def test_a_row_stale_in_any_one_column_is_named(column: str, stale: Any) -> None:
    assert _differences({**_row_as_entered(), column: stale}) == [column]


# --- `enter_draft_for_seed`: R9's first draft (ADR-127 Amendment 23, "R9's draft") -------------------
# A recipe the seed has not entered has no row for `restore_to_draft` to restore from, so the first
# seed writes R9's draft itself, once, keeping its id and version, and leaves any row there alone.
# Pure: a connection stand-in holds the rows. The rows, the transaction and what `feeding` and
# `list_drafts` then list are proved live in `test_studio_recipes_store.py`.

SOURCE = "/ingest/uploaded/prison-intelligence/pid_intel_reports.csv"


class _DraftConn:
    """Holds `studio_recipes` rows as the store's own statements write them."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def transaction(self) -> _Tx:
        return _Tx()

    async def execute(self, sql: str, *args: Any) -> None:
        self.executed.append((sql, args))
        if sql.startswith("INSERT"):
            keys = ("recipe_id", "version", "label", "status", "content", "owning_unit",
                    "created_by", "created_at", "dataset_id")  # fmt: skip
            self.rows.append(
                {
                    "verified_at": None, "ontology_version": None, "pack_versions": None,
                    "git_path": None, "published_by": None, "published_at": None,
                    "schedule_cron": None, "schedule_watch": None, **dict(zip(keys, args)),
                }  # fmt: skip
            )

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        mine = [r for r in self.rows if r["recipe_id"] == args[0]]
        return max(mine, key=lambda r: r["version"]) if mine else None


def _draft_store(conn: _DraftConn) -> StudioRecipeStore:
    return StudioRecipeStore(_RestorePool(conn))  # type: ignore[arg-type, call-overload]


async def _enter_draft(store: StudioRecipeStore, rec: Recipe | None = None) -> Any:
    return await store.enter_draft_for_seed(  # type: ignore[attr-defined]
        rec or recipe("pid_intel_reports_recipe.yaml"), source_location=SOURCE,
        dataset_id="prison-intelligence", owning_unit="verify", created_by="osprey-demo-engineer",
        now=NOW, pipeline=_starting(),
    )  # fmt: skip


async def test_the_first_entry_writes_the_draft_at_the_recipes_own_id_and_version() -> None:
    import json

    conn = _DraftConn()
    draft = await _enter_draft(_draft_store(conn))
    (insert,) = [a for sql, a in conn.executed if sql.startswith("INSERT")]
    assert (insert[0], insert[1], insert[3]) == ("pid-intel-reports", 1, "draft")
    assert insert[5:7] == ("verify", "osprey-demo-engineer") and insert[8] == "prison-intelligence"
    content = json.loads(insert[4])
    assert content["row_template"] is None and content["unmapped_fields"] == []
    assert content["deduplicate"] is None
    assert content["pipeline"] == _starting().model_dump(by_alias=True)
    assert content["connector_profile"] == "generic-csv" and content["source_location"] == SOURCE
    assert content["legal_basis"] == "Synthetic demonstration data"
    assert content["handling"]["units"] and content["handling"]["handling_columns"]
    assert content["handling"]["classification"] == "OFFICIAL"
    assert (draft.recipe_id, draft.version, draft.status.value) == ("pid-intel-reports", 1, "draft")
    assert draft.row_template is None and draft.ready_for_profile
    assert draft.published_at is None and draft.verified_at is None and draft.git_path is None


async def test_a_row_already_there_is_left_exactly_as_it_is_whatever_its_status() -> None:
    """A second seed, or one after the rehearsal's reset, must not write over what the engineer did
    or what the reset restored."""
    for status in ("draft", "published", "flagged", "superseded"):
        entered = await _enter_draft(_draft_store(_DraftConn()))
        row = {
            "recipe_id": "pid-intel-reports", "version": 7, "status": status, "label": "Mapped",
            "content": "{}", "owning_unit": "verify", "created_by": "someone",
            "created_at": NOW, "dataset_id": "prison-intelligence", "verified_at": NOW,
            "ontology_version": 17, "pack_versions": None, "git_path": None, "published_by": None,
            "published_at": None, "schedule_cron": None, "schedule_watch": None,
        }  # fmt: skip
        conn = _DraftConn([row])
        again = await _enter_draft(_draft_store(conn))
        assert [sql for sql, _ in conn.executed if sql.startswith(("INSERT", "UPDATE"))] == []
        assert (again.version, again.status.value, again.label) == (7, status, "Mapped")
        assert entered.version == 1


async def test_a_recipe_with_no_legal_basis_is_refused_before_the_database() -> None:
    rec = recipe("pid_intel_reports_recipe.yaml").model_copy(deep=True)
    rec.defaults.legal_basis = "  "
    with pytest.raises(SeededRecipeNoLegalBasis):
        await _enter_draft(offline_store(), rec)


async def test_columns_for_a_unit_with_no_units_declared_are_refused_before_the_database() -> None:
    rec = recipe("pid_intel_reports_recipe.yaml").model_copy(deep=True)
    rec.defaults.units = []
    with pytest.raises(ValueError, match="units"):
        await _enter_draft(offline_store(), rec)


async def test_a_recipe_that_passes_reaches_the_database_for_the_draft_too() -> None:
    """The control for the two refusals above."""
    with pytest.raises(AttributeError):
        await _enter_draft(offline_store())


def test_the_draft_takes_its_pipeline_as_a_required_keyword() -> None:
    import inspect

    parameter = inspect.signature(StudioRecipeStore.enter_draft_for_seed).parameters  # type: ignore[attr-defined]
    assert parameter["pipeline"].default is inspect.Parameter.empty
    assert parameter["pipeline"].kind is inspect.Parameter.KEYWORD_ONLY
