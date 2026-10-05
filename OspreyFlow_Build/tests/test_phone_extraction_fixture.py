"""The synthetic phone extraction (ADR-094 step 3): its export, its media, and its load through the
recipe the Studio would build. The media is made by ffmpeg and `say` where they are present."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest
from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe

from adapters.media_objectstore.testing import InMemoryMediaStore
from demo_fixtures.phone_extraction import FIELDS, write_phone_extraction
from tests.ingest.test_message_content import LOADER, ONTOLOGY, RecordingGraph

RECIPE = Path(__file__).resolve().parent / "scenarios" / "fixtures" / "phone_extraction_recipe.yaml"


def test_without_the_tools_the_rows_are_written_and_what_was_left_out_is_said(
    tmp_path: Path,
) -> None:
    path, missing = write_phone_extraction(tmp_path, ffmpeg="", say="")
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    assert tuple(rows[0]) == FIELDS
    assert all(r["photo"] == "" and r["video"] == "" for r in rows)
    assert any("IMG_0001.png" in m and "ffmpeg" in m for m in missing)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg makes the media")
async def test_the_extraction_loads_as_documents_held_by_the_phones(tmp_path: Path) -> None:
    path, _ = write_phone_extraction(tmp_path)
    assert (path.parent / "IMG_0001.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (path.parent / "VID_0001.mp4").read_bytes()[4:8] == b"ftyp"
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
