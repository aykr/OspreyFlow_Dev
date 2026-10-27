"""The Prison Intelligence seed's brief step — ADR-128 decision 3: "The seed writes it: the priority
requirement from the script's chapter 1, and four requirements, one per clause (who orchestrates the
throw-overs; where and when the packages arrive; how they are organised; what can be done to
disrupt them). It is written as the case's author."

Pure: the step is run over the in-memory brief store of `tests/services/api/case_brief_fakes.py`
and a level-aware stand-in for the case store. What needs the live stack (the same step against
Postgres, as the account the seed grants author: Amendment 4) is the owner's run of the seed.
"""

from __future__ import annotations

from typing import Any

import pytest
from scripts import seed_pid
from services.api.case_brief import MAX_TEXT_CHARS, CaseBriefService
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    InvestigationNotFoundError,
)

from schemas.domain import Principal
from tests.services.api.case_brief_fakes import InMemoryBriefs

AUTHOR = Principal(id="osprey-demo-engineer", clearance="OFFICIAL", org_unit="verify")
EDITOR = Principal(id="an-editor", clearance="OFFICIAL", org_unit="verify")
CASE = "case-pid"


class _Cases:
    """Applies a level as the real store does: none is not-found, too low is insufficient."""

    def __init__(self, held: dict[str, AccessLevel]) -> None:
        self.held = held

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Any:
        level = self.held.get(principal.id)
        if investigation_id != CASE or level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError(need.value)
        return object()


def _service() -> tuple[CaseBriefService, InMemoryBriefs]:
    store = InMemoryBriefs()
    return CaseBriefService(store, {}), store


# --- what the brief says ----------------------------------------------------------------------


def test_the_priority_is_the_scripts_sentence_and_the_requirements_are_its_four_clauses() -> None:
    """One requirement per clause, in the script's order, each a question the case answers."""
    clauses = (
        ("orchestrat", "throw-over"),
        ("where", "when", "packages"),
        ("how", "organised"),
        ("disrupt",),
    )
    assert len(seed_pid.BRIEF_REQUIREMENTS) == 4
    for text, words in zip(seed_pid.BRIEF_REQUIREMENTS, clauses, strict=True):
        assert all(w in text.lower() for w in words), (text, words)
        assert text.endswith("?")
    priority = seed_pid.BRIEF_PRIORITY.lower()
    for words in clauses:
        assert all(w in priority for w in words), (seed_pid.BRIEF_PRIORITY, words)


def test_every_text_is_within_the_brief_limit_and_spelt_in_british_english() -> None:
    for text in (seed_pid.BRIEF_PRIORITY, *seed_pid.BRIEF_REQUIREMENTS):
        assert 0 < len(text) <= MAX_TEXT_CHARS
        assert "organized" not in text.lower() and "organization" not in text.lower()


# --- the step -------------------------------------------------------------------------------


async def test_the_step_writes_the_priority_and_the_four_requirements_open_as_the_author() -> None:
    service, store = _service()
    summary = await seed_pid.seed_brief(service, CASE, AUTHOR)
    stored = store.rows[CASE]
    assert stored.priority == seed_pid.BRIEF_PRIORITY
    assert [r.text for r in stored.requirements] == list(seed_pid.BRIEF_REQUIREMENTS)
    assert all(r.status == "open" for r in stored.requirements), "the seed marks nothing answered"
    assert all(r.attachments == [] for r in stored.requirements)
    assert stored.updated_by == AUTHOR.id
    assert summary.written is True and summary.requirements == 4 and summary.ok


async def test_a_second_run_adds_nothing_and_says_the_brief_was_left_alone() -> None:
    service, store = _service()
    await seed_pid.seed_brief(service, CASE, AUTHOR)
    first = store.rows[CASE].model_dump_json()
    again = await seed_pid.seed_brief(service, CASE, AUTHOR)
    assert store.rows[CASE].model_dump_json() == first
    assert again.written is False and again.ok and again.requirements == 4


async def test_an_analysts_own_brief_is_left_alone_even_when_it_differs() -> None:
    service, store = _service()
    await service.set_priority(CASE, AUTHOR, "Our own question")
    await service.add_requirement(CASE, AUTHOR, "Our own requirement")
    before = store.rows[CASE].model_dump_json()
    summary = await seed_pid.seed_brief(service, CASE, AUTHOR)
    assert store.rows[CASE].model_dump_json() == before
    assert summary.written is False and summary.ok


async def test_a_requirement_an_analyst_marked_answered_stays_answered_after_a_second_seed() -> (
    None
):
    service, store = _service()
    await seed_pid.seed_brief(service, CASE, AUTHOR)
    first = store.rows[CASE].requirements[0].id
    await service.set_status(CASE, first, AUTHOR, "answered")
    await seed_pid.seed_brief(service, CASE, AUTHOR)
    assert store.rows[CASE].requirements[0].status == "answered"


# --- as the case's author -------------------------------------------------------------------


async def test_the_step_is_taken_only_by_the_cases_author() -> None:
    await seed_pid.require_author(_Cases({AUTHOR.id: AccessLevel.AUTHOR}), CASE, AUTHOR)


