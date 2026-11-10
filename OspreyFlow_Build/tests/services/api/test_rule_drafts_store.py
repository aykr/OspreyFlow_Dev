"""The rule editor's draft, *Test* and *Make live* in `TypologyRuleStore` against live Postgres
(`spec/06_DECISIONS.md` ADR-146 decision 3 and Amendment 6, L2.11): a rule names one dataset, fixed
once saved; a draft never runs; a rule cannot go live untested; with a second-person policy it goes
live only on another person's approval; every saved version keeps its `.bpmn` and `.dmn` beside it.

What a mistake would do, and the case that catches it:
- a draft evaluated, or saved without its files: `test_a_saved_draft_never_runs_and_keeps_its_files`;
- a rule moved to another dataset: `test_a_rules_dataset_is_fixed_once_saved`;
- a rule live untested, or live on a test of an older draft:
  `test_a_draft_cannot_go_live_untested_nor_on_an_older_drafts_test`;
- a second-person policy ignored, or the author approving their own:
  `test_with_a_second_person_policy_a_rule_goes_live_only_on_another_persons_approval`;
- a live rule changed before its draft goes live: `test_a_draft_of_a_live_rule_leaves_it_running_as_it_stood`;
- a sent-back rule thrown away: `test_a_make_live_sent_back_returns_to_its_draft`;
- two drafts of one rule: `test_saving_again_replaces_the_one_draft`;
- a test kept on a draft saved again while it ran: `test_a_test_of_a_draft_saved_again_meanwhile_is_refused`;
- a refresh starting a draft or another list's rule: `test_a_list_refresh_reads_only_the_running_rules_that_name_that_list`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from conduit_common.identity import new_id
from schemas.domain import Principal, TypologyRuleInput
from schemas.sentences import RuleSentence, SentenceRuleParams
from services.api.config import PostgresConfig
from services.api.typology_rules import (
    OwnChangeRefused,
    RuleChangeRefused,
    RuleDatasetFixed,
    RuleFiles,
    RuleUntested,
    TypologyRuleStore,
)

AUTHOR = Principal(id="author", clearance="OFFICIAL", org_unit="unit-1", datasets=["ds-a"])
CHECKER = Principal(id="checker", clearance="OFFICIAL", org_unit="unit-1", datasets=["ds-a"])
FILES = RuleFiles(bpmn=b"<definitions>one</definitions>", dmn=b"<definitions>table</definitions>")


@pytest.fixture
async def store() -> AsyncIterator[TypologyRuleStore]:
    rules = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
    yield rules
    await rules.close()


def _input(name: str, severity: str = "high") -> TypologyRuleInput:
    sentence = RuleSentence.model_validate({"subject": "Person", "severity": severity})
    return TypologyRuleInput(name=name, params=SentenceRuleParams(pattern_id="p", sentence=sentence))


async def _active(store: TypologyRuleStore, case: str) -> set[str]:
    return {r.id for r in await store.list_active_for_case(case)}


async def _tested_draft(store: TypologyRuleStore, case: str, name: str = "Rule") -> str:
    rule = await store.save_draft(AUTHOR, case, _input(name), dataset_id="ds-a", files=FILES)
    draft = await store.draft(rule.id, case, AUTHOR)
    assert draft is not None
    await store.record_test(
        rule.id, case, AUTHOR, version=draft.version, saved_at=draft.proposed_at, days=30,
        would_raise=3,
    )  # fmt: skip
    return rule.id


async def test_a_saved_draft_never_runs_and_keeps_its_files(store: TypologyRuleStore) -> None:
    case = new_id()
    rule = await store.save_draft(AUTHOR, case, _input("New"), dataset_id="ds-a", files=FILES)
    assert (rule.status, rule.dataset_id) == ("draft", "ds-a")
    assert rule.id not in await _active(store, case)
    draft = await store.draft(rule.id, case, AUTHOR)
    assert draft is not None and (draft.status, draft.action) == ("draft", "deploy")
    assert await store.rule_files(rule.id, draft.version) == FILES


async def test_a_rules_dataset_is_fixed_once_saved(store: TypologyRuleStore) -> None:
    case = new_id()
    rule = await store.save_draft(AUTHOR, case, _input("Fixed"), dataset_id="ds-a", files=FILES)
    with pytest.raises(RuleDatasetFixed, match="never changed"):
        await store.save_draft(
            AUTHOR, case, _input("Fixed"), dataset_id="ds-b", files=FILES, rule_id=rule.id
        )
    same = await store.save_draft(
        AUTHOR, case, _input("Fixed again"), dataset_id="ds-a", files=FILES, rule_id=rule.id
    )
    assert same.dataset_id == "ds-a"


async def test_a_draft_cannot_go_live_untested_nor_on_an_older_drafts_test(
    store: TypologyRuleStore,
) -> None:
    case = new_id()
    rule = await store.save_draft(AUTHOR, case, _input("Untested"), dataset_id="ds-a", files=FILES)
    with pytest.raises(RuleUntested, match="tested"):
        await store.make_live(rule.id, case, AUTHOR, second_person=False)
    draft = await store.draft(rule.id, case, AUTHOR)
    assert draft is not None
    await store.record_test(
        rule.id, case, AUTHOR, version=draft.version, saved_at=draft.proposed_at, days=30,
        would_raise=1,
    )  # fmt: skip
    await store.save_draft(
        AUTHOR, case, _input("Untested", "low"), dataset_id="ds-a", files=FILES, rule_id=rule.id
    )
    with pytest.raises(RuleUntested, match="tested"):
        await store.make_live(rule.id, case, AUTHOR, second_person=False)
    assert rule.id not in await _active(store, case)


async def test_a_tested_draft_goes_live_at_once_without_a_second_person_policy(
    store: TypologyRuleStore,
) -> None:
    case = new_id()
    rule_id = await _tested_draft(store, case)
    live = await store.make_live(rule_id, case, AUTHOR, second_person=False)
    assert (live.status, live.pending_action) == ("active", None)
    assert rule_id in await _active(store, case)
    assert await store.draft(rule_id, case, AUTHOR) is None
    (version,) = await store.versions(rule_id, case, AUTHOR)
    assert (version.status, version.would_raise, version.tested_days) == ("applied", 3, 30)


async def test_with_a_second_person_policy_a_rule_goes_live_only_on_another_persons_approval(
    store: TypologyRuleStore,
) -> None:
    case = new_id()
    rule_id = await _tested_draft(store, case)
    waiting = await store.make_live(rule_id, case, AUTHOR, second_person=True)
    assert (waiting.status, waiting.pending_action, waiting.pending_by) == (
        "draft", "deploy", "author")  # fmt: skip
    assert rule_id not in await _active(store, case)
    with pytest.raises(OwnChangeRefused, match="a second person"):
        await store.approve(rule_id, case, AUTHOR)
    approved = await store.approve(rule_id, case, CHECKER)
    assert approved.status == "active"
    assert rule_id in await _active(store, case)


async def test_a_draft_of_a_live_rule_leaves_it_running_as_it_stood(
    store: TypologyRuleStore,
) -> None:
    case = new_id()
    rule_id = await _tested_draft(store, case, "Running")
    await store.make_live(rule_id, case, AUTHOR, second_person=False)
    changed = await store.save_draft(
        AUTHOR, case, _input("Running, changed", "low"), dataset_id="ds-a", files=FILES,
        rule_id=rule_id,
    )  # fmt: skip
    assert (changed.status, changed.name) == ("active", "Running")
    draft = await store.draft(rule_id, case, AUTHOR)
    assert draft is not None and (draft.action, draft.name) == ("change", "Running, changed")
    await store.record_test(
        rule_id, case, AUTHOR, version=draft.version, saved_at=draft.proposed_at, days=30,
        would_raise=0,
    )  # fmt: skip
    live = await store.make_live(rule_id, case, AUTHOR, second_person=False)
    assert (live.status, live.name, live.version) == ("active", "Running, changed", draft.version)


async def test_a_make_live_sent_back_returns_to_its_draft(store: TypologyRuleStore) -> None:
    case = new_id()
    rule_id = await _tested_draft(store, case, "Sent back")
    await store.make_live(rule_id, case, AUTHOR, second_person=True)
    back = await store.reject(rule_id, case, CHECKER, "the threshold is too low")
    assert (back.status, back.pending_action) == ("draft", None)
    draft = await store.draft(rule_id, case, AUTHOR)
    assert draft is not None and (draft.status, draft.words) == ("draft", "the threshold is too low")


async def test_saving_again_replaces_the_one_draft(store: TypologyRuleStore) -> None:
    case = new_id()
    rule = await store.save_draft(AUTHOR, case, _input("One"), dataset_id="ds-a", files=FILES)
    other = RuleFiles(bpmn=b"<definitions>two</definitions>", dmn=FILES.dmn)
    await store.save_draft(
        AUTHOR, case, _input("One", "low"), dataset_id="ds-a", files=other, rule_id=rule.id
    )
    drafts = [v for v in await store.versions(rule.id, case, AUTHOR) if v.status == "draft"]
    assert len(drafts) == 1
    assert await store.rule_files(rule.id, drafts[0].version) == other


async def test_a_retired_rule_takes_no_draft(store: TypologyRuleStore) -> None:
    case = new_id()
    rule_id = await _tested_draft(store, case, "Gone")
    await store.make_live(rule_id, case, AUTHOR, second_person=False)
    await store.retire(rule_id, case, AUTHOR)
    with pytest.raises(RuleChangeRefused, match="retired"):
        await store.save_draft(
            AUTHOR, case, _input("Gone"), dataset_id="ds-a", files=FILES, rule_id=rule_id
        )


async def test_a_test_of_a_draft_saved_again_meanwhile_is_refused(store: TypologyRuleStore) -> None:
    case = new_id()
    rule = await store.save_draft(AUTHOR, case, _input("Raced"), dataset_id="ds-a", files=FILES)
    tested = await store.draft(rule.id, case, AUTHOR)
    assert tested is not None
    await store.save_draft(
        AUTHOR, case, _input("Raced", "low"), dataset_id="ds-a", files=FILES, rule_id=rule.id
    )
    with pytest.raises(RuleChangeRefused, match="saved again"):
        await store.record_test(
            rule.id, case, AUTHOR, version=tested.version, saved_at=tested.proposed_at, days=30,
            would_raise=2,
        )  # fmt: skip


async def test_a_list_refresh_reads_only_the_running_rules_that_name_that_list(
    store: TypologyRuleStore,
) -> None:
    """ADR-146 decision 3: `list_refresh_rules` is what a refresh starts. A draft never runs, and a
    rule naming another list is not this one's."""
    case, list_id = new_id(), f"l-{new_id()}"

    def on_list(name: str, listed: str) -> TypologyRuleInput:
        sentence = RuleSentence.model_validate({
            "subject": "Person", "runs": "list_refresh",
            "relationship": {"kind": "on_screening_list", "list_id": listed}})  # fmt: skip
        return TypologyRuleInput(name=name, params=SentenceRuleParams(pattern_id="p", sentence=sentence),
                                 trigger="list_refresh")  # fmt: skip

    async def live(spec: TypologyRuleInput) -> str:
        rule = await store.save_draft(AUTHOR, case, spec, dataset_id="ds-a", files=FILES)
        draft = await store.draft(rule.id, case, AUTHOR)
        assert draft is not None
        await store.record_test(rule.id, case, AUTHOR, version=draft.version, saved_at=draft.proposed_at,
                                days=30, would_raise=0)  # fmt: skip
        await store.make_live(rule.id, case, AUTHOR, second_person=False)
        return rule.id

    running = await live(on_list("Listed visitors", list_id))
    other = await live(on_list("Another list's", f"l-{new_id()}"))
    draft = await store.save_draft(AUTHOR, case, on_list("Not yet live", list_id), dataset_id="ds-a", files=FILES)
    found = {r.id for r in await store.list_refresh_rules(list_id)}
    assert running in found and other not in found and draft.id not in found
