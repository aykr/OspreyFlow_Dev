"""The case brief — `06_DECISIONS.md` ADR-128 decision 3. The service's own rules, over an in-memory
store that applies the very transitions the Postgres store applies (so the rules cannot differ
between the two), and over resolvers that refuse what the real ones refuse; the real Postgres store
has its own file (`test_case_brief_store.py`, owner-run like the other store tests).

The sentences under test:

* **Rule 3.** An attachment the reader may not read is left out entirely: no title, no placeholder,
  no count. The reader's whole response equals the response for a brief that never had it.
* **Rule 5.** A requirement is marked answered only by a person's request to the status route.
* A brief holds at most twenty requirements, each at most ten attachments, and a refusal says so
  (`CLAUDE.md` rule 2: nothing is cut silently).
* An attachment is attached only by someone who may read it, and an id that does not exist and one
  that may not be read are refused in the same words.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from services.api.case_brief import (
    MAX_ATTACHMENTS,
    MAX_REQUIREMENTS,
    MAX_TEXT_CHARS,
    AttachmentNotFoundError,
    CaseBrief,
    CaseBriefService,
    InvalidBriefTextError,
    RequirementNotFoundError,
    StoredAttachment,
    StoredBrief,
    TooManyAttachmentsError,
    TooManyRequirementsError,
    with_attachment,
)

from schemas.domain import Principal

from .case_brief_fakes import AsyncUpdate, InMemoryBriefs, Update
from .case_brief_fakes import make_service as _service

AUTHOR = Principal(id="author-1", clearance="OFFICIAL", org_unit="unit-1")
READER = Principal(id="reader-1", clearance="OFFICIAL", org_unit="unit-1")
CASE = "case-1"


async def test_a_case_with_no_brief_reads_as_an_empty_one() -> None:
    service, _, _ = _service()
    brief = await service.read(CASE, READER)
    assert brief == CaseBrief(priority="", requirements=[])


async def test_the_priority_requirement_is_one_text_set_and_changed_by_the_author() -> None:
    service, _, _ = _service()
    await service.set_priority(CASE, AUTHOR, "  Who is orchestrating the throw-overs?  ")
    assert (await service.read(CASE, READER)).priority == "Who is orchestrating the throw-overs?"
    await service.set_priority(CASE, AUTHOR, "Where do the packages arrive?")
    assert (await service.read(CASE, READER)).priority == "Where do the packages arrive?"


async def test_the_priority_can_be_cleared_with_an_empty_text() -> None:
    service, _, _ = _service()
    await service.set_priority(CASE, AUTHOR, "Something")
    await service.set_priority(CASE, AUTHOR, "   ")
    assert (await service.read(CASE, READER)).priority == ""


async def test_requirements_come_back_in_the_order_they_were_added_each_open() -> None:
    service, _, _ = _service()
    await service.add_requirement(CASE, AUTHOR, "Who orchestrates?")
    await service.add_requirement(CASE, AUTHOR, "Where and when?")
    brief = await service.read(CASE, READER)
    assert [(r.id, r.text, r.status) for r in brief.requirements] == [
        ("req-1", "Who orchestrates?", "open"),
        ("req-2", "Where and when?", "open"),
    ]
    assert all(r.attachments == [] and r.answered_at is None for r in brief.requirements)


async def test_a_twenty_first_requirement_is_refused_stating_the_limit_and_keeps_the_twenty() -> (
    None
):
    """Rule 2: the brief never drops or cuts a requirement silently. The refusal names the limit."""
    service, _, _ = _service()
    for n in range(MAX_REQUIREMENTS):
        await service.add_requirement(CASE, AUTHOR, f"Requirement {n}")
    with pytest.raises(TooManyRequirementsError) as refused:
        await service.add_requirement(CASE, AUTHOR, "One too many")
    assert MAX_REQUIREMENTS == 20
    assert "20" in str(refused.value)
    brief = await service.read(CASE, READER)
    assert [r.text for r in brief.requirements] == [f"Requirement {n}" for n in range(20)]


async def test_a_text_over_the_limit_is_refused_not_cut_and_an_empty_requirement_is_refused() -> (
    None
):
    service, _, _ = _service()
    with pytest.raises(InvalidBriefTextError) as long:
        await service.add_requirement(CASE, AUTHOR, "x" * (MAX_TEXT_CHARS + 1))
    assert str(MAX_TEXT_CHARS) in str(long.value)
    with pytest.raises(InvalidBriefTextError):
        await service.add_requirement(CASE, AUTHOR, "   ")
    with pytest.raises(InvalidBriefTextError):
        await service.set_priority(CASE, AUTHOR, "y" * (MAX_TEXT_CHARS + 1))
    assert (await service.read(CASE, READER)).requirements == []
    added = await service.add_requirement(CASE, AUTHOR, "z" * MAX_TEXT_CHARS)
    requirement_id = added.requirements[0].id
    with pytest.raises(InvalidBriefTextError):
        await service.edit_requirement(CASE, requirement_id, AUTHOR, "")
    assert (await service.read(CASE, READER)).requirements[0].text == "z" * MAX_TEXT_CHARS


async def test_a_requirements_text_is_edited_and_an_unknown_one_is_refused() -> None:
    service, _, _ = _service()
    await service.add_requirement(CASE, AUTHOR, "Draft")
    await service.edit_requirement(CASE, "req-1", AUTHOR, "  Final  ")
    assert (await service.read(CASE, READER)).requirements[0].text == "Final"
    with pytest.raises(RequirementNotFoundError):
        await service.edit_requirement(CASE, "nope", AUTHOR, "x")


async def test_a_requirement_is_marked_answered_by_a_person_and_reopened() -> None:
    service, _, _ = _service()
    await service.add_requirement(CASE, AUTHOR, "Who?")
    answered = await service.set_status(CASE, "req-1", AUTHOR, "answered")
    assert answered.requirements[0].status == "answered"
    assert answered.requirements[0].answered_at is not None
    reopened = await service.set_status(CASE, "req-1", AUTHOR, "open")
    assert reopened.requirements[0].status == "open"
    assert reopened.requirements[0].answered_at is None
    with pytest.raises(RequirementNotFoundError):
        await service.set_status(CASE, "nope", AUTHOR, "answered")


async def test_editing_a_requirements_text_does_not_change_its_status() -> None:
    service, _, _ = _service()
    await service.add_requirement(CASE, AUTHOR, "Who?")
    await service.set_status(CASE, "req-1", AUTHOR, "answered")
    await service.edit_requirement(CASE, "req-1", AUTHOR, "Who, exactly?")
    assert (await service.read(CASE, READER)).requirements[0].status == "answered"


async def test_a_requirement_is_removed_with_its_attachments() -> None:
    service, store, readable = _service()
    readable.allow("trend", "t1", "Throw-overs by week", AUTHOR)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    await service.add_requirement(CASE, AUTHOR, "Where?")
    await service.attach(CASE, "req-1", AUTHOR, "trend", "t1")
    await service.remove_requirement(CASE, "req-1", AUTHOR)
    brief = await service.read(CASE, AUTHOR)
    assert [r.id for r in brief.requirements] == ["req-2"]
    assert "t1" not in store.rows[CASE].model_dump_json()
    with pytest.raises(RequirementNotFoundError):
        await service.remove_requirement(CASE, "req-1", AUTHOR)


async def test_a_requirement_of_another_case_is_not_found_here() -> None:
    service, _, _ = _service()
    await service.add_requirement("case-2", AUTHOR, "Elsewhere")
    with pytest.raises(RequirementNotFoundError):
        await service.edit_requirement(CASE, "req-1", AUTHOR, "x")
    with pytest.raises(RequirementNotFoundError):
        await service.set_status(CASE, "req-1", AUTHOR, "answered")
    with pytest.raises(RequirementNotFoundError):
        await service.remove_requirement(CASE, "req-1", AUTHOR)
    assert [r.text for r in (await service.read("case-2", AUTHOR)).requirements] == ["Elsewhere"]


# --- attachments ----------------------------------------------------------------------------


async def test_an_attachment_a_reader_may_read_is_shown_with_its_title_in_the_order_attached() -> (
    None
):
    service, _, readable = _service()
    readable.allow("trend", "t1", "Throw-overs by week", AUTHOR, READER)
    readable.allow("assessment", "j1", "The wing's organiser", AUTHOR, READER)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    await service.attach(CASE, "req-1", AUTHOR, "trend", "t1")
    await service.attach(CASE, "req-1", AUTHOR, "assessment", "j1")
    shown = (await service.read(CASE, READER)).requirements[0].attachments
    assert [(a.kind, a.id, a.title) for a in shown] == [
        ("trend", "t1", "Throw-overs by week"),
        ("assessment", "j1", "The wing's organiser"),
    ]


async def test_all_four_kinds_can_be_attached() -> None:
    service, _, readable = _service()
    for kind in ("trend", "pattern", "assessment", "view"):
        readable.allow(kind, f"{kind}-1", f"A {kind}", AUTHOR)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    for kind in ("trend", "pattern", "assessment", "view"):
        await service.attach(CASE, "req-1", AUTHOR, kind, f"{kind}-1")  # type: ignore[arg-type]
    shown = (await service.read(CASE, AUTHOR)).requirements[0].attachments
    assert [a.kind for a in shown] == ["trend", "pattern", "assessment", "view"]


async def test_attaching_the_same_thing_twice_holds_it_once() -> None:
    service, store, readable = _service()
    readable.allow("trend", "t1", "T", AUTHOR)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    await service.attach(CASE, "req-1", AUTHOR, "trend", "t1")
    await service.attach(CASE, "req-1", AUTHOR, "trend", "t1")
    assert len(store.rows[CASE].requirements[0].attachments) == 1


async def test_the_same_id_of_another_kind_is_another_attachment() -> None:
    service, store, readable = _service()
    readable.allow("trend", "x", "T", AUTHOR)
    readable.allow("pattern", "x", "P", AUTHOR)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    await service.attach(CASE, "req-1", AUTHOR, "trend", "x")
    await service.attach(CASE, "req-1", AUTHOR, "pattern", "x")
    assert len(store.rows[CASE].requirements[0].attachments) == 2


async def test_an_attachment_over_the_limit_is_refused_stating_the_limit() -> None:
    service, store, readable = _service()
    await service.add_requirement(CASE, AUTHOR, "Who?")
    for n in range(MAX_ATTACHMENTS):
        readable.allow("trend", f"t{n}", f"Trend {n}", AUTHOR)
        await service.attach(CASE, "req-1", AUTHOR, "trend", f"t{n}")
    readable.allow("trend", "extra", "Extra", AUTHOR)
    with pytest.raises(TooManyAttachmentsError) as refused:
        await service.attach(CASE, "req-1", AUTHOR, "trend", "extra")
    assert str(MAX_ATTACHMENTS) in str(refused.value)
    assert len(store.rows[CASE].requirements[0].attachments) == MAX_ATTACHMENTS


async def test_the_attachment_limit_counts_only_what_the_caller_can_see() -> None:
    """Rule 3 on the write path: a refusal for "too many" must not reveal attachments the caller
    cannot read. Ten attachments only the author may read leave a reader who sees none free to
    attach their own, and what they are refused is decided by what they can see alone."""
    service, store, readable = _service()
    await service.add_requirement(CASE, AUTHOR, "Who?")
    for n in range(MAX_ATTACHMENTS):
        readable.allow("trend", f"t{n}", f"Trend {n}", AUTHOR)
        await service.attach(CASE, "req-1", AUTHOR, "trend", f"t{n}")
    readable.allow("trend", "mine", "Mine", READER)
    brief = await service.attach(CASE, "req-1", READER, "trend", "mine")
    assert [a.id for a in brief.requirements[0].attachments] == ["mine"]
    assert len(store.rows[CASE].requirements[0].attachments) == MAX_ATTACHMENTS + 1


async def test_the_limit_still_refuses_a_caller_who_can_see_all_of_them() -> None:
    """The case above is able to fail the other way: ten attachments the caller can see refuse an
    eleventh, even when hidden ones are also present."""
    service, _, readable = _service()
    await service.add_requirement(CASE, AUTHOR, "Who?")
    readable.allow("trend", "hidden", "Hidden", AUTHOR)
    await service.attach(CASE, "req-1", AUTHOR, "trend", "hidden")
    for n in range(MAX_ATTACHMENTS):
        readable.allow("trend", f"t{n}", f"Trend {n}", AUTHOR, READER)
        await service.attach(CASE, "req-1", READER, "trend", f"t{n}")
    readable.allow("trend", "extra", "Extra", READER)
    with pytest.raises(TooManyAttachmentsError):
        await service.attach(CASE, "req-1", READER, "trend", "extra")


async def test_an_attachment_the_author_cannot_read_is_refused_exactly_as_one_that_does_not_exist() -> (
    None
):
    """Rule 3 on the write path: the refusal cannot be used to learn that a pattern of someone
    else's, or a judgement a citation hides, exists."""
    service, store, readable = _service()
    readable.allow("pattern", "someone-elses", "Hidden", READER)  # the author is not its owner
    await service.add_requirement(CASE, AUTHOR, "Who?")
    with pytest.raises(AttachmentNotFoundError) as unreadable:
        await service.attach(CASE, "req-1", AUTHOR, "pattern", "someone-elses")
    with pytest.raises(AttachmentNotFoundError) as absent:
        await service.attach(CASE, "req-1", AUTHOR, "pattern", "no-such-pattern")
    assert str(unreadable.value) == str(absent.value)
    assert type(unreadable.value) is type(absent.value)
    assert store.rows[CASE].requirements[0].attachments == []


