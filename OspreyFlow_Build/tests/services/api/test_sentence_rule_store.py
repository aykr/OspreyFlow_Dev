"""Sentence rules in `TypologyRuleStore`, against live Postgres (`spec/06_DECISIONS.md` ADR-133
decision 1, stage (b)): a sentence deployed for the whole deployment watches every case's loads and
belongs to no one case's dataset; one deployed for a case watches that case only; and the stored
sentence reads back as written.

What a mistake would do, and the case that catches it:
- a deployment-wide rule watching only the case it was written in, or a case rule watching every
  case — `test_a_deployment_wide_sentence_watches_every_case_and_a_case_sentence_its_own`;
- a deployment-wide rule hidden from a case outside the author's dataset —
  `test_a_deployment_wide_sentence_is_listed_in_every_cases_reach`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from services.api.config import PostgresConfig
from services.api.typology_rules import TypologyRuleStore

from conduit_common.identity import new_id
from schemas.domain import Principal, TypologyRuleInput
from schemas.sentences import RuleSentence, SentenceRuleParams

ADMIN = Principal(id="admin", clearance="OFFICIAL", org_unit="unit-1", datasets=["ds-a"])
READER_B = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=["ds-b"])


@pytest.fixture
async def store() -> AsyncIterator[TypologyRuleStore]:
    rules = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
    yield rules
    await rules.close()


def _input(scope: str, name: str) -> TypologyRuleInput:
    sentence = RuleSentence.model_validate({"subject": "Person", "scope": scope, "severity": "high"})
    return TypologyRuleInput(name=name, params=SentenceRuleParams(pattern_id="p", sentence=sentence))


async def test_a_deployment_wide_sentence_watches_every_case_and_a_case_sentence_its_own(
    store: TypologyRuleStore,
) -> None:
    case_a, case_b = new_id(), new_id()
    wide = await store.create(ADMIN, case_a, _input("deployment", "Everywhere"))
    own = await store.create(ADMIN, case_a, _input("this_case", "Here"))
    in_b = {r.id for r in await store.list_active_for_case(case_b)}
    in_a = {r.id for r in await store.list_active_for_case(case_a)}
    assert wide.id in in_b and own.id not in in_b
    assert {wide.id, own.id} <= in_a
    assert (wide.dataset_id, own.dataset_id) == (None, "ds-a")
    await store.retire(wide.id, case_a, ADMIN)
    assert wide.id not in {r.id for r in await store.list_active_for_case(case_b)}


async def test_a_deployment_wide_sentence_is_listed_in_every_cases_reach(store: TypologyRuleStore) -> None:
    case_a, case_b = new_id(), new_id()
    wide = await store.create(ADMIN, case_a, _input("deployment", "Everywhere"))
    listed = await store.list_for_case(case_b, READER_B)
    (read,) = [r for r in listed if r.id == wide.id]
    assert isinstance(read.params, SentenceRuleParams)
    assert (read.params.sentence.scope, read.params.sentence.severity) == ("deployment", "high")
    await store.retire(wide.id, case_a, ADMIN)
