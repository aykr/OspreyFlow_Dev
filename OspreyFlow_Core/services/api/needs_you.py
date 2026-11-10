"""The data engineer's *Needs you* (`06_DECISIONS.md` ADR-145 decision 11, A2; Amendment 4
decision 11, R7; ADR-090 Amendment 4; ADR-143 Amendment 4's *Open*, the strict reading; L2.7).

One read, `GET /v1/me/needs-you`, for the top bar's *Needs you · n* and the Studio's *1 Model · n
proposed*. It names no right of its own, because each half is gated by what it lists, as the reader:

- **Promotions overdue**: through `PromotionAgeingStore.alerts_for(person, still)`, with `still`
  the sweep's own `_promotion_recipients`. So an alert is served only to someone who is still one
  of its recipients now: still enabled, still an Author holding `review_promotions` or the dataset's
  unit's administrator, and still cleared to its marking. The notice carries no other recipient.
- **Proposed link types to decide**: only to a holder of `accept_types`, and only for the datasets
  the reader's own cases load into. That is exactly the Studio's reach (`scope_to_dataset`, ADR-140
  Amendment 2), so a dataset reached by no case of theirs, or held by another unit, is not asked.
  A dataset whose proposals the reader is not cleared to read (`may_read_proposal_words`) is not
  asked of, so nothing of it is said, not even that one is open (ADR-143 Amendment 4 (b), the
  strict reading, ruled at L2.7's review); for one they may read, the service answers a count
  alone (`LinkTypeService.open_proposal_count`), so no proposal reaches this module.
- **Scheduled loads' notices** (ADR-110 Amendment 19, granted to the rules lane for this item): the
  reader's own notices of the last seven days, newest first, at most twenty with the total said,
  through `AlertStore.list_schedule_notices`, which reads by owner in the query. They are anyone's
  who owns a schedule, so no right gates them; they are only ever their owner's.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from datetime import datetime, timedelta
from typing import Protocol

from schemas.admin import NeedsYouProposals, ScheduleNoticeEntry
from schemas.domain import Alert, Principal

#: Amendment 19: how far back a notice stays in *Needs you*, and how many are listed at once.
NOTICE_DAYS = 7
NOTICE_LIMIT = 20


class ScheduleNotices(Protocol):
    async def list_schedule_notices(
        self, principal: Principal, *, since: datetime, limit: int = ...
    ) -> tuple[list[Alert], int]: ...


async def proposals_to_decide(
    dataset_ids: Iterable[str],
    names: dict[str, str],
    open_count: Callable[[str], Awaitable[int]],
    may_read_words: Callable[[str], Awaitable[bool]],
) -> list[NeedsYouProposals]:
    """One entry for each reached dataset whose proposals the reader may read and which has one to
    decide. A dataset above the reader's clearance is not asked of at all, so nothing of it is said
    (the strict reading, ruled at L2.7's review); a count is the only thing read."""
    found: list[NeedsYouProposals] = []
    for dataset_id in sorted(set(dataset_ids)):
        if not await may_read_words(dataset_id):
            continue
        count = await open_count(dataset_id)
        if count:
            found.append(
                NeedsYouProposals(
                    dataset_id=dataset_id, dataset_name=names.get(dataset_id, dataset_id),
                    to_decide=count,
                )
            )  # fmt: skip
    return found


async def reached_datasets(
    principal: Principal,
    cases_of: Callable[[Principal], Awaitable[Sequence[tuple[object, object]]]],
    ids_of_case: Callable[[str], Awaitable[list[str]]],
) -> list[str]:
    """The datasets the Studio may open for this reader: the first dataset of each case they hold a
    level in (`dataset_scope.scope_to_dataset`'s reach, the Studio's switcher's)."""
    reached: list[str] = []
    for case, _level in await cases_of(principal):
        ids = await ids_of_case(str(getattr(case, "id")))
        if ids and ids[0] not in reached:
            reached.append(ids[0])
    return reached


async def schedule_notices_for(
    principal: Principal, store: ScheduleNotices, now: datetime
) -> tuple[list[ScheduleNoticeEntry], int]:
    """The reader's own scheduled loads' notices (Amendment 19) and how many there are in all. The
    store reads by owner in its query; this only shapes what it served."""
    notices, total = await store.list_schedule_notices(
        principal, since=now - timedelta(days=NOTICE_DAYS), limit=NOTICE_LIMIT
    )
    return [
        ScheduleNoticeEntry(
            notice_id=n.id, recipe_id=n.rule_id.split(":", 1)[-1], raised_at=n.created_at,
            words=n.words or "A scheduled load did not finish.",
        )
        for n in notices
    ], total  # fmt: skip
