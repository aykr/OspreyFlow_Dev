"""`GET`/`PUT .../resolution/threshold`, `POST .../resolution/link`, `POST .../resolution/split`,
`GET .../resolution/explain/{cluster_id}` — `docs/03_CONDUIT_MIDDLEWARE.md` §3.5,
`docs/01_DOMAIN_MODEL.md` §4.

Nested under `/v1/investigations/{investigation_id}/...`, not the bare `/v1/resolution/...` §3.5's
own illustrative listing shows — the same departure `services/api/working_set/models.py`'s own
docstring already accepts for `DeltaSnapshot` ("a real shape belongs in code, not only in a
docstring"): τ, manual link/split and `explain` are all per-investigation working-set concepts in
this build (`WorkingSetService.set_resolution_threshold`'s own docstring has the full reasoning
for τ; `manual_link`/`manual_split`/`explain_cluster` extend the same rationale), and every other
working-set mutation in `app.py` (`/branch`, `/seed`, `/expand`, `/nodes`) is already nested the
same way.

Request/response models plus the pure business-logic call live here, matching `search.py`'s own
split — `app.py` owns the actual route decorator, audit recording and delta broadcast, the same
as `/v1/search`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from services.api.working_set.models import ClusterExplanation, DeltaReproject
from services.api.working_set.service import WorkingSetService

from schemas.domain import ClusterId, NodeId, Principal


class ThresholdResponse(BaseModel):
    threshold: float


class SetThresholdRequest(BaseModel):
    threshold: float = Field(ge=0.0, le=1.0)


class ManualAssertionRequest(BaseModel):
    """`POST /resolution/link`/`POST /resolution/split`'s shared body shape —
    `03_CONDUIT_MIDDLEWARE.md` §3.5's own listing gives both the same two-node shape."""

    node_a: NodeId
    node_b: NodeId


async def get_threshold(working_set: WorkingSetService, investigation_id: str) -> ThresholdResponse:
    tau = await working_set.get_resolution_threshold(investigation_id)
    return ThresholdResponse(threshold=tau)


async def set_threshold(
    working_set: WorkingSetService,
    investigation_id: str,
    body: SetThresholdRequest,
    principal: Principal,
) -> DeltaReproject:
    return await working_set.set_resolution_threshold(investigation_id, body.threshold, principal)


async def link(
    working_set: WorkingSetService,
    investigation_id: str,
    body: ManualAssertionRequest,
    principal: Principal,
) -> DeltaReproject:
    return await working_set.manual_link(investigation_id, body.node_a, body.node_b, principal)


async def split(
    working_set: WorkingSetService,
    investigation_id: str,
    body: ManualAssertionRequest,
    principal: Principal,
) -> DeltaReproject:
    return await working_set.manual_split(investigation_id, body.node_a, body.node_b, principal)


async def explain(
    working_set: WorkingSetService,
    investigation_id: str,
    cluster_id: ClusterId,
    principal: Principal,
) -> ClusterExplanation:
    return await working_set.explain_cluster(investigation_id, cluster_id, principal)