async def test_an_unknown_requirement_is_refused_before_the_attachment_is_looked_up() -> None:
    service, _, readable = _service()
    readable.allow("trend", "t1", "T", AUTHOR)
    with pytest.raises(RequirementNotFoundError):
        await service.attach(CASE, "nope", AUTHOR, "trend", "t1")


async def test_the_attachment_is_looked_up_in_the_requests_own_case() -> None:
    service, _, readable = _service()
    readable.allow("trend", "t1", "T", AUTHOR)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    await service.attach(CASE, "req-1", AUTHOR, "trend", "t1")
    assert ("trend", CASE, "t1") in readable.asked


async def test_an_attachment_is_detached_and_detaching_what_is_not_there_changes_nothing() -> None:
    service, store, readable = _service()
    readable.allow("trend", "t1", "T", AUTHOR)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    await service.attach(CASE, "req-1", AUTHOR, "trend", "t1")
    await service.detach(CASE, "req-1", AUTHOR, "trend", "t1")
    assert store.rows[CASE].requirements[0].attachments == []
    await service.detach(CASE, "req-1", AUTHOR, "trend", "t1")
    with pytest.raises(RequirementNotFoundError):
        await service.detach(CASE, "nope", AUTHOR, "trend", "t1")


async def test_detaching_needs_no_read_of_the_attachment() -> None:
    """An attachment an Author can no longer read is still theirs to take off the brief: the
    answer is the same whether it was attached or not."""
    service, store, readable = _service()
    readable.allow("pattern", "p1", "P", AUTHOR)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    await service.attach(CASE, "req-1", AUTHOR, "pattern", "p1")
    readable.revoke("pattern", "p1")
    await service.detach(CASE, "req-1", AUTHOR, "pattern", "p1")
    assert store.rows[CASE].requirements[0].attachments == []


