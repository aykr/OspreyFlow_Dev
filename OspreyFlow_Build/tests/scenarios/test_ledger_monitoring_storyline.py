"""Operation Ledger's monitoring week (`spec/06_DECISIONS.md` ADR-108 Amendment 5;
`process/ALERTING_MONITORING_PLAN.md` A1 to A4): the next weekly export raises exactly a pass-through,
a circle and a hotlist alert, in that order; a list update raises one screening alert; and the closed
pass-through goes into the pack and the monitoring figures — each as the reader may see it (rules 3, 4,
7).

September is the seed's own (`build_ledger_graph`); the week is loaded through the committed recipe as
the run route runs it (`ledger_monitoring_support.load_week`): the case's rules after commit, then the
hotlists over the run's touched nodes. The list is refreshed by `screening_refresh.refresh` with the real
`Rescreener`. Real Postgres (a database of this module's own, dropped after) holds the hotlists, the
alerts and the screening lists; real DuckDB, through the adapter, the events and the alert facts; the
graph answers as the adapter does (the support module says how, and what it does not model).

**The story** (`story`, run once per scenario): the analyst hotlists Carter's Lloyds account ("only
me") and deploys the two rules from the templates; the week loads (R1, C1, H1); the case's screening
rule is live; the administrator refreshes the UK Sanctions List at version 1 (nothing), version 2 is
released and refreshed (K1). Then A4: R1 closed as *Referred*.

What each case would catch (the amendment names each):
- A1 and A2 together: an alert more or fewer, or out of order —
  `test_the_week_raises_exactly_these_alerts_in_this_order`;
- A1: `test_the_week_raises_one_pass_through_and_one_circle`,
  `test_a_rule_deployed_after_the_week_two_load_raises_nothing_for_it`,
  `test_a_second_run_of_the_week_two_file_raises_nothing`, `test_the_background_raises_nothing`,
  `test_the_structuring_template_raises_nothing_for_the_week`,
  `test_a_rule_author_without_the_dataset_raises_nothing`,
  `test_a_reader_without_the_dataset_sees_no_week_two_alert`;
- A2: `test_the_cash_deposit_raises_one_hotlist_alert_on_carters_account`,
  `test_a_hotlist_added_after_the_week_two_load_raises_nothing`,
  `test_a_hotlist_made_in_another_dataset_raises_nothing`,
  `test_a_hotlist_on_an_account_the_week_does_not_touch_raises_nothing`,
  `test_another_analyst_does_not_see_the_owners_hotlist_alert`;
- A3: `test_the_list_update_raises_one_screening_alert_on_ruiz`, `test_the_first_version_raises_nothing`,
  `test_the_same_version_again_rescreens_no_one`, `test_a_case_without_a_screening_rule_raises_nothing`,
  `test_a_screening_rule_whose_deployer_lacks_the_dataset_raises_nothing`,
  `test_a_reader_without_the_dataset_sees_no_screening_alert`;
- A4: `test_the_referred_alert_goes_into_the_pack_closed_and_inferred`,
  `test_the_monitoring_figures_count_the_week`, `test_a_reason_outside_the_five_is_refused`,
  `test_the_alert_item_is_withheld_from_a_reader_without_the_dataset`,
  `test_the_board_never_counts_the_owners_only_me_hotlist`,
  `test_a_reader_without_the_dataset_counts_nothing_on_the_board`.
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import duckdb
import pytest
import pytest_asyncio
from pydantic import TypeAdapter, ValidationError
from services.api import alert_queue, packs, reports
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.hotlists import HotlistStore
from services.api.screening import ScreeningListStore
from services.api.screening_refresh import Rescreener, refresh
from tests.scenarios import ledger_monitoring_support as support
from tests.scenarios import pid_monitoring_support
from tests.scenarios.ledger_monitoring_support import (
    DATASET,
    SCHEME,
    Audit,
    SignatureSet,
    Stores,
    World,
    load_week,
)

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table
from conduit_common.identity import new_id
from demo_fixtures import ledger, ledger_monitoring
from demo_fixtures.ledger_monitoring import (
    CARTER_ACC,
    CRESCENT_ACC,
    HOTLISTED_ACCOUNT,
    RUIZ_ACC,
)
from schemas.domain import Principal, TypologyParams, TypologyRule
from schemas.screening import ScreeningSubscriptionInput

pytestmark = [pytest.mark.asyncio(loop_scope="module")]

OTHER_DATASET = "another-dataset"
REVIEW = date(2027, 1, 31)
LISTS = Path(ledger.__file__).resolve().parent / "screening_lists"
PARAMS: TypeAdapter[Any] = TypeAdapter(TypologyParams)


# --- The module's stores -----------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _staged_locally() -> Iterator[None]:
    with pid_monitoring_support.local_staging():
        yield


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def dsn() -> AsyncIterator[str]:
    """A database of this module's own on the throwaway Postgres: `list_all_active` reads every
    hotlist in a database, so another module's must not be in it."""
    base = PostgresConfig.from_env()
    name = f"ledger_monitoring_{new_id().replace('-', '')[:16]}"
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


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def base(dsn: str) -> World:
    return await support.base_world()


