"""The four title resolvers of the case brief — ADR-128 decision 3, rule 3.

Each answers one question for one reader: what is this attachment called to *you*? The answer is the
attachment's title when that kind's own store and its own access rule let this reader read it, and
`None` otherwise, whether the thing does not exist or exists and is not theirs to read. `None` is
one answer for both so that nothing the brief does can tell a reader that a hidden thing exists
(`case_brief.py`). No access rule is written here: each is the rule the kind already has.

* **trend:** saved per case, readable by anyone who reads the case; looked up in *this* case only,
  so another case's trend id is not found (`TrendStore.get`).
* **pattern:** readable by its owner and, within the case's datasets, nobody else (ADR-036, ADR-040
  not accepted): `PatternStore.get_authorized`, which filters on the owner in the query itself.
* **assessment:** a judgement of this case, in the reader's unit, and not hidden by ADR-046's
  hide-in-full rule, which `judgement_visible_to` applies (one `get_node` per supporting citation,
  as the reader). Ownership alone is not enough: a judgement resting on a node the reader cannot see
  is not theirs to see either.
* **view:** a canvas tab is a case (ADR-084; ADR-128 decision 2 names the branch "the tab");
  readable when the reader holds any level on it.
"""

from __future__ import annotations

from ports.graph import GraphPort
from schemas.domain import Principal

from .assessments import JudgementNotFoundError, JudgementStore, judgement_visible_to
from .case_brief import TitleResolver
from .investigations import (
    AccessLevel,
    InsufficientAccessError,
    InvestigationNotFoundError,
    InvestigationStore,
)
from .pattern_store import PatternNotFoundError, PatternStore
from .trends import TrendStore

#: A title is a label, not the thing: the first line of an assessment's statement, cut at this many
#: characters with an ellipsis. The statement itself is never changed.
MAX_TITLE_CHARS = 120
UNTITLED_VIEW = "Untitled view"


def _label(statement: str) -> str:
    first = statement.strip().splitlines()[0].strip() if statement.strip() else ""
    if len(first) <= MAX_TITLE_CHARS and "\n" not in statement.strip():
        return first
    return first[: MAX_TITLE_CHARS - 1].rstrip() + "…"


def title_resolvers(
    *,
    trends: TrendStore,
    patterns: PatternStore,
    judgements: JudgementStore,
    graph: GraphPort,
    investigations: InvestigationStore,
) -> dict[str, TitleResolver]:
    async def trend(case_id: str, ref_id: str, principal: Principal) -> str | None:
        found = await trends.get(case_id, ref_id)
        return None if found is None else str(found.title)

    async def pattern(case_id: str, ref_id: str, principal: Principal) -> str | None:
        try:
            return str((await patterns.get_authorized(ref_id, principal)).name)
        except PatternNotFoundError:
            return None

    async def assessment(case_id: str, ref_id: str, principal: Principal) -> str | None:
        try:
            judgement = await judgements.get_authorized(ref_id, principal)
        except JudgementNotFoundError:
            return None
        if judgement.investigation_id != case_id:
            return None
        if not await judgement_visible_to(judgement, principal, graph):
            return None
        return _label(judgement.statement)

    async def view(case_id: str, ref_id: str, principal: Principal) -> str | None:
        try:
            case = await investigations.get_authorized(ref_id, principal, need=AccessLevel.VIEWER)
        except (InvestigationNotFoundError, InsufficientAccessError):
            return None
        return case.name or UNTITLED_VIEW

    return {"trend": trend, "pattern": pattern, "assessment": assessment, "view": view}
