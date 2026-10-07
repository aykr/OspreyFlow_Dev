"""`LinkTypeProposalStore` against real Postgres (ADR-090): a proposal round-trips, a decision is
kept, the revision rises, and an administrator reads only their own unit's proposals, another
unit's answering as a missing one (decision 5 and 9)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.config import PostgresConfig
from services.api.link_type_store import LinkTypeProposalStore, ProposalNotFoundError
from services.api.link_types import LinkTypeProposal, ProposalStatus

from conduit_common.identity import new_id
from schemas.domain import Principal

ADMIN_1 = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-1", roles=["osprey-admin"])
ADMIN_2 = Principal(id="admin-2", clearance="OFFICIAL", org_unit="unit-2", roles=["osprey-admin"])


@pytest.fixture
async def store():
    s = await LinkTypeProposalStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


def _proposal(
    unit: str = "unit-1", case: str | None = None, name: str = "KNOWN_TO"
) -> LinkTypeProposal:
    return LinkTypeProposal(
        id=new_id(),
        name=name,
        from_types=["Person"],
        to_types=["Person"],
        directed=False,
        investigation_id=case or new_id(),
        owning_unit=unit,
        proposed_by="analyst-1",
        proposed_at=datetime(2026, 10, 5, 9, tzinfo=UTC),
        reason="They know each other by sight",
        colour="jade",
        thickness=2,
    )


async def test_a_proposal_round_trips_and_is_found_for_its_case(
    store: LinkTypeProposalStore,
) -> None:
    p = _proposal()
    await store.create(p)
    assert await store.get(p.id) == p
    assert [x.id for x in await store.pending_for_cases([p.investigation_id])] == [p.id]
    assert p.id in {x.id for x in await store.pending_named(["KNOWN_TO"])}


async def test_an_administrator_reads_only_their_own_units_proposals(
    store: LinkTypeProposalStore,
) -> None:
    mine, theirs = _proposal("unit-1"), _proposal("unit-2")
    await store.create(mine)
    await store.create(theirs)
    assert (await store.get_authorized(mine.id, ADMIN_1)).id == mine.id
    with pytest.raises(ProposalNotFoundError):
        await store.get_authorized(theirs.id, ADMIN_1)
    with pytest.raises(ProposalNotFoundError):
        await store.get_authorized("no-such-proposal", ADMIN_1)
    listed = {p.id for p in await store.list_authorized(ADMIN_1)}
    assert mine.id in listed and theirs.id not in listed
    assert theirs.id in {p.id for p in await store.list_authorized(ADMIN_2)}


async def test_a_decision_is_kept_and_a_decided_proposal_is_no_longer_pending(
    store: LinkTypeProposalStore,
) -> None:
    p = _proposal()
    await store.create(p)
    at = datetime(2026, 10, 5, 12, tzinfo=UTC)
    await store.decide(
        p.id,
        status=ProposalStatus.PROMOTED,
        by="admin-1",
        at=at,
        reason="Seen in three cases",
        basis="direct",
        promoted_name="KNOWN_TO",
        direct_since=at,
    )
    decided = await store.get(p.id)
    assert (decided.status, decided.basis, decided.direct_since, decided.decided_by) == (
        ProposalStatus.PROMOTED,
        "direct",
        at,
        "admin-1",
    )
    assert p.id not in {x.id for x in await store.pending_for_cases([p.investigation_id])}


async def test_the_revision_rises_by_one_each_time(store: LinkTypeProposalStore) -> None:
    before = await store.revision()
    assert await store.bump_revision() == before + 1
    assert await store.revision() == before + 1


async def test_a_proposal_keeps_its_dataset_and_is_found_for_it_and_no_other(
    store: LinkTypeProposalStore,
) -> None:
    """ADR-099 Amendment 3, in the database itself: the dataset round-trips, and a dataset's
    pending proposals are its own (a proposal of no dataset, made before, is not among them)."""
    mine = new_id()
    p = _proposal().model_copy(update={"dataset_id": mine})
    older = _proposal(name="KNOWN_FROM")  # made before the amendment: no dataset
    other = _proposal(name="SEEN_WITH").model_copy(update={"dataset_id": new_id()})
    for proposal in (p, older, other):
        await store.create(proposal)
    assert (await store.get(p.id)).dataset_id == mine
    assert [q.id for q in await store.pending_for_datasets([mine])] == [p.id]
    await store.decide(p.id, status=ProposalStatus.WITHDRAWN, by="x", at=p.proposed_at, reason="r")
    assert await store.pending_for_datasets([mine]) == []
