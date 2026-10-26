"""ADR-127 decision 5 (B2-5): a recipe remembers the rows it has loaded, per case.

A recipe with `deduplicate` keeps each loaded row's key (its fields canonicalised, then hashed:
`engine.dedup_key`, the one canonicalisation `01_DOMAIN_MODEL.md` §7 rule 2 describes) for its case.
A later run of the same recipe into the same case skips a row whose key is kept, whatever the
recipe's version, counting it in `rows_already_loaded`. What a mistake would do, and the case that
catches it:

- S5's second run doubling every link's occurrences and returning every event again
  (`test_a_second_run_of_the_same_file_into_the_same_case_loads_nothing`);
- a second case told its rows were loaded because another case loaded them
  (`test_a_second_case_loads_its_own_and_learns_nothing_of_the_first`);
- a corrected mapping silently re-loading what the old version loaded
  (`test_a_new_version_still_skips_the_rows_already_loaded`);
- a revert that leaves the keys, so the rerun loads nothing
  (`test_a_revert_then_a_rerun_loads_again`);
- a key kept for a row that was held, rejected or never committed, which would skip it for good
  (`test_a_held_row_is_not_kept_until_its_release_loads_it`, `test_a_rejected_row_is_not_kept`,
  `test_nothing_is_kept_when_the_load_fails_before_it_commits`);
- a recipe with no `deduplicate` keeping keys, or asking for them
  (`test_a_recipe_without_deduplicate_keeps_no_keys_and_asks_for_none`);
- Verify promising a different outcome from the run, or writing a key
  (`test_verifys_dry_run_reports_the_rows_already_loaded_as_the_run_would_and_writes_nothing`);
- the keys, or a count of another case's, in a route's answer
  (`test_no_route_answer_carries_the_keys`).

The keys are kept **after** the graph commit, in the same Postgres transaction as the load's
record (`RecipeRunStore.add_record`), never before it. A crash before the commit keeps no key for a
row that never loaded; a crash between the two stores leaves loaded rows with neither record nor
keys (the same unrecorded load the ledger already has), which a rerun loads again; the run's ledger
row stays `running`, which says the load did not finish. A key is never kept for a row that did not
load."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.load_records import report_view
from services.api.studio_publish import load_with_rules
from services.ingest.engine import (
    RowKeyDefinitionChanged,
    RowKeyRunInProgress,
    dedup_fingerprint,
    dedup_key,
    dry_run_recipe,
    run_recipe,
)
from services.ingest.load_ledger import load_record_from_report
from services.ingest.load_revert import RevertDeps, revert

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.ingest import LoadReport, Recipe
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_load_record_created_and_merged import _recipe as _base_recipe
from tests.ingest.test_revert_load import (
    Alerts,
    Analytics,
    Audit,
    Held,
    Ledger,
    Steps,
    WorkingSets,
    no_caches,
)

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")
CASE = "case-1"
KEY = [{"field": "payer"}, {"field": "payee"}, {"field": "paid_at"}]
NOW = datetime(2026, 10, 26, tzinfo=UTC)


def _recipe(*, version: int = 1, deduplicate: bool = True) -> Recipe:
    document = _base_recipe().model_dump(by_alias=True)
    document["version"] = version
    if deduplicate:
        document["deduplicate"] = {"key": KEY}
    return Recipe.model_validate(document)


def _row(payer: str, payee: str, day: int) -> dict[str, str]:
    return {
        "payer": payer,
        "payee": payee,
        "paid_at": f"2026-03-0{day}T09:00:00+00:00",
        "memo": "",
    }


ROWS = [_row("SYN-1", "SYN-2", 1), _row("SYN-3", "SYN-4", 2), _row("SYN-5", "SYN-6", 3)]


class KeyStore:
    """The row-key half of `RecipeRunStore`, as the table behaves: a key is kept for a (recipe,
    case) with the load that kept it; keeping one already kept changes nothing; releasing a load's
    keys frees exactly those. `kept` is a read of what is there."""

    def __init__(self) -> None:
        #: (recipe, case, key) -> the load that kept it.
        self.rows: dict[tuple[str, str, str], str] = {}
        #: (recipe, case, key) -> the fingerprint of the definition that made it.
        self.made_by: dict[tuple[str, str, str], str] = {}
        self.asked = 0

    async def kept(self, recipe_id: str, case: str, keys: Sequence[str]) -> set[str]:
        self.asked += 1
        return {k for k in keys if (recipe_id, case, k) in self.rows}

    async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]:
        """The definitions the case's kept keys were made under, each with how many loads kept
        keys under it."""
        loads: dict[str, set[str]] = {}
        for (recipe, kept_case, key), load in self.rows.items():
            if (recipe, kept_case) == (recipe_id, case):
                loads.setdefault(self.made_by[(recipe, kept_case, key)], set()).add(load)
        return {fp: len(ids) for fp, ids in loads.items()}

    def keep(
        self,
        recipe_id: str,
        case: str,
        load_id: str,
        keys: Sequence[str],
        fingerprint: str | None,
    ) -> None:
        for key in keys:
            self.rows.setdefault((recipe_id, case, key), load_id)
            self.made_by.setdefault((recipe_id, case, key), fingerprint or "")

    async def release(self, load_ids: Sequence[str]) -> int:
        gone = [k for k, load in self.rows.items() if load in set(load_ids)]
        for key in gone:
            del self.rows[key]
            self.made_by.pop(key, None)
        return len(gone)


class Sink:
    """A `LoadSink` over `KeyStore`: the record and the keys land together, as `add_record` does
    them in one transaction, after the graph's commit."""

    def __init__(self, store: KeyStore, case: str = CASE) -> None:
        self.store, self.case = store, case
        self.records: list[LoadReport] = []

    async def kept(self, recipe_id: str, case: str, keys: Sequence[str]) -> set[str]:
        return await self.store.kept(recipe_id, case, keys)

    async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]:
        return await self.store.fingerprints(recipe_id, case)

    def hold_row_keys(self, recipe_id: str, case: str) -> Any:
        """No lock: the cases that need one use `LockingSink`."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def unheld() -> Any:
            yield

        return unheld()

    async def committed(self, report: LoadReport, *, source: str) -> None:
        self.records.append(report)
        self.store.keep(
            report.recipe_id,
            self.case,
            report.load_id,
            report.kept_row_keys,
            report.row_key_fingerprint,
        )

    async def geometries(self, load_id: str, refs: Sequence[str]) -> None:
        return None

    async def rule_writes(self, load_id: str, **_: Any) -> None:
        return None

    async def uncovered(self, load_id: str) -> None:
        return None


async def _load(
    graph: MergingGraph,
    rows: list[dict[str, str]],
    load_id: str,
    sink: Sink,
    *,
    recipe: Recipe | None = None,
    case: str = CASE,
) -> tuple[LoadReport, list[Any]]:
    report, events, _ = await load_with_rules(
        recipe or _recipe(),
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=load_id,
        investigation_scope=case,
        source="private_cash.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
        sink=sink,  # type: ignore[arg-type]
    )
    assert report.rejections == [], report.rejections
    return report, events


async def test_a_second_run_of_the_same_file_into_the_same_case_loads_nothing() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    first, first_events = await _load(graph, ROWS, "load-1", sink)
    assert first.rows_already_loaded == 0 and len(first_events) == 3
    written = (len(graph.committed_nodes), len(graph.committed_edges))

    second, second_events = await _load(graph, ROWS, "load-2", sink)

    assert second.rows_read == 3 and second.rows_already_loaded == 3
    assert (second.nodes_created, second.nodes_referenced, second.edges_created) == (0, 0, 0)
    assert second_events == [], "no event is loaded again"
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == written, (
        "nothing written: no node, no link, no occurrence added to a link that exists"
    )
    assert second.kept_row_keys == [], "and nothing to keep"


async def test_a_partly_new_file_loads_the_new_rows_only() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    await _load(graph, ROWS[:2], "load-1", sink)
    report, events = await _load(graph, ROWS, "load-2", sink)
    assert (report.rows_read, report.rows_already_loaded) == (3, 2)
    assert len(events) == 1 and len(report.kept_row_keys) == 1


async def test_a_second_case_loads_its_own_and_learns_nothing_of_the_first() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    await _load(graph, ROWS, "load-1", Sink(store, "case-a"), case="case-a")
    other = await _load(graph, ROWS, "load-2", Sink(store, "case-b"), case="case-b")
    report, events = other
    assert report.rows_already_loaded == 0, "the other case's keys are not this case's"
    assert len(events) == 3
    assert {case for (_, case, _) in store.rows} == {"case-a", "case-b"}
    # And the count a case is told is of its own keys: the first case's rerun counts its own.
    again, _ = await _load(graph, ROWS, "load-3", Sink(store, "case-a"), case="case-a")
    assert again.rows_already_loaded == 3


async def test_a_new_version_still_skips_the_rows_already_loaded() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    await _load(graph, ROWS, "load-1", sink, recipe=_recipe(version=1))
    report, events = await _load(graph, ROWS, "load-2", sink, recipe=_recipe(version=2))
    assert report.rows_already_loaded == 3 and events == []
    assert report.recipe_version == 2


async def test_within_one_file_duplicates_keep_one_key_and_a_rerun_counts_every_row() -> None:
    """The key is of the group, kept once; a rerun skips the whole group and counts each of its
    rows, and none of them as a within-file duplicate."""
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    rows = [ROWS[0], ROWS[0], ROWS[1]]
    first, _ = await _load(graph, rows, "load-1", sink)
    assert first.rows_deduplicated == 1 and len(first.kept_row_keys) == 2
    second, _ = await _load(graph, rows, "load-2", sink)
    assert (second.rows_already_loaded, second.rows_deduplicated) == (3, 0)


async def test_a_recipe_without_deduplicate_keeps_no_keys_and_asks_for_none() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    recipe = _recipe(deduplicate=False)
    await _load(graph, ROWS, "load-1", sink, recipe=recipe)
    second, events = await _load(graph, ROWS, "load-2", sink, recipe=recipe)
    assert store.rows == {} and store.asked == 0
    assert second.rows_already_loaded == 0 and len(events) == 3, "every row loads every time"


async def test_a_rejected_row_is_not_kept() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    rows = [ROWS[0], {**ROWS[1], "paid_at": "not a time"}]
    report, _, _ = await load_with_rules(
        _recipe(),
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id="load-1",
        investigation_scope=CASE,
        source="s.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
        sink=sink,  # type: ignore[arg-type]
    )
    assert len(report.rejections) == 1
    assert len(report.kept_row_keys) == 1, "only the row that loaded"
    # The rejected row can be corrected and loaded: its key was never kept.
    fixed, events = await _load(graph, [ROWS[0], ROWS[1]], "load-2", sink)
    assert fixed.rows_already_loaded == 1 and len(events) == 1


async def test_a_held_row_is_not_kept_until_its_release_loads_it() -> None:
    """A row a rule holds is resolved and not written, so its key is not kept; the release loads it
    under its own load id and keeps it then (`run_recipe`'s `skip_row_indices`)."""
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    tx = await graph.begin_transaction()
    held_run, _ = await run_recipe(
        _recipe(),
        ROWS,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        tx=tx,
        principal=LOADER,
        load_id="load-1",
        investigation_scope=CASE,
        source="s.csv",
        media=InMemoryMediaStore(),
        scheme=SCHEME,
        skip_row_indices=frozenset({1}),
        row_keys=store,
    )
    await graph.commit_transaction(tx)
    assert len(held_run.kept_row_keys) == 2
    held_key = dedup_key(ROWS[1], _recipe().deduplicate.key)  # type: ignore[union-attr]
    assert held_key is not None and held_key not in held_run.kept_row_keys

    # What the sink keeps at the commit: the two rows that loaded, not the held one.
    store.keep(
        held_run.recipe_id, CASE, "load-1", held_run.kept_row_keys, held_run.row_key_fingerprint
    )
    released, _ = await _load(graph, [ROWS[1]], "release-1", Sink(store))
    assert released.rows_already_loaded == 0 and released.kept_row_keys == [held_key]


async def test_nothing_is_kept_when_the_load_fails_before_it_commits() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)

    async def refuse(*_: Any) -> list[str]:
        raise RuntimeError("the graph refused the write")

    graph.upsert_edges = refuse  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await _load(graph, ROWS, "load-1", sink)
    assert store.rows == {} and sink.records == [], "no key for a row that never loaded"


