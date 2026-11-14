"""A batch expansion: the working-set cap's third choice, `promote_to_batch` (`06_DECISIONS.md`
ADR-151; `03_CONDUIT_MIDDLEWARE.md` §3.2 and §4).

The expansion the cap refused is sent again whole (`BatchExpansionInput`), run by the job worker
under the requester's own access, and either saved as a private view of the case or refused with
its figures. It is never cut to fit (rule 2). `BatchExpansion` is what the Glass is told, at
submission and each time it asks: always a whole sentence in `words`, and nothing that names a
node (rule 7). The saved view is ADR-144's own wire shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .case_views import CaseView
from .domain import ExpandRequest

BatchState = Literal["queued", "running", "done", "refused", "failed"]

#: Why a batch saved nothing (ADR-151 decisions 3 and 5).
BatchRefusalCode = Literal[
    "too_many_nodes", "too_many_links", "found_nothing", "no_longer_an_editor", "took_too_long"
]


class BatchExpansionInput(BaseModel):
    """`POST /v1/investigations/{id}/batch-expansions`: the refused expansion's own body
    (`ExpandBody`), with the view's name if the analyst gave one."""

    model_config = ConfigDict(extra="forbid")

    request: ExpandRequest
    justification: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)


class BatchRefusal(BaseModel):
    """Why nothing was saved. For a result past the cap, the cap and the figure it would have
    been, so the analyst knows how far to narrow."""

    model_config = ConfigDict(extra="forbid")

    code: BatchRefusalCode
    cap_kind: Literal["nodes", "edges"] | None = None
    cap: int | None = Field(default=None, ge=0)
    would_be: int | None = Field(default=None, ge=0)


class BatchExpansion(BaseModel):
    """A batch expansion as its requester is told it."""

    model_config = ConfigDict(extra="forbid")

    id: str
    state: BatchState
    #: Always a whole sentence: the stage while running, what was saved, or why nothing was.
    words: str
    #: Done: the private view saved (ADR-144), opened through `GET …/views/{view.id}`.
    view: CaseView | None = None
    nodes: int | None = Field(default=None, ge=0)
    links: int | None = Field(default=None, ge=0)
    refusal: BatchRefusal | None = None


ALL_MODELS: tuple[type[BaseModel], ...] = (BatchExpansionInput, BatchRefusal, BatchExpansion)
