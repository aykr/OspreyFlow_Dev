"""Site geospatial calibration metadata — `docs/00_ARCHITECTURE.md` §1.2
"Geospatial reference data as entities" (site plans row),
`docs/02_GLASS_FRONTEND.md` §3.5, `08_ACCEPTANCE_SCENARIOS.md` A1.

A `Site` is investigation-scoped analyst data — an uploaded image, the
four control points that calibrate it, and a grid definition — not
deployment config. It is a different concern from `MapProvider(kind=image)`
(`packages/schemas/mapconfig.py`), which is an ops-provisioned, already-
georeferenced image registered in `osprey.yaml` ahead of time
(`docs/00_ARCHITECTURE.md` §1.2's `site-4471` example); this checkpoint
does not touch the provider registry at all. Persisted the same way
`services/api/investigations.py` persists investigation metadata:
Postgres, idempotent bootstrap SQL, no migration framework — small,
relational, control-plane data, not graph/analytics content.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import asyncpg
from pydantic import BaseModel, Field, model_validator

from conduit_common.identity import new_id
from schemas.domain import Principal

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS sites (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    created_by TEXT NOT NULL,
    label TEXT NOT NULL,
    image_object_key TEXT NOT NULL,
    image_width_px INTEGER NOT NULL,
    image_height_px INTEGER NOT NULL,
    control_points TEXT,
    grid_rows INTEGER,
    grid_cols INTEGER
);
"""


class ControlPointRecord(BaseModel):
    """One correspondence — the persisted shape of
    `packages/geo/bilinear.ControlPoint`. `px`/`py` are image-pixel
    coordinates (top-left origin); `lon`/`lat` are WGS84."""

    px: float
    py: float
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


#: Exactly 4, in TL/TR/BR/BL winding order (`packages/geo/bilinear.py`).
ControlPointQuad = tuple[
    ControlPointRecord, ControlPointRecord, ControlPointRecord, ControlPointRecord
]


class Site(BaseModel):
    id: str
    investigation_id: str
    owning_unit: str
    created_at: datetime
    created_by: str
    label: str
    image_object_key: str
    image_width_px: int
    image_height_px: int
    control_points: ControlPointQuad | None = None
    grid_rows: int | None = None
    grid_cols: int | None = None

    @model_validator(mode="after")
    def _grid_needs_control_points(self) -> Site:
        if (self.grid_rows, self.grid_cols) != (None, None) and self.control_points is None:
            raise ValueError("a grid cannot be set before the site has 4 control points")
        return self


class SiteNotFoundError(Exception):
    """Also raised — deliberately, not a 403 — when the site exists but
    `principal.org_unit` does not match `owning_unit`: the same
    existence-leak discipline `InvestigationNotFoundError`
    (`services/api/investigations.py`) already applies."""


def _row_to_site(row: asyncpg.Record) -> Site:
    data = dict(row)
    control_points_raw = data.pop("control_points")
    control_points = (
        tuple(ControlPointRecord(**cp) for cp in json.loads(control_points_raw))
        if control_points_raw is not None
        else None
    )
    return Site(control_points=control_points, **data)  # type: ignore[arg-type]


class SiteStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> SiteStore:
        pool = await asyncpg.create_pool(dsn=dsn)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create(
        self,
        principal: Principal,
        *,
        investigation_id: str,
        label: str,
        image_object_key: str,
        image_width_px: int,
        image_height_px: int,
        site_id: str | None = None,
    ) -> Site:
        """`site_id` is normally left to mint itself, exactly like
        `InvestigationStore.create`'s `id`. The one exception is the
        `POST .../sites` route (`app.py`), which needs the id *before* this
        call to name the uploaded image's object key
        (`services/api/site_images.py`'s `object_key_for`) — minting it
        there and passing it through keeps that one id, rather than this
        store silently generating a second one nothing would ever use."""
        site = Site(
            id=site_id or new_id(),
            investigation_id=investigation_id,
            owning_unit=principal.org_unit,
            created_at=datetime.now(UTC),
            created_by=principal.id,
            label=label,
            image_object_key=image_object_key,
            image_width_px=image_width_px,
            image_height_px=image_height_px,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO sites (id, investigation_id, owning_unit, created_at, "
                "created_by, label, image_object_key, image_width_px, image_height_px) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                site.id,
                site.investigation_id,
                site.owning_unit,
                site.created_at,
                site.created_by,
                site.label,
                site.image_object_key,
                site.image_width_px,
                site.image_height_px,
            )
        return site

    async def get(self, site_id: str) -> Site:
        """No authorization check here — this is the raw record lookup.
        `app.py`'s authorized dependency is what wraps this with the
        `owning_unit` check every route actually uses."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM sites WHERE id = $1", site_id)
        if row is None:
            raise SiteNotFoundError(site_id)
        return _row_to_site(row)

    async def get_authorized(self, site_id: str, principal: Principal) -> Site:
        """`owning_unit` filtered in the query itself, not after fetch — `06_DECISIONS.md`
        ADR-041's own fix, the same shape `review.py`'s `get_authorized`/`get_document_text`
        and `pattern_store.py`'s `get_authorized` already use. A hazard, not a leak, before this
        fix: the Python-side check below it replaced correctly rejected a mismatched principal
        (checked directly — no caller of `get()` elsewhere bypasses it), it just pulled the full
        row into process memory first."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sites WHERE id = $1 AND owning_unit = $2",
                site_id,
                principal.org_unit,
            )
        if row is None:
            raise SiteNotFoundError(site_id)
        return _row_to_site(row)

    async def set_control_points(
        self, site_id: str, principal: Principal, control_points: ControlPointQuad
    ) -> Site:
        await self.get_authorized(site_id, principal)
        payload = json.dumps([cp.model_dump() for cp in control_points])
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE sites SET control_points = $1 WHERE id = $2", payload, site_id
            )
        return await self.get(site_id)

    async def set_grid(self, site_id: str, principal: Principal, *, rows: int, cols: int) -> Site:
        site = await self.get_authorized(site_id, principal)
        if site.control_points is None:
            raise ValueError("cannot set a grid before the site has 4 control points")
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE sites SET grid_rows = $1, grid_cols = $2 WHERE id = $3",
                rows,
                cols,
                site_id,
            )
        return await self.get(site_id)