async def test_a_failure_in_the_stores_after_the_commit_keeps_the_record_and_keys_or_neither() -> (
    None
):
    """The record and the keys are one transaction in the ledger. A sink that fails writes neither:
    the load is in the graph, unrecorded and unkept (the unrecorded load the ledger already
    admits), never keys without a record or a record whose keys were lost."""

    class DiesBeforeWriting(Sink):
        async def committed(self, report: LoadReport, *, source: str) -> None:
            raise RuntimeError("the process died between the two stores")

    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    with pytest.raises(RuntimeError):
        await _load(graph, ROWS, "load-1", DiesBeforeWriting(store))
    assert store.rows == {}
    assert len(graph.committed_nodes) > 0, (
        "the rows are loaded, which the run's `running` row shows"
    )


async def test_a_revert_then_a_rerun_loads_again() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    first, _ = await _load(graph, ROWS, "load-1", sink)
    assert len(store.rows) == 3
    record = load_record_from_report(
        first, source="s.csv", created_by="loader-1", started_at=NOW, now=NOW, investigation_id=CASE
    )
    steps = Steps()

    class KeyedLedger(Ledger):
        """The ledger the revert asks to release a load's keys: `RecipeRunStore.release_row_keys`
        over the same table the runs ask."""

        async def release_row_keys(self, load_ids: Any) -> int:
            return await store.release(load_ids)

    deps = RevertDeps(
        ledger=KeyedLedger(record),
        graph=graph,  # type: ignore[arg-type]
        analytics=Analytics(steps),  # type: ignore[arg-type]
        held_rows=Held(steps),
        alerts=Alerts(steps),
        audit=Audit(steps),
        working_sets=WorkingSets(steps),
        invalidate_caches=no_caches,
    )
    await revert("load-1", reverted_by="operator-1", deps=deps, now=NOW)
    assert store.rows == {}, "the keys went with the load"

    again, events = await _load(graph, ROWS, "load-2", sink)
    assert again.rows_already_loaded == 0 and len(events) == 3
    assert len(again.kept_row_keys) == 3