@dataclass
class Scene:
    """One run of the week in a case of its own, with its own people and its own list."""

    world: World
    stores: Stores
    screening: ScreeningListStore
    root: Path
    case: str
    list_name: str
    analyst: Principal
    colleague: Principal
    stranger: Principal
    rules: dict[str, TypologyRule] = field(default_factory=dict)
    hotlist: Any = None
    loaded: Any = None
    updates: list[Any] = field(default_factory=list)


def _analyst(unit: str, **update: Any) -> Principal:
    return Principal(
        id=f"analyst-{new_id()}", clearance="OFFICIAL", org_unit=unit, roles=["analyst"],
        datasets=[DATASET],
    ).model_copy(update=update)  # fmt: skip


@pytest_asyncio.fixture(loop_scope="module")
async def scene(base: World, dsn: str, tmp_path: Path) -> AsyncIterator[Scene]:
    hotlists = await HotlistStore.connect(dsn)
    alerts = await AlertStore.connect(dsn)
    screening = await ScreeningListStore.connect(dsn)
    con = duckdb.connect(":memory:")
    create_events_table(con)
    analytics = AnalyticsDuckDBAdapter(con, SCHEME)
    alerts.fact_sink = analytics.load_alert_facts
    case = f"ledger-case-{new_id()}"
    world = base.copy()
    await analytics.load_events(support.september_for(world, case))
    # The seed's own unit: September is marked for it (`ledger._HANDLING`, owning unit `verify`).
    analyst, colleague = _analyst("verify"), _analyst("verify")
    stranger = _analyst("verify", datasets=[OTHER_DATASET])
    stores = Stores(
        hotlists=hotlists, alerts=alerts, analytics=analytics, valkey=SignatureSet(), audit=Audit(),
        principals={p.id: p for p in (analyst, colleague)},
    )  # fmt: skip
    root = tmp_path / "ingest"
    listed = root / "uploaded" / DATASET / "lists"
    listed.mkdir(parents=True)
    shutil.copy(LISTS / ledger_monitoring.UK_LIST_V1, listed / "uk_sanctions_list.xml")
    name = f"{ledger_monitoring.UK_LIST_NAME} {new_id()[-10:]}"  # the ULID's random tail
    yield Scene(world, stores, screening, root, case, name, analyst, colleague, stranger)
    await screening.close()
    await alerts.close()
    await hotlists.close()
    con.close()


def deploy(scene: Scene, params: Mapping[str, Any], name: str, *, dataset: str = DATASET,
           owner: Principal | None = None) -> TypologyRule:  # fmt: skip
    """A rule as the analyst deploys it from a template: after each load commits, in the case's
    dataset (ADR-099), as theirs."""
    rule = TypologyRule(
        id=f"rule-{new_id()}", investigation_id=scene.case, owner_id=(owner or scene.analyst).id,
        name=name, created_at=datetime.now(UTC), trigger="post_commit", dataset_id=dataset,
        params=PARAMS.validate_python(dict(params)),
    )  # fmt: skip
    scene.rules[name] = rule
    return rule


def the_two_rules(scene: Scene) -> list[TypologyRule]:
    return [
        deploy(scene, ledger_monitoring.RAPID_MOVEMENT, ledger_monitoring.RAPID_MOVEMENT_NAME),
        deploy(scene, ledger_monitoring.CIRCULAR_FLOW, ledger_monitoring.CIRCULAR_FLOW_NAME),
    ]


