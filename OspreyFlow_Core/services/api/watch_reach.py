"""Whether a watch's owner still reaches its dataset (`06_DECISIONS.md` ADR-146 Amendment 4 point 7,
the orchestrator's L2.10 review, item 4).

A hotlist or watched pattern made in a case watches that case's dataset, and its owner is matched
as that dataset's reader. Narrowing the owner to the dataset alone would give back one they have
lost, so a watch is matched within it only while the owner holds a level, by the case's own Viewer
check, on some case reading the dataset. The check reads the owner's id, unit and teams (the case's
grants), not their `datasets`, so it answers the same for the owner as resolved and for one already
narrowed: it is asked before the narrowing, and the narrowing never stands in for it.

A store that is missing answers no (fail closed): a load path built without the case store matches
no watch that has a dataset, and says so in the log (`evaluation._within_its_dataset`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from schemas.domain import Principal

from .investigations import AccessLevel, InsufficientAccessError, InvestigationNotFoundError

#: The check: whether `owner` reaches `dataset_id`.
DatasetReach = Callable[[Principal, str], Awaitable[bool]]


def owner_reaches_dataset_in(datasets: Any, investigations: Any) -> DatasetReach:
    """The check over a dataset store (`cases_reading`) and a case store (`get_authorized`), each
    given as itself or as a getter read on every call, so a store set after start-up is used."""

    async def reaches(owner: Principal, dataset_id: str) -> bool:
        cases_store = datasets() if callable(datasets) else datasets
        levels = investigations() if callable(investigations) else investigations
        if cases_store is None or levels is None:
            return False  # no store to ask: no case to reach it through
        for case in await cases_store.cases_reading(dataset_id):
            try:
                await levels.get_authorized(case, owner, need=AccessLevel.VIEWER)
            except (InvestigationNotFoundError, InsufficientAccessError):
                continue
            return True
        return False

    return reaches


__all__ = ["DatasetReach", "owner_reaches_dataset_in"]