async def test_the_keys_of_another_load_are_not_released() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    await _load(graph, ROWS[:1], "load-1", sink)
    await _load(graph, ROWS, "load-2", sink)  # keeps the other two under load-2
    assert await store.release(["load-1"]) == 1
    assert {v for v in store.rows.values()} == {"load-2"}


async def test_verifys_dry_run_reports_the_rows_already_loaded_as_the_run_would_and_writes_nothing() -> (
    None
):
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    await _load(graph, ROWS[:2], "load-1", Sink(store))
    before = (dict(store.rows), len(graph.committed_nodes), len(graph.committed_edges))
    dry = await dry_run_recipe(
        _recipe(),
        ROWS,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        principal=LOADER,
        source="s.csv",
        scheme=SCHEME,
        row_keys=store,
        investigation_scope=CASE,
    )
    assert dry.rows_read == 3 and dry.rows_already_loaded == 2
    assert sum(c.created for c in dry.edges_by_type.values()) == 1, "only the new row is simulated"
    assert (dict(store.rows), len(graph.committed_nodes), len(graph.committed_edges)) == before

    # The real run gives the same count.
    real, _ = await _load(graph, ROWS, "load-2", Sink(store))
    assert real.rows_already_loaded == dry.rows_already_loaded


async def test_a_dry_run_with_no_case_or_no_store_counts_none() -> None:
    graph = MergingGraph(ONTOLOGY)
    dry = await dry_run_recipe(
        _recipe(),
        ROWS,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        principal=LOADER,
        source="s.csv",
        scheme=SCHEME,
    )
    assert dry.rows_already_loaded == 0


