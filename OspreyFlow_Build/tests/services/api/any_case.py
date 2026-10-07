"""A case store that holds every case asked for, at Author, in the asker's own unit.

For route tests whose subject is not access to the case (ADR-099 moved search, suggestions, the
query builder, paths and the node actions under `/v1/investigations/{id}/`; their level checks are
`test_investigation_levels.py`'s table, and the case-level refusals are tested there)."""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.investigations import AccessLevel, Investigation

from schemas.domain import Principal


class AnyCase:
    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        return Investigation(
            id=investigation_id,
            name="A case",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by=principal.id,
            owning_unit=principal.org_unit,
        )