# --- rule 3 ---------------------------------------------------------------------------------


async def _briefs_with_and_without_a_hidden_attachment() -> tuple[
    CaseBriefService, CaseBriefService
]:
    """Two cases' briefs built by the same steps, the first with a pattern only the author may read
    attached to its second requirement, the second without. Same service state otherwise, so the
    requirement ids and the clock agree."""
    with_one, _, readable = _service()
    readable.allow("pattern", "authors-own", "The author's pattern", AUTHOR)
    readable.allow("trend", "shared", "Throw-overs by week", AUTHOR, READER)
    without, _, readable_without = _service()
    readable_without.allow("trend", "shared", "Throw-overs by week", AUTHOR, READER)
    for service in (with_one, without):
        await service.set_priority(CASE, AUTHOR, "Who is orchestrating the throw-overs?")
        await service.add_requirement(CASE, AUTHOR, "Who orchestrates?")
        await service.add_requirement(CASE, AUTHOR, "Where and when?")
        await service.attach(CASE, "req-1", AUTHOR, "trend", "shared")
        await service.set_status(CASE, "req-2", AUTHOR, "answered")
    await with_one.attach(CASE, "req-2", AUTHOR, "pattern", "authors-own")
    return with_one, without


async def test_an_attachment_the_reader_cannot_read_leaves_no_trace_in_the_readers_brief() -> None:
    """Rule 3, the test that fails if a hidden attachment is shown, replaced by a placeholder, or
    counted: the reader's whole response equals the response for a brief without it."""
    with_hidden, without = await _briefs_with_and_without_a_hidden_attachment()
    seen = await with_hidden.read(CASE, READER)
    baseline = await without.read(CASE, READER)
    assert seen == baseline
    assert seen.model_dump_json() == baseline.model_dump_json()
    # What the author reads is different: the attachment is there for the person who may read it.
    authors = await with_hidden.read(CASE, AUTHOR)
    assert [a.title for a in authors.requirements[1].attachments] == ["The author's pattern"]