async def hotlist(scene: Scene, identifier: str = HOTLISTED_ACCOUNT, owner: Principal | None = None) -> Any:
    scene.hotlist = await scene.stores.hotlists.create(
        owner or scene.analyst, identifier=identifier, review_date=REVIEW
    )
    return scene.hotlist


async def week(scene: Scene, rules: list[TypologyRule] | None = None, **kw: Any) -> Any:
    scene.loaded = await load_week(scene.world, scene.stores, case=scene.case, rules=rules or [], **kw)
    return scene.loaded


async def queue(scene: Scene, reader: Principal) -> list[Any]:
    rows = await alert_queue.monitoring_queue(
        scene.stores.alerts, scene.world.graph, scene.stores.analytics, scene.case, reader
    )
    return sorted(rows, key=lambda q: q.alert.created_at)


# --- A3's list ------------------------------------------------------------------------------------


class _Rules:
    def __init__(self, rules: list[TypologyRule]) -> None:
        self.rules = rules

    async def list_active_of_typology(self, typology: str) -> list[TypologyRule]:
        return [r for r in self.rules if r.params.typology == typology and r.status == "active"]


class _Datasets:
    def __init__(self, case: str) -> None:
        self.case = case

    async def ids_of_case(self, investigation_id: str) -> list[str]:
        return [DATASET] if investigation_id == self.case else []


async def subscribe(scene: Scene) -> None:
    await scene.screening.subscribe(
        ScreeningSubscriptionInput(
            list_name=scene.list_name, source="uk_sanctions_list",
            location=f"uploaded/{DATASET}/{ledger_monitoring.UK_LIST_FILE}",
        ),
        "osprey-demo-admin",
        synthetic=True,
    )  # fmt: skip


def release_version_2(scene: Scene) -> None:
    shutil.copy(LISTS / ledger_monitoring.UK_LIST_V2,
                scene.root / "uploaded" / DATASET / ledger_monitoring.UK_LIST_FILE)  # fmt: skip


async def refresh_list(scene: Scene, rules: list[TypologyRule]) -> Any:
    """*Refresh now*, as the administrator presses it: the real refresh and re-screening."""
    admin = Principal(id="osprey-demo-admin", clearance="OFFICIAL", org_unit="verify",
                      roles=["administrator"])  # fmt: skip
    rescreen = Rescreener(
        rules=_Rules(rules), datasets=_Datasets(scene.case),
        graph=support.DatasetStampingGraph(scene.world.graph),  # type: ignore[arg-type]
        scheme=SCHEME, alert_store=scene.stores.alerts, audit=scene.stores.audit,  # type: ignore[arg-type]
        valkey=scene.stores.valkey,  # type: ignore[arg-type]
        principal_for_owner=scene.stores.principal_for_owner, runner=admin,
    )  # fmt: skip
    update = await refresh(scene.list_name, store=scene.screening, rescreen=rescreen, root=scene.root)
    scene.updates.append(update)
    return update


async def story(scene: Scene, *, close: bool = True) -> Scene:
    """The act as the walkthrough runs it: A1 and A2 as the week loads, A3 as the list updates, then
    A4's close."""
    await hotlist(scene)
    await week(scene, the_two_rules(scene))
    screening = deploy(scene, ledger_monitoring.SCREENING, ledger_monitoring.SCREENING_NAME)
    await subscribe(scene)
    await refresh_list(scene, [screening])
    release_version_2(scene)
    await refresh_list(scene, [screening])
    if close:
        r1 = (await queue(scene, scene.analyst))[0]
        assert r1.alert.typology == ledger_monitoring.CLOSED_KIND
        closed = await alert_queue.dispose(
            scene.stores.alerts, scene.world.graph, scene.case, r1.alert.id, scene.analyst,
            disposition=ledger_monitoring.CLOSING_REASON, reason=ledger_monitoring.CLOSING_WORDS,
        )  # fmt: skip
        assert closed.status == "closed", "a medium-severity alert closes without a second person"
    return scene


