"""Link-strength influencers' routes (`spec/06_DECISIONS.md` ADR-139 decision 3): installation-wide
by maker–checker, a case's own by its Author, every version kept and audited.

The influencer store is the real one on a throwaway Postgres, connected inside the app's own event
loop; the case store, the names directory and the audit are `test_monitoring_routes.py`'s and
`test_rule_sentence_routes.py`'s stand-ins (levels applied as the real store applies them).

What a mistake would do, and the case that catches it:
- an installation-wide influencer in force on one person's say —
  `test_an_installation_influencer_has_no_effect_until_a_second_person_approves`;
- self-approval — `test_the_proposer_cannot_approve_their_own_version`;
- a version lost or unaudited — `test_every_version_is_kept_with_who_proposed_and_who_decided`;
- a case override reaching another case, or set by a non-Author —
  `test_a_case_override_applies_only_in_its_case_and_only_its_author_sets_it`;
- an influencer naming what the ontology does not declare —
  `test_an_influencer_naming_an_undeclared_type_is_refused_in_words`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_investigations,
    get_ontology,
    get_principal,
    get_principal_names,
    get_strength_defaults,
    get_strength_influencers,
)
from services.api.config import PostgresConfig
from services.api.investigations import AccessLevel
from services.api.strength_influencers import InfluencerStore

from conduit_common.identity import new_id
from ontology.influencers import load_strength_defaults
from ontology.loader import load_default_ontology
from ontology.packs import compose_with_packs
from schemas.domain import Principal
from tests.services.api.test_monitoring_routes import _Case, _Names
from tests.services.api.test_rule_sentence_routes import _Audit

ONTOLOGY = compose_with_packs(load_default_ontology(), ["niem"])

MONEY = {
    "id": "money-floor", "label": "Money is at least medium", "link_types": ["TRANSACTED"],
    "change": "floor", "size": 0.5,
}  # fmt: skip
ASSAULT = {
    "id": "incident-source", "label": "Assault only", "link_types": ["IN_CONFLICT_WITH"],
    "trigger": {"entity_type": "Incident", "property": "category", "values": ["assault"]},
    "change": "add", "size": 0.4,
}  # fmt: skip


@asynccontextmanager
async def _no_lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


async def _clear() -> None:
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await conn.execute(
            "DROP TABLE IF EXISTS strength_influencer_versions, case_strength_influencers"
        )
    finally:
        await conn.close()


class _World:
    def __init__(self) -> None:
        self.case = f"case-{new_id()}"
        self.other_case = f"case-{new_id()}"

        def who(name: str, *roles: str) -> Principal:
            return Principal(id=f"{name}-{new_id()}", clearance="OFFICIAL", org_unit="unit-1",
                             roles=list(roles), datasets=["ds-1"])  # fmt: skip

        self.maker = who("maker", "analyst")
        self.checker = who("checker", "analyst")
        self.admin = who("admin", "osprey-admin")
        self.editor = who("editor", "analyst")
        self.engineer = who("engineer", "data_engineer")
        self.as_ = self.maker
        levels = {
            self.maker.id: AccessLevel.AUTHOR, self.checker.id: AccessLevel.AUTHOR,
            self.editor.id: AccessLevel.EDITOR,
        }  # fmt: skip
        self.cases = {self.case: _Case(self.case, levels), self.other_case: _Case(
            self.other_case, {self.maker.id: AccessLevel.AUTHOR, self.checker.id: AccessLevel.AUTHOR})}  # fmt: skip
        self.audit = _Audit()
        self.store: InfluencerStore | None = None

    async def influencers(self) -> InfluencerStore:
        if self.store is None:
            self.store = await InfluencerStore.connect(PostgresConfig.from_env().dsn)
        return self.store


class _Cases:
    """Both cases, each with its own levels, as the real store would answer."""

    def __init__(self, world: _World) -> None:
        self.world = world

    async def get_authorized(self, investigation_id: str, principal: Principal, *, need: AccessLevel) -> Any:
        case = self.world.cases.get(investigation_id) or next(iter(self.world.cases.values()))
        return await case.get_authorized(investigation_id, principal, need=need)


@pytest.fixture
def world() -> Iterator[tuple[_World, TestClient]]:
    import asyncio

    asyncio.run(_clear())
    w = _World()
    previous = app.router.lifespan_context
    app.router.lifespan_context = _no_lifespan
    defaults = load_strength_defaults()
    app.dependency_overrides.update({
        get_principal: lambda: w.as_, get_investigations: lambda: _Cases(w),
        get_ontology: lambda: ONTOLOGY, get_strength_influencers: w.influencers,
        get_strength_defaults: lambda: defaults, get_audit: lambda: w.audit,
        get_principal_names: lambda: _Names(),
    })  # fmt: skip
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield w, client
            if w.store is not None:
                client.portal.call(w.store.close)  # type: ignore[union-attr]
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = previous


def _legend(w: _World, client: TestClient, case: str | None = None) -> dict[str, Any]:
    got = client.get(f"/v1/investigations/{case or w.case}/strength-influencers")
    assert got.status_code == 200, got.text
    return got.json()  # type: ignore[no-any-return]


def _in_force(w: _World, client: TestClient, case: str | None = None) -> dict[str, tuple[str, float]]:
    return {
        a["influencer"]["id"]: (a["layer"], a["influencer"]["size"])
        for a in _legend(w, client, case)["legend"]["influencers"]
    }


def _propose(w: _World, client: TestClient, *influencers: dict[str, Any]) -> dict[str, Any]:
    made = client.post("/v1/strength-influencers", json={"influencers": list(influencers),
                                                         "words": "the client's sizes"})  # fmt: skip
    assert made.status_code == 201, made.text
    return made.json()  # type: ignore[no-any-return]


def test_an_installation_influencer_has_no_effect_until_a_second_person_approves(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    shipped = _in_force(w, client)
    assert shipped == {"direct": ("file", 0.1348), "incident-source": ("file", 0.1348)}
    proposed = _propose(w, client, MONEY, ASSAULT)
    assert proposed["status"] == "pending" and proposed["in_force"] is False
    # Waiting: nothing has changed for anyone.
    assert _in_force(w, client) == shipped
    w.as_ = w.checker
    approved = client.post(f"/v1/strength-influencers/{proposed['version']}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved" and approved.json()["in_force"] is True
    assert _in_force(w, client) == {
        "direct": ("file", 0.1348),
        "incident-source": ("installation", 0.4),
        "money-floor": ("installation", 0.5),
    }


def test_the_proposer_cannot_approve_their_own_version(world: tuple[_World, TestClient]) -> None:
    w, client = world
    proposed = _propose(w, client, MONEY)
    refused = client.post(f"/v1/strength-influencers/{proposed['version']}/approve")
    assert refused.status_code == 403
    assert refused.json()["detail"]["error"] == "own_change"
    assert "money-floor" not in _in_force(w, client)
    # The administrator holds the right too (Amendment 1's reading) and may approve.
    w.as_ = w.admin
    assert client.post(f"/v1/strength-influencers/{proposed['version']}/approve").status_code == 200


def test_one_version_waits_at_a_time_and_a_sent_back_version_changes_nothing(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    first = _propose(w, client, MONEY)
    again = client.post("/v1/strength-influencers", json={"influencers": [ASSAULT]})
    assert again.status_code == 409 and "already waiting" in again.json()["message"]
    w.as_ = w.checker
    sent = client.post(f"/v1/strength-influencers/{first['version']}/send-back",
                       json={"words": "sizes not yet agreed"})  # fmt: skip
    assert sent.status_code == 200 and sent.json()["status"] == "sent_back"
    assert "money-floor" not in _in_force(w, client)
    assert client.post(f"/v1/strength-influencers/{first['version']}/approve").status_code == 409


def test_every_version_is_kept_with_who_proposed_and_who_decided(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    one = _propose(w, client, MONEY)
    w.as_ = w.checker
    client.post(f"/v1/strength-influencers/{one['version']}/approve")
    two = _propose(w, client, ASSAULT)
    w.as_ = w.maker
    client.post(f"/v1/strength-influencers/{two['version']}/approve")
    history = client.get("/v1/strength-influencers").json()
    versions = [(v["version"], v["status"], v["in_force"]) for v in history["versions"]]
    assert versions == [(2, "approved", True), (1, "approved", False)]
    newest = history["versions"][0]
    assert newest["proposed_by"] == w.checker.id and newest["decided_by"] == w.maker.id
    assert newest["proposed_by_name"] == f"Name of {w.checker.id}"
    assert [i["id"] for i in history["defaults"]] == ["direct", "incident-source"]
    assert w.audit.actions == [
        "strength_influencers_proposed", "strength_influencers_approved",
        "strength_influencers_proposed", "strength_influencers_approved",
    ]  # fmt: skip
    # The set in force is the latest approved version alone: version 1's floor is gone.
    assert "money-floor" not in _in_force(w, client)


def test_an_influencer_naming_an_undeclared_type_is_refused_in_words(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    for bad, says in (
        ({**MONEY, "link_types": ["KNOWS_OF"]}, "KNOWS_OF"),
        ({**ASSAULT, "trigger": {**ASSAULT["trigger"], "entity_type": "Riot"}}, "Riot"),
        ({**ASSAULT, "trigger": {**ASSAULT["trigger"], "property": "severity"}}, "severity"),
        ({**ASSAULT, "trigger": {**ASSAULT["trigger"], "values": ["arson"]}}, "arson"),
    ):
        refused = client.post("/v1/strength-influencers", json={"influencers": [bad]})
        assert refused.status_code == 422, bad
        assert refused.json()["error"] == "influencer_refused" and says in refused.json()["reason"]
    assert client.get("/v1/strength-influencers").json()["versions"] == []


def test_a_case_override_applies_only_in_its_case_and_only_its_author_sets_it(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    override = {"added": [{**MONEY, "id": "case-money"}], "switched_off": ["direct"],
                "words": "this case's money matters"}  # fmt: skip
    w.as_ = w.editor
    assert _legend(w, client)["can_override"] is False
    refused = client.put(f"/v1/investigations/{w.case}/strength-influencers", json=override)
    assert refused.status_code == 403
    w.as_ = w.maker
    assert _legend(w, client)["can_override"] is True
    saved = client.put(f"/v1/investigations/{w.case}/strength-influencers", json=override)
    assert saved.status_code == 200, saved.text
    legend = saved.json()["legend"]
    assert [(a["influencer"]["id"], a["layer"]) for a in legend["influencers"]] == [
        ("incident-source", "file"), ("case-money", "case")
    ]
    assert legend["switched_off"] == ["direct"]
    # A rule with no trigger is a direct-links rule (decision 1): money counts as direct here.
    assert legend["direct_link_types"] == ["TRANSACTED"]
    assert legend["case_version"] == 1 and legend["case_set_by_name"] == f"Name of {w.maker.id}"
    assert "case_strength_influencers_set" in w.audit.actions
    # Another case is untouched.
    other = _in_force(w, client, w.other_case)
    assert other == {"direct": ("file", 0.1348), "incident-source": ("file", 0.1348)}
    # The resolution order: the case's own, over the installation's, over the file's.
    proposed = _propose(w, client, {**ASSAULT, "size": 0.6})
    w.as_ = w.checker
    client.post(f"/v1/strength-influencers/{proposed['version']}/approve")
    w.as_ = w.maker
    client.put(f"/v1/investigations/{w.case}/strength-influencers",
               json={"added": [{**ASSAULT, "size": 0.9}]})  # fmt: skip
    assert _in_force(w, client)["incident-source"] == ("case", 0.9)
    assert _in_force(w, client, w.other_case)["incident-source"] == ("installation", 0.6)


# --- ADR-139 Amendment 2: the composition, the rarity measure and dataset triggers -------------


def _composition(w: _World, client: TestClient, case: str | None = None) -> tuple[str, str, str]:
    legend = _legend(w, client, case)["legend"]
    return legend["composition"], legend["composition_layer"], legend["rarity_measure"]


def test_an_installation_composition_takes_effect_only_when_a_second_person_approves(
    world: tuple[_World, TestClient],
) -> None:
    """Amendment 2: an installation chooses client parity (and a rarity measure) by maker–checker,
    as it does its influencers: the proposal changes nothing until approved, and the version keeps
    what it chose."""
    w, client = world
    assert _composition(w, client) == ("standard", "file", "share")
    history = client.get("/v1/strength-influencers").json()
    assert (history["default_composition"], history["default_rarity_measure"]) == ("standard", "share")
    made = client.post("/v1/strength-influencers", json={
        "influencers": [MONEY], "composition": "client_parity", "rarity_measure": "share",
        "words": "the client's own sum",
    })  # fmt: skip
    assert made.status_code == 201, made.text
    assert made.json()["composition"] == "client_parity"
    assert _composition(w, client) == ("standard", "file", "share")
    w.as_ = w.checker
    assert client.post(f"/v1/strength-influencers/{made.json()['version']}/approve").status_code == 200
    assert _composition(w, client) == ("client_parity", "installation", "share")
    # A later version that chooses IDF under the standard composition.
    again = client.post("/v1/strength-influencers", json={
        "influencers": [MONEY], "composition": "standard", "rarity_measure": "idf"})  # fmt: skip
    w.as_ = w.maker
    client.post(f"/v1/strength-influencers/{again.json()['version']}/approve")
    assert _composition(w, client) == ("standard", "installation", "idf")


def test_a_case_override_switches_only_its_case_to_client_parity(
    world: tuple[_World, TestClient],
) -> None:
    """Amendment 2, ruling 5: the demonstration's switch. The case's Author sets client parity for
    the case alone; the case's own wins over the installation's; clearing it restores it."""
    w, client = world
    w.as_ = w.maker
    saved = client.put(f"/v1/investigations/{w.case}/strength-influencers",
                       json={"composition": "client_parity"})  # fmt: skip
    assert saved.status_code == 200, saved.text
    assert saved.json()["override"]["composition"] == "client_parity"
    assert _composition(w, client) == ("client_parity", "case", "share")
    assert _composition(w, client, w.other_case) == ("standard", "file", "share")
    w.as_ = w.editor
    refused = client.put(f"/v1/investigations/{w.case}/strength-influencers",
                         json={"composition": "standard"})  # fmt: skip
    assert refused.status_code == 403
    w.as_ = w.maker
    client.put(f"/v1/investigations/{w.case}/strength-influencers", json={})
    assert _composition(w, client) == ("standard", "file", "share")


def test_a_dataset_trigger_and_a_shared_value_are_accepted_and_told_only_to_a_reader_of_it(
    world: tuple[_World, TestClient],
) -> None:
    """Amendment 2, ruling 3: a dataset-triggered influencer, on stored links and on a pair linked
    through a shared value, is accepted (no ontology name to check beyond the link types); the
    legend names it only to a reader whose case reads that dataset (the fixture's analysts read
    `ds-1`)."""
    w, client = world
    w.as_ = w.maker
    by_dataset = {
        "id": "source-ds-1", "label": "From ds-1", "link_types": ["TRANSACTED", "SHARED_VALUE"],
        "trigger": {"kind": "dataset", "datasets": ["ds-1", "ds-2"]}, "size": 0.2,
    }  # fmt: skip
    elsewhere = {**by_dataset, "id": "source-ds-9", "trigger": {"kind": "dataset", "datasets": ["ds-9"]}}
    saved = client.put(f"/v1/investigations/{w.case}/strength-influencers",
                       json={"added": [by_dataset, elsewhere]})  # fmt: skip
    assert saved.status_code == 200, saved.text
    shown = {a["influencer"]["id"]: a["influencer"]["trigger"] for a in saved.json()["legend"]["influencers"]}
    assert shown["source-ds-1"] == {"kind": "dataset", "datasets": ["ds-1"]}
    assert "source-ds-9" not in shown
    assert "ds-9" not in str(saved.json()["legend"])
    # A reader who cannot set the override is not told of it there either.
    w.as_ = w.editor
    override = _legend(w, client)["override"]
    assert [i["id"] for i in override["added"]] == ["source-ds-1"]
    assert "ds-9" not in str(override)
    # A record trigger on a shared value is refused in words.
    w.as_ = w.maker
    bad = {**ASSAULT, "link_types": ["SHARED_VALUE"]}
    refused = client.put(f"/v1/investigations/{w.case}/strength-influencers", json={"added": [bad]})
    assert refused.status_code == 422