def test_no_route_answer_carries_the_keys() -> None:
    """Rule 3: the keys are hashes of the loader's own source rows, for the load's record and
    the ledger alone. A route answers the count, which is of this case's own kept rows, and never a
    key (`report_view` drops them with the id lists)."""
    report = LoadReport(
        load_id="l",
        recipe_id="r",
        recipe_version=1,
        rows_read=3,
        rows_already_loaded=2,
        kept_row_keys=["abc", "def"],
    )
    view = report_view(report, LOADER, SCHEME)
    assert view.rows_already_loaded == 2
    assert "kept_row_keys" not in view.model_dump()
    assert "abc" not in view.model_dump_json()
    assert SimpleNamespace  # keep the import honest for the checker


def _published_draft(tmp_path: Any) -> tuple[Any, Any]:
    """A published Studio recipe whose committed YAML has `deduplicate`, and its source file."""
    import csv
    import shutil  # noqa: F401

    from services.api.studio_publish import serialise_recipe

    from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus

    repo = tmp_path / "repo"
    (repo / "recipes").mkdir(parents=True)
    (repo / "recipes" / "private-cash.yaml").write_text(serialise_recipe(_recipe()))
    source = tmp_path / "cash.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROWS[0]))
        writer.writeheader()
        writer.writerows(ROWS)
    draft = StudioRecipeDraft(
        recipe_id="private-cash",
        version=1,
        status=StudioRecipeStatus.PUBLISHED,
        label="Private cash",
        connector_profile="generic-csv",
        source_location=str(source),
        owning_unit="unit-1",
        created_by="analyst-1",
        created_at=NOW,
        git_path="recipes/private-cash.yaml",
    )
    return repo, draft


async def test_a_published_recipe_run_twice_through_the_studios_own_path_loads_once(
    tmp_path: Any,
) -> None:
    """The route's path (`run_published_recipe`, which reads the committed YAML): the sink is the
    store of loaded rows, so a second run of the same source into the same case skips every row."""
    from services.api.studio_publish import run_published_recipe

    repo, draft = _published_draft(tmp_path)
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)

    async def run(load_id: str) -> LoadReport:
        return await run_published_recipe(
            draft,
            LOADER,
            graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            load_id=load_id,
            investigation_scope=CASE,
            repo_root=repo,
            media=InMemoryMediaStore(),
            scheme=SCHEME,
            sink=sink,  # type: ignore[arg-type]
        )

    first = await run("load-1")
    second = await run("load-2")
    assert (first.rows_already_loaded, len(first.kept_row_keys)) == (0, 3)
    assert (second.rows_already_loaded, second.nodes_created, second.edges_created) == (3, 0, 0)
    assert len(store.rows) == 3


