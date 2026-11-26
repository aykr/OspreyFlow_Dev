"""SE9e (the owner, 26 November 2026, 12:40 UTC, option (a)): no recipe sets `object_ref` or
`media_kind` on a `Document`, from a column or as a fixed value; only the engine's own writes set
them. A media reference is content-addressed and nothing records which dataset stored it, so a bound
one could name a file stored for another dataset, which the file route would then serve to whoever
may read the new `Document`, at the loader's marking. What a mistake would do, and the case that
catches it:

- a `Document` with no content block binding `object_ref` saved, published and run (case 1);
- the load trusting that the validation saw every such recipe, so one that gets past it writes
  another dataset's file onto a `Document` (case 2; the validation is taken out of the run's path
  here, at the engine's own call of it);
- a binding let through because the file happens to be this dataset's own (case 3);
- the load's refusal applied to what the engine itself writes, so a `Document` holding its own text,
  or held content, no longer loads (case 4);
- a refusal that names the file, its dataset or its marking, or that reads differently for a file
  that exists, so the words say what the loader may not read (case 5, rule 3).

The run is the engine's own (`run_recipe`, `dry_run_recipe`) against a graph stand-in that refuses
what the ArcadeDB adapter refuses (rule 15). The load against a real store is the server's and the
merge's live step's."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from services.ingest import engine
from services.ingest.engine import dry_run_recipe, run_recipe
from services.ingest.recipe_rules import (
    RecipeRuleError,
    check_recipe_rules,
    recipe_rule_violations,
)

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.ingest import Recipe
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    ValidatingGraph,
    local_staging,
)

ONTOLOGY = load_default_ontology()
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-a")
NAMES = ["object_ref", "media_kind"]
OTHERS_TEXT = "Text another dataset stored, which this one was never given."
OWN_TEXT = "Text this dataset itself stored in an earlier load."
PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic"


def words(ref: str, name: str) -> str:
    """The whole refusal: the recipe entity's ref and the property, and nothing else that varies."""
    return (
        f"{ref!r} is a Document, whose {name!r} the engine alone sets, for its own text or a file "
        "it stores: a pipeline cannot set it, from a column or as a fixed value."
    )


def _recipe(
    entities: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    *,
    recipe_id: str = "dataset-a",
    classification: str = "OFFICIAL",
    unit: str = "unit-a",
) -> Recipe:
    return Recipe.model_validate(
        {
            "id": recipe_id,
            "version": 1,
            "label": recipe_id,
            "connector": {"profile": "csv"},
            "ontology_version": ONTOLOGY.version,
            "pack_versions": {},
            "defaults": {
                "provenance": {"state": "asserted"},
                "handling": {
                    "classification": classification,
                    "handling_code": "P",
                    "originator": unit,
                    "owning_unit": unit,
                },
            },
            "row_template": {"entities": entities, "edges": edges or []},
        }
    )


def _document(content: str | None = None, **properties: Any) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "ref": "doc",
        "pole_class": "object",
        "type": "Document",
        "properties": {"title": {"field": "title"}, **properties},
    }
    if content is not None:
        entity["content"] = {"kind": content, "field": "text"}
    return entity


#: Written before the Document on each row, so a refusal that comes only at the Document's own write
#: would leave this one behind.
AREA: dict[str, Any] = {
    "ref": "area",
    "pole_class": "location",
    "type": "Location",
    "properties": {"site_ref": {"field": "area"}},
}
MENTION: dict[str, Any] = {"type": "MENTIONED_IN", "from": "area", "to": "doc"}


def _binding_recipe(name: str, binding: dict[str, Any], content: str | None = None) -> Recipe:
    return _recipe([AREA, _document(content, **{name: binding})], [MENTION])


def _row(value: str) -> dict[str, str]:
    return {"area": "site-1", "title": "A row", "text": "Some text.", "file": value}


async def _run(
    graph: ValidatingGraph,
    recipe: Recipe,
    rows: list[dict[str, str]],
    media: InMemoryMediaStore,
    *,
    load_id: str = "load-1",
    source: str = "export.csv",
) -> Any:
    report, _events = await run_recipe(
        recipe,
        rows,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        tx=await graph.begin_transaction(),  # type: ignore[arg-type]
        principal=LOADER,
        load_id=load_id,
        investigation_scope="case-1",
        source=source,
        media=media,
    )
    return report


