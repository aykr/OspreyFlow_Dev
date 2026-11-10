"""The typology-rule, rule-audit and held-row routes (`spec/06_DECISIONS.md` ADR-109 phase A).

The real app, its real lifespan, real Postgres and ArcadeDB and real JWT bearer auth — the shape
`tests/services/api/test_assessment_routes.py` set. Here under `tests/ingest` beside the store-level
cases in `test_typology_rules.py`, which prove the logic; this file proves each route's level and
its access control (`CLAUDE.md` rule 4: every read path gets an access-control test).

The levels, as ruled (ruling 4: an Author deploys; ruling 1: the audit is the case's Authors' and
the admin's), or chosen and recorded in ADR-109 Amendment 1 (held rows listed at Editor, decided
at Author):

- deploy and retire need Author (`test_only_an_author_deploys_and_retires_a_rule`);
- the rule list needs only a level in the case, and nothing is told to an account with none
  (`test_the_rule_list_is_the_case_teams_and_nobody_elses`);
- the audit is an Author's, or the admin's through the safety net
  (`test_the_rule_audit_is_read_by_authors_and_the_admin_only`);
- held rows are listed at Editor, filtered by marking in the store, and a rejection needs a reason
  (`test_held_rows_are_listed_at_editor_and_only_at_the_readers_marking`,
  `test_a_rejection_needs_a_reason_and_an_author`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.config import PostgresConfig
from services.api.held_rows import HeldRowStore
from services.api.investigations import AccessLevel, InvestigationStore

from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from schemas.domain import Handling, HeldRow, Principal
from tests.conftest import default_claims, sign_token
from tests.services.api.case_dataset import give_case_its_dataset

AUTHOR = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
EDITOR = "analyst-editor"
VIEWER = "analyst-viewer"
OUTSIDER = "analyst-outsider"

RULE = {
    "name": "Structuring",
    "params": {"typology": "structuring", "threshold": 10000, "window_days": 7,
               "minimum_count": 3},
    "trigger": "pre_commit",
    # ADR-146 Amendment 6 decision 12: this form keeps a rule just for its author.
    "just_me": True,
}  # fmt: skip


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    import os

    previous = {k: os.environ.get(k) for k in ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE")}
    os.environ["OIDC_JWKS_URL"] = jwks_url
    os.environ["OIDC_ALGORITHMS"] = "RS256"
    os.environ["ARCADEDB_DATABASE"] = "ospreyflow"
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _as(private_key: rsa.RSAPrivateKey, sub: str, **claims: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(private_key, default_claims(sub=sub, **claims))}"}


async def _case() -> str:
    store = await InvestigationStore.connect(PostgresConfig.from_env().dsn)
    try:
        case = await store.create(AUTHOR, name="Rules case")
        await give_case_its_dataset(case.id, AUTHOR)
        await store.set_grant(case.id, EDITOR, AccessLevel.EDITOR, by=AUTHOR)
        await store.set_grant(case.id, VIEWER, AccessLevel.VIEWER, by=AUTHOR)
        return case.id
    finally:
        await store.close()


async def _hold(case: str, classification: str) -> str:
    store = await HeldRowStore.connect(PostgresConfig.from_env().dsn, load_uk_le_scheme())
    try:
        row = HeldRow(
            id=new_id(), investigation_id=case, recipe_id="r", recipe_version=1, load_id="l",
            source="s", row_index=0, row={"amount": "9500"}, rule_id="rule", reason="test",
            handling=Handling(classification=classification, handling_code="P",
                              originator="unit-1", owning_unit="unit-1"),
            held_at=datetime.now(UTC),
        )  # fmt: skip
        await store.hold([row])
        return row.id
    finally:
        await store.close()


def test_only_an_author_deploys_and_retires_a_rule(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case())
    from services.api.app import app

    with TestClient(app) as client:
        refused = client.post(f"/v1/investigations/{case}/rules", headers=_as(key, EDITOR), json=RULE)
        assert refused.status_code == 403, refused.text
        made = client.post(f"/v1/investigations/{case}/rules", headers=_as(key, AUTHOR.id), json=RULE)
        assert made.status_code == 201, made.text
        rule_id = made.json()["id"]
        assert made.json()["owner_id"] == AUTHOR.id and made.json()["trigger"] == "pre_commit"
        assert made.json()["just_me"] is True
        # A template made case-wide here is refused: a rule for the case is written in the rule
        # editor, drafted, tested and past its second person (decision 12). Red with the route's
        # refusal removed: it went live at once for the whole case, untested.
        wide = client.post(f"/v1/investigations/{case}/rules", headers=_as(key, AUTHOR.id),
                           json={**RULE, "just_me": False})  # fmt: skip
        assert (wide.status_code, wide.json()["error"]) == (409, "use_the_rule_editor"), wide.text

        # An expression smuggled into the closed vocabulary is refused at the schema (rule 8).
        bad = {**RULE, "params": {"typology": "custom", "expression": "amount > 1"}}
        assert client.post(f"/v1/investigations/{case}/rules", headers=_as(key, AUTHOR.id),
                           json=bad).status_code == 422  # fmt: skip

        path = f"/v1/investigations/{case}/rules/{rule_id}/retire"
        assert client.post(path, headers=_as(key, EDITOR)).status_code == 403
        retired = client.post(path, headers=_as(key, AUTHOR.id))
        assert retired.status_code == 200 and retired.json()["status"] == "retired"
        assert client.post(path, headers=_as(key, AUTHOR.id)).status_code == 404


def test_the_rule_list_is_the_case_teams_and_nobody_elses(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case())
    other_case = asyncio.run(_case())
    from services.api.app import app

    # The list also holds every deployment-wide sentence (ADR-133 decision 1), and the shared stack
    # holds other runs' (the orchestrator's note of 9 November: red on main for that alone), so
    # each case is judged by the rules of its own that it lists.
    def own(rules: list[dict[str, object]], of: str) -> list[dict[str, object]]:
        return [r for r in rules if r.get("investigation_id") == of]

    with TestClient(app) as client:
        made = client.post(f"/v1/investigations/{case}/rules", headers=_as(key, AUTHOR.id), json=RULE)
        listed = client.get(f"/v1/investigations/{case}/rules", headers=_as(key, VIEWER))
        assert listed.status_code == 200
        assert [r["id"] for r in own(listed.json(), case)] == [made.json()["id"]]
        elsewhere = client.get(f"/v1/investigations/{other_case}/rules", headers=_as(key, AUTHOR.id)).json()
        assert made.json()["id"] not in [r["id"] for r in elsewhere], "another case never lists it"
        assert own(elsewhere, other_case) == []
        assert client.get(f"/v1/investigations/{case}/rules",
                          headers=_as(key, OUTSIDER)).status_code == 404  # fmt: skip


def test_the_rule_audit_is_read_by_authors_and_the_admin_only(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case())
    from services.api.app import app

    with TestClient(app) as client:
        client.post(f"/v1/investigations/{case}/rules", headers=_as(key, AUTHOR.id), json=RULE)
        path = f"/v1/investigations/{case}/rules/audit"
        page = client.get(path, headers=_as(key, AUTHOR.id))
        assert page.status_code == 200, page.text
        assert [e["action"] for e in page.json()["entries"]] == ["rule_deployed"]
        assert page.json()["total"] == 1
        assert client.get(path, headers=_as(key, EDITOR)).status_code == 403
        assert client.get(path, headers=_as(key, OUTSIDER)).status_code == 404
        admin = _as(key, "admin-1", roles=["analyst", "osprey-admin"])
        assert client.get(path, headers=admin).status_code == 200


class _Names:
    """Stands in for the principal-name directory (its own refusals are proven in
    `test_principal_names.py`); records which ids the route asked for."""

    def __init__(self, names: dict[str, str]) -> None:
        self.names, self.asked = names, []  # type: ignore[var-annotated]

    async def display_names(self, ids: object) -> dict[str, str]:
        wanted = [i for i in dict.fromkeys(ids) if i]  # type: ignore[call-overload]
        self.asked.append(wanted)
        return {i: self.names[i] for i in wanted if i in self.names}

    async def aclose(self) -> None:
        """Closed by the lifespan's shutdown."""