async def test_a_studio_built_recipe_run_twice_creates_nothing_the_second_time() -> None:
    """The whole job inside the Studio (Brief 2 §6, §7): a draft with `deduplicate` is built into a
    recipe by Publish, committed as YAML, run twice into one case; the second run loads nothing and
    reports `rows_already_loaded`. And Verify, which reads the draft, counts what the run would."""
    from unittest import mock

    from services.api import studio_verify
    from services.api.studio_publish import build_recipe, run_published_recipe, serialise_recipe

    from schemas.ingest import (
        DeduplicateConfig,
        FieldBinding,
        StudioRecipeDraft,
        StudioRecipeStatus,
    )

    base = _recipe(deduplicate=False)
    draft = StudioRecipeDraft(  # type: ignore[call-arg]
        recipe_id=base.id,
        version=1,
        status=StudioRecipeStatus.DRAFT,
        label="Private cash",
        connector_profile="generic-csv",
        source_location="/tmp/unused.csv",
        handling={
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        legal_basis="a basis",
        owning_unit="unit-1",
        created_by="analyst-1",
        created_at=NOW,
        row_template=base.row_template,
        deduplicate=DeduplicateConfig(
            key=[
                FieldBinding(field="payer"),
                FieldBinding(field="payee"),
                FieldBinding(field="paid_at"),
            ]
        ),
    )
    published = build_recipe(
        draft,
        ontology_version=ONTOLOGY.version,
        pack_versions={},
        schedule_cron=None,
        schedule_watch=None,
    )
    assert published.deduplicate == draft.deduplicate, "Publish carries it into the recipe"

    import csv
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "recipes").mkdir()
        (root / "recipes" / f"{base.id}.yaml").write_text(serialise_recipe(published))
        source = root / "cash.csv"
        with source.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(ROWS[0]))
            writer.writeheader()
            writer.writerows(ROWS)
        live = draft.model_copy(
            update={
                "status": StudioRecipeStatus.PUBLISHED,
                "git_path": f"recipes/{base.id}.yaml",
                "source_location": str(source),
            }
        )
        graph, store = MergingGraph(ONTOLOGY), KeyStore()
        sink = Sink(store)

        async def run(load_id: str) -> LoadReport:
            return await run_published_recipe(
                live,
                LOADER,
                graph=graph,  # type: ignore[arg-type]
                ontology=ONTOLOGY,
                load_id=load_id,
                investigation_scope=CASE,
                repo_root=root,
                media=InMemoryMediaStore(),
                scheme=SCHEME,
                sink=sink,  # type: ignore[arg-type]
            )

        first = await run("load-1")
        written = (len(graph.committed_nodes), len(graph.committed_edges))
        second = await run("load-2")
        assert (first.rows_already_loaded, len(first.kept_row_keys)) == (0, 3)
        assert (second.rows_already_loaded, second.nodes_created, second.edges_created) == (3, 0, 0)
        assert (len(graph.committed_nodes), len(graph.committed_edges)) == written

        # Verify, by the draft's own `deduplicate`, counts the same.
        with mock.patch.object(studio_verify, "_read_recipe_rows", lambda _d: list(ROWS)):
            report = await studio_verify.run_verify(
                draft,
                LOADER,
                SCHEME,
                graph,  # type: ignore[arg-type]
                ONTOLOGY,
                row_keys=store,
                investigation_id=CASE,
            )
        assert report.rows_already_loaded == 3
        assert second.rows_already_loaded == report.rows_already_loaded


async def test_a_draft_with_no_deduplicate_builds_a_recipe_with_none_and_keeps_no_keys() -> None:
    from services.api.studio_publish import build_recipe

    from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus

    base = _recipe(deduplicate=False)
    draft = StudioRecipeDraft(  # type: ignore[call-arg]
        recipe_id=base.id,
        version=1,
        status=StudioRecipeStatus.DRAFT,
        label="x",
        connector_profile="generic-csv",
        handling={
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "u",
            "owning_unit": "u",
        },
        legal_basis="b",
        owning_unit="u",
        created_by="a",
        created_at=NOW,
        row_template=base.row_template,
    )
    recipe = build_recipe(
        draft, ontology_version=ONTOLOGY.version, pack_versions={}, schedule_cron=None,
        schedule_watch=None,
    )  # fmt: skip
    assert recipe.deduplicate is None