def _kind(queued: Any) -> str:
    return queued.alert.typology if queued.kind == "typology" else queued.kind


def _names(scene: Scene, queued: Any) -> str:
    """What the alert is about, as `ExpectedAlert.names` says it: the account a flow alert's words
    begin with, the hotlisted account, or the screened customer's family name."""
    graph = scene.world.graph
    if queued.kind == "hotlist":
        (node_id,) = queued.alert.referent_node_ids
        return str(graph.nodes[node_id].properties["account_number"])
    if queued.alert.typology == "kyc_screening":
        people = [graph.nodes[i] for i in queued.alert.referent_node_ids
                  if graph.nodes[i].type == "Person" and not graph.nodes[i].properties.get("listing")]  # fmt: skip
        (person,) = people
        return str(person.properties["family_name"])
    accounts = [graph.nodes[i] for i in queued.alert.referent_node_ids]
    words = str(queued.alert.words)
    (first,) = [a for a in accounts if words.find(a.id) == min(words.find(x.id) for x in accounts
                                                                 if x.id in words)]  # fmt: skip
    return str(first.properties["account_number"])


# --- A1 and A2 together ------------------------------------------------------------------------


async def test_the_week_raises_exactly_these_alerts_in_this_order(scene: Scene) -> None:
    await story(scene, close=False)
    raised = await queue(scene, scene.analyst)
    assert [(_kind(q), _names(scene, q)) for q in raised] == [
        (e.kind, e.names) for e in ledger_monitoring.EXPECTED_ALERTS
    ]
    r1, c1, h1, k1 = raised
    assert (r1.severity, r1.audience) == (c1.severity, c1.audience) == ("medium", "case")
    assert (h1.severity, h1.audience) == ("high", "owner")
    assert h1.alert.rule_id == f"hotlist:{scene.hotlist.id}"
    assert (k1.severity, k1.audience) == ("high", "case")
    assert scene.loaded.rule_notes == [
        f"Rule “{ledger_monitoring.RAPID_MOVEMENT_NAME}” raised 1 alert(s).",
        f"Rule “{ledger_monitoring.CIRCULAR_FLOW_NAME}” raised 1 alert(s).",
    ]
    assert len(scene.loaded.hotlist_alerts) == 1
    assert len(await scene.stores.alerts.list_authorized(scene.analyst)) == 4


# --- A1: the pass-through and the circle ----------------------------------------------------------


async def test_the_week_raises_one_pass_through_and_one_circle(scene: Scene) -> None:
    loaded = await week(scene, the_two_rules(scene))
    r1, c1 = await queue(scene, scene.analyst)
    graph = scene.world.graph
    ruiz, crescent = graph.account(RUIZ_ACC), graph.account(CRESCENT_ACC)
    assert r1.alert.typology == "rapid_movement" and r1.alert.words.startswith(
        f"18,000 arrived at {ruiz.id} and 17,400 left within 6.2 hour(s)")  # fmt: skip
    assert len(r1.alert.event_ids) == 2
    assert c1.alert.typology == "circular_flow" and c1.alert.words.startswith(
        f"value left {crescent.id} and returned to it over 3 movements")  # fmt: skip
    assert len(c1.alert.event_ids) == 3
    for queued in (r1, c1):
        node = graph.nodes[queued.alert.alert_node_id]
        assert node.provenance.state.value == "inferred", "rule 5: a rule's finding is inferred"
    assert loaded.report.rows_already_loaded == 0 and loaded.hotlist_alerts == []


async def test_a_rule_deployed_after_the_week_two_load_raises_nothing_for_it(scene: Scene) -> None:
    loaded = await week(scene)
    the_two_rules(scene)  # deployed now: they judge later loads, never this one
    assert loaded.rule_notes == [] and await queue(scene, scene.analyst) == []


async def test_a_second_run_of_the_week_two_file_raises_nothing(scene: Scene) -> None:
    rules = the_two_rules(scene)
    await week(scene, rules)
    again = await week(scene, rules)
    # The transactions recipe keeps no row keys (`ledger_transactions_recipe.yaml`), so a second run
    # reads every row again; each finding is the same transactions (`one_per_transaction`) and is
    # alerted once (its signature).
    assert again.report.rows_read == 13 and again.rule_notes == []
    assert len(await queue(scene, scene.analyst)) == 2


