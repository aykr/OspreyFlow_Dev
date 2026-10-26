"""ADR-127 Amendment 29 (B2-9b): a run never holds the loop long enough to lose its transaction.

The keep-alive of an open graph transaction is an asyncio task. It runs only when the loop gets a
turn, and a run that spends seconds in synchronous work gives it none. The keep-alive's own tests
idle with real sleeps, which yield, so nothing saw this until the first real seed's million-row R5
lost its transaction. Each case runs a load under `LoopMonitor` (a task asking the loop for a turn
every 100 ms) and holds the longest stall to two seconds.

- `test_the_row_loop_yields_while_its_own_steps_are_slow`: the work a row costs inside the loop
  (here `_staged_entity_to_resolved`, 25 ms a call, about 5 s over 100 rows). Plant: remove the
  loop's yield and the stall is the whole of it.
- `test_the_resolve_step_runs_off_the_loop`: the work of resolving the rows (`_resolve_row`, 50 ms a
  row, 5 s over 100 rows). Plant: run `resolve_rows_keyed` on the loop again.
- `test_the_staging_and_read_back_run_off_the_loop`: the raw staging, the staging write and the
  read-back (made 3 s each). Plants: call `_stage_raw_rows`, or `_stage_rows`, on the loop again.
- `test_the_row_keys_are_computed_off_the_loop`: the key hashing over all rows (`dedup_key`, 50 ms a
  row, in `kept_among` and again in the resolve step). Plant: compute `_sorted_keys` on the loop
  again (the resolve step's own computation is held off the loop by the resolve case's plant).

- `test_the_published_runs_file_read_runs_off_the_loop`: `run_published_recipe` reading and parsing
  the whole source file (made 3 s). Plant: read it on the loop again.

Each also asserts the synthetic work really was done, so a case that cost nothing cannot pass.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest
from services.api import studio_publish
from services.api.studio_publish import load_with_rules
from services.ingest import engine

from adapters.media_objectstore.testing import InMemoryMediaStore
from schemas.ingest import Recipe, StudioRecipeStatus
from tests.ingest.loop_monitor import LoopMonitor
from tests.ingest.recipe_test_support import (
    MergingGraph,
    local_staging,  # noqa: F401 (the autouse fixture)
)
from tests.ingest.test_load_record_created_and_merged import (
    LOADER,
    ONTOLOGY,
    SCHEME,
    _recipe,
)
from tests.ingest.test_row_keys import KeyStore, Sink

ROWS = 100
LIMIT = 2.0


def _rows() -> list[dict[str, str]]:
    return [
        {
            "payer": f"SYN-{i}",
            "payee": f"SYN-{i + 1000}",
            "paid_at": f"2026-03-0{1 + i % 9}T09:00:00+00:00",
            "memo": "",
        }
        for i in range(ROWS)
    ]


def _keyed() -> Recipe:
    document = _recipe().model_dump(by_alias=True)
    document["deduplicate"] = {"key": [{"field": "payer"}, {"field": "payee"}]}
    return Recipe.model_validate(document)


async def _monitored_load(recipe: Recipe, sink: Sink | None = None) -> LoopMonitor:
    async with LoopMonitor() as monitor:
        report, _events, _held = await load_with_rules(
            recipe,
            _rows(),
            LOADER,
            graph=MergingGraph(ONTOLOGY),  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            load_id="load-1",
            investigation_scope="case-1",
            source="private_cash.csv",
            media=InMemoryMediaStore(),
            rules=None,
            scheme=SCHEME,
            sink=sink,
        )
    assert report.rejections == [], report.rejections[:3]
    assert report.rows_read == ROWS
    return monitor


def _slowed(monkeypatch: pytest.MonkeyPatch, name: str, seconds: float) -> dict[str, float]:
    """`engine.<name>` made to hold its thread for `seconds` a call; the total spent is returned."""
    real = getattr(engine, name)
    spent = {"seconds": 0.0}

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(seconds)
        spent["seconds"] += seconds
        return real(*args, **kwargs)

    monkeypatch.setattr(engine, name, slow)
    return spent


async def test_the_row_loop_yields_while_its_own_steps_are_slow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spent = _slowed(monkeypatch, "_staged_entity_to_resolved", 0.025)
    monitor = await _monitored_load(_recipe())
    assert spent["seconds"] >= 4.0, "the synthetic work was done"
    assert monitor.longest <= LIMIT, monitor.report()


async def test_the_resolve_step_runs_off_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    spent = _slowed(monkeypatch, "_resolve_row", 0.05)
    monitor = await _monitored_load(_recipe())
    assert spent["seconds"] >= 4.0, "the synthetic work was done"
    assert monitor.longest <= LIMIT, monitor.report()


async def test_the_staging_and_read_back_run_off_the_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spent = _slowed(monkeypatch, "_stage_rows", 3.0)
    _slowed(monkeypatch, "_stage_raw_rows", 3.0)
    _slowed(monkeypatch, "_read_staged_rows", 3.0)
    monitor = await _monitored_load(_recipe())
    assert spent["seconds"] >= 3.0, "the synthetic work was done"
    assert monitor.longest <= LIMIT, monitor.report()


async def test_the_row_keys_are_computed_off_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    spent = _slowed(monkeypatch, "dedup_key", 0.05)
    # With a sink the run asks the store which keys the case already kept (`kept_among`), which is
    # where the keys are first computed over every row.
    monitor = await _monitored_load(_keyed(), Sink(KeyStore(), "case-1"))
    assert spent["seconds"] >= 4.0, "the synthetic work was done"
    assert monitor.longest <= LIMIT, monitor.report()


async def test_the_published_runs_file_read_runs_off_the_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe = _recipe()
    spent = {"seconds": 0.0}

    def slow_read(draft: Any) -> list[dict[str, str]]:
        time.sleep(3.0)
        spent["seconds"] += 3.0
        return _rows()

    monkeypatch.setattr(studio_publish, "_read_recipe_rows", slow_read)
    monkeypatch.setattr(studio_publish, "load_published_recipe", lambda draft, repo_root: recipe)
    draft = SimpleNamespace(
        status=StudioRecipeStatus.PUBLISHED,
        git_path="recipes/private-cash.yaml",
        recipe_id="private-cash",
        source_location=None,
    )
    async with LoopMonitor() as monitor:
        report = await studio_publish.run_published_recipe(
            draft,  # type: ignore[arg-type]
            LOADER,
            graph=MergingGraph(ONTOLOGY),  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            load_id="load-1",
            investigation_scope="case-1",
            media=InMemoryMediaStore(),
            scheme=SCHEME,
        )
    assert report.rows_read == ROWS
    assert spent["seconds"] >= 3.0, "the synthetic work was done"
    assert monitor.longest <= LIMIT, monitor.report()