async def test_the_ledger_sink_hands_the_keys_to_the_ledger_with_the_record_and_asks_it_for_kept() -> (
    None
):
    """`LedgerSink.committed` is where the load's record is written; the keys of the rows it wrote
    go in the same call (the ledger makes them one transaction), and a lookup is the ledger's."""
    from services.api.load_records import LedgerSink

    calls: list[dict[str, Any]] = []

    class RecordingLedger:
        async def add_record(
            self,
            run_id: str,
            record: Any,
            *,
            row_keys: Sequence[str] = (),
            row_key_fingerprint: str = "",
        ) -> None:
            calls.append(
                {
                    "run": run_id,
                    "record": record,
                    "keys": list(row_keys),
                    "fingerprint": row_key_fingerprint,
                }
            )

        async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]:
            return {"fp": 2}

        async def kept_row_keys(self, recipe_id: str, case: str, keys: Sequence[str]) -> set[str]:
            calls.append({"asked": (recipe_id, case, list(keys))})
            return {"k1"}

    sink = LedgerSink(
        RecordingLedger(),  # type: ignore[arg-type]
        "run-1",
        created_by="loader-1",
        investigation_id=CASE,
        started_at=NOW,
    )
    report = LoadReport(
        load_id="load-1",
        recipe_id="r",
        recipe_version=1,
        kept_row_keys=["k1", "k2"],
        row_key_fingerprint="fp",
    )
    await sink.committed(report, source="s.csv")
    assert calls[0]["keys"] == ["k1", "k2"] and calls[0]["record"].investigation_id == CASE
    assert calls[0]["fingerprint"] == "fp", "the definition that made the keys goes with them"
    assert await sink.fingerprints("r", CASE) == {"fp": 2}
    calls.clear()
    assert await sink.kept("r", CASE, ["k1", "k9"]) == {"k1"}
    assert calls[0] == {"asked": ("r", CASE, ["k1", "k9"])}


# --- a new version must not apply itself to rows already loaded ----------------------------------


def _recipe_keyed_on(*fields: str, version: int = 2) -> Recipe:
    document = _base_recipe().model_dump(by_alias=True)
    document["version"] = version
    document["deduplicate"] = {"key": [{"field": f} for f in fields]}
    return Recipe.model_validate(document)


async def test_a_new_version_with_a_changed_key_is_refused_naming_how_many_loads_to_revert() -> (
    None
):
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    await _load(graph, ROWS[:1], "load-1", sink)
    await _load(graph, ROWS[1:2], "load-2", sink)
    written = (len(graph.committed_nodes), len(graph.committed_edges), len(store.rows))

    with pytest.raises(RowKeyDefinitionChanged) as refused:
        await _load(graph, ROWS, "load-3", sink, recipe=_recipe_keyed_on("payer", "payee"))

    assert refused.value.loads == 2, "a count of loads, never their ids"
    assert "2 load(s)" in str(refused.value) and "load-1" not in str(refused.value)
    assert (len(graph.committed_nodes), len(graph.committed_edges), len(store.rows)) == written


async def test_a_new_version_that_left_the_key_unchanged_still_skips() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    await _load(graph, ROWS, "load-1", sink, recipe=_recipe(version=1))
    again, events = await _load(graph, ROWS, "load-2", sink, recipe=_recipe(version=7))
    assert again.rows_already_loaded == 3 and events == []


async def test_a_changed_key_is_fine_once_the_loads_that_kept_the_old_keys_are_reverted() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    await _load(graph, ROWS, "load-1", sink)
    await store.release(["load-1"])  # what the revert does
    report, events = await _load(
        graph, ROWS, "load-2", sink, recipe=_recipe_keyed_on("payer", "payee")
    )
    assert report.rows_already_loaded == 0 and len(events) == 3
    assert {fp for fp in store.made_by.values()} == {
        dedup_fingerprint(_recipe_keyed_on("payer", "payee").deduplicate)  # type: ignore[arg-type]
    }


async def test_a_new_version_that_removed_deduplicate_is_refused_while_keys_are_kept() -> None:
    """Dropping `deduplicate` must not reload every row the case already holds: a run with none
    still asks which keys the case kept, and refuses (naming the loads) while any are."""
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    await _load(graph, ROWS[:1], "load-1", sink)
    written = (len(graph.committed_nodes), len(graph.committed_edges), len(store.rows))
    with pytest.raises(RowKeyDefinitionChanged) as refused:
        await _load(graph, ROWS, "load-2", sink, recipe=_recipe(version=2, deduplicate=False))
    assert refused.value.loads == 1
    assert (len(graph.committed_nodes), len(graph.committed_edges), len(store.rows)) == written