async def test_the_background_raises_nothing(scene: Scene) -> None:
    structuring = deploy(scene, {"typology": "structuring", "threshold": 10_000, "window_days": 7,
                                 "minimum_count": 3}, "Structuring")  # fmt: skip
    await hotlist(scene)
    loaded = await week(scene, [*the_two_rules(scene), structuring],
                        rows=ledger_monitoring.background_rows())
    assert loaded.rule_notes == [] and loaded.hotlist_alerts == []
    assert await queue(scene, scene.analyst) == []


async def test_the_structuring_template_raises_nothing_for_the_week(scene: Scene) -> None:
    structuring = deploy(scene, {"typology": "structuring", "threshold": 10_000, "window_days": 7,
                                 "minimum_count": 3}, "Structuring")  # fmt: skip
    loaded = await week(scene, [structuring])
    assert loaded.rule_notes == [], "one cash deposit into Carter's account is no ring"


async def test_a_rule_author_without_the_dataset_raises_nothing(scene: Scene) -> None:
    rules = [deploy(scene, ledger_monitoring.RAPID_MOVEMENT, "Elsewhere", dataset=OTHER_DATASET)]
    loaded = await week(scene, rules)
    assert loaded.rule_notes == []
    assert await scene.stores.alerts.list_authorized(scene.analyst) == []


async def test_a_reader_without_the_dataset_sees_no_week_two_alert(scene: Scene) -> None:
    await story(scene)
    assert await queue(scene, scene.stranger) == []
    assert await scene.stores.alerts.list_authorized(scene.stranger) == []


# --- A2: the hotlisted account ----------------------------------------------------------------------


async def test_the_cash_deposit_raises_one_hotlist_alert_on_carters_account(scene: Scene) -> None:
    made = await hotlist(scene)
    assert made.identifier == "GB58LOYD30961700709943", "stored in the adapter's form"
    loaded = await week(scene)
    (alert,) = loaded.hotlist_alerts
    carter = scene.world.graph.account(CARTER_ACC)
    assert alert.referent_node_ids == [carter.id]
    assert alert.rule_id == f"hotlist:{made.id}" and alert.owner_id == scene.analyst.id
    (queued,) = await queue(scene, scene.analyst)
    assert (queued.kind, queued.severity, queued.audience) == ("hotlist", "high", "owner")


async def test_a_hotlist_added_after_the_week_two_load_raises_nothing(scene: Scene) -> None:
    loaded = await week(scene)
    await hotlist(scene)
    assert loaded.hotlist_alerts == [] and await queue(scene, scene.analyst) == []


async def test_a_hotlist_made_in_another_dataset_raises_nothing(scene: Scene) -> None:
    elsewhere = scene.analyst.model_copy(update={"datasets": [OTHER_DATASET]})
    scene.stores.principals[elsewhere.id] = elsewhere
    await hotlist(scene, owner=elsewhere)
    loaded = await week(scene)
    assert loaded.hotlist_alerts == []


async def test_a_hotlist_on_an_account_the_week_does_not_touch_raises_nothing(scene: Scene) -> None:
    await hotlist(scene, identifier=ledger.HALE_BIZ)
    loaded = await week(scene)
    assert loaded.hotlist_alerts == []


async def test_another_analyst_does_not_see_the_owners_hotlist_alert(scene: Scene) -> None:
    await story(scene, close=False)
    colleague = [_kind(q) for q in await queue(scene, scene.colleague)]
    assert colleague == ["rapid_movement", "circular_flow", "kyc_screening"], (
        "the hotlist is the owner's alone; the rules' alerts are the case's"
    )


# --- A3: the list update ------------------------------------------------------------------------------


