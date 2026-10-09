"""A place loaded through the Ingest Studio is on the map (found 9 October 2026).

A `Location` holds a `geometry_ref`, never its coordinates (`03_CONDUIT_MIDDLEWARE.md` §5.1); the
point itself is a row in the analytics store's geometry partition. The recipe engine computes the
ref and writes nothing else, and nothing after a Studio run wrote the row either, so a cell site
loaded through the Studio carried a ref that resolved to nothing and the map stayed empty however
the recipe was written. The site grid's draw route was the only writer of the partition.

These run the cell-site layout (`connectors/cell-site-csv.yaml`, `source_crs: EPSG:4326`) as a
published recipe against a synthetic three-mast export.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.api.studio_profile import connector_for
from services.api.studio_publish import run_published_recipe
from services.ingest.geometries import point_geometries
from services.ingest.recipe_loader import load_recipe

from knowledge_adapters import REGISTRY
from ontology.loader import load_default_ontology
from schemas.analytics import EventRecord, GeometryRecord
from schemas.domain import Principal
from schemas.ingest import (
    FieldBinding,
    Recipe,
    RecipeConnector,
    RecipeDefaults,
    RecipeEntity,
    RowTemplate,
    StudioRecipeDraft,
    StudioRecipeStatus,
)
from tests.ingest.test_message_content import LOADER
from tests.ingest.test_studio_run_events import TransactionalGraph

ONTOLOGY = load_default_ontology()
MASTS = [
    ("MCR-001", "Piccadilly mast", "-2.2309", "53.4776"),
    ("MCR-002", "Deansgate mast", "-2.2507", "53.4794"),
    ("MCR-003", "Salford Quays mast", "-2.2854", "53.4713"),
]
HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}


def _recipe(source_crs: str | None = "EPSG:4326") -> Recipe:
    return Recipe(
        id="cell-sites",
        version=1,
        label="Cell sites",
        connector=RecipeConnector(profile="cell-site-csv", source_crs=source_crs),
        ontology_version=ONTOLOGY.version,
        defaults=RecipeDefaults(handling=HANDLING, provenance={}),
        row_template=RowTemplate(
            entities=[
                RecipeEntity(
                    ref="site",
                    pole_class="location",
                    type="Location",
                    match_on="site_ref",
                    on_match="reference",
                    properties={
                        "site_ref": FieldBinding(field="cell_id"),
                        "name": FieldBinding(field="site_name"),
                        "geometry_ref": FieldBinding(
                            fields=["longitude", "latitude"], transform="geometry_ref"
                        ),
                    },
                )
            ]
        ),
    )


def _rows() -> list[dict[str, str]]:
    keys = ("cell_id", "site_name", "longitude", "latitude")
    return [dict(zip(keys, mast, strict=True)) for mast in MASTS]


class RecordingAnalytics:
    def __init__(self, already: list[GeometryRecord] | None = None) -> None:
        self.events: list[EventRecord] = []
        self.geometries: list[GeometryRecord] = list(already or [])
        self.loads: list[list[GeometryRecord]] = []

    async def load_events(self, records: list[EventRecord]) -> None:
        self.events.extend(records)

    async def get_geometries(
        self, refs: list[str], principal: Principal, *, version: int | None = None
    ) -> list[GeometryRecord]:
        return [g for g in self.geometries if g.geometry_ref in refs]

    async def load_geometries(self, records: list[GeometryRecord]) -> None:
        # The partition's key is (geometry_ref, version): a second insert of a ref fails.
        held = {(g.geometry_ref, g.version) for g in self.geometries}
        assert not any((r.geometry_ref, r.version) in held for r in records), "duplicate insert"
        self.loads.append(list(records))
        self.geometries.extend(records)


def test_the_cell_site_layout_declares_its_coordinate_system() -> None:
    draft = _draft(Path("unused.csv"))
    assert connector_for(draft).source_crs == "EPSG:4326"


def test_each_mast_is_a_point_under_the_ref_its_location_carries() -> None:
    to_ref = REGISTRY["geometry_ref"]
    records = point_geometries(_recipe(), _rows())
    assert [(r.lon, r.lat) for r in records] == [
        (float(lon), float(lat)) for _, _, lon, lat in MASTS
    ]
    assert [r.geometry_ref for r in records] == [
        to_ref((lon, lat), source_crs="EPSG:4326") for _, _, lon, lat in MASTS
    ]
    assert {r.handling.classification for r in records} == {"OFFICIAL"}
    assert {(r.source_crs, r.version) for r in records} == {("EPSG:4326", 1)}


def test_a_row_whose_coordinates_do_not_read_gives_no_point() -> None:
    rows = _rows()
    rows[1]["latitude"] = "north-ish"
    assert len(point_geometries(_recipe(), rows)) == 2


def test_a_source_with_no_declared_coordinate_system_gives_no_point() -> None:
    assert point_geometries(_recipe(source_crs=None), _rows()) == []


def _draft(source: Path) -> StudioRecipeDraft:
    return StudioRecipeDraft(
        recipe_id="cell-sites",
        version=1,
        status=StudioRecipeStatus.PUBLISHED,
        label="Cell sites",
        connector_profile="cell-site-csv",
        source_location=str(source),
        owning_unit="unit-1",
        created_by="analyst-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        git_path="recipes/cell-sites.yaml",
    )


async def _run(tmp_path: Path, analytics: RecordingAnalytics) -> None:
    repo = tmp_path / "repo"
    (repo / "recipes").mkdir(parents=True, exist_ok=True)
    recipe_path = repo / "recipes" / "cell-sites.yaml"
    recipe_path.write_text(_recipe().model_dump_json(by_alias=True), encoding="utf-8")
    assert load_recipe(recipe_path).connector.source_crs == "EPSG:4326"
    source = tmp_path / "cell-sites.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_rows()[0]))
        writer.writeheader()
        writer.writerows(_rows())
    kwargs: dict[str, Any] = {"analytics": analytics}
    report = await run_published_recipe(
        _draft(source),
        LOADER,
        graph=TransactionalGraph(),  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id="load-1",
        investigation_scope="case-1",
        repo_root=repo,
        **kwargs,
    )
    assert report.rejections == []


async def test_a_studio_run_puts_its_places_on_the_map(tmp_path: Path) -> None:
    analytics = RecordingAnalytics()
    await _run(tmp_path, analytics)
    assert len(analytics.geometries) == len(MASTS)


async def test_running_the_same_places_again_loads_no_second_copy(tmp_path: Path) -> None:
    analytics = RecordingAnalytics()
    await _run(tmp_path, analytics)
    await _run(tmp_path, analytics)
    assert len(analytics.geometries) == len(MASTS)
