"""Generates `data.json` for the throwaway Map-screen prototype by calling
the REAL headless recipe engine (`services/ingest/engine.py`) against the
REAL CDR fixture (`packages/demo_fixtures/cdr.py`) — ADR-018: "a
throwaway front end over a real recipe and a real fixture", not mocked-up
data shaped to look convincing.

Run from the repository root:

    PYTHONPATH=packages python3 prototypes/ingest-map/generate_data.py

Regenerate whenever the CDR recipe or fixture changes; `data.json` is
committed so the prototype works without a Python environment to view it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))
sys.path.insert(0, str(REPO_ROOT))

from services.ingest.engine import resolve_rows  # noqa: E402
from services.ingest.recipe_loader import load_recipe  # noqa: E402

from demo_fixtures.cdr import generate_cdr_rows  # noqa: E402

RECIPE_PATH = REPO_ROOT / "tests" / "scenarios" / "fixtures" / "cdr_recipe.yaml"
OUTPUT_PATH = Path(__file__).resolve().parent / "data.json"


def main() -> None:
    recipe = load_recipe(RECIPE_PATH)
    rows = generate_cdr_rows()

    staged_rows, rejections, rows_read, rows_deduplicated = resolve_rows(
        recipe, rows, load_id="prototype-load", source="cdr.csv"
    )

    # Map every original row index back to what happened to it, so the
    # prototype can page through the real source file row by row rather
    # than only showing survivors.
    by_index: dict[int, dict[str, object]] = {}
    for staged in staged_rows:
        by_index[staged.row_index] = {
            "row_index": staged.row_index,
            "status": "loaded",
            "entities": [
                {"ref": e.ref, "type": e.type, "properties": e.properties}
                for e in staged.entities
            ],
            "edges": [
                {
                    "type": e.type,
                    "from": e.from_ref,
                    "to": e.to_ref,
                    "properties": e.properties,
                    "instant": e.instant.isoformat() if e.instant else None,
                }
                for e in staged.edges
            ],
        }
        for dup_index in staged.duplicate_row_indices:
            by_index[dup_index] = {
                "row_index": dup_index,
                "status": "duplicate",
                "duplicate_of": staged.row_index,
            }
    for rejection in rejections:
        by_index[rejection.row_index] = {
            "row_index": rejection.row_index,
            "status": "rejected",
            "reason": rejection.reason,
        }

    row_views = [
        {**by_index[i], "raw": rows[i]}
        for i in range(len(rows))
        if i in by_index
    ]

    data = {
        "recipe": {
            "id": recipe.id,
            "version": recipe.version,
            "label": recipe.label,
            "ontology_version": recipe.ontology_version,
            "connector": recipe.connector.model_dump(),
            "entities": [
                e.model_dump(by_alias=False) for e in recipe.row_template.entities
            ],
            "edges": [e.model_dump(by_alias=True) for e in recipe.row_template.edges],
        },
        "unmapped_fields": [f.model_dump() for f in recipe.unmapped_fields],
        "source_columns": list(rows[0].keys()) if rows else [],
        "summary": {
            "rows_read": rows_read,
            "rows_deduplicated": rows_deduplicated,
            "rejections": len(rejections),
        },
        "rows": row_views,
    }

    OUTPUT_PATH.write_text(json.dumps(data, indent=2))
    print(f"Wrote {OUTPUT_PATH} ({len(row_views)} rows)")


if __name__ == "__main__":
    main()
