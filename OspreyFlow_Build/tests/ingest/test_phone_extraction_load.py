"""The synthetic phone extraction (ADR-094 step 3) loads, through the recipe the Studio would build, as documents
held by the phones. A live test: `run_recipe` stages the raw rows in the object store (services/ingest/staging.py,
`stage_raw_rows`), so it runs where a store is up (this folder is in the Makefile's live set and CI's conformance
job), never in the offline `make test`. Until 18 November 2026 it sat in the offline suite behind an ffmpeg skip: CI's
runner has no ffmpeg so it skipped, and on a Mac with ffmpeg it failed at the closed object store (59995). The media
it loads is made by ffmpeg (tests/test_phone_extraction_fixture.py checks the media offline)."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest
from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe

from adapters.media_objectstore.testing import InMemoryMediaStore
from demo_fixtures.phone_extraction import write_phone_extraction
from tests.ingest.test_message_content import LOADER, ONTOLOGY, RecordingGraph

pytestmark = pytest.mark.store

RECIPE = Path(__file__).resolve().parents[1] / "scenarios" / "fixtures" / "phone_extraction_recipe.yaml"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg makes the media")
async def test_the_extraction_loads_as_documents_held_by_the_phones(tmp_path: Path) -> None:
    path, _ = write_phone_extraction(tmp_path)
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    media = InMemoryMediaStore()
    graph = RecordingGraph()
    report, _ = await run_recipe(
        load_recipe(RECIPE),
        iter(rows),
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        tx="tx-1",  # type: ignore[arg-type]
        principal=LOADER,
        load_id="load-1",
        investigation_scope="case-1",
        source=str(path),
        media=media,
    )
    assert report.rejections == []
    kinds = sorted(n.properties["media_kind"] for n in graph.nodes if n.type == "Document")
    assert kinds == ["image", "image", "text", "text", "video"]
    assert len([e for e in graph.edges if e.type == "HOLDS"]) == 5
