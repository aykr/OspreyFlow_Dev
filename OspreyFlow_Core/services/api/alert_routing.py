"""Team routing and the team lead's queue tools (`06_DECISIONS.md` ADR-146 decision 8 and
Amendment 1; ADR-112 Amendment 5 decision 4; ADR-145 Amendment 5 points 5 and 6).

**Who reads a routed alert (rule 3).** A rule's *Alert goes to* may name a team. Its alerts are then
read only by the team's members and by the Authors of the home case of the alert's dataset; the
check is in the queue's query (`alerts.queue_scope`, `_routed_sql`), never a filter on a list. A
member is whoever holds the team's role on this request (`alerts.reader_teams`), so leaving the
role is leaving the team at once. Who answers for a dataset is read here, per read
(`answers_for_datasets`): the reader's datasets whose home case they are an Author of, in their own
name or through a team, in their own unit (`InvestigationStore.effective_level`).

**The lead's tools.** The team's acting lead (its cover while the cover lasts, else its lead,
`custom_roles.acting_lead`) may give one of the team's alerts to a named member of the team and
suppress one until a date (ADR-146 Amendment 1). Each is audited by its route.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import date
from typing import Protocol

from schemas.admin import Team
from schemas.domain import Principal

from .alerts import reader_teams
from .custom_roles import acting_lead
from .investigations import AccessLevel


class _HomeCases(Protocol):
    async def home_case_of(self, dataset_id: str) -> object | None: ...


class _Levels(Protocol):
    async def effective_level(
        self, investigation_id: str, principal: Principal
    ) -> AccessLevel | None: ...


class _Teams(Protocol):
    async def team(self, role_id: str, today: date) -> Team | None: ...


def answers_for_datasets(
    datasets: _HomeCases, investigations: _Levels
) -> Callable[[Principal], Awaitable[Sequence[str]]]:
    """The store's `answers_for`: of the reader's datasets, those whose home case they are an
    Author of. A dataset with no home case is answered for by no one."""

    async def answers_for(principal: Principal) -> Sequence[str]:
        found: list[str] = []
        for dataset_id in principal.datasets or []:
            home = await datasets.home_case_of(dataset_id)
            case = getattr(home, "investigation_id", None)
            if case is None:
                continue
            if await investigations.effective_level(case, principal) == AccessLevel.AUTHOR:
                found.append(dataset_id)
        return found

    return answers_for


async def leads_today(teams: _Teams, principal: Principal, today: date) -> set[str]:
    """The teams the principal acts as lead of today: of the teams they are in, those whose acting
    lead they are (the cover through their last day, else the lead). Only a member may be lead or
    cover (ADR-145 Amendment 5 point 6), and membership is read from this request."""
    led: set[str] = set()
    for role_id in reader_teams(principal):
        team = await teams.team(role_id, today)
        if team is not None and acting_lead(team, today) == principal.id:
            led.add(role_id)
    return led


__all__ = ["answers_for_datasets", "leads_today"]