async def _stored_for(
    recipe_id: str, text: str, *, classification: str = "OFFICIAL", unit: str = "unit-a"
) -> tuple[ValidatingGraph, InMemoryMediaStore, str]:
    """A file a dataset really stored: its own load of a Document holding its own text. Returns the
    graph and the store as that load left them, and the reference the engine wrote."""
    graph, media = ValidatingGraph(ONTOLOGY), InMemoryMediaStore()
    recipe = _recipe(
        [_document("document_text")],
        recipe_id=recipe_id,
        classification=classification,
        unit=unit,
    )
    report = await _run(graph, recipe, [{"title": "Stored", "text": text}], media, load_id="first")
    assert report.rejections == []
    await graph.commit_transaction("tx-1")
    (document,) = graph.committed_nodes
    return graph, media, str(document.properties["object_ref"])


async def _others_file() -> tuple[ValidatingGraph, InMemoryMediaStore, str]:
    return await _stored_for("dataset-b", OTHERS_TEXT, classification="SECRET", unit="unit-b")


def _unseen_by_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The planted case: a recipe the run's validation does not see, at the engine's own call."""
    monkeypatch.setattr(engine, "check_recipe_rules", lambda *args, **kwargs: None)


def _bindings(value: str) -> dict[str, dict[str, Any]]:
    return {
        "column": {"field": "file"},
        "optional column": {"field": "file", "optional": True},
        "fixed value": {"literal": value},
    }


KINDS = ["column", "optional column", "fixed value"]


def _value(name: str, ref: str) -> str:
    return ref if name == "object_ref" else "text"


# --- case 1: refused at recipe validation ------------------------------------------------------


@pytest.mark.parametrize("complete", [True, False], ids=["publish", "map-save"])
@pytest.mark.parametrize("content", [None, "document_text"], ids=["no-content", "own-text"])
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("name", NAMES)
def test_case1_a_binding_on_a_document_is_refused_at_validation(
    name: str, kind: str, content: str | None, complete: bool
) -> None:
    binding = _bindings(_value(name, f"media/{'a' * 64}.txt"))[kind]
    template = _binding_recipe(name, binding, content).row_template
    assert recipe_rule_violations(template, ONTOLOGY, complete=complete) == [words("doc", name)]
    with pytest.raises(RecipeRuleError) as refused:
        check_recipe_rules(template, ONTOLOGY, complete=complete)
    assert refused.value.problems == [words("doc", name)]


def test_case1_a_document_looked_up_by_reference_may_not_bind_either() -> None:
    document = _document(object_ref={"field": "file"}, media_kind={"literal": "image"})
    document |= {"match_on": "title", "on_match": "reference"}
    template = _recipe([document]).row_template
    problems = recipe_rule_violations(template, ONTOLOGY)
    assert [p for p in problems if "engine alone sets" in p] == [
        words("doc", "object_ref"),
        words("doc", "media_kind"),
    ]


def test_case1_a_document_binding_neither_is_not_refused() -> None:
    assert (
        recipe_rule_violations(_recipe([AREA, _document()], [MENTION]).row_template, ONTOLOGY) == []
    )


@pytest.mark.parametrize("name", NAMES)
async def test_case1_the_run_refuses_the_recipe_whole_before_anything_is_written(name: str) -> None:
    _, media, ref = await _others_file()
    graph, kept = ValidatingGraph(ONTOLOGY), dict(media.files)
    recipe = _binding_recipe(name, {"field": "file"})
    with pytest.raises(RecipeRuleError) as refused:
        await _run(graph, recipe, [_row(_value(name, ref))], media)
    assert refused.value.problems == [words("doc", name)]
    assert graph.open_nodes == [] and graph.open_edges == []
    assert media.files == kept


# --- case 2: refused at load, whatever the validation saw --------------------------------------


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("name", NAMES)
async def test_case2_the_load_refuses_another_datasets_file_and_writes_nothing_of_the_row(
    name: str, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, media, ref = await _others_file()
    graph, kept = ValidatingGraph(ONTOLOGY), dict(media.files)
    recipe = _binding_recipe(name, _bindings(_value(name, ref))[kind])
    _unseen_by_validation(monkeypatch)
    report = await _run(graph, recipe, [_row(_value(name, ref))], media)
    assert graph.open_nodes == [] and graph.open_edges == [], "something of the row was written"
    assert (report.nodes_created, report.nodes_referenced, report.edges_created) == (0, 0, 0)
    assert [r.reason for r in report.rejections] == [words("doc", name)]
    assert media.files == kept


async def test_case2_an_empty_optional_cell_does_not_let_the_binding_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = ValidatingGraph(ONTOLOGY)
    recipe = _binding_recipe("object_ref", {"field": "file", "optional": True})
    _unseen_by_validation(monkeypatch)
    report = await _run(graph, recipe, [_row("")], InMemoryMediaStore())
    assert graph.open_nodes == [] and graph.open_edges == []
    assert [r.reason for r in report.rejections] == [words("doc", "object_ref")]


async def test_case2_test_refuses_the_row_as_the_load_does() -> None:
    """Test (`dry_run_recipe`) makes no recipe-rule check of its own: only the load's check is in
    its path."""
    _, _, ref = await _others_file()
    result = await dry_run_recipe(
        _binding_recipe("object_ref", {"field": "file"}),
        [_row(ref)],
        graph=ValidatingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        principal=LOADER,
        source="export.csv",
    )
    assert result.nodes == [] and result.edges == []
    assert [r.reason for r in result.rejections] == [words("doc", "object_ref")]


# --- case 3: this dataset's own file is refused too (a) ----------------------------------------


@pytest.mark.parametrize("kind", KINDS)
async def test_case3_this_datasets_own_file_is_refused_at_validation_and_at_load(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, media, ref = await _stored_for("dataset-a", OWN_TEXT)
    stored, kept = list(graph.committed_nodes), dict(media.files)
    recipe = _binding_recipe("object_ref", _bindings(ref)[kind])
    assert recipe_rule_violations(recipe.row_template, ONTOLOGY) == [words("doc", "object_ref")]
    with pytest.raises(RecipeRuleError):
        await _run(graph, recipe, [_row(ref)], media, load_id="second")
    _unseen_by_validation(monkeypatch)
    report = await _run(graph, recipe, [_row(ref)], media, load_id="third")
    assert [r.reason for r in report.rejections] == [words("doc", "object_ref")]
    assert graph.open_nodes == [] and graph.open_edges == []
    assert graph.committed_nodes == stored and media.files == kept


# --- case 4: what the engine itself writes is unchanged ----------------------------------------


async def test_case4_a_document_holding_its_own_text_still_gets_both_from_the_engine() -> None:
    graph, media = ValidatingGraph(ONTOLOGY), InMemoryMediaStore()
    recipe = _recipe([AREA, _document("document_text")], [MENTION])
    assert recipe_rule_violations(recipe.row_template, ONTOLOGY) == []
    report = await _run(graph, recipe, [_row("")], media)
    assert report.rejections == []
    (document,) = [n for n in graph.open_nodes if n.type == "Document"]
    assert document.properties["media_kind"] == "text"
    assert await media.get(str(document.properties["object_ref"])) == b"Some text."


@pytest.mark.parametrize(
    ("kind", "item", "media_kind", "data"),
    [
        ("document_text", "A saved note.", "text", b"A saved note."),
        ("image_file", "photo.png", "image", PNG),
    ],
)
async def test_case4_held_content_still_gets_a_document_naming_its_file(
    kind: str, item: str, media_kind: str, data: bytes, tmp_path: Path
) -> None:
    (tmp_path / "photo.png").write_bytes(PNG)
    graph, media = ValidatingGraph(ONTOLOGY), InMemoryMediaStore()
    recipe = _recipe(
        [
            {
                "ref": "holder",
                "pole_class": "person",
                "type": "Person",
                "properties": {"family_name": {"literal": "Synthetic"}},
                "content": {"kind": kind, "field": "item"},
            }
        ]
    )
    assert recipe_rule_violations(recipe.row_template, ONTOLOGY) == []
    report = await _run(graph, recipe, [{"item": item}], media, source=str(tmp_path / "export.csv"))
    assert report.rejections == []
    (document,) = [n for n in graph.open_nodes if n.type == "Document"]
    assert document.properties["media_kind"] == media_kind
    assert await media.get(str(document.properties["object_ref"])) == data


# --- case 5: the words name the entity and the property only (rule 3) --------------------------


async def test_case5_the_words_are_the_same_whatever_file_is_named_and_say_nothing_of_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, media, others = await _others_file()
    _, _, own = await _stored_for("dataset-a", OWN_TEXT)
    nowhere = f"media/{'0' * 64}.txt"
    _unseen_by_validation(monkeypatch)
    said: set[str] = set()
    for ref in (others, own, nowhere):
        recipe = _binding_recipe("object_ref", {"literal": ref})
        said.update(recipe_rule_violations(recipe.row_template, ONTOLOGY))
        report = await _run(ValidatingGraph(ONTOLOGY), recipe, [_row(ref)], media)
        said.update(r.reason for r in report.rejections)
    assert said == {words("doc", "object_ref")}
    for hidden in (others, others.split("/")[1].split(".")[0], "SECRET", "unit-b", "dataset-b"):
        assert not any(hidden in sentence for sentence in said)


async def test_case5_a_row_binding_both_is_told_each_property_and_no_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, media, ref = await _others_file()
    recipe = _recipe([_document(object_ref={"field": "file"}, media_kind={"literal": "video"})])
    _unseen_by_validation(monkeypatch)
    report = await _run(ValidatingGraph(ONTOLOGY), recipe, [_row(ref)], media)
    assert [r.reason for r in report.rejections] == [
        f"{words('doc', 'object_ref')}; {words('doc', 'media_kind')}"
    ]