async def test_a_recipe_without_deduplicate_runs_in_a_case_that_kept_none_of_its_keys() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    await _load(graph, ROWS[:1], "load-1", sink)
    # The same recipe in another case, and another recipe in this one, hold no keys to protect.
    other = _recipe(deduplicate=False).model_copy(update={"id": "another-recipe"})
    report, events = await _load(graph, ROWS, "load-2", sink, recipe=other)
    assert report.rows_already_loaded == 0 and len(events) == 3
    assert report.row_key_fingerprint is None


async def test_removing_deduplicate_is_fine_once_the_loads_that_kept_keys_are_reverted() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    await _load(graph, ROWS, "load-1", sink)
    await store.release(["load-1"])
    report, events = await _load(graph, ROWS, "load-2", sink, recipe=_recipe(deduplicate=False))
    assert report.rows_already_loaded == 0 and len(events) == 3


async def test_verify_refuses_a_draft_that_removed_deduplicate_while_keys_are_kept() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    await _load(graph, ROWS[:1], "load-1", Sink(store))
    with pytest.raises(RowKeyDefinitionChanged) as refused:
        await dry_run_recipe(
            _recipe(version=2, deduplicate=False),
            ROWS,
            graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            principal=LOADER,
            source="s.csv",
            scheme=SCHEME,
            row_keys=store,
            investigation_scope=CASE,
        )
    assert refused.value.loads == 1


def _datetime_keyed(*, date_order: str | None, source_crs: str | None = None) -> Recipe:
    document = _base_recipe().model_dump(by_alias=True)
    document["version"] = 2
    document["deduplicate"] = {
        "key": [{"field": "payer"}, {"field": "paid_at", "transform": "datetime"}]
    }
    document["connector"] = {
        **document["connector"],
        "date_order": date_order,
        "source_crs": source_crs,
    }
    return Recipe.model_validate(document)


async def test_a_changed_connector_date_order_is_refused_because_it_changes_the_keys() -> None:
    """`dedup_key` canonicalises a date with the connector's `date_order`, so the same recipe with
    another order makes other keys for the same rows: it is a changed definition."""
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    await _load(graph, ROWS[:1], "load-1", sink, recipe=_datetime_keyed(date_order="dmy"))
    written = (len(graph.committed_nodes), len(store.rows))
    with pytest.raises(RowKeyDefinitionChanged) as refused:
        await _load(graph, ROWS, "load-2", sink, recipe=_datetime_keyed(date_order="mdy"))
    assert refused.value.loads == 1
    assert (len(graph.committed_nodes), len(store.rows)) == written
    # Verify says the same.
    with pytest.raises(RowKeyDefinitionChanged):
        await dry_run_recipe(
            _datetime_keyed(date_order="mdy"),
            ROWS,
            graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            principal=LOADER,
            source="s.csv",
            scheme=SCHEME,
            row_keys=store,
            investigation_scope=CASE,
        )


async def test_a_connector_setting_the_key_does_not_use_does_not_change_the_fingerprint() -> None:
    """A source CRS feeds no `datetime` key, so changing it changes no key and refuses nothing."""
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = Sink(store)
    await _load(graph, ROWS[:1], "load-1", sink, recipe=_datetime_keyed(date_order="dmy"))
    recipe = _datetime_keyed(date_order="dmy", source_crs="EPSG:27700")
    again, _ = await _load(graph, ROWS, "load-2", sink, recipe=recipe)
    assert again.rows_already_loaded == 1


async def test_each_load_records_the_fingerprint_its_keys_were_made_under() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    report, _ = await _load(graph, ROWS, "load-1", Sink(store))
    assert report.row_key_fingerprint == dedup_fingerprint(_recipe().deduplicate)  # type: ignore[arg-type]
    assert set(store.made_by.values()) == {report.row_key_fingerprint}


async def test_verify_reports_the_same_refusal() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    await _load(graph, ROWS[:1], "load-1", Sink(store))
    with pytest.raises(RowKeyDefinitionChanged) as refused:
        await dry_run_recipe(
            _recipe_keyed_on("payer"),
            ROWS,
            graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            principal=LOADER,
            source="s.csv",
            scheme=SCHEME,
            row_keys=store,
            investigation_scope=CASE,
        )
    assert refused.value.loads == 1


# --- two runs of one recipe into one case are serialised (an advisory lock on (recipe, case)) -----


