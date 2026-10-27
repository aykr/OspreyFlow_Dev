"""`CaseBriefStore` against real Postgres (`make dev-up`) — the half `test_case_brief.py`'s in-memory
stand-in cannot prove: that the row survives a round trip through JSONB, that a refusal inside a
change stores nothing, that cases do not share a brief, and that the row lock makes the cap of
twenty hold when requests arrive together.

Owner-run, like the other store tests: it needs the Postgres of `make dev-up`."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from services.api.case_brief import (
    MAX_ATTACHMENTS,
    MAX_REQUIREMENTS,
    CaseBriefStore,
    RequirementNotFoundError,
    StoredAttachment,
    StoredBrief,
    TooManyAttachmentsError,
    TooManyRequirementsError,
    with_attachment,
    with_priority,
    with_requirement_added,
    with_requirement_edited,
    with_status,
    without_attachment,
    without_requirement,
)
from services.api.config import PostgresConfig

from conduit_common.identity import new_id

NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


@pytest.fixture
async def store():
    s = await CaseBriefStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def _add(store: CaseBriefStore, case: str, text: str) -> str:
    requirement_id = new_id()
    await store.update(
        case, lambda b: with_requirement_added(b, requirement_id, text, "author-1", NOW)
    )
    return requirement_id


async def test_a_case_with_no_brief_reads_as_an_empty_one(store) -> None:
    case = new_id()
    assert await store.get(case) == StoredBrief(investigation_id=case)


async def test_reading_a_case_with_no_brief_writes_nothing(store) -> None:
    case = new_id()
    await store.get(case)
    async with store._pool.acquire() as conn:
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM case_briefs WHERE investigation_id = $1", case
            )
            == 0
        )


async def test_a_brief_round_trips_priority_requirements_status_and_attachments(store) -> None:
    case = new_id()
    await store.update(case, lambda b: with_priority(b, "Who is orchestrating?", "author-1", NOW))
    first = await _add(store, case, "Who orchestrates?")
    second = await _add(store, case, "Where and when?")
    await store.update(case, lambda b: with_status(b, second, "answered", "author-2", NOW))
    attachment = StoredAttachment(kind="trend", id="t1")
    await store.update(case, lambda b: with_attachment(b, first, attachment, "author-1", NOW))

    read = await store.get(case)

    assert read.priority == "Who is orchestrating?"
    assert [r.id for r in read.requirements] == [first, second]
    assert read.requirements[0].status == "open" and read.requirements[0].attachments == [
        attachment
    ]
    assert read.requirements[1].status == "answered"
    assert read.requirements[1].answered_by == "author-2"
    assert read.requirements[1].answered_at == NOW
    assert read.updated_by == "author-1" and read.updated_at == NOW


async def test_an_edit_and_a_removal_are_stored(store) -> None:
    case = new_id()
    first = await _add(store, case, "Draft")
    second = await _add(store, case, "Keep")
    await store.update(case, lambda b: with_requirement_edited(b, first, "Final", "author-1", NOW))
    assert (await store.get(case)).requirements[0].text == "Final"
    await store.update(case, lambda b: without_requirement(b, first, "author-1", NOW))
    assert [r.id for r in (await store.get(case)).requirements] == [second]


async def test_a_refusal_inside_a_change_stores_nothing(store) -> None:
    case = new_id()
    await _add(store, case, "One")
    with pytest.raises(RequirementNotFoundError):
        await store.update(case, lambda b: with_requirement_edited(b, "nope", "x", "author-1", NOW))
    assert [r.text for r in (await store.get(case)).requirements] == ["One"]


async def test_a_refusal_for_a_case_with_no_brief_leaves_no_row_behind(store) -> None:
    case = new_id()
    with pytest.raises(RequirementNotFoundError):
        await store.update(case, lambda b: with_status(b, "nope", "answered", "a", NOW))
    async with store._pool.acquire() as conn:
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM case_briefs WHERE investigation_id = $1", case
            )
            == 0
        )


async def test_two_cases_do_not_share_a_brief_or_a_requirement(store) -> None:
    one, two = new_id(), new_id()
    requirement = await _add(store, one, "Only here")
    assert (await store.get(two)).requirements == []
    with pytest.raises(RequirementNotFoundError):
        await store.update(two, lambda b: with_status(b, requirement, "answered", "a", NOW))
    assert (await store.get(one)).requirements[0].status == "open"


async def test_the_twenty_first_requirement_is_refused_and_the_twenty_stay(store) -> None:
    case = new_id()
    for n in range(MAX_REQUIREMENTS):
        await _add(store, case, f"Requirement {n}")
    with pytest.raises(TooManyRequirementsError):
        await _add(store, case, "One too many")
    assert len((await store.get(case)).requirements) == MAX_REQUIREMENTS


async def test_requests_arriving_together_cannot_pass_the_cap_between_them(store) -> None:
    """The row lock: thirty adds at once leave exactly twenty, the other ten refused, none lost
    to a read-modify-write race."""
    case = new_id()
    results = await asyncio.gather(
        *(_add(store, case, f"Requirement {n}") for n in range(30)), return_exceptions=True
    )
    refused = [r for r in results if isinstance(r, TooManyRequirementsError)]
    assert len(refused) == 10 and len([r for r in results if isinstance(r, str)]) == 20
    stored = await store.get(case)
    assert len(stored.requirements) == MAX_REQUIREMENTS
    assert {r.id for r in stored.requirements} == {r for r in results if isinstance(r, str)}


async def test_attachments_are_held_once_capped_and_detached(store) -> None:
    case = new_id()
    requirement = await _add(store, case, "Who?")
    first = StoredAttachment(kind="trend", id="t0")
    for n in range(MAX_ATTACHMENTS):
        att = StoredAttachment(kind="trend", id=f"t{n}")
        await store.update(case, lambda b, att=att: with_attachment(b, requirement, att, "a", NOW))
    await store.update(case, lambda b: with_attachment(b, requirement, first, "a", NOW))
    assert len((await store.get(case)).requirements[0].attachments) == MAX_ATTACHMENTS
    with pytest.raises(TooManyAttachmentsError):
        await store.update(
            case,
            lambda b: with_attachment(
                b, requirement, StoredAttachment(kind="view", id="v"), "a", NOW
            ),
        )
    await store.update(case, lambda b: without_attachment(b, requirement, first, "a", NOW))
    assert first not in (await store.get(case)).requirements[0].attachments


async def test_connecting_twice_is_harmless_and_keeps_what_was_stored(store) -> None:
    case = new_id()
    await _add(store, case, "Kept")
    again = await CaseBriefStore.connect(PostgresConfig.from_env().dsn)
    try:
        assert [r.text for r in (await again.get(case)).requirements] == ["Kept"]
    finally:
        await again.close()


async def test_an_async_change_sees_what_a_racing_writer_stored_and_they_do_not_interleave(
    store,
) -> None:
    """`update_async` holds the row lock across a change that awaits: twenty at once, each yielding
    before it decides, still leave exactly the twenty-requirement cap, because each saw the brief
    the one before it stored (rule 3's attachment decision depends on exactly this)."""
    case = new_id()

    async def add(n: int) -> str:
        requirement = new_id()

        async def change(brief: StoredBrief) -> StoredBrief:
            await asyncio.sleep(0)  # the decision awaits, as a resolver does
            return with_requirement_added(brief, requirement, f"Requirement {n}", "a", NOW)

        await store.update_async(case, change)
        return requirement

    results = await asyncio.gather(*(add(n) for n in range(30)), return_exceptions=True)
    assert len([r for r in results if isinstance(r, TooManyRequirementsError)]) == 10
    assert len((await store.get(case)).requirements) == MAX_REQUIREMENTS