def test_the_rule_audit_names_who_acted_not_their_account_id(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """Found live, 11 October 2026: the Audit tab's Who column read "2f0ef3c4-09d7-…". The page now
    carries each entry's display name beside its id (ADR-106 decision 3: only ids it serves)."""
    key, _ = keypair
    case = asyncio.run(_case())
    from services.api.app import app

    with TestClient(app) as client:
        names = _Names({AUTHOR.id: "Demo Author"})
        app.state.principal_names = names
        client.post(f"/v1/investigations/{case}/rules", headers=_as(key, AUTHOR.id), json=RULE)
        page = client.get(f"/v1/investigations/{case}/rules/audit", headers=_as(key, AUTHOR.id))
        assert page.status_code == 200, page.text
        (entry,) = page.json()["entries"]
        assert (entry["principal_id"], entry["principal_name"]) == (AUTHOR.id, "Demo Author")
        assert names.asked == [[AUTHOR.id]]


def test_held_rows_are_listed_at_editor_and_only_at_the_readers_marking(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case())
    official = asyncio.run(_hold(case, "OFFICIAL"))
    asyncio.run(_hold(case, "SECRET"))
    from services.api.app import app

    with TestClient(app) as client:
        path = f"/v1/investigations/{case}/held-rows"
        listed = client.get(path, headers=_as(key, EDITOR))
        assert listed.status_code == 200, listed.text
        assert [h["id"] for h in listed.json()] == [official]
        assert len(client.get(path, headers=_as(key, AUTHOR.id, clearance="SECRET")).json()) == 2
        assert client.get(path, headers=_as(key, VIEWER)).status_code == 403
        assert client.get(path, headers=_as(key, OUTSIDER)).status_code == 404


def test_a_rejection_needs_a_reason_and_an_author(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case())
    held = asyncio.run(_hold(case, "OFFICIAL"))
    secret = asyncio.run(_hold(case, "SECRET"))
    from services.api.app import app

    with TestClient(app) as client:
        path = f"/v1/investigations/{case}/held-rows/reject"
        assert client.post(path, headers=_as(key, EDITOR),
                           json={"ids": [held], "reason": "no"}).status_code == 403  # fmt: skip
        no_reason = client.post(path, headers=_as(key, AUTHOR.id), json={"ids": [held]})
        assert no_reason.status_code == 422 and no_reason.json()["error"] == "release_refused"
        # A row above the reviewer is "not found", and nothing in the decision is made.
        hidden = client.post(path, headers=_as(key, AUTHOR.id),
                             json={"ids": [held, secret], "reason": "no"})  # fmt: skip
        assert hidden.status_code == 404
        done = client.post(path, headers=_as(key, AUTHOR.id), json={"ids": [held], "reason": "fake"})
        assert done.status_code == 200 and done.json()[0]["status"] == "rejected"
        assert client.get(f"/v1/investigations/{case}/held-rows",
                          headers=_as(key, AUTHOR.id)).json() == []  # fmt: skip


# --- phase B: the alert queue's routes ----------------------------------------


async def _queued_alert(case: str, classification: str = "OFFICIAL") -> str:
    """Two accounts in the case's dataset and a rule-raised alert on them, written straight to the
    stores the running app reads."""
    from services.api.alerts import AlertStore

    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from ontology.packs import load_deployment_ontology
    from schemas.domain import Alert, AlertMode, NodeWrite, Provenance, ProvenanceState, SourceRef
    from tests.services.api.case_dataset import dataset_for

    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    now = datetime.now(UTC)
    try:
        graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        await graph.apply_schema(load_deployment_ontology())
        tx = await graph.begin_transaction()
        ids = await graph.upsert_nodes(
            [
                NodeWrite(
                    id=new_id(), type="Account", properties={"account_number": f"GB-{new_id()}"},
                    provenance=Provenance(state=ProvenanceState.ASSERTED, first_seen=now,
                                          sources=[SourceRef(document_id="t", locator="r",
                                                             excerpt_hash="")]),
                    handling=Handling(classification=classification, handling_code="P",
                                      originator="unit-1", owning_unit="unit-1"),
                    created_by="test", created_at=now, datasets=[dataset_for(AUTHOR)],
                )  # fmt: skip
                for _ in range(2)
            ],
            tx,
        )
        await graph.commit_transaction(tx)
    finally:
        await client.aclose()
    store = await AlertStore.connect(PostgresConfig.from_env().dsn)
    try:
        alert = Alert(
            id=new_id(), rule_id="typology:r", owner_id=AUTHOR.id, mode=AlertMode.FULL,
            referent_node_ids=list(ids), investigation_id=case, created_at=now,
            dataset_id=dataset_for(AUTHOR), typology="structuring",
            words=f"4 movements from {ids[0]} to {ids[1]}", trigger="post_commit",
        )  # fmt: skip
        await store.save(alert)
        return alert.id
    finally:
        await store.close()


def test_the_queue_is_read_at_viewer_and_triaged_at_editor(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case())
    alert_id = asyncio.run(_queued_alert(case))
    hidden_id = asyncio.run(_queued_alert(case, "SECRET"))
    from services.api.app import app

    with TestClient(app) as client:
        base = f"/v1/investigations/{case}/alert-queue"
        listed = client.get(base, headers=_as(key, VIEWER))
        assert listed.status_code == 200, listed.text
        assert [q["alert"]["id"] for q in listed.json()] == [alert_id], "the SECRET one withheld"
        assert alert_id not in listed.json()[0]["summary"]
        assert client.get(base, headers=_as(key, OUTSIDER)).status_code == 404
        assert client.get(f"{base}/{hidden_id}", headers=_as(key, VIEWER)).status_code == 404
        assert client.get(f"{base}/{alert_id}", headers=_as(key, VIEWER)).status_code == 200

        assert client.post(f"{base}/{alert_id}/claim", headers=_as(key, VIEWER)).status_code == 403
        claimed = client.post(f"{base}/{alert_id}/claim", headers=_as(key, EDITOR))
        assert claimed.status_code == 200 and claimed.json()["assignee"] == EDITOR
        assert client.post(f"{base}/{alert_id}/claim",
                           headers=_as(key, AUTHOR.id)).status_code == 409  # fmt: skip
        assert client.post(f"{base}/{alert_id}/canvas", headers=_as(key, EDITOR)).status_code == 200
        no_reason = client.post(f"{base}/{alert_id}/disposition", headers=_as(key, EDITOR),
                                json={"disposition": "false_positive", "reason": ""})  # fmt: skip
        assert no_reason.status_code == 422
        closed = client.post(f"{base}/{alert_id}/disposition", headers=_as(key, EDITOR),
                             json={"disposition": "false_positive", "reason": "payroll"})  # fmt: skip
        assert closed.status_code == 200 and closed.json()["status"] == "closed"
        assert client.get(base, headers=_as(key, VIEWER)).json() == []
        assert len(client.get(f"{base}?status=closed", headers=_as(key, VIEWER)).json()) == 1


# --- phase C: ownership's routes ------------------------------------------------


def test_ownership_is_traced_at_viewer_and_drawn_at_editor(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case())
    alert_id = asyncio.run(_queued_alert(case))
    from services.api.alerts import AlertStore

    async def referents() -> list[str]:
        store = await AlertStore.connect(PostgresConfig.from_env().dsn)
        try:
            return (await store.get_case_alert(alert_id, case, AUTHOR.model_copy(update={"datasets": None}))).referent_node_ids
        finally:
            await store.close()

    owned = asyncio.run(referents())[0]
    from services.api.app import app

    with TestClient(app) as client:
        base = f"/v1/investigations/{case}/ownership/{owned}"
        traced = client.get(base, headers=_as(key, VIEWER))
        assert traced.status_code == 200, traced.text
        assert traced.json()["trace"]["target"] == owned
        assert client.get(base, headers=_as(key, OUTSIDER)).status_code == 404
        assert client.get(f"/v1/investigations/{case}/ownership/{new_id()}",
                          headers=_as(key, VIEWER)).status_code == 404  # fmt: skip
        assert client.post(f"{base}/canvas", headers=_as(key, VIEWER)).status_code == 403
        assert client.post(f"{base}/canvas", headers=_as(key, EDITOR)).status_code == 200


# --- phase F: the KYC status route ------------------------------------------------


def test_the_kyc_status_is_read_at_viewer_and_only_of_a_customer(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case())
    alert_id = asyncio.run(_queued_alert(case))
    from services.api.alerts import AlertStore

    async def an_account() -> str:
        store = await AlertStore.connect(PostgresConfig.from_env().dsn)
        try:
            alert = await store.get_case_alert(alert_id, case, AUTHOR.model_copy(update={"datasets": None}))
            return alert.referent_node_ids[0]
        finally:
            await store.close()

    account = asyncio.run(an_account())
    from services.api.app import app

    with TestClient(app) as client:
        base = f"/v1/investigations/{case}/kyc"
        refused = client.get(f"{base}/{account}", headers=_as(key, VIEWER))
        assert refused.status_code == 422 and refused.json()["error"] == "kyc_not_applicable"
        assert client.get(f"{base}/{account}", headers=_as(key, OUTSIDER)).status_code == 404
        assert client.get(f"{base}/{new_id()}", headers=_as(key, VIEWER)).status_code == 404


# --- phase D: a drawn pattern deployed as a rule ------------------------------------


def test_only_a_pattern_the_author_saved_is_deployed_as_a_rule(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case())
    from services.api.pattern_store import PatternStore

    from schemas.domain import PatternEdge, PatternNode, PatternQuery

    async def saved_by(owner: Principal) -> str:
        store = await PatternStore.connect(PostgresConfig.from_env().dsn)
        try:
            pattern = await store.save(owner, pattern_id=None, name="Company with a phone",
                definition=PatternQuery(
                    nodes=[PatternNode(var="o", entity_type="Organisation"), PatternNode(var="p", entity_type="Endpoint")],
                    edges=[PatternEdge(edge_type="USES", from_var="o", to_var="p")]))  # fmt: skip
            return pattern.pattern_id
        finally:
            await store.close()

    mine = asyncio.run(saved_by(AUTHOR))
    theirs = asyncio.run(saved_by(Principal(id=EDITOR, clearance="OFFICIAL", org_unit="unit-1")))
    from services.api.app import app

    with TestClient(app) as client:
        path = f"/v1/investigations/{case}/rules"
        body = {"name": "Drawn", "params": {"typology": "pattern", "pattern_id": theirs}, "just_me": True}
        refused = client.post(path, headers=_as(key, AUTHOR.id), json=body)
        assert refused.status_code == 422 and "only a pattern you saved" in refused.json()["detail"]
        made = client.post(path, headers=_as(key, AUTHOR.id), json={**body, "params": {"typology": "pattern", "pattern_id": mine}})
        assert made.status_code == 201, made.text
        before = client.post(path, headers=_as(key, AUTHOR.id),
                             json={**body, "params": {"typology": "pattern", "pattern_id": mine}, "trigger": "pre_commit"})  # fmt: skip
        assert before.status_code == 422


# --- phase E: neighbourhood risk's route ---------------------------------------------


def test_neighbourhood_risk_is_read_at_viewer(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    case = asyncio.run(_case())
    alert_id = asyncio.run(_queued_alert(case))
    from services.api.alerts import AlertStore

    async def a_referent() -> str:
        store = await AlertStore.connect(PostgresConfig.from_env().dsn)
        try:
            alert = await store.get_case_alert(alert_id, case, AUTHOR.model_copy(update={"datasets": None}))
            return alert.referent_node_ids[0]
        finally:
            await store.close()

    node = asyncio.run(a_referent())
    from services.api.app import app

    with TestClient(app) as client:
        base = f"/v1/investigations/{case}/risk"
        read = client.get(f"{base}/{node}", headers=_as(key, VIEWER))
        assert read.status_code == 200, read.text
        assert read.json()["score"] == 1.0, "its own alert, at no hops"
        assert client.get(f"{base}/{node}", headers=_as(key, OUTSIDER)).status_code == 404
        assert client.get(f"{base}/{new_id()}", headers=_as(key, VIEWER)).status_code == 404


def test_the_running_conduit_gives_the_alert_store_the_working_set_a_settle_purges_through(
    api_env: None,
) -> None:
    """L2.10's carry (`test_read_path_purge.py`), through the real app and its lifespan: a settle on a
    read path purges what it re-marked through `alerts_store.working_set`, so the running Conduit
    must give the store the working-set service every other purge goes through; without it, the
    copy keeps its old marking until the canvas next synchronises. Red with that line of the
    lifespan removed (rule 12: the unit case presets the wiring, so only this case sees it)."""
    from services.api.alerts import settle_repoints
    from services.api.app import app
    from services.api.working_set.service import WorkingSetService

    with TestClient(app) as client:
        store = app.state.alerts_store
        assert isinstance(store.working_set, WorkingSetService)
        assert store.working_set is app.state.working_set
        # The settle a read path calls runs on the real store and graph with it, in the app's loop.
        client.portal.call(settle_repoints, store, app.state.graph)  # type: ignore[union-attr]


def test_a_member_whose_token_no_longer_carries_the_team_reads_nothing_routed_to_it(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """ADR-146 decision 8 through a real signed token (the orchestrator's review of L2.10): a team's
    membership is the `role:<team>` its member's token carries, read on each request and never kept.
    The same Editor, signed in with the team's role, is given the routed alert; signed in again
    without it (they left the team), the queue does not show it to them."""
    from schemas.domain import Alert, AlertMode

    key, _ = keypair
    case, team = asyncio.run(_case()), f"team-{new_id()}"
    alert = Alert(id=new_id(), rule_id=f"typology:r-{new_id()}", owner_id=AUTHOR.id, mode=AlertMode.FULL,
                  investigation_id=case, created_at=datetime.now(UTC), typology="sentence",
                  words="a routed finding", routed_team=team)  # fmt: skip
    from services.api.app import app

    with TestClient(app) as client:
        store = app.state.alerts_store
        client.portal.call(store.save, alert)  # type: ignore[union-attr]
        try:
            def queued(**claims: object) -> list[str]:
                got = client.get(f"/v1/investigations/{case}/alert-queue", headers=_as(key, EDITOR, **claims))
                assert got.status_code == 200, got.text
                return [row["alert"]["id"] for row in got.json()]

            assert alert.id in queued(roles=["analyst", f"role:{team}"])
            assert alert.id not in queued(roles=["analyst"])
            assert alert.id not in queued(roles=["analyst", f"role:team-{new_id()}"])
        finally:  # Prompt L: a live test removes what it writes to a shared stack
            async def remove() -> None:
                async with store._pool.acquire() as conn:  # noqa: SLF001 - the test's own clean-up
                    await conn.execute("DELETE FROM alerts WHERE id = $1", alert.id)

            client.portal.call(remove)  # type: ignore[union-attr]
