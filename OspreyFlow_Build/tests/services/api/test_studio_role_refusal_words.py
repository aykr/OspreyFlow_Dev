"""The Studio's refusal for a missing studio role says it in words, naming the roles that hold it,
never the role's id (CARRIES row 40; ADR-145 Amendment 4 decision 12, the owner's ruling (c):
roles, never people). Red before: `require_studio_role` answered "principal lacks required studio
role: source_approver". Read at the real call site, the dependency every Studio route uses."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from services.api.app import require_studio_role

from schemas.domain import Principal
from schemas.ingest import StudioRole

NOBODY = Principal(id="p-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])


@pytest.mark.parametrize(
    ("role", "action"),
    [
        (StudioRole.SOURCE_APPROVER, "deploy pipelines"),
        (StudioRole.SOURCE_AUTHOR, "edit pipelines"),
        (StudioRole.LOADER, "run pipelines"),
    ],
)
def test_the_refusal_names_the_action_and_the_roles_that_hold_it(role: StudioRole, action: str) -> None:
    check = require_studio_role(role)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(check(NOBODY))
    words = str(refused.value.detail)
    assert refused.value.status_code == 403
    assert role.value not in words and "studio role" not in words
    assert f"You may not {action} here." in words
    assert "Data Engineer" in words and "Super user" in words
    assert "analyst" not in words.lower().split("held by")[-1]
