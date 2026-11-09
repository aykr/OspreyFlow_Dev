"""`LinkTypeProposalStore` against real Postgres (ADR-090): a proposal round-trips, a decision is
kept, the revision rises, and an administrator reads only their own unit's proposals, another
unit's answering as a missing one (decision 5 and 9)."""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.link_type_store import LinkTypeProposalStore, ProposalNotFoundError
from services.api.link_types import LinkTypeProposal, ProposalStatus

from conduit_common.identity import new_id
from schemas.domain import Principal

ADMIN_1 = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-1", roles=["osprey-admin"])
ADMIN_2 = Principal(id="admin-2", clearance="OFFICIAL", org_unit="unit-2", roles=["osprey-admin"])


@pytest.fixture
async def store(own_store: LinkTypeProposalStore):
    """Every case over a schema of its own, dropped afterwards, so none leaves a row in the shared
    table (L2.7's review: these cases wrote to it and kept it)."""
    yield own_store


@pytest.fixture
async def own_store():
    """A store over a schema of its own, dropped afterwards whatever the test did: a status main's
    schema does not know yet (`accepted`, ADR-143 decision 9) must never be left in the shared
    table, where it stops every other lane's Conduit from starting (8 November 2026)."""
    base = PostgresConfig.from_env().dsn
    schema = f"link_types_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    held = None
    try:
        held = await LinkTypeProposalStore.connect(
            f"{base}{'&' if '?' in base else '?'}search_path={schema}"
        )
        yield held
    finally:
        if held is not None:
            await held.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


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


async def test_the_administrators_list_keeps_to_proposals_naming_no_dataset(
    own_store: LinkTypeProposalStore,
) -> None:
    """L2.7: `without_dataset` keeps the administrator's list to the proposals made before ADR-099
    Amendment 3, in the query itself; a proposal naming a dataset is decided on its Model tab. Over a
    schema of its own, dropped afterwards, so nothing is left in the shared table. Red with the
    query's `AND dataset_id IS NULL` removed."""
    legacy, bound = _proposal("unit-1"), _proposal("unit-1").model_copy(update={"dataset_id": "ds-a"})
    await own_store.create(legacy)
    await own_store.create(bound)
    listed = {p.id for p in await own_store.list_authorized(ADMIN_1, without_dataset=True)}
    assert legacy.id in listed and bound.id not in listed
    assert bound.id in {p.id for p in await own_store.list_authorized(ADMIN_1)}


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
    proposals are its own (a proposal of no dataset, made before, is not among them). The read of
    every pending proposal of a dataset, which offered them in every case reading it, is gone with
    ADR-143 decision 9 (rule 3)."""
    mine = new_id()
    p = _proposal().model_copy(update={"dataset_id": mine})
    older = _proposal(name="KNOWN_FROM")  # made before the amendment: no dataset
    other = _proposal(name="SEEN_WITH").model_copy(update={"dataset_id": new_id()})
    for proposal in (p, older, other):
        await store.create(proposal)
    assert (await store.get(p.id)).dataset_id == mine
    # Read by the Model tab's query, which names the dataset (ADR-143 decision 9).
    assert [q.id for q in await store.for_dataset(mine)] == [p.id]
    await store.decide(p.id, status=ProposalStatus.WITHDRAWN, by="x", at=p.proposed_at, reason="r")
    assert [q.status for q in await store.for_dataset(mine)] == [ProposalStatus.WITHDRAWN]


async def test_the_model_tab_reads_its_own_datasets_proposals_and_no_other(
    own_store: LinkTypeProposalStore,
) -> None:
    """ADR-143 decision 9 in the database itself (rule 3): the Model tab's list and its decisions
    read by `dataset_id` in the query, so another dataset's proposal is never read and answers as
    a missing one. An `accepted` status is kept (the check was replaced whole), and a case reads
    its own proposals whatever their status, by name or all. In a schema of its own
    (`own_store`), so no `accepted` row is ever left in the shared table."""
    mine, theirs = new_id(), new_id()
    case = new_id()
    p = _proposal(case=case, name="BRIBED").model_copy(update={"dataset_id": mine})
    other = _proposal(name="BRIBED").model_copy(update={"dataset_id": theirs})
    for proposal in (p, other):
        await own_store.create(proposal)
    assert [q.id for q in await own_store.for_dataset(mine)] == [p.id]
    assert (await own_store.get_for_dataset(p.id, mine)).id == p.id
    with pytest.raises(ProposalNotFoundError):
        await own_store.get_for_dataset(other.id, mine)
    await own_store.decide(
        p.id, status=ProposalStatus.ACCEPTED, by="dan", at=p.proposed_at, reason="r",
        promoted_name="BRIBED",
    )  # fmt: skip
    assert (await own_store.get(p.id)).status is ProposalStatus.ACCEPTED
    assert [q.id for q in await own_store.accepted_for_datasets([mine])] == [p.id]
    assert await own_store.accepted_for_datasets([theirs]) == []
    assert [q.id for q in await own_store.named_in_case(case, ["BRIBED"])] == [p.id]
    assert [q.id for q in await own_store.named_in_case(case, None)] == [p.id]
    assert await own_store.named_in_case(case, ["OTHER"]) == []


async def test_a_table_made_before_accepted_takes_it_after_connect() -> None:
    """ADR-143 decision 9: a deployment's table made with the old status check (no `accepted`) is
    upgraded by `connect`, which replaces the check whole (red with the replacement removed: the
    accepted decision is refused by the old check). In a schema of its own, so the shared table's
    check is never touched."""
    base = PostgresConfig.from_env().dsn
    schema = f"link_types_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        await admin.execute(
            f'CREATE TABLE "{schema}".link_type_proposals (id TEXT PRIMARY KEY, name TEXT NOT NULL, '
            "label TEXT, from_types TEXT[] NOT NULL, to_types TEXT[] NOT NULL, directed BOOLEAN "
            "NOT NULL, colour TEXT, thickness INTEGER, investigation_id TEXT NOT NULL, owning_unit "
            "TEXT NOT NULL, proposed_by TEXT NOT NULL, proposed_at TIMESTAMPTZ NOT NULL, reason "
            "TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('pending', 'promoted', "
            "'rejected', 'withdrawn', 'merged', 'retired')), decided_by TEXT, decided_at "
            "TIMESTAMPTZ, decision_reason TEXT, basis TEXT, promoted_name TEXT, direct_since "
            "TIMESTAMPTZ)"
        )
        dsn = f"{base}{'&' if '?' in base else '?'}search_path={schema}"
        old = await LinkTypeProposalStore.connect(dsn)
        try:
            p = _proposal(name="BRIBED").model_copy(update={"dataset_id": new_id()})
            await old.create(p)
            assert await old.decide(
                p.id, status=ProposalStatus.ACCEPTED, by="dan", at=p.proposed_at, reason="r",
                only_from=ProposalStatus.PENDING,
            )  # fmt: skip
            assert (await old.get(p.id)).status is ProposalStatus.ACCEPTED
            # Only from the status read: a second decision from pending is not written.
            assert not await old.decide(
                p.id, status=ProposalStatus.REJECTED, by="erin", at=p.proposed_at, reason="r",
                only_from=ProposalStatus.PENDING,
            )  # fmt: skip
            assert (await old.get(p.id)).status is ProposalStatus.ACCEPTED
        finally:
            await old.close()
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()
