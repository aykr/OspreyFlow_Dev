"""Operation Ledger's seed makes the case's screening rule live (step 9d finding 4), against the real
`TypologyRuleStore` on a live Postgres. A3 of the monitoring week (`DEMO_GUIDE.md` §8b) raises its
screening alert when the list is refreshed, and the refresh re-screens with every active
`kyc_screening` rule (`screening_refresh.Rescreen`); the seed never deployed one, so on a seeded
deployment the list update raised nothing until someone deployed it by hand.

What a mistake would do, and the case that catches it:
- the seed leaving the case with no live screening rule, or one the refresh would not run (not
  active, not `kyc_screening`, outside the Ledger's dataset, not after commit) —
  `test_the_seed_deploys_the_screening_rule_from_its_template_as_the_cases_author`;
- a reseed deploying it again, so a list update raises the alert twice —
  `test_a_reseed_keeps_the_one_already_live`;
- a rehearsal's retired rule leaving the next seed with none — `test_a_retired_one_is_deployed_afresh`;
- a rule owned by an account that is not the case's Author, or by the seed's own worker, which no
  identity provider resolves when the refresh runs it as its deployer —
  `test_with_no_author_granted_it_deploys_nothing_and_says_so`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from scripts import seed_ledger_fixture as seed
from services.api.config import PostgresConfig
from services.api.typology_rules import TypologyRuleStore

from conduit_common.identity import new_id
from demo_fixtures import ledger_monitoring
from demo_fixtures.datasets import LEDGER
from schemas.domain import KycScreeningParams, Principal

AUTHOR = "demo-admin-subject"
GRANTS = [f"{AUTHOR}=author", "demo-analyst-subject=editor"]


@pytest.fixture
async def rules() -> AsyncIterator[TypologyRuleStore]:
    store = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
    yield store
    await store.close()


async def _screening(rules: TypologyRuleStore, case: str) -> list[object]:
    return [
        r for r in await rules.list_active_of_typology("kyc_screening") if r.investigation_id == case
    ]


async def test_the_seed_deploys_the_screening_rule_from_its_template_as_the_cases_author(
    rules: TypologyRuleStore,
) -> None:
    case = f"case-{new_id()}"
    said = await seed.deploy_screening_rule(rules, case, GRANTS, clearance="OFFICIAL", org_unit="u")
    (rule,) = await _screening(rules, case)
    assert rule.name == ledger_monitoring.SCREENING_NAME  # type: ignore[attr-defined]
    # The template's defaults, as the Glass's Templates tab deploys it: nothing tuned.
    assert rule.params == KycScreeningParams()  # type: ignore[attr-defined]
    assert (rule.owner_id, rule.dataset_id, rule.trigger, rule.status) == (  # type: ignore[attr-defined]
        AUTHOR, LEDGER.id, "post_commit", "active"
    )
    assert ledger_monitoring.SCREENING_NAME in said and "deployed" in said


async def test_a_reseed_keeps_the_one_already_live(rules: TypologyRuleStore) -> None:
    case = f"case-{new_id()}"
    await seed.deploy_screening_rule(rules, case, GRANTS, clearance="OFFICIAL", org_unit="u")
    said = await seed.deploy_screening_rule(rules, case, GRANTS, clearance="OFFICIAL", org_unit="u")
    assert len(await _screening(rules, case)) == 1
    assert "live already" in said


async def test_a_retired_one_is_deployed_afresh(rules: TypologyRuleStore) -> None:
    case = f"case-{new_id()}"
    await seed.deploy_screening_rule(rules, case, GRANTS, clearance="OFFICIAL", org_unit="u")
    (first,) = await _screening(rules, case)
    author = Principal(id=AUTHOR, clearance="OFFICIAL", org_unit="u", datasets=[LEDGER.id])
    await rules.retire(first.id, case, author)  # type: ignore[attr-defined]
    assert await _screening(rules, case) == []
    await seed.deploy_screening_rule(rules, case, GRANTS, clearance="OFFICIAL", org_unit="u")
    (again,) = await _screening(rules, case)
    assert again.id != first.id  # type: ignore[attr-defined]


async def test_with_no_author_granted_it_deploys_nothing_and_says_so(
    rules: TypologyRuleStore,
) -> None:
    case = f"case-{new_id()}"
    said = await seed.deploy_screening_rule(
        rules, case, ["demo-analyst-subject=editor"], clearance="OFFICIAL", org_unit="u"
    )
    assert await _screening(rules, case) == []
    assert "not deployed" in said and "author" in said.lower()