async def test_the_list_update_raises_one_screening_alert_on_ruiz(scene: Scene) -> None:
    rule = deploy(scene, ledger_monitoring.SCREENING, ledger_monitoring.SCREENING_NAME)
    await subscribe(scene)
    first = await refresh_list(scene, [rule])
    release_version_2(scene)
    update = await refresh_list(scene, [rule])
    assert (first.version, update.version, update.previous_version) == ("28/09/2026", "06/10/2026", "28/09/2026")
    assert (update.added, update.changed, update.delisted, update.alerts) == (1, 1, 1, 1)
    assert "1 added, 1 changed, 1 removed" in update.words and "1 alert raised" in update.words
    (k1,) = await queue(scene, scene.analyst)
    assert (k1.alert.typology, k1.severity, k1.audience) == ("kyc_screening", "high", "case")
    assert _names(scene, k1) == "Ruiz"
    assert "matches “RUIZ, Sofia” on a sanctions list" in k1.alert.words
    graph = scene.world.graph
    ruiz = graph.person("Ruiz")
    (same_as,) = [e for e in graph.committed_edges if e.type == "SAME_AS" and e.source == ruiz.id]
    assert same_as.provenance.state.value == "inferred", "rule 5: a screening match is inferred"
    listed = graph.nodes[same_as.target]
    assert listed.properties.get("listing") == "sanction" and listed.id != ruiz.id, "rule 6: no merge"


async def test_the_first_version_raises_nothing(scene: Scene) -> None:
    rule = deploy(scene, ledger_monitoring.SCREENING, ledger_monitoring.SCREENING_NAME)
    await subscribe(scene)
    first = await refresh_list(scene, [rule])
    assert (first.outcome, first.added, first.alerts) == ("updated", 5, 0)
    assert first.rescreened > 0, "every customer was re-screened, and none matched"
    assert await queue(scene, scene.analyst) == []


async def test_the_same_version_again_rescreens_no_one(scene: Scene) -> None:
    rule = deploy(scene, ledger_monitoring.SCREENING, ledger_monitoring.SCREENING_NAME)
    await subscribe(scene)
    await refresh_list(scene, [rule])
    release_version_2(scene)
    await refresh_list(scene, [rule])
    again = await refresh_list(scene, [rule])
    assert (again.outcome, again.rescreened, again.alerts) == ("unchanged", 0, 0)
    assert len(await queue(scene, scene.analyst)) == 1


async def test_a_case_without_a_screening_rule_raises_nothing(scene: Scene) -> None:
    await subscribe(scene)
    await refresh_list(scene, [])
    release_version_2(scene)
    update = await refresh_list(scene, [])
    assert (update.added, update.rescreened, update.alerts) == (1, 0, 0)
    assert await queue(scene, scene.analyst) == []


async def test_a_screening_rule_whose_deployer_lacks_the_dataset_raises_nothing(scene: Scene) -> None:
    rule = deploy(scene, ledger_monitoring.SCREENING, "Elsewhere", dataset=OTHER_DATASET)
    await subscribe(scene)
    await refresh_list(scene, [rule])
    release_version_2(scene)
    update = await refresh_list(scene, [rule])
    assert (update.rescreened, update.alerts) == (0, 0), "rule 3: no customer of the case is read"
    assert await scene.stores.alerts.list_authorized(scene.analyst) == []


async def test_a_reader_without_the_dataset_sees_no_screening_alert(scene: Scene) -> None:
    await story(scene, close=False)
    assert [q for q in await queue(scene, scene.stranger) if q.alert.typology == "kyc_screening"] == []


# --- A4: closed, packed and counted -------------------------------------------------------------


async def _r1_item(scene: Scene) -> Any:
    r1 = (await queue(scene, scene.analyst))[0]
    explained, events = await alert_queue.explain_with_evidence(
        scene.stores.alerts, scene.world.graph, scene.stores.analytics, scene.case, r1.alert.id,
        scene.analyst,
    )  # fmt: skip
    return packs.alert_item(explained, events, scene.analyst, SCHEME)


async def test_the_referred_alert_goes_into_the_pack_closed_and_inferred(scene: Scene) -> None:
    await story(scene)
    item = await _r1_item(scene)
    snapshot = item.alert
    assert (snapshot.kind, snapshot.status, snapshot.outcome, snapshot.match) == (
        "typology", "closed", "referred", "inferred")  # fmt: skip
    assert snapshot.typology == "rapid_movement"
    shown, withheld = await packs.readable([item], scene.analyst, SCHEME, scene.world.graph, scene.case)
    assert shown == [item] and withheld is False