class LockingSink(Sink):
    """A sink whose `hold_row_keys` is the ledger's advisory lock: one holder per (recipe, case),
    held from the key check to the record's write; a second waits up to `wait` seconds and is then
    refused (`RowKeyRunInProgress`). Records the order things happened in."""

    def __init__(self, store: KeyStore, case: str = CASE, *, wait: float = 5.0) -> None:
        super().__init__(store, case)
        self.wait = wait
        self.held = 0

    def hold_row_keys(self, recipe_id: str, case: str) -> Any:
        from contextlib import asynccontextmanager

        locks = self.store.__dict__.setdefault("_locks", {})
        lock = locks.setdefault((recipe_id, case), asyncio.Lock())

        @asynccontextmanager
        async def held() -> Any:
            try:
                await asyncio.wait_for(lock.acquire(), timeout=self.wait)
            except TimeoutError as exc:
                raise RowKeyRunInProgress(recipe_id) from exc
            self.held += 1
            try:
                yield
            finally:
                lock.release()

        return held()


class GatedGraph(MergingGraph):
    """A graph whose first write waits for the test: the load is in the middle of writing."""

    def __init__(self, ontology: Any) -> None:
        super().__init__(ontology)
        self.entered = asyncio.Event()
        self.go = asyncio.Event()
        self.fail = False

    async def upsert_nodes(self, nodes: Any, tx: object) -> list[str]:
        if not self.entered.is_set():
            self.entered.set()
            await self.go.wait()
            if self.fail:
                raise RuntimeError("the graph refused the write")
        return await super().upsert_nodes(nodes, tx)


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


async def test_a_second_run_of_the_same_file_waits_then_loads_nothing_and_attribution_is_right() -> (
    None
):
    graph, store = GatedGraph(ONTOLOGY), KeyStore()
    sink = LockingSink(store)
    first = asyncio.create_task(_load(graph, ROWS, "load-1", sink))
    await graph.entered.wait()
    second = asyncio.create_task(_load(graph, ROWS, "load-2", sink))
    await _settle()
    assert store.asked == 1, "the second has not yet looked at the keys: it is waiting"
    assert not second.done()
    graph.go.set()
    one, two = await asyncio.gather(first, second)
    assert one[0].rows_already_loaded == 0 and len(one[1]) == 3
    assert (two[0].rows_already_loaded, two[0].nodes_created, two[0].edges_created) == (3, 0, 0)
    assert two[1] == [], "no event is loaded twice"
    assert set(store.rows.values()) == {"load-1"}, "every key is the first load's"


async def test_runs_into_different_cases_do_not_wait_for_each_other() -> None:
    graph, store = GatedGraph(ONTOLOGY), KeyStore()
    gated = asyncio.create_task(
        _load(graph, ROWS, "load-1", LockingSink(store, "case-a"), case="case-a")
    )
    await graph.entered.wait()
    other_graph = MergingGraph(ONTOLOGY)
    report, events = await asyncio.wait_for(
        _load(other_graph, ROWS, "load-2", LockingSink(store, "case-b"), case="case-b"), 5
    )
    assert report.rows_already_loaded == 0 and len(events) == 3
    graph.go.set()
    await gated


async def test_the_lock_is_released_when_the_first_run_fails_and_the_second_then_loads() -> None:
    graph, store = GatedGraph(ONTOLOGY), KeyStore()
    graph.fail = True
    sink = LockingSink(store)
    first = asyncio.create_task(_load(graph, ROWS, "load-1", sink))
    await graph.entered.wait()
    second = asyncio.create_task(_load(MergingGraph(ONTOLOGY), ROWS, "load-2", sink))
    await _settle()
    graph.go.set()
    with pytest.raises(RuntimeError):
        await first
    report, events = await asyncio.wait_for(second, 5)
    assert report.rows_already_loaded == 0 and len(events) == 3, "nothing was kept by the failure"
    assert set(store.rows.values()) == {"load-2"}


async def test_a_second_run_that_would_wait_too_long_is_refused_and_writes_nothing() -> None:
    graph, store = GatedGraph(ONTOLOGY), KeyStore()
    first = asyncio.create_task(_load(graph, ROWS, "load-1", LockingSink(store)))
    await graph.entered.wait()
    other_graph = MergingGraph(ONTOLOGY)
    with pytest.raises(RowKeyRunInProgress):
        await _load(other_graph, ROWS, "load-2", LockingSink(store, wait=0.05))
    assert other_graph.committed_nodes == [] and other_graph.open_nodes == []
    graph.go.set()
    await first


async def test_a_recipe_without_deduplicate_takes_no_lock() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    sink = LockingSink(store)
    await _load(graph, ROWS, "load-1", sink, recipe=_recipe(deduplicate=False))
    assert sink.held == 0
