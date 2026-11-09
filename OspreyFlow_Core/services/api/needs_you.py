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
  A proposal the reader is not cleared to read (`may_read_proposal_words`) is neither counted nor
  described. The dataset says only that *one or more still to decide* exist above their clearance,
  with no count, no words and no status: `above_clearance` is a flag, raised by an open proposal
  alone (a declined one raises nothing).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence

from schemas.admin import NeedsYouProposals
from schemas.domain import Principal

#: A proposal's view as `LinkTypeService.dataset_proposal_views` answers it (duck-typed: `status`,
#: `in_model`, `withheld`).
ProposalViews = Callable[[str, bool], Awaitable[Sequence[object]]]


def to_decide(view: object) -> bool:
    """Still to decide, and readable by this reader: pending, or accepted and since lost from both
    the live model and the draft (`link_types._decidable`'s rule). A withheld one is never counted,
    and neither is one whose words the reader may not read."""
    if getattr(view, "withheld", False):
        return False
    status = getattr(view, "status", None)
    value = getattr(status, "value", status)
    return value == "pending" or (value == "accepted" and getattr(view, "in_model", None) is None)


async def proposals_to_decide(
    dataset_ids: Iterable[str],
    names: dict[str, str],
    views: ProposalViews,
    may_read_words: Callable[[str], Awaitable[bool]],
) -> list[NeedsYouProposals]:
    """One entry for each reached dataset that has something to say: a count of the proposals to
    decide, and whether any exist above the reader's clearance. A dataset with neither is left
    out."""
    found: list[NeedsYouProposals] = []
    for dataset_id in sorted(set(dataset_ids)):
        words = await may_read_words(dataset_id)
        # Read whole inside the Conduit and reduced here to a count or a flag, so the flag is raised
        # only by a proposal still to decide (`without_words` keeps no status); no word of a
        # proposal the reader may not read leaves this function.
        listed = await views(dataset_id, True)
        open_ = sum(1 for v in listed if to_decide(v))
        count = open_ if words else 0
        hidden = not words and open_ > 0
        if count or hidden:
            found.append(
                NeedsYouProposals(
                    dataset_id=dataset_id,
                    dataset_name=names.get(dataset_id, dataset_id),
                    to_decide=count,
                    above_clearance=hidden,
                )
            )
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