async def test_a_reason_outside_the_five_is_refused() -> None:
    from schemas.domain import AlertDispositionInput

    for reason in ("true_positive", "false_positive", "duplicate", "no_further_action", "referred"):
        AlertDispositionInput(disposition=reason, reason="words")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        AlertDispositionInput(disposition="sar_filed", reason="words")  # type: ignore[arg-type]


async def test_the_alert_item_is_withheld_from_a_reader_without_the_dataset(scene: Scene) -> None:
    await story(scene)
    item = await _r1_item(scene)
    public = scene.colleague.model_copy(update={"clearance": "PUBLIC"})
    for reader in (scene.stranger, public):
        shown, withheld = await packs.readable([item], reader, SCHEME, scene.world.graph, scene.case)
        assert shown == [] and withheld is True  # a yes, never a count or a name


async def test_an_item_citing_an_alert_the_revert_took_back_is_not_shown_to_its_adder(
    scene: Scene,
) -> None:
    """Build order step 15: the rehearsal's pack said "Some items … withheld from you" to the analyst
    who had added R1. The revert of the week's load takes back the load's own `Alert` nodes (they are
    in its record, ADR-127 decision 6), R1's among them, so the item cites a node no one may read
    now: not shown, and said as the yes it always is. The Glass's sentence says this reason as well
    as access (`packText.WITHHELD_ITEMS_SENTENCE`); here, that the analyst was not denied it on access:
    before the revert she gets it."""
    await story(scene)
    item = await _r1_item(scene)
    graph = scene.world.graph
    assert await packs.readable([item], scene.analyst, SCHEME, graph, scene.case) == ([item], False)
    r1 = item.alert
    assert r1 is not None
    alert_nodes = [n for n in r1.node_ids if graph.nodes[n].type == "Alert"]
    assert len(alert_nodes) == 1, "the item cites R1's own Alert node"
    tx = await graph.begin_transaction()
    await graph.revert_elements(alert_nodes, [], tx)
    await graph.commit_transaction(tx)
    assert await packs.readable([item], scene.analyst, SCHEME, graph, scene.case) == ([], True)


async def _figures(scene: Scene, reader: Principal) -> Any:
    return await reports.alert_report(
        scene.stores.alerts, scene.world.graph, scene.stores.analytics, scene.case, reader,
        today=datetime.now(UTC).date(),
    )


def _week() -> date:
    today = datetime.now(UTC).date()
    return today - timedelta(days=today.weekday())


async def test_the_monitoring_figures_count_the_week(scene: Scene) -> None:
    await story(scene)
    m = (await _figures(scene, scene.analyst)).monitoring
    week_start = _week()
    assert sorted((w.label, w.typology, w.week_start, w.count) for w in m.raised_by_rule) == [
        ("hotlists", "", week_start, 1),
        ("typology", "circular_flow", week_start, 1),
        ("typology", "kyc_screening", week_start, 1),
        ("typology", "rapid_movement", week_start, 1),
    ]
    assert [(w.label, w.week_start, w.count) for w in m.closed_by_outcome] == [("referred", week_start, 1)]
    assert {c.label: c.value for c in m.time_to_close}["under a day"] == 1
    assert [(w.label, w.count) for w in m.hotlist_matches] == [("hotlists", 1)]
    still_open = [_kind(q) for q in await queue(scene, scene.analyst) if q.alert.status != "closed"]
    assert still_open == ["circular_flow", "hotlist", "kyc_screening"]


async def test_the_board_never_counts_the_owners_only_me_hotlist(scene: Scene) -> None:
    await story(scene)
    m = (await _figures(scene, scene.colleague)).monitoring
    assert sorted((w.label, w.typology, w.count) for w in m.raised_by_rule) == [
        ("typology", "circular_flow", 1), ("typology", "kyc_screening", 1),
        ("typology", "rapid_movement", 1)]  # fmt: skip
    assert m.hotlist_matches == []


async def test_a_reader_without_the_dataset_counts_nothing_on_the_board(scene: Scene) -> None:
    await story(scene)
    figures = await _figures(scene, scene.stranger)
    m = figures.monitoring
    assert m.raised_by_rule == m.closed_by_outcome == m.hotlist_matches == []
    assert all(c.value == 0 for c in m.time_to_close) and figures.alerts_total == 0