async def test_the_readers_brief_carries_no_count_of_attachments_and_no_field_of_the_stored_form() -> (
    None
):
    with_hidden, _ = await _briefs_with_and_without_a_hidden_attachment()
    wire = (await with_hidden.read(CASE, READER)).model_dump(mode="json")
    text = str(wire)
    assert "authors-own" not in text and "pattern" not in text and "hidden" not in text.lower()
    assert set(wire) == {"priority", "requirements"}
    assert all(
        set(r) == {"id", "text", "status", "answered_at", "attachments"}
        for r in wire["requirements"]
    )


async def test_an_attachment_revoked_after_it_was_attached_is_dropped_from_the_next_read() -> None:
    """The check is at read time, not at attach time: a pattern whose owner changed, or a judgement
    a citation now hides, vanishes from the reader at once."""
    service, store, readable = _service()
    readable.allow("pattern", "p1", "P", AUTHOR, READER)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    await service.attach(CASE, "req-1", AUTHOR, "pattern", "p1")
    assert len((await service.read(CASE, READER)).requirements[0].attachments) == 1
    readable.revoke("pattern", "p1")
    assert (await service.read(CASE, READER)).requirements[0].attachments == []
    assert (await service.read(CASE, AUTHOR)).requirements[0].attachments == []
    # It is still stored, and comes back for whoever may read it again.
    assert len(store.rows[CASE].requirements[0].attachments) == 1
    readable.allow("pattern", "p1", "P", READER)
    assert len((await service.read(CASE, READER)).requirements[0].attachments) == 1


