"""`require_studio_role` — `docs/09_INGEST_STUDIO.md` §8's role-based
action authorisation for the Ingest Studio, a different axis from
`AccessFilter`'s per-record clearance/handling gate. Exercised directly
against the dependency function, the same way `PrincipalResolver` is
exercised in `test_auth.py` without a live server — no studio route
exists yet to attach this to (Publish-stage scope), so what belongs here
is only "does the right role, and only the right role, pass".
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from services.api.app import require_studio_role

from schemas.domain import Principal
from schemas.ingest import StudioRole


def _principal(*roles: str) -> Principal:
    return Principal(id="p-1", clearance="OFFICIAL", org_unit="unit-1", roles=list(roles))


async def test_a_principal_holding_the_required_role_is_returned() -> None:
    dependency = require_studio_role(StudioRole.SOURCE_APPROVER)
    principal = _principal("source_approver")

    assert await dependency(principal) is principal


async def test_a_principal_missing_the_required_role_is_rejected() -> None:
    dependency = require_studio_role(StudioRole.SOURCE_APPROVER)
    principal = _principal("source_author")

    with pytest.raises(HTTPException) as exc_info:
        await dependency(principal)

    assert exc_info.value.status_code == 403


async def test_a_principal_may_hold_more_than_one_studio_role() -> None:
    principal = _principal("source_author", "source_approver")

    assert await require_studio_role(StudioRole.SOURCE_AUTHOR)(principal) is principal
    assert await require_studio_role(StudioRole.SOURCE_APPROVER)(principal) is principal
    with pytest.raises(HTTPException):
        await require_studio_role(StudioRole.LOADER)(principal)
