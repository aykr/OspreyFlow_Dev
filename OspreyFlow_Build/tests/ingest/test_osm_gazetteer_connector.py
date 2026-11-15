"""The OSM-derived gazetteer connector — `spec/00_ARCHITECTURE.md` §1.2,
`pbf_wire.py`'s own varint/zigzag
round-trip is exercised implicitly by every test here (the synthetic
fixture is encoded with it, the connector decodes with it) rather than in
a separate unit test — the two directions have no meaning apart from each
other on a format neither side invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from services.ingest.connectors.geo.osm import read_osm_places
from services.ingest.connectors.geo.osm_pbf import read_osm_pbf

from tests.scenarios.fixtures.osm_extract import build_synthetic_osm_pbf


@pytest.fixture
def synthetic_pbf(tmp_path: Path) -> Path:
    path = tmp_path / "extract.osm.pbf"
    build_synthetic_osm_pbf(path)
    return path


def test_read_osm_pbf_decodes_every_dense_node_including_the_unnamed_one(
    synthetic_pbf: Path,
) -> None:
    nodes = list(read_osm_pbf(str(synthetic_pbf)))
    assert len(nodes) == 4  # three named places plus the one unnamed node

    cranford = next(n for n in nodes if n.tags.get("name") == "Cranford")
    assert cranford.tags["place"] == "hamlet"
    assert cranford.lat == pytest.approx(51.4880, abs=1e-4)
    assert cranford.lon == pytest.approx(-0.4590, abs=1e-4)

    unnamed = next(n for n in nodes if not n.tags)
    assert unnamed.lat == pytest.approx(52.0, abs=1e-4)


def test_read_osm_places_yields_settlements_only(tmp_path: Path) -> None:
    """The owner's ruling, 15 November 2026: the gazetteer carries settlements only, `place=*`
    nodes such as cities, towns, villages and hamlets, not every named point (about 900,000 for
    Great Britain). A named cafe, a farm, an island, a locality and a square are left out; so is a
    settlement with no name."""
    path = tmp_path / "mixed.osm.pbf"
    build_synthetic_osm_pbf(path, places=[
        ("Bigtown", "place", "city", 51.50, -0.12), ("Smalltown", "place", "town", 51.6, -0.2),
        ("Midvillage", "place", "village", 51.7, -0.3), ("Fewhouses", "place", "hamlet", 51.8, -0.4),
        ("Lonecottage", "place", "isolated_dwelling", 51.9, -0.5),
        ("Northside", "place", "suburb", 51.51, -0.13), ("Oldquarter", "place", "quarter", 51.52, -0.14),
        ("Greenrow", "place", "neighbourhood", 51.53, -0.15),
        ("The Anchor", "amenity", "cafe", 51.5074, -0.1278),
        ("Hill Farm", "place", "farm", 52.0, -1.1), ("Eel Island", "place", "island", 52.1, -1.2),
        ("Black Moss", "place", "locality", 52.2, -1.3), ("Market Square", "place", "square", 52.3, -1.4),
    ])  # fmt: skip
    names = {r["name"] for r in read_osm_places(str(path))}
    assert names == {"Bigtown", "Smalltown", "Midvillage", "Fewhouses", "Lonecottage", "Northside",
                     "Oldquarter", "Greenrow"}  # fmt: skip


def test_read_osm_places_excludes_the_unnamed_node(synthetic_pbf: Path) -> None:
    rows = list(read_osm_places(str(synthetic_pbf)))
    assert len(rows) == 3


def test_read_osm_places_rows_carry_string_coordinates_for_the_recipe_engine(
    synthetic_pbf: Path,
) -> None:
    rows = list(read_osm_places(str(synthetic_pbf)))
    hollywood = next(r for r in rows if r["name"] == "Hollywood")
    assert isinstance(hollywood["lat"], str)
    assert isinstance(hollywood["lon"], str)
    assert float(hollywood["lat"]) == pytest.approx(52.4085, abs=1e-4)
    assert float(hollywood["lon"]) == pytest.approx(-1.8351, abs=1e-4)