async def test_an_attachment_whose_target_is_gone_is_dropped_for_everyone() -> None:
    service, _, readable = _service()
    readable.allow("trend", "t1", "T", AUTHOR, READER)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    await service.attach(CASE, "req-1", AUTHOR, "trend", "t1")
    readable.forget("trend", "t1")
    assert (await service.read(CASE, READER)).requirements[0].attachments == []
    assert (await service.read(CASE, AUTHOR)).requirements[0].attachments == []


async def test_a_mutation_returns_the_brief_as_the_person_who_made_it_may_read_it() -> None:
    service, _, readable = _service()
    readable.allow("pattern", "p1", "P", AUTHOR)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    after = await service.attach(CASE, "req-1", AUTHOR, "pattern", "p1")
    assert [a.title for a in after.requirements[0].attachments] == ["P"]
    readable.revoke("pattern", "p1")
    after = await service.edit_requirement(CASE, "req-1", AUTHOR, "Who, then?")
    assert after.requirements[0].attachments == []


# --- the seed's write (ADR-128: the PID's brief is written as its case's author) ---------------


async def test_a_case_with_no_brief_is_given_one_whole_by_the_seed_as_its_author() -> None:
    service, store, _ = _service()
    wrote = await service.seed_if_empty(CASE, AUTHOR, "The priority?", ["One?", "Two?", "Three?"])
    assert wrote is True
    stored = store.rows[CASE]
    assert stored.priority == "The priority?"
    assert [(r.text, r.status, r.attachments) for r in stored.requirements] == [
        ("One?", "open", []),
        ("Two?", "open", []),
        ("Three?", "open", []),
    ]
    assert stored.updated_by == "author-1"
    assert len({r.id for r in stored.requirements}) == 3
    assert all(r.answered_by is None and r.answered_at is None for r in stored.requirements)


