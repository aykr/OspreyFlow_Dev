"""`GeometryRecord`'s `kind`/payload validator — `docs/07_BUILD_PLAN.md`
Phase 5 known-gaps closure's polygon-storage addition. `AnalyticsPort`/`analytics_duckdb`'s
own conformance suite (`tests/conformance/analytics_port/test_suite.py`)
covers the write/read round trip; this file covers only the schema-level
`kind`/payload agreement `model_validator` enforces before either adapter
ever sees a record."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.analytics import GeometryKind, GeometryRecord
from schemas.domain import Handling


def _handling() -> Handling:
    return Handling(classification="OFFICIAL", handling_code="P", owning_unit="unit-1",
                     originator="unit-1")


def test_a_point_record_with_lon_lat_and_no_wkb_is_valid() -> None:
    record = GeometryRecord(
        geometry_ref="geo-1", version=1, kind=GeometryKind.POINT,
        lon=-0.1, lat=51.5, handling=_handling(),
    )
    assert record.kind is GeometryKind.POINT


def test_kind_defaults_to_point() -> None:
    record = GeometryRecord(geometry_ref="geo-1", version=1, lon=-0.1, lat=51.5,
                             handling=_handling())
    assert record.kind is GeometryKind.POINT


def test_a_polygon_record_with_wkb_and_no_lon_lat_is_valid() -> None:
    record = GeometryRecord(
        geometry_ref="geo-boundary", version=1, kind=GeometryKind.POLYGON,
        geometry_wkb=b"\x00" * 4, handling=_handling(),
    )
    assert record.kind is GeometryKind.POLYGON


def test_a_point_record_missing_lon_is_rejected() -> None:
    with pytest.raises(ValidationError, match="requires both lon and lat"):
        GeometryRecord(geometry_ref="geo-1", version=1, kind=GeometryKind.POINT, lat=51.5,
                        handling=_handling())


def test_a_point_record_carrying_geometry_wkb_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not carry geometry_wkb"):
        GeometryRecord(
            geometry_ref="geo-1", version=1, kind=GeometryKind.POINT,
            lon=-0.1, lat=51.5, geometry_wkb=b"\x00" * 4, handling=_handling(),
        )


def test_a_polygon_record_missing_geometry_wkb_is_rejected() -> None:
    with pytest.raises(ValidationError, match="requires geometry_wkb"):
        GeometryRecord(geometry_ref="geo-boundary", version=1, kind=GeometryKind.POLYGON,
                        handling=_handling())


def test_a_polygon_record_carrying_lon_lat_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not carry lon/lat"):
        GeometryRecord(
            geometry_ref="geo-boundary", version=1, kind=GeometryKind.POLYGON,
            lon=-0.1, lat=51.5, geometry_wkb=b"\x00" * 4, handling=_handling(),
        )
