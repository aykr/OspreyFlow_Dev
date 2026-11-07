"""Chapter 9's three alerts against the real graph store (`spec/06_DECISIONS.md` ADR-127 Amendment
41): the golden case of `tests/scenarios/test_pid_monitoring_storyline.py`, with a throwaway ArcadeDB
database in place of the stand-in graph, so the access step that decides what each reader sees is the
adapter's own Gremlin (rule 15: the real dependency, not a model of it).

**Live:** it needs ArcadeDB (`ARCADEDB_*`) and Postgres (`POSTGRES_*`), as every live test under
`tests/ingest`, and runs in CI's live job; `make test` leaves `tests/ingest` out. Its database is
created and dropped by `arcadedb_adapter`, its Postgres database by this module.

What it would catch:
- the real store answering the rule's two-step reach, a hotlist's touched node, or the queue's batched
  read differently from the stand-in, so chapter 9 raises other alerts, or in another order, than the
  amendment's — `test_chapter_nine_raises_exactly_these_alerts_on_the_real_store`;
- the adapter's access step letting another analyst see the owner's "only me" hotlist alerts, or a
  reader without the dataset see any — the same test's last assertions.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any

import asyncpg
import pytest
from services.api import alert_queue
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.hotlists import HotlistStore
from services.resolve.trigger import service_principal

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from demo_fixtures import pid_files, pid_monitoring
from schemas.domain import Principal, TypologyRule
from schemas.sentences import RuleSentence, SentenceRuleParams
from tests.services.api.no_transactions import NO_TRANSACTIONS
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_row_keys import KeyStore
from tests.scenarios import pid_monitoring_support as support

OTHER_DATASET = "another-dataset"


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    base = PostgresConfig.from_env()
    name = f"pid_monitoring_live_{new_id().replace('-', '')[:12]}"
    admin = await asyncpg.connect(base.dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    yield base.dsn.rsplit("/", 1)[0] + f"/{name}"
    admin = await asyncpg.connect(base.dsn)
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()


def _analyst(unit: str, **update: Any) -> Principal:
    return Principal(
        id=f"analyst-{new_id()}", clearance="OFFICIAL", org_unit=unit, roles=["analyst"],
        datasets=[support.DATASET],
    ).model_copy(update=update)  # fmt: skip


async def test_chapter_nine_raises_exactly_these_alerts_on_the_real_store(dsn: str) -> None:
    async with arcadedb_adapter(support.ONTOLOGY, support.SCHEME) as graph:
        world = support.World(graph, KeyStore())  # type: ignore[arg-type]
        for file in support.BASE_FILES:
            await support._load_base(world, file)
        await support._load_base(world, "pid_pin_calls.csv", support._calls_slice().rows)
        await support._load_base(world, pid_files.BATCH_1)

        hotlists, alerts = await HotlistStore.connect(dsn), await AlertStore.connect(dsn)
        try:
            unit = f"verify-{new_id()}"
            analyst, colleague = _analyst(unit), _analyst(unit)
            stranger = _analyst(unit, datasets=[OTHER_DATASET])
            stores = support.Stores(hotlists, alerts, support.SignatureSet(), support.Audit(),
                                    {p.id: p for p in (analyst, colleague)})  # fmt: skip
            case = f"pid-case-{new_id()}"
            hotlist = await hotlists.create(analyst, identifier="07700 900640", review_date=date(2026, 8, 1))
            await support.run_chapter_9_file(world, pid_files.BATCH_2, stores, case=case)
            await support.run_chapter_9_file(world, pid_monitoring.VISIT_BOOKINGS, stores, case=case)
            rule = TypologyRule(
                id=f"rule-{new_id()}", investigation_id=case, owner_id=analyst.id,
                name=pid_monitoring.P1_RULE_NAME, created_at=datetime.now(UTC), trigger="post_commit",
                dataset_id=support.DATASET,
                params=SentenceRuleParams(pattern_id=f"pattern-{new_id()}",
                                          sentence=RuleSentence.model_validate(dict(pid_monitoring.P1_SENTENCE))),
            )  # fmt: skip
            await support.run_chapter_9_file(
                world, pid_monitoring.PIN_NEW_CONTACTS, stores, case=case, rules=[rule],
                patterns=support.RulePatterns(rule),
            )  # fmt: skip

            async def queue(reader: Principal) -> list[Any]:
                rows = await alert_queue.monitoring_queue(alerts, graph, NO_TRANSACTIONS, case, reader)
                return sorted(rows, key=lambda q: q.alert.created_at)

            async def number_of(queued: Any) -> str:
                (node,) = await graph.get_nodes(queued.alert.referent_node_ids, service_principal(support.SCHEME))
                return str(node.properties["value_normalised"])

            raised = await queue(analyst)
            seen = [("sentence" if q.alert.typology == "sentence" else q.kind, await number_of(q)) for q in raised]
            assert seen == [(e.kind, e.number) for e in pid_monitoring.EXPECTED_ALERTS]
            assert raised[0].alert.rule_id == raised[1].alert.rule_id == f"hotlist:{hotlist.id}"
            assert raised[2].alert.rule_id == f"typology:{rule.id}" and raised[2].alert.alert_node_id
            assert [q.alert.typology for q in await queue(colleague)] == ["sentence"]
            assert await queue(stranger) == []
        finally:
            await alerts.close()
            await hotlists.close()