async def test_a_second_seed_writes_nothing_and_neither_does_one_over_an_analysts_own_brief() -> (
    None
):
    service, store, _ = _service()
    await service.seed_if_empty(CASE, AUTHOR, "The priority?", ["One?"])
    before = store.rows[CASE].model_dump_json()
    assert await service.seed_if_empty(CASE, AUTHOR, "The priority?", ["One?"]) is False
    assert store.rows[CASE].model_dump_json() == before

    analysts, analysts_store, _ = _service()
    await analysts.set_priority(CASE, AUTHOR, "Mine")
    before = analysts_store.rows[CASE].model_dump_json()
    assert await analysts.seed_if_empty(CASE, AUTHOR, "The priority?", ["One?"]) is False
    assert analysts_store.rows[CASE].model_dump_json() == before


async def test_a_seed_that_cannot_be_written_whole_writes_none_of_it() -> None:
    """Atomic: more than twenty requirements, or one invalid text, leaves the case with no brief
    at all, so a re-run is still a first run and no half-brief is left to be mistaken for an
    analyst's."""
    service, store, _ = _service()
    with pytest.raises(TooManyRequirementsError):
        await service.seed_if_empty(
            CASE, AUTHOR, "P", [f"r{n}" for n in range(MAX_REQUIREMENTS + 1)]
        )
    with pytest.raises(InvalidBriefTextError):
        await service.seed_if_empty(CASE, AUTHOR, "P", ["fine", "  "])
    assert CASE not in store.rows
    assert await service.seed_if_empty(CASE, AUTHOR, "P", ["fine"]) is True


class _RacedBriefs(InMemoryBriefs):
    """Another writer wins the row lock first: just before the first locked update runs, `race`
    changes the stored brief, as a second request would between this one's read and its lock."""

    def __init__(self) -> None:
        super().__init__()
        self._race: Callable[[StoredBrief], StoredBrief] | None = None

    def arm(self, race: Callable[[StoredBrief], StoredBrief]) -> None:
        self._race = race

    def _raced(self, investigation_id: str) -> None:
        if self._race is not None:
            self.rows[investigation_id] = self._race(self.rows[investigation_id])
            self._race = None

    async def update(self, investigation_id: str, change: Update) -> StoredBrief:
        self._raced(investigation_id)
        return await super().update(investigation_id, change)

    async def update_async(self, investigation_id: str, change: AsyncUpdate) -> StoredBrief:
        self._raced(investigation_id)
        return await super().update_async(investigation_id, change)


async def test_the_attachment_limit_is_decided_against_the_brief_the_row_lock_holds() -> None:
    """Rule 3 on the write path, under a race. The reader reads nine attachments they can see;
    before their update takes the row lock the author attaches a tenth that only the author may
    read. What the reader may read must be computed from the brief the lock holds: computed from
    the read before it, the hidden one counts as theirs, the cap is hit and the refusal tells them
    it exists."""
    hidden = StoredAttachment(kind="trend", id="authors-own")
    store = _RacedBriefs()
    service, _, readable = _service(store=store)
    await service.add_requirement(CASE, AUTHOR, "Who?")
    readable.allow("trend", "authors-own", "Authors own", AUTHOR)
    for n in range(MAX_ATTACHMENTS - 1):
        readable.allow("trend", f"t{n}", f"Trend {n}", AUTHOR, READER)
        await service.attach(CASE, "req-1", READER, "trend", f"t{n}")
    readable.allow("trend", "mine", "Mine", READER)
    store.arm(
        lambda b: with_attachment(b, "req-1", hidden, AUTHOR.id, datetime(2026, 10, 26, tzinfo=UTC))
    )
    brief = await service.attach(CASE, "req-1", READER, "trend", "mine")
    assert len(brief.requirements[0].attachments) == MAX_ATTACHMENTS
    assert "authors-own" not in [a.id for a in brief.requirements[0].attachments]
