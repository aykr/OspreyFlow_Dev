"""ADR-127 Amendment 29 (B2-9b), against the real ArcadeDB: a run whose rows take 20 seconds of
synchronous work in total, with no graph call between, commits.

**Live, slow, and outside `make ci`.** It needs the dev stack's ArcadeDB and skips unless
`OSPREYFLOW_RUN_SLOW=1`. Rule 14: run it with nothing else using the stack.

The run opens its transaction, then resolves its rows (20 of them, a second each, so no graph call
for 20 s). ArcadeDB's session lives 5 to 10 seconds without a call, so only the keep-alive (an
asyncio task) can keep it, and it runs only if the run lets the loop turn. Before the change the run
held the loop and the commit failed with "Remote transaction session not found or expired". What it
would catch: any step of a run that holds the event loop for longer than the session's life.
"""

from __future__ import annotations

import os
import time
from typing import Any

import pytest
from services.api.studio_publish import load_with_rules
from services.ingest import engine

from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from schemas.domain import Principal
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_load_record_created_and_merged import (
    LOADER,
    ONTOLOGY,
    SCHEME,
    _recipe,
)
from tests.ingest.test_run_yields_the_loop import _rows

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("OSPREYFLOW_RUN_SLOW"),
        reason="holds a real transaction open for 20 s: set OSPREYFLOW_RUN_SLOW=1",
    ),
]

ROWS = 20
SECONDS_A_ROW = 1.0


async def test_a_run_with_twenty_seconds_of_synchronous_work_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = engine._resolve_row
    spent = {"seconds": 0.0}

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(SECONDS_A_ROW)
        spent["seconds"] += SECONDS_A_ROW
        return real(*args, **kwargs)

    monkeypatch.setattr(engine, "_resolve_row", slow)
    rows = _rows()[:ROWS]
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        report, _events, _held = await load_with_rules(
            _recipe(),
            rows,
            LOADER,
            graph=graph,
            ontology=ONTOLOGY,
            load_id="load-long",
            investigation_scope="case-1",
            source="private_cash.csv",
            media=InMemoryMediaStore(),
            rules=None,
            scheme=SCHEME,
        )
        assert spent["seconds"] >= 20.0, "the synthetic work was done"
        assert report.rejections == [], report.rejections[:3]
        reader = Principal(id="reader", clearance="SECRET", org_unit=LOADER.org_unit)
        stored = await graph.get_nodes(report.created_node_ids, reader)
        assert len(report.created_node_ids) == 2 * ROWS
        assert len(stored) == len(report.created_node_ids), (
            "the run committed: its nodes are stored"
        )
