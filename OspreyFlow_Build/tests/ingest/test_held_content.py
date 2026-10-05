"""ADR-094 step 2: content held by an entity. An entity row marks a column as document text, an
image file or a video file; the engine keeps the text or file in the media store, writes a
`Document` (`media_kind`, `object_ref`, a title) and links the entity to it by `HOLDS`. What a
mistake would do, and the case that catches it:

- a file path that reaches outside the source's own folder would read any file the loader can see
  (`test_a_path_outside_the_source_folder_rejects_the_row`);
- a missing file would be dropped with nothing said (`test_a_missing_file_is_reported_not_dropped`);
- one file held by two phones would become two Documents
  (`test_one_file_held_twice_is_one_document`);
- a file would be stored in the graph (`test_the_file_is_in_the_media_store_never_the_graph`).

The graph stand-in validates every write against the ontology (rule 15)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from services.ingest.engine import run_recipe
from services.ingest.recipe_rules import RecipeRuleError, recipe_rule_violations

from adapters.media_objectstore.testing import InMemoryMediaStore
from schemas.ingest import Recipe
from tests.ingest.test_message_content import LOADER, ONTOLOGY, RecordingGraph

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic"


def recipe(kind: str) -> Recipe:
    return Recipe.model_validate(
        {
            "id": "held",
            "version": 1,
            "label": "Phone extraction",
            "connector": {"profile": "csv"},
            "ontology_version": ONTOLOGY.version,
            "defaults": {
                "provenance": {"state": "asserted"},
                "handling": {
                    "classification": "OFFICIAL",
                    "handling_code": "P",
                    "originator": "unit-1",
                    "owning_unit": "unit-1",
                },
            },
            "row_template": {
                "entities": [
                    {
                        "ref": "phone",
                        "pole_class": "object",
                        "type": "Endpoint",
                        "match_on": "value_normalised",
                        "on_match": "reference",
                        "properties": {
                            "value_raw": {"field": "phone"},
                            "value_normalised": {"field": "phone", "transform": "msisdn"},
                            "endpoint_kind": {"literal": "msisdn"},
                        },
                        "content": {"kind": kind, "field": "item"},
                    }
                ]
            },
        }
    )


async def _run(
    kind: str, rows: list[dict[str, str]], source: Path, media: Any = None
) -> tuple[RecordingGraph, Any, InMemoryMediaStore]:
    store = media if media is not None else InMemoryMediaStore()
    graph = RecordingGraph()
    report, _ = await run_recipe(
        recipe(kind),
        iter(rows),
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        tx="tx-1",  # type: ignore[arg-type]
        principal=LOADER,
        load_id="load-1",
        investigation_scope="case-1",
        source=str(source),
        media=store,
    )
    return graph, report, store


def _documents(graph: RecordingGraph) -> list[Any]:
    return [n for n in graph.nodes if n.type == "Document"]


async def test_a_document_text_column_becomes_a_held_text_document(tmp_path: Path) -> None:
    text = "Shopping list: tape, ten bags, the blue van keys."
    graph, report, store = await _run(
        "document_text", [{"phone": "07911123456", "item": text}], tmp_path / "export.csv"
    )
    assert report.rejections == []
    (doc,) = _documents(graph)
    assert doc.properties["media_kind"] == "text"
    assert doc.properties["title"].startswith("Shopping list")
    assert await store.get(doc.properties["object_ref"]) == text.encode()
    (holds,) = [e for e in graph.edges if e.type == "HOLDS"]
    assert holds.target == doc.id


async def test_an_image_file_next_to_the_export_is_kept_and_held(tmp_path: Path) -> None:
    (tmp_path / "photos").mkdir()
    (tmp_path / "photos" / "IMG_0001.png").write_bytes(PNG)
    graph, report, store = await _run(
        "image_file",
        [{"phone": "07911123456", "item": "photos/IMG_0001.png"}],
        tmp_path / "export.csv",
    )
    assert report.rejections == []
    (doc,) = _documents(graph)
    assert (doc.properties["media_kind"], doc.properties["title"]) == ("image", "IMG_0001.png")
    assert doc.properties["object_ref"].endswith(".png")
    assert await store.get(doc.properties["object_ref"]) == PNG


async def test_the_file_is_in_the_media_store_never_the_graph(tmp_path: Path) -> None:
    (tmp_path / "IMG_0001.png").write_bytes(PNG)
    graph, _, _ = await _run(
        "image_file", [{"phone": "07911123456", "item": "IMG_0001.png"}], tmp_path / "export.csv"
    )
    for node in graph.nodes:
        assert all(
            not isinstance(v, bytes) and PNG.decode("latin-1") not in str(v)
            for v in node.properties.values()
        )


@pytest.mark.parametrize("path", ["../secret.png", "/etc/passwd.png", "photos/../../x.png"])
async def test_a_path_outside_the_source_folder_rejects_the_row(tmp_path: Path, path: str) -> None:
    graph, report, store = await _run(
        "image_file", [{"phone": "07911123456", "item": path}], tmp_path / "export.csv"
    )
    (rejection,) = report.rejections
    assert "outside" in rejection.reason
    assert graph.nodes == [] and store.files == {}


async def test_a_file_of_the_wrong_kind_rejects_the_row(tmp_path: Path) -> None:
    (tmp_path / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    _, report, _ = await _run(
        "image_file", [{"phone": "07911123456", "item": "clip.mp4"}], tmp_path / "export.csv"
    )
    (rejection,) = report.rejections
    assert "image" in rejection.reason


async def test_a_missing_file_is_reported_not_dropped(tmp_path: Path) -> None:
    graph, report, _ = await _run(
        "image_file", [{"phone": "07911123456", "item": "gone.png"}], tmp_path / "export.csv"
    )
    (rejection,) = report.rejections
    assert "gone.png" in rejection.reason and "not found" in rejection.reason
    assert [n.type for n in graph.nodes] == ["Endpoint"]  # the phone is loaded, without the file


async def test_one_file_held_twice_is_one_document(tmp_path: Path) -> None:
    (tmp_path / "IMG_0001.png").write_bytes(PNG)
    graph, _, _ = await _run(
        "image_file",
        [
            {"phone": "07911123456", "item": "IMG_0001.png"},
            {"phone": "07912345678", "item": "IMG_0001.png"},
        ],
        tmp_path / "export.csv",
    )
    assert len({d.id for d in _documents(graph)}) == 1
    assert len([e for e in graph.edges if e.type == "HOLDS"]) == 2


async def test_held_content_without_a_media_store_is_refused_before_anything_is_written(
    tmp_path: Path,
) -> None:
    with pytest.raises(RecipeRuleError, match="media store"):
        await run_recipe(
            recipe("image_file"),
            iter([{"phone": "07911123456", "item": "IMG.png"}]),
            graph=RecordingGraph(),  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            tx="tx-1",  # type: ignore[arg-type]
            principal=LOADER,
            load_id="load-1",
            investigation_scope="case-1",
            source=str(tmp_path / "export.csv"),
        )


def test_a_link_cannot_carry_a_file() -> None:
    edge_recipe = Recipe.model_validate(
        {
            **recipe("document_text").model_dump(by_alias=True),
            "row_template": {
                "entities": [
                    {"ref": "a", "pole_class": "object", "type": "Endpoint", "properties": {}},
                    {"ref": "b", "pole_class": "object", "type": "Endpoint", "properties": {}},
                ],
                "edges": [
                    {
                        "type": "COMMUNICATED_WITH",
                        "from": "a",
                        "to": "b",
                        "temporal": {"at": {"field": "t"}},
                        "content": {"kind": "image_file", "field": "item"},
                    }
                ],
            },
        }
    )
    (problem,) = recipe_rule_violations(edge_recipe.row_template, ONTOLOGY)
    assert "file" in problem
