"""A load report's `edges_created` is the links a load created, not the writes it made.

9 October 2026, the data engineer's journey: the Studio's Carrier B load reported "Edges created:
236" while the store held 141 links from it — exactly what Verify had predicted, because a second
call between the same two numbers merges into the first link (`upsert_edges`, ADR-052). The report
counted every edge write (`state.edges_written`), so it disagreed with both the store and Verify.

Against a live ArcadeDB, like `test_recipe_engine_end_to_end.py`: the merge being counted is the
adapter's own.
"""

from __future__ import annotations

import csv
from pathlib import Path

from services.ingest.connectors.csv_connector import read_csv
from services.ingest.engine import dry_run_recipe, run_recipe
from services.ingest.recipe_loader import load_recipe

from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal

FIXTURES = Path(__file__).resolve().parents[1] / "scenarios" / "fixtures"
CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _call(seq: int, b_party: str, day: int) -> dict[str, str]:
    return {
        "seq": str(seq), "a_party": "07700900461", "b_party": b_party,
        "start_time": f"2026-01-{day:02d}T10:00:00Z", "duration": "30", "direction": "O",
    }  # fmt: skip


# Three calls A→B at different times (no duplicates) and one A→C: two links.
_ROWS = [
    _call(1, "07700900462", 10),
    _call(2, "07700900462", 11),
    _call(3, "07700900462", 12),
    _call(4, "07700900463", 13),
]


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "calls.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_ROWS[0]))
        writer.writeheader()
        writer.writerows(_ROWS)
    return path


async def test_a_load_reports_the_links_it_created_as_verify_and_the_store_do(
    tmp_path: Path,
) -> None:
    csv_path = _write(tmp_path)
    recipe = load_recipe(FIXTURES / "cdr_recipe.yaml")
    ontology = load_default_ontology()
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        dry = await dry_run_recipe(
            recipe, read_csv(csv_path), graph=graph, ontology=ontology, principal=CLEARED,
            source=str(csv_path),
        )
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe, read_csv(csv_path), graph=graph, ontology=ontology, tx=tx, principal=CLEARED,
            load_id="load-1", investigation_scope="case-links", source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert dry.edges_by_type["COMMUNICATED_WITH"].created == 2
        assert report.edges_created == 2, "two links: three calls A→B merge into one"
        assert len(set(report.touched_edge_ids)) == 2

        # The same file again creates no link: each write merges into one the first load made.
        tx = await graph.begin_transaction()
        again, _ = await run_recipe(
            recipe, read_csv(csv_path), graph=graph, ontology=ontology, tx=tx, principal=CLEARED,
            load_id="load-2", investigation_scope="case-links", source=str(csv_path),
        )
        await graph.commit_transaction(tx)
        assert again.edges_created == 0
        assert again.nodes_created == 0
