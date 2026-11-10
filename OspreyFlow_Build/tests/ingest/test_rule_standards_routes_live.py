"""A rule's files to the standards through the real app, the real rules store and real JWT bearer
auth (`spec/06_DECISIONS.md` ADR-146 decision 3; rule 4). Live: it needs the stack's Postgres, so
`make test` leaves it out with the rest of `tests/ingest`.

The offline cases (`tests/services/api/test_rule_standards_routes.py`) prove the routes' logic
over a fake store; this file proves the real store's own refusal, which the export depends on:
the rules list's `WHERE` (`get_listed`, `reach_clause`) finds no rule of another case and none in a
dataset the reader's case does not read, so each is the same 404 as a missing rule (rule 3).

Every rule written here is removed in teardown, its versions first, even when a case fails (the
stacks are shared).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import asyncpg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from rule_standards import to_bpmn, to_dmn
from services.api.config import PostgresConfig
from services.api.investigations import AccessLevel, InvestigationStore
from services.api.typology_rules import TypologyRuleStore

from schemas.domain import Principal, TypologyRuleInput
from schemas.sentences import RuleSentence, SentenceRuleInput, SentenceRuleParams
from tests.conftest import default_claims, sign_token
from tests.services.api.case_dataset import dataset_for, give_case_its_dataset

AUTHOR = Principal(id="rule-standards-author", clearance="OFFICIAL", org_unit="unit-1",
                   roles=["analyst", "rule_author"])  # fmt: skip
VIEWER = "rule-standards-viewer"
SENTENCE = RuleSentence.model_validate({"subject": "Person"})


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    import os

    keys = ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE")
    previous = {k: os.environ.get(k) for k in keys}
    os.environ.update({"OIDC_JWKS_URL": jwks_url, "OIDC_ALGORITHMS": "RS256", "ARCADEDB_DATABASE": "ospreyflow"})
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _as(key: rsa.RSAPrivateKey, sub: str, roles: list[str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(key, default_claims(sub=sub, roles=roles))}"}


async def _world() -> dict[str, str]:
    """Two cases of one unit; the author holds the first only. Three rules: the first case's own,
    the second case's, and one in the first case kept in a dataset the first case does not read."""
    cases = await InvestigationStore.connect(PostgresConfig.from_env().dsn)
    rules = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
    try:
        mine = await cases.create(AUTHOR, name="Rule standards case")
        other = await cases.create(Principal(id="someone-else", clearance="OFFICIAL", org_unit="unit-1"),
                                   name="Another case")  # fmt: skip
        await give_case_its_dataset(mine.id, AUTHOR)
        await give_case_its_dataset(other.id, AUTHOR)
        await cases.set_grant(mine.id, VIEWER, AccessLevel.VIEWER, by=AUTHOR)
        spec = TypologyRuleInput(name="Every person", params=SentenceRuleParams(pattern_id="p", sentence=SENTENCE))
        in_case = AUTHOR.model_copy(update={"datasets": [dataset_for(AUTHOR)]})
        hidden = AUTHOR.model_copy(update={"datasets": ["rule-standards-dataset-not-read"]})
        return {
            "case": mine.id,
            "own": (await rules.create(in_case, mine.id, spec)).id,
            "other": (await rules.create(in_case, other.id, spec)).id,
            "hidden": (await rules.create(hidden, mine.id, spec)).id,
        }
    finally:
        await cases.close()
        await rules.close()


async def _remove(ids: list[str]) -> None:
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await conn.execute("DELETE FROM typology_rule_versions WHERE rule_id = ANY($1::text[])", ids)
        await conn.execute("DELETE FROM typology_rules WHERE id = ANY($1::text[])", ids)
    finally:
        await conn.close()


@pytest.fixture
def world(api_env: None) -> Iterator[dict[str, str]]:
    made = asyncio.run(_world())
    try:
        yield made
    finally:
        asyncio.run(_remove([made["own"], made["other"], made["hidden"]]))


def test_export_reads_through_the_real_rules_lists_reach(
    world: dict[str, str], keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    base = f"/v1/investigations/{world['case']}/rules"
    from services.api.app import app

    with TestClient(app) as client:
        viewer = _as(key, VIEWER, ["analyst"])
        own = client.get(f"{base}/{world['own']}/export.bpmn", headers=viewer)
        assert own.status_code == 200, own.text
        assert f'osprey:rule dataset="{dataset_for(AUTHOR)}"' in own.text
        missing = client.get(f"{base}/no-such-rule/export.bpmn", headers=viewer)
        assert missing.status_code == 404
        for rid in (world["other"], world["hidden"]):
            refused = client.get(f"{base}/{rid}/export.dmn", headers=viewer)
            assert (refused.status_code, refused.json()) == (missing.status_code, missing.json())


def test_import_takes_only_a_dataset_the_case_reads(
    world: dict[str, str], keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    base = f"/v1/investigations/{world['case']}/rules"
    rule = SentenceRuleInput(name="Every person", sentence=SENTENCE)
    from services.api.app import app

    def files(dataset: str) -> dict[str, tuple[str, str]]:
        return {"bpmn": ("r.bpmn", to_bpmn(rule, dataset_id=dataset)), "dmn": ("r.dmn", to_dmn(rule))}

    with TestClient(app) as client:
        author = _as(key, AUTHOR.id, AUTHOR.roles)
        taken = client.post(f"{base}/import", headers=author, files=files(dataset_for(AUTHOR)))
        assert taken.status_code == 200, taken.text
        assert SentenceRuleInput.model_validate(taken.json()) == rule
        unread = client.post(f"{base}/import", headers=author, files=files("rule-standards-dataset-not-read"))
        nowhere = client.post(f"{base}/import", headers=author, files=files("no-such-dataset-anywhere"))
        assert unread.status_code == 404
        assert (unread.status_code, unread.json()) == (nowhere.status_code, nowhere.json())
        viewer = client.post(f"{base}/import", headers=_as(key, VIEWER, ["analyst", "rule_author"]),
                             files=files(dataset_for(AUTHOR)))  # fmt: skip
        assert viewer.status_code == 403