@pytest.mark.parametrize(
    ("held", "who"),
    [
        ({"an-editor": AccessLevel.EDITOR}, EDITOR),
        ({"an-editor": AccessLevel.VIEWER}, EDITOR),
        ({}, EDITOR),
    ],
    ids=["editor", "viewer", "no level"],
)
async def test_a_persona_who_is_not_the_author_is_refused_by_name_before_anything_is_written(
    held: dict[str, AccessLevel], who: Principal
) -> None:
    """The brief is the Author's to write. A seed run with an account that is not the case's Author
    (the case was made by someone else, `--investigation-scope` named another) stops with a refusal
    saying so, rather than writing through the store as someone with no standing."""
    with pytest.raises(seed_pid.SeedRefusal) as refused:
        await seed_pid.require_author(_Cases(held), CASE, who)
    assert who.id in str(refused.value) and "Author" in str(refused.value)


# --- who writes it on a real deployment (ADR-128 Amendment 4) -----------------------------------

#: The grants `seed_internal` passes, by ADR-113 decision 8: the admin authors the case and the data
#: engineer, who runs the seed, edits it.
ADMIN_SUB = "sub-demo-admin"
ENGINEER_SUB = "sub-demo-engineer"
PACK_GRANTS = [
    f"{ADMIN_SUB}=author",
    "sub-demo-analyst=editor",
    f"{ENGINEER_SUB}=editor",
    "sub-demo-report-viewer=viewer",
]
PACK_LEVELS = {
    ADMIN_SUB: AccessLevel.AUTHOR,
    "sub-demo-analyst": AccessLevel.EDITOR,
    ENGINEER_SUB: AccessLevel.EDITOR,
    "sub-demo-report-viewer": AccessLevel.VIEWER,
}


async def test_under_the_packs_grants_the_brief_is_written_as_the_account_granted_author() -> None:
    """Found installing the pack on the owner's deployment: the seed runs as the engineer, whom the
    pack makes an Editor, so the brief step refused and the install stopped. The brief is written
    as the account the seed's own grants make Author, and that account passes the Author check."""
    engineer = seed_pid.engineer("verify", ENGINEER_SUB)
    author = seed_pid.brief_author(PACK_GRANTS, engineer)
    assert author.id == ADMIN_SUB
    assert author.roles == []
    await seed_pid.require_author(_Cases(PACK_LEVELS), CASE, author)
    with pytest.raises(seed_pid.SeedRefusal):
        await seed_pid.require_author(_Cases(PACK_LEVELS), CASE, engineer)


def test_with_no_author_granted_the_seeder_who_made_the_case_writes_it() -> None:
    """A seed with no grants (the local stack, no identity provider) makes the case as the seeder,
    who is its Author."""
    engineer = seed_pid.engineer("verify")
    assert seed_pid.brief_author([f"{ENGINEER_SUB}=editor"], engineer) == engineer


def test_two_accounts_granted_author_are_refused_by_name_rather_than_one_guessed() -> None:
    with pytest.raises(seed_pid.SeedRefusal) as refused:
        seed_pid.brief_author(["a=author", "b=author"], seed_pid.engineer("verify"))
    assert "a" in str(refused.value) and "b" in str(refused.value)


def test_a_refusal_of_the_brief_is_one_the_seed_prints_by_name() -> None:
    assert seed_pid.SeedRefusal in seed_pid.REFUSALS


# --- what it prints -------------------------------------------------------------------------


def test_the_lines_say_what_was_written_and_what_was_left_alone() -> None:
    written = seed_pid.brief_lines(
        seed_pid.BriefSummary(written=True, requirements=4, ok=True), AUTHOR.id
    )
    left = seed_pid.brief_lines(
        seed_pid.BriefSummary(written=False, requirements=4, ok=True), AUTHOR.id
    )
    assert any("written" in line and AUTHOR.id in line and "4" in line for line in written)
    assert any("left alone" in line for line in left)
    assert not any("FAILED" in line for line in written + left)


def test_a_brief_that_is_not_there_fails_its_check_and_the_seeds_exit() -> None:
    summary = seed_pid.BriefSummary(written=False, requirements=0, ok=False)
    lines = seed_pid.brief_lines(summary, AUTHOR.id)
    assert any("check FAILED" in line for line in lines)
    assert seed_pid.exit_code(files_ok=True, pictures_ok=True, demo_ok=True, brief_ok=False) == 1
    assert seed_pid.exit_code(files_ok=True, pictures_ok=True, demo_ok=True, brief_ok=True) == 0
    assert seed_pid.exit_code(files_ok=True, pictures_ok=True, demo_ok=True) == 0


async def test_the_summary_is_read_back_from_the_store_and_not_assumed() -> None:
    """A step that reports 'written' must have read the brief back: with a store that silently
    drops the write the check fails, as the seed's pictures and inferred links' checks do."""

    class Forgetful:
        async def seed_if_empty(self, *args: Any) -> bool:
            return True

        async def read(self, investigation_id: str, principal: Principal) -> Any:
            from services.api.case_brief import CaseBrief

            return CaseBrief()

    summary = await seed_pid.seed_brief(Forgetful(), CASE, AUTHOR)  # type: ignore[arg-type]
    assert summary.written is True
    assert summary.ok is False and summary.requirements == 0
