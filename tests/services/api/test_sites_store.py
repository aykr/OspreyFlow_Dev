"""`services/api/sites.py`'s `SiteStore` — direct, live-Postgres
correctness (the JSON-encoded `control_points` round trip and the
existence-leak discipline in particular deserve their own proof, rather
than only being exercised indirectly through route-level fakes the way
`InvestigationStore` is in `test_app.py`). `docs/00_ARCHITECTURE.md` §1.2,
`08_ACCEPTANCE_SCENARIOS.md` A1.
"""

from __future__ import annotations

import pytest
from services.api.config import PostgresConfig
from services.api.sites import ControlPointRecord, Site, SiteNotFoundError, SiteStore

from schemas.domain import Principal

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
OTHER_UNIT_ANALYST = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-2")

_CONTROL_POINTS = (
    ControlPointRecord(px=0, py=0, lon=-1.836, lat=52.409),
    ControlPointRecord(px=1000, py=0, lon=-1.834, lat=52.409),
    ControlPointRecord(px=1000, py=1000, lon=-1.834, lat=52.408),
    ControlPointRecord(px=0, py=1000, lon=-1.836, lat=52.408),
)


@pytest.fixture
async def store():
    s = await SiteStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_a_created_site_has_no_control_points_or_grid_yet(store: SiteStore) -> None:
    site = await store.create(
        ANALYST,
        investigation_id="case-1",
        label="HMP Hollywood aerial",
        image_object_key="sites/site-1/image",
        image_width_px=2000,
        image_height_px=1500,
    )
    assert site.control_points is None
    assert site.grid_rows is None
    fetched = await store.get(site.id)
    assert fetched == site


async def test_control_points_round_trip_through_postgres_exactly(store: SiteStore) -> None:
    site = await store.create(
        ANALYST,
        investigation_id="case-1",
        label="HMP Hollywood aerial",
        image_object_key="sites/site-2/image",
        image_width_px=2000,
        image_height_px=1500,
    )
    updated = await store.set_control_points(site.id, ANALYST, _CONTROL_POINTS)
    assert updated.control_points == _CONTROL_POINTS

    reloaded = await store.get(site.id)
    assert reloaded.control_points == _CONTROL_POINTS


async def test_a_grid_cannot_be_set_before_control_points(store: SiteStore) -> None:
    site = await store.create(
        ANALYST,
        investigation_id="case-1",
        label="HMP Hollywood aerial",
        image_object_key="sites/site-3/image",
        image_width_px=2000,
        image_height_px=1500,
    )
    with pytest.raises(ValueError, match="control points"):
        await store.set_grid(site.id, ANALYST, rows=10, cols=10)


async def test_setting_the_grid_after_control_points_succeeds(store: SiteStore) -> None:
    site = await store.create(
        ANALYST,
        investigation_id="case-1",
        label="HMP Hollywood aerial",
        image_object_key="sites/site-4/image",
        image_width_px=2000,
        image_height_px=1500,
    )
    await store.set_control_points(site.id, ANALYST, _CONTROL_POINTS)
    updated = await store.set_grid(site.id, ANALYST, rows=10, cols=10)
    assert (updated.grid_rows, updated.grid_cols) == (10, 10)


async def test_a_missing_site_id_raises_not_found(store: SiteStore) -> None:
    with pytest.raises(SiteNotFoundError):
        await store.get("no-such-site")


async def test_a_site_owned_by_a_different_unit_is_not_found_not_forbidden(
    store: SiteStore,
) -> None:
    """Existence-leak discipline, matching `InvestigationNotFoundError`'s
    own doc comment: wrong unit and no-such-site collapse to the same
    error rather than a distinguishable 403."""
    site = await store.create(
        ANALYST,
        investigation_id="case-1",
        label="HMP Hollywood aerial",
        image_object_key="sites/site-5/image",
        image_width_px=2000,
        image_height_px=1500,
    )
    with pytest.raises(SiteNotFoundError):
        await store.get_authorized(site.id, OTHER_UNIT_ANALYST)


def test_a_grid_field_cannot_be_set_on_a_site_with_no_control_points() -> None:
    """The model-level guard `Site` itself enforces, independent of the
    store — belt-and-braces alongside `SiteStore.set_grid`'s own check."""
    with pytest.raises(ValueError, match="control points"):
        Site(
            id="s1",
            investigation_id="case-1",
            owning_unit="unit-1",
            created_at="2026-01-01T00:00:00Z",
            created_by="analyst-1",
            label="x",
            image_object_key="k",
            image_width_px=1,
            image_height_px=1,
            grid_rows=10,
            grid_cols=10,
        )
