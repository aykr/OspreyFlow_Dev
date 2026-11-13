"""Admin › Roles, teams and *Disable…*, L2.5 (ADR-145 decisions 6 and 7 and Amendment 5; ADR-112
Amendments 4 and 5). The real app, `require_right` and the routes run; the stores are stand-ins
holding what the real ones hold (`test_custom_roles_store.py` runs the real ones under the lease).

What a mistake would do, and the case that catches it (each shown red with its check removed,
`process/lanes/admin/L2.5_RED_RECORD.md`):

- a route answered without `manage_people`: `test_every_route_refuses_without_the_right`;
- decision 7's refusals skipped at the route (the form alone refusing):
  `test_a_role_is_refused_at_the_route_in_words` (name, no rights, unknown right, each pair, a right
  the giver may not give) and `test_a_change_that_locks_out_every_administrator_is_refused`;
- a custom role conferring more than it was given: `test_a_custom_role_confers_exactly_its_rights`;
- a person given an administration right by someone without it, or the last people manager's
  roles taken away: the `test_giving_…` cases;
- a service account made a team member, lead or cover: `test_a_service_account_…` cases;
- *Disable…* accepted with an item untransferred, or to someone who cannot take it:
  `test_disable_is_refused_while_an_item_is_untransferred`, `test_disable_refuses_a_recipient_…`,
  and allowed once all are: `test_disable_transfers_every_item_then_disables`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import admin_people as admin_people_module
from services.api.admin_people import DisableRefused, check_transfers
from services.api.app import app
from services.api.custom_roles import RoleRefused, acting_lead

from ontology.handling import load_uk_le_scheme
from schemas.admin import (
    CustomRole,
    CustomRoleVersion,
    DisablePlan,
    OwnedItem,
    OwnedTransfer,
    PersonAccount,
    Team,
    TeamInput,
)
from schemas.domain import Principal
from schemas.rights import Right

T0 = datetime(2026, 11, 8, tzinfo=UTC)

PEOPLE: dict[str, PersonAccount] = {}
TOKENS: dict[str, Principal] = {}


def _person(pid: str, roles: list[str], *, enabled: bool = True, system: bool = False,
            username: str | None = None) -> None:  # fmt: skip
    PEOPLE[pid] = PersonAccount(id=pid, username=username or pid, name=f"Name {pid}",
                                enabled=enabled, roles=list(roles), system_account=system,
                                org_unit="unit-1")  # fmt: skip
    TOKENS[pid] = Principal(id=pid, clearance="SECRET", org_unit="unit-1", roles=list(roles))


class _Resolver:
    async def resolve_principal(self, token: str) -> Principal:
        return self.resolve(token)

    def resolve(self, token: str) -> Principal:
        return TOKENS[token]


class _Directory:
    """The identity provider's people (`IdentityAdmin`)."""

    def __init__(self) -> None:
        self.disabled: list[str] = []
        self.refuse = False
        self.write_delay = 0.0
        self.invited: list[str] = []

    async def list_people(self) -> list[PersonAccount]:
        """As the real one: a client's service account (`service-account-*`) is never listed; an
        account OspreyFlow itself uses (the verify probes) is listed and marked a system account."""
        return [p.model_copy() for p in PEOPLE.values()
                if not p.username.startswith("service-account-")]  # fmt: skip

    async def set_roles(self, user_id: str, roles: list[str]) -> PersonAccount:
        import asyncio

        await asyncio.sleep(self.write_delay)  # the identity provider's round trip
        PEOPLE[user_id] = PEOPLE[user_id].model_copy(update={"roles": roles})
        return PEOPLE[user_id]

    async def invite(self, invite: Any) -> Any:
        from schemas.admin import SignInDelivery

        self.invited.append(invite.username)
        made = PersonAccount(id=f"new-{invite.username}", username=invite.username,
                             name=invite.username, enabled=True, roles=invite.roles)  # fmt: skip
        return SignInDelivery(person=made, delivery="one_time_code", one_time_code="ABCD-EFGH")

    async def list_dashboards(self) -> list[Any]:
        return [SimpleNamespace(account_id="sa-board")]

    async def remove_person(self, user_id: str, custom: Any = None) -> PersonAccount:
        return PEOPLE.pop(user_id)

    async def set_enabled(self, user_id: str, enabled: bool) -> PersonAccount:
        if self.refuse:
            from services.api.identity_admin import IdentityAdminRefused

            raise IdentityAdminRefused("the identity provider did not answer")
        self.disabled.append(user_id)
        PEOPLE[user_id] = PEOPLE[user_id].model_copy(update={"enabled": enabled})
        return PEOPLE[user_id]


class _Roles:
    """`CustomRoleStore` as it holds roles: versions, a unique name, teams, and the people lock
    (`people_lock`, one at a time, as the real advisory lock is)."""

    def __init__(self) -> None:
        import asyncio

        self._lock = asyncio.Lock()
        self.locked_now = 0
        self.roles: dict[str, CustomRole] = {}
        self.versions_of: dict[str, list[CustomRoleVersion]] = {}
        self.teams_of: dict[str, Team] = {}

    def seed(self, role_id: str, name: str, rights: Sequence[Right]) -> None:
        self.roles[role_id] = CustomRole(id=role_id, name=name, version=1, rights=list(rights),
                                         changed_by="seed", changed_at=T0)  # fmt: skip
        self.versions_of[role_id] = [CustomRoleVersion(version=1, name=name, rights=list(rights),
                                                       changed_by="seed", changed_at=T0)]  # fmt: skip

    async def current_rights(self, ids: Sequence[str] | None = None) -> dict[str, frozenset[Right]]:
        return {i: frozenset(r.rights) for i, r in self.roles.items() if ids is None or i in ids}

    def people_lock(self) -> Any:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def held() -> Any:
            async with self._lock:
                self.locked_now += 1
                try:
                    yield
                finally:
                    self.locked_now -= 1

        return held()

    async def expand(self, principal: Principal) -> Principal:
        from services.api.custom_roles import custom_role_ids, expand

        return expand(principal, await self.current_rights(custom_role_ids(principal.roles)))

    async def names(self, *, except_id: str | None = None) -> list[str]:
        return [r.name for i, r in self.roles.items() if i != except_id]

    async def list(self, today: date) -> list[CustomRole]:
        return [r.model_copy(update={"team": self.teams_of.get(i)}) for i, r in self.roles.items()]

    async def get(self, role_id: str, today: date) -> CustomRole | None:
        return self.roles.get(role_id)

    async def create(self, name: str, rights: Sequence[Right], *, by: str) -> CustomRole:
        role_id = f"r{len(self.roles) + 1}"
        self.seed(role_id, name, rights)
        return self.roles[role_id]

    async def update(self, role_id: str, name: str, rights: Sequence[Right], *, by: str) -> Any:
        before = self.roles[role_id]
        after = before.model_copy(update={"name": name, "rights": list(rights),
                                          "version": before.version + 1})  # fmt: skip
        self.roles[role_id] = after
        return before, after

    async def versions(self, role_id: str) -> list[CustomRoleVersion]:
        return self.versions_of.get(role_id, [])

    async def make_team(self, role_id: str, team: TeamInput, today: date) -> Team:
        """As the real store's upsert: a re-save keeps the lead and the cover; a name another team
        holds is refused, as its unique index refuses it."""
        if any(t.display_name.lower() == team.display_name.strip().lower()
               for rid, t in self.teams_of.items() if rid != role_id):  # fmt: skip
            raise RoleRefused("team_name_taken", f"a team called {team.display_name} already exists")
        kept = self.teams_of.get(role_id)
        self.teams_of[role_id] = Team(role_id=role_id, display_name=team.display_name,
                                      mailbox=team.mailbox, lead=kept.lead if kept else None,
                                      cover=kept.cover if kept else None,
                                      cover_until=kept.cover_until if kept else None)  # fmt: skip
        return self.teams_of[role_id]

    async def teams(self, today: date) -> list[Team]:
        return [t for t in [await self.team(i, today) for i in self.teams_of] if t is not None]

    async def all(self, today: date) -> list[CustomRole]:
        return await self.list(today)

    async def team(self, role_id: str, today: date) -> Team | None:
        team = self.teams_of.get(role_id)
        return None if team is None else team.model_copy(update={"acting_lead": acting_lead(team, today)})

    async def set_lead(self, role_id: str, lead: str, today: date) -> Any:
        before = self.teams_of[role_id]
        self.teams_of[role_id] = before.model_copy(update={"lead": lead})
        return before, self.teams_of[role_id]

    async def set_cover(self, role_id: str, cover: str | None, until: date | None, today: date) -> Any:
        before = self.teams_of[role_id]
        self.teams_of[role_id] = before.model_copy(update={"cover": cover, "cover_until": until})
        return before, self.teams_of[role_id]


class _AdminPeople:
    """`AdminPeopleStore`: the plan as given, and the real `check_transfers` before any write."""

    def __init__(self) -> None:
        self.items: dict[str, list[OwnedItem]] = {}
        self.moved: list[tuple[str, str, str]] = []
        #: How many items each person owns in another unit (the real store counts them in SQL).
        self.elsewhere: dict[str, int] = {}
        #: Whether each person owns items the administrator may not see (L3.8's `withheld`).
        self.withheld: dict[str, bool] = {}
        self.asked_withheld: list[str] = []
        #: The store calls the route makes after the transfer, in order.
        self.order: list[str] = []

    async def end_covers(self, person: str, *, by: Principal, audit: Any) -> None:
        self.order.append("end_covers")

    async def plan(self, person: str, *, admin: Principal, scheme: Any,
                   people: Any = None) -> DisablePlan:  # fmt: skip
        return DisablePlan(person=person, items=self.items.get(person, []),
                           not_yet_listed=list(admin_people_module.L38_OWNED_KINDS))  # fmt: skip

    async def refuse_if_withheld(self, person: str, *, admin: Principal, scheme: Any) -> None:
        """The real `person_ownership.refuse_if_withheld`, its one read answered as the real
        `_WITHHELD_SQL` would for this person (`test_disable_l38_transfers.py` runs the real one)."""
        from services.api.person_ownership import refuse_if_withheld

        class _Answers:
            def __init__(self, hidden: bool) -> None:
                self.hidden = hidden

            async def fetchval(self, sql: str, *args: Any) -> bool:
                # What the real `_WITHHELD_SQL` binds: the person, the administrator's unit, the
                # markings they clear, the scheme's highest (review finding 10), and the handling
                # codes they may receive, which a screening list's schedule is read by (ADR-146
                # Amendment 7; the orchestrator's verification of lane/rules-lists at 7a1c760).
                cleared = [m for m in scheme.classification if scheme.clears(admin.clearance, m)]
                codes = [k for k, d in scheme.handling_codes.items()
                         if d.dissemination != "restricted" or k in admin.receivable_handling_codes]  # fmt: skip
                assert "EXISTS" in sql and "screening_lists" in sql
                assert args == (person, admin.org_unit, cleared, scheme.classification[-1], codes), args
                return self.hidden

        self.asked_withheld.append(person)
        self.order.append("refuse_if_withheld")
        await refuse_if_withheld(_Answers(self.withheld.get(person, False)), person,  # type: ignore[arg-type]
                                 admin=admin, scheme=scheme)  # fmt: skip

    async def transfer(self, person: str, transfers: Any, who: Any, *, by: Principal, audit: Any,
                       admin_unit: str | None,
                       scheme: Any) -> tuple[list[tuple[OwnedItem, str]], int]:  # fmt: skip
        items = self.items.get(person, [])
        chosen = check_transfers(person, items, transfers, who, admin_unit)
        for item in items:
            to = chosen[(item.kind, item.id)]
            self.moved.append((item.kind, item.id, to))
            await audit.record(principal=by, action="transfer_owned_item", result_cardinality=1,
                               resolved_query={"from": person, "to": to, "kind": item.kind,
                                               "id": item.id})  # fmt: skip
        self.items[person] = []
        return [(i, chosen[(i.kind, i.id)]) for i in items], self.elsewhere.get(person, 0)


class _Cases:
    """`InvestigationStore`'s safety-net reads: a case found by unit only, its grants."""

    def __init__(self) -> None:
        from services.api.investigations import AccessLevel, Investigation

        self.made = {
            cid: Investigation(id=cid, name=name, created_at=T0, created_by="seed", owning_unit=unit)
            for cid, name, unit in (("c3", "Op Wren", "unit-1"), ("c4", "Op Kite", "unit-1"),
                                    ("c9", "Elsewhere", "unit-2"))
        }  # fmt: skip
        self.grants: dict[str, dict[str, Any]] = {
            "c3": {"gone": AccessLevel.AUTHOR}, "c4": {"ana-1": AccessLevel.AUTHOR}, "c9": {}}  # fmt: skip

    async def get_for_access_admin(self, case_id: str, principal: Principal) -> Any:
        from services.api.investigations import InvestigationNotFoundError

        case = self.made.get(case_id)
        if case is None or case.owning_unit != principal.org_unit:
            raise InvestigationNotFoundError(case_id)
        return case

    async def list_grants(self, case_id: str) -> dict[str, Any]:
        return dict(self.grants[case_id])

    async def set_grant(self, case_id: str, account: str, level: Any, *, by: Principal) -> None:
        self.grants[case_id][account] = level


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    PEOPLE.clear()
    TOKENS.clear()
    _person("adm-1", ["osprey-admin"])
    _person("adm-2", ["osprey-admin"])
    _person("ppl-1", ["right:manage_people"])
    _person("ana-1", ["analyst", "role:r1"])
    _person("ana-2", ["analyst", "role:r1"])
    _person("eng-1", ["data_engineer"])
    _person("robot", ["role:r2"], system=True, username="osprey-verify-probe")
    _person("sa-1", ["reports_viewer"], system=True, username="service-account-osprey-dashboard-x")
    _person("gone", ["analyst"], enabled=False)
    roles, directory, admin_people, audit = _Roles(), _Directory(), _AdminPeople(), _Audit()
    roles.seed("r1", "Intel desk", [Right.INVESTIGATE, Right.READ_REPORTS])
    roles.seed("r2", "Feeds", [Right.READ_DATA_FEEDS])
    state = {"principal_resolver": _Resolver(), "custom_roles": roles, "identity_admin": directory,
             "investigations": _Cases(), "principal_names": _People(),
             "admin_people": admin_people, "audit": audit,
             "handling_scheme": load_uk_le_scheme()}  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(client=TestClient(app), roles=roles, directory=directory,
                          admin_people=admin_people, audit=audit,
                          cases=app.state.investigations)  # fmt: skip


def _as(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/v1/admin/roles", None),
    ("POST", "/v1/admin/roles", {"name": "Desk", "rights": ["investigate"]}),
    ("PUT", "/v1/admin/roles/r1", {"name": "Intel desk", "rights": ["investigate"]}),
    ("GET", "/v1/admin/roles/r1/versions", None),
    ("PUT", "/v1/admin/roles/r1/team", {"display_name": "Intel", "mailbox": "intel@example.org"}),
    ("PUT", "/v1/admin/teams/r1/lead", {"lead": "ana-1"}),
    ("PUT", "/v1/admin/teams/r1/cover", {"cover": None}),
    ("GET", "/v1/admin/people/rows", None),
    ("GET", "/v1/admin/people/ana-1/disable-plan", None),
    ("POST", "/v1/admin/people/ana-1/disable", {"transfers": []}),
    ("PUT", "/v1/admin/cases/c3/authors/ana-2", None),
]  # fmt: skip


@pytest.mark.parametrize(("method", "path", "body"), ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
@pytest.mark.parametrize("person", ["eng-1", "ana-1"])
def test_every_route_refuses_without_the_right(
    world: SimpleNamespace, person: str, method: str, path: str, body: Any
) -> None:
    answer = world.client.request(method, path, json=body, headers=_as(person))
    assert answer.status_code == 403, answer.text
    assert answer.json()["detail"] == {"error": "right_required", "right": "manage_people"}
    assert world.audit.entries == []


def _make(world: SimpleNamespace, rights: list[str], *, name: str = "Desk",
          who: str = "adm-1") -> Any:  # fmt: skip
    return world.client.post("/v1/admin/roles", json={"name": name, "rights": rights},
                             headers=_as(who))  # fmt: skip


@pytest.mark.parametrize(
    ("name", "rights", "who", "error"),
    [
        ("intel  DESK", ["investigate"], "adm-1", "name_taken"),
        ("Analyst", ["investigate"], "adm-1", "name_taken"),
        ("Desk", [], "adm-1", "no_rights"),
        ("Desk", ["investigate", "fly"], "adm-1", "unknown_right"),
        ("Desk", ["promote_to_dataset", "review_promotions"], "adm-1", "forbidden_pair"),
        ("Desk", ["propose_types", "accept_types"], "adm-1", "forbidden_pair"),
        ("Desk", ["administer_system"], "ppl-1", "beyond_your_rights"),
    ],
    ids=["name-used", "built-in-name", "no-rights", "unknown", "promote-pair", "types-pair",
         "beyond-giver"],
)  # fmt: skip
def test_a_role_is_refused_at_the_route_in_words(
    world: SimpleNamespace, name: str, rights: list[str], who: str, error: str
) -> None:
    answer = _make(world, rights, name=name, who=who)
    assert answer.status_code == 409, answer.text
    assert answer.json()["detail"]["error"] == error
    assert answer.json()["detail"]["message"]
    assert set(world.roles.roles) == {"r1", "r2"}
    assert world.audit.entries == []


def test_a_role_is_made_v1_with_exactly_its_rights_and_audited(world: SimpleNamespace) -> None:
    answer = _make(world, ["run_analysis", "investigate"])
    assert answer.status_code == 201, answer.text
    assert answer.json()["version"] == 1
    assert answer.json()["rights"] == ["investigate", "run_analysis"]
    (entry,) = world.audit.entries
    assert entry["action"] == "create_custom_role"
    assert entry["resolved_query"]["rights"] == ["investigate", "run_analysis"]


def test_a_change_is_the_next_version_with_before_and_after(world: SimpleNamespace) -> None:
    answer = world.client.put("/v1/admin/roles/r1", json={"name": "Intel desk",
                              "rights": ["investigate"]}, headers=_as("adm-1"))  # fmt: skip
    assert answer.status_code == 200, answer.text
    assert answer.json()["version"] == 2
    (entry,) = world.audit.entries
    assert entry["resolved_query"]["before"]["rights"] == ["investigate", "read_reports"]
    assert entry["resolved_query"]["after"]["rights"] == ["investigate"]


def test_a_change_that_locks_out_every_administrator_is_refused(world: SimpleNamespace) -> None:
    """The people managers are adm-1, adm-2 and ppl-1; make r1 the only way to manage people, then
    take manage_people out of it."""
    for pid in ("adm-1", "adm-2", "ppl-1"):
        PEOPLE[pid] = PEOPLE[pid].model_copy(update={"enabled": False})
    world.roles.seed("r3", "People desk", [Right.MANAGE_PEOPLE])
    _person("ppl-2", ["role:r3"])
    answer = world.client.put("/v1/admin/roles/r3", json={"name": "People desk",
                              "rights": ["investigate"]}, headers=_as("ppl-2"))  # fmt: skip
    assert answer.status_code == 409, answer.text
    assert answer.json()["detail"]["error"] == "locks_out_administrators"
    assert world.roles.roles["r3"].version == 1


def test_a_custom_role_confers_exactly_its_rights(world: SimpleNamespace) -> None:
    """`GET /v1/me/rights` for a holder of r1 alone: its two rights, and nothing more."""
    _person("solo", ["role:r1"])
    answer = world.client.get("/v1/me/rights", headers=_as("solo"))
    assert answer.status_code == 200, answer.text
    assert answer.json()["rights"] == ["investigate", "read_reports"]


def test_a_custom_role_edit_applies_at_the_next_request(world: SimpleNamespace) -> None:
    """Asked before and after the edit, so a rights read kept between requests fails (rule 15: the
    first version asked only after, and a cache planted in passed it)."""
    _person("solo", ["role:r1"])
    before = world.client.get("/v1/me/rights", headers=_as("solo")).json()["rights"]
    assert before == ["investigate", "read_reports"]
    world.roles.roles["r1"] = world.roles.roles["r1"].model_copy(update={"rights": [Right.READ_REPORTS]})
    assert world.client.get("/v1/me/rights", headers=_as("solo")).json()["rights"] == ["read_reports"]


# --- giving roles (PUT /v1/admin/people/{id}/roles) -----------------------------------------------


def _give(world: SimpleNamespace, who: str, to: str, roles: list[str]) -> Any:
    return world.client.put(f"/v1/admin/people/{to}/roles", json={"roles": roles}, headers=_as(who))


def test_giving_an_administration_right_needs_its_holder(world: SimpleNamespace) -> None:
    answer = _give(world, "ppl-1", "eng-1", ["data_engineer", "osprey-admin"])
    assert answer.status_code == 409, answer.text
    assert answer.json()["detail"]["error"] == "beyond_your_rights"
    assert PEOPLE["eng-1"].roles == ["data_engineer"]
    assert _give(world, "ppl-1", "eng-1", ["data_engineer", "analyst"]).status_code == 200


def test_giving_a_custom_role_that_does_not_exist_is_refused(world: SimpleNamespace) -> None:
    answer = _give(world, "adm-1", "eng-1", ["data_engineer", "role:nope"])
    assert answer.status_code == 422, answer.text


def test_giving_away_the_last_people_managers_right_is_refused(world: SimpleNamespace) -> None:
    PEOPLE["adm-2"] = PEOPLE["adm-2"].model_copy(update={"enabled": False})
    PEOPLE["ppl-1"] = PEOPLE["ppl-1"].model_copy(update={"enabled": False})
    answer = _give(world, "adm-1", "adm-1", ["analyst"])
    assert answer.status_code == 409, answer.text
    assert answer.json()["detail"]["error"] == "locks_out_administrators"


def test_the_super_user_preset_is_given_as_three_roles(world: SimpleNamespace) -> None:
    catalogue = world.client.get("/v1/admin/roles", headers=_as("adm-1")).json()
    (preset,) = [r for r in catalogue["built_in"] if r["id"] == "super_user"]
    assert preset["gives"] == ["analyst", "data_engineer", "rule_author"]
    assert _give(world, "adm-1", "eng-1", preset["gives"]).status_code == 200


# --- teams, leads and service accounts --------------------------------------------------------------


def _team(world: SimpleNamespace, role: str = "r1") -> Any:
    return world.client.put(f"/v1/admin/roles/{role}/team", json={"display_name": "Intel",
                            "mailbox": "intel@example.org"}, headers=_as("adm-1"))  # fmt: skip


def test_a_role_held_by_a_service_account_is_not_made_a_team(world: SimpleNamespace) -> None:
    answer = _team(world, "r2")
    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "service_account"
    assert "r2" not in world.roles.teams_of


def test_a_team_role_is_not_given_to_a_service_account(world: SimpleNamespace) -> None:
    assert _team(world).status_code == 200
    answer = _give(world, "adm-1", "robot", ["role:r2", "role:r1"])
    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "service_account"


def test_a_team_lists_its_holders_as_members(world: SimpleNamespace) -> None:
    team = _team(world).json()
    assert {m["id"] for m in team["members"]} == {"ana-1", "ana-2"}


def test_only_a_member_may_be_lead_and_a_service_account_never(world: SimpleNamespace) -> None:
    _team(world)
    lead = lambda who: world.client.put("/v1/admin/teams/r1/lead", json={"lead": who},  # noqa: E731
                                        headers=_as("adm-1"))  # fmt: skip
    assert lead("eng-1").json()["detail"]["error"] == "not_a_member"
    _person("robot", ["role:r1"], system=True, username="osprey-verify-probe")
    assert lead("robot").json()["detail"]["error"] == "service_account"
    answer = lead("ana-1")
    assert answer.status_code == 200 and answer.json()["lead"] == "ana-1"
    assert world.audit.entries[-1]["action"] == "set_team_lead"


def test_a_cover_is_a_member_until_a_day_and_never_a_service_account(world: SimpleNamespace) -> None:
    _team(world)
    world.client.put("/v1/admin/teams/r1/lead", json={"lead": "ana-1"}, headers=_as("adm-1"))
    until = str(T0.date() + timedelta(days=400))
    cover = lambda who, day=until: world.client.put(  # noqa: E731
        "/v1/admin/teams/r1/cover", json={"cover": who, "until": day}, headers=_as("adm-1"))
    _person("robot", ["role:r1"], system=True, username="osprey-verify-probe")
    assert cover("robot").json()["detail"]["error"] == "service_account"
    assert cover("eng-1").json()["detail"]["error"] == "not_a_member"
    assert cover("ana-1").json()["detail"]["error"] == "cover_is_lead"
    assert cover("ana-2", "2001-01-01").json()["detail"]["error"] == "cover_date"
    answer = cover("ana-2")
    assert answer.status_code == 200 and answer.json()["cover"] == "ana-2"


# --- Disable… ---------------------------------------------------------------------------------------


ITEMS = [
    OwnedItem(kind="case_author", id="c1", label="Only Author of the case Kestrel"),
    OwnedItem(kind="typology_rule", id="t1", label="The rule Structuring, whose runs act as them"),
    OwnedItem(kind="team_lead", id="r1", label="Lead of the team Intel"),
]


def _disable(world: SimpleNamespace, transfers: list[dict[str, str]], who: str = "ana-1") -> Any:
    return world.client.post(f"/v1/admin/people/{who}/disable", json={"transfers": transfers},
                             headers=_as("adm-1"))  # fmt: skip


def test_the_plan_names_what_is_not_yet_listed(world: SimpleNamespace) -> None:
    world.admin_people.items["ana-1"] = ITEMS
    plan = world.client.get("/v1/admin/people/ana-1/disable-plan", headers=_as("adm-1")).json()
    assert [i["id"] for i in plan["items"]] == ["c1", "t1", "r1"]
    # L2.5b: views, boards, proposed types and drawn watches are listed now (L3.8's route); only
    # the promotions' kinds are still to come.
    assert plan["not_yet_listed"] == ["promotions waiting for review", "reviews waiting on them"]


# --- L2.5b: Disable's full transfer list (ADR-145 Amendment 8) ---------------------------------------

L38_ITEMS = [
    OwnedItem(kind="view", id="v1", label="A private view of the case Kestrel", investigation_id="c1"),
    OwnedItem(kind="board", id="b1", label="A private board of the case Kestrel", investigation_id="c1"),
    OwnedItem(kind="link_type_proposal", id="p1", investigation_id="c1",
              label="A proposed link type in the case Kestrel, waiting for a decision"),
    OwnedItem(kind="drawn_watch", id="w1", investigation_id="c1",
              label="A watch on an item they drew in the case Kestrel"),
]  # fmt: skip


def test_the_plan_offers_each_of_l38s_items_with_its_case(world: SimpleNamespace) -> None:
    world.admin_people.items["ana-1"] = L38_ITEMS
    plan = world.client.get("/v1/admin/people/ana-1/disable-plan", headers=_as("adm-1")).json()
    assert [(i["kind"], i["investigation_id"]) for i in plan["items"]] == [
        ("view", "c1"), ("board", "c1"), ("link_type_proposal", "c1"), ("drawn_watch", "c1")]  # fmt: skip


def test_disable_is_refused_while_an_item_is_withheld_and_the_visible_transfers_stand(
    world: SimpleNamespace,
) -> None:
    """ADR-145 Amendment 8 decision 3 (the owner's ruling of 9 November 2026): asked after the
    visible transfers commit, which stand; 409 `withheld_items`, in words naming nothing of the
    items, and the identity provider never asked. Once nothing is withheld, the disable goes."""
    world.admin_people.items["ana-1"] = L38_ITEMS[:1]
    world.admin_people.withheld["ana-1"] = True
    answer = _disable(world, [{"kind": "view", "id": "v1", "to": "ana-2"}])
    assert answer.status_code == 409, answer.text
    detail = answer.json()["detail"]
    assert detail["error"] == "withheld_items"
    assert "1 transferred, and those stand" in detail["message"]
    said = detail["message"].lower().replace("1 transferred", "")
    for word in ("view", "board", "proposal", "type", "watch", "secret", "official", "kestrel"):
        assert word not in said, word
    assert not any(ch.isdigit() for ch in said), "never how many"
    assert world.admin_people.moved == [("view", "v1", "ana-2")]
    assert world.admin_people.asked_withheld == ["ana-1"], "asked after the transfers"
    assert world.admin_people.order == ["refuse_if_withheld"], "no cover ends while refused"
    assert world.directory.disabled == []
    assert "disable_person" not in [e["action"] for e in world.audit.entries]
    world.admin_people.withheld["ana-1"] = False
    assert _disable(world, []).status_code == 200 and world.directory.disabled == ["ana-1"]
    assert world.admin_people.order[1:] == ["refuse_if_withheld", "end_covers"]


def test_withheld_is_asked_only_once_the_transfers_are_accepted(world: SimpleNamespace) -> None:
    """A refused transfer (an item untransferred) answers its own refusal; nothing is asked after
    it, so a person never learns from the order of refusals that withheld items exist."""
    world.admin_people.items["ana-1"] = L38_ITEMS[:2]
    world.admin_people.withheld["ana-1"] = True
    answer = _disable(world, [{"kind": "view", "id": "v1", "to": "ana-2"}])
    assert answer.json()["detail"]["error"] == "untransferred"
    assert world.admin_people.asked_withheld == []


def test_other_units_items_are_answered_before_withheld_ones(world: SimpleNamespace) -> None:
    world.admin_people.items["ana-1"] = []
    world.admin_people.elsewhere["ana-1"] = 1
    world.admin_people.withheld["ana-1"] = True
    assert _disable(world, []).json()["detail"]["error"] == "other_unit"


@pytest.mark.parametrize(
    ("kind", "right"),
    [("board", "draw_on_boards"), ("drawn_watch", "draw_on_boards"),
     ("link_type_proposal", "propose_types"), ("view", "investigate")],
)  # fmt: skip
def test_each_l38_item_needs_the_right_its_own_route_asks(kind: str, right: str) -> None:
    """The right each item's own route checks (`_DRAWS`, the proposal route, the views' save),
    which its recipient must hold or the item is theirs and they cannot use it."""
    from services.api.admin_people import Recipients

    item = next(i for i in L38_ITEMS if i.kind == kind)
    bea = PersonAccount(id="bea", username="bea", name="Bea", enabled=True, roles=["data_engineer"],
                        org_unit="unit-1")  # fmt: skip
    held = frozenset(r for r in Right if r.value != right)
    who = Recipients(people={"bea": bea}, rights={"bea": held}, team_members={})
    with pytest.raises(DisableRefused) as raised:
        check_transfers("ana-1", [item], [OwnedTransfer(kind=kind, id=item.id, to="bea")], who,
                        "unit-1")  # type: ignore[arg-type]  # fmt: skip
    assert raised.value.error == "recipient_refused" and right in raised.value.words
    who_all = Recipients(people={"bea": bea}, rights={"bea": frozenset(Right)}, team_members={})
    assert check_transfers("ana-1", [item], [OwnedTransfer(kind=kind, id=item.id, to="bea")],  # type: ignore[arg-type]
                           who_all, "unit-1") == {(kind, item.id): "bea"}  # fmt: skip


@pytest.mark.parametrize("kind", ["view", "board", "link_type_proposal", "drawn_watch"])
def test_an_l38_item_never_goes_to_a_person_of_another_unit(kind: str) -> None:
    from services.api.admin_people import Recipients

    item = next(i for i in L38_ITEMS if i.kind == kind)
    far = PersonAccount(id="far", username="far", name="Far", enabled=True, roles=["analyst"],
                        org_unit="unit-2")  # fmt: skip
    who = Recipients(people={"far": far}, rights={"far": frozenset(Right)}, team_members={})
    with pytest.raises(DisableRefused) as raised:
        check_transfers("ana-1", [item], [OwnedTransfer(kind=kind, id=item.id, to="far")], who,
                        "unit-1")  # type: ignore[arg-type]  # fmt: skip
    assert "another unit" in raised.value.words


def test_disable_is_refused_while_an_item_is_untransferred(world: SimpleNamespace) -> None:
    world.admin_people.items["ana-1"] = ITEMS
    answer = _disable(world, [{"kind": "case_author", "id": "c1", "to": "ana-2"},
                              {"kind": "team_lead", "id": "r1", "to": "ana-2"}])  # fmt: skip
    assert answer.status_code == 409, answer.text
    detail = answer.json()["detail"]
    assert detail["error"] == "untransferred"
    assert "Structuring" in detail["message"]
    assert [i["id"] for i in detail["items"]] == ["t1"]
    assert world.directory.disabled == [] and world.admin_people.moved == []


@pytest.mark.parametrize(
    ("to", "why"),
    [("ana-1", "being disabled"), ("gone", "disabled"), ("robot", "service account"),
     ("nobody", "not a person")],
)  # fmt: skip
def test_disable_refuses_a_recipient_who_cannot_take_an_item(
    world: SimpleNamespace, to: str, why: str
) -> None:
    world.admin_people.items["ana-1"] = ITEMS[:1]
    answer = _disable(world, [{"kind": "case_author", "id": "c1", "to": to}])
    assert answer.status_code == 409, answer.text
    assert answer.json()["detail"]["error"] == "recipient_refused"
    assert why in answer.json()["detail"]["message"]
    assert world.directory.disabled == []


def test_disable_refuses_a_rule_to_someone_without_the_right_its_runs_need(
    world: SimpleNamespace,
) -> None:
    world.admin_people.items["ana-1"] = [ITEMS[1]]
    _person("viewer", ["reports_viewer"])
    answer = _disable(world, [{"kind": "typology_rule", "id": "t1", "to": "viewer"}])
    assert "deploy_rules" in answer.json()["detail"]["message"]


def test_disable_transfers_every_item_then_disables(world: SimpleNamespace) -> None:
    world.roles.teams_of["r1"] = Team(role_id="r1", display_name="Intel", mailbox="i@example.org",
                                      lead="ana-1")  # fmt: skip
    world.admin_people.items["ana-1"] = ITEMS
    answer = _disable(world, [{"kind": i.kind, "id": i.id, "to": "ana-2"} for i in ITEMS])
    assert answer.status_code == 200, answer.text
    assert answer.json()["enabled"] is False
    assert world.admin_people.moved == [("case_author", "c1", "ana-2"),
                                        ("typology_rule", "t1", "ana-2"), ("team_lead", "r1", "ana-2")]  # fmt: skip
    assert world.directory.disabled == ["ana-1"]
    actions = [e["action"] for e in world.audit.entries]
    assert actions == ["transfer_owned_item"] * 3 + ["disable_person"]


def test_a_person_owning_nothing_is_disabled_with_no_transfers(world: SimpleNamespace) -> None:
    answer = _disable(world, [], who="eng-1")
    assert answer.status_code == 200 and world.directory.disabled == ["eng-1"]


def test_check_transfers_refuses_a_transfer_the_plan_does_not_hold() -> None:
    with pytest.raises(DisableRefused) as raised:
        check_transfers("ana-1", [], [OwnedTransfer(kind="hotlist", id="h9",
                                                                        to="ana-2")], None)  # type: ignore[arg-type]  # fmt: skip
    assert raised.value.error == "not_in_plan"


def test_role_refused_carries_its_words() -> None:
    assert RoleRefused("x", "said").words == "said"


# --- who may hold a level in a case (ADR-145 Amendment 5 point 7, Q5 (a)) ---------------------------


class _People:
    """`PrincipalNameDirectory.people`: of the ids, those the directory holds as enabled people."""

    def __init__(self, configured: bool = True) -> None:
        self.configured = configured

    async def people(self, ids: Any) -> set[str] | None:
        if not self.configured:
            return None
        return {i for i in ids if i in PEOPLE and PEOPLE[i].enabled and not PEOPLE[i].system_account}


class _Dashboards:
    async def list_dashboards(self) -> list[Any]:
        return [SimpleNamespace(account_id="sa-board")]


class _Unreachable:
    async def list_dashboards(self) -> list[Any]:
        from services.api.identity_admin import IdentityAdminRefused

        raise IdentityAdminRefused("the identity provider could not be reached")


def _level(
    world: SimpleNamespace, grantee: str, level: str, *, configured: bool = True, admin: Any = None
) -> Any:
    import asyncio

    from fastapi import HTTPException
    from services.api.app import _may_hold_a_level
    from services.api.investigations import AccessLevel

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        custom_roles=world.roles, principal_names=_People(configured), identity_admin=admin or _Dashboards())))  # fmt: skip
    try:
        asyncio.run(_may_hold_a_level(request, grantee, AccessLevel(level), _People(configured)))  # type: ignore[arg-type]
    except HTTPException as refused:
        return refused.detail
    return None


def test_a_dashboard_identity_may_be_a_viewer_and_nothing_more(world: SimpleNamespace) -> None:
    assert _level(world, "sa-board", "viewer") is None
    assert _level(world, "sa-board", "editor")["error"] == "service_account"
    assert _level(world, "sa-board", "author")["error"] == "service_account"


def test_a_dashboard_is_held_to_viewer_where_the_directory_cannot_tell_people(
    world: SimpleNamespace,
) -> None:
    """On Entra ID the names directory holds no people (`people()` is None), and a registered
    dashboard identity is still a Viewer and nothing more: its registration is read first
    (ADR-148 Amendment 10, the lane review's must 2)."""
    assert _level(world, "sa-board", "viewer", configured=False) is None
    refused = _level(world, "sa-board", "author", configured=False)
    assert refused["error"] == "service_account" and "Viewer" in refused["message"]
    assert _level(world, "sa-board", "editor", configured=False)["error"] == "service_account"


def test_another_service_account_is_refused_even_as_a_viewer(world: SimpleNamespace) -> None:
    refused = _level(world, "robot", "viewer")
    assert refused["error"] == "service_account" and "owns nothing" in refused["message"]
    assert _level(world, "gone", "viewer")["error"] == "service_account"
    assert _level(world, "ana-1", "author") is None


def test_a_team_level_needs_a_team_that_exists(world: SimpleNamespace) -> None:
    assert _level(world, "team:r1", "editor")["error"] == "no_such_team"
    world.roles.teams_of["r1"] = Team(role_id="r1", display_name="Intel", mailbox="i@example.org")
    assert _level(world, "team:r1", "editor") is None


def test_a_deployment_with_no_directory_grants_as_before(world: SimpleNamespace) -> None:
    assert _level(world, "robot", "author", configured=False) is None
    # ... also when its identity provider cannot list dashboards: it cannot tell, as before.
    assert _level(world, "robot", "author", configured=False, admin=_Unreachable()) is None


def test_a_person_is_granted_without_asking_for_dashboards(world: SimpleNamespace) -> None:
    assert _level(world, "ana-1", "author", admin=_Unreachable()) is None


# --- Name an Author (R1) ----------------------------------------------------------------------------


def _name(world: SimpleNamespace, case_id: str, account: str) -> Any:
    return world.client.put(f"/v1/admin/cases/{case_id}/authors/{account}", headers=_as("adm-1"))


def test_an_author_is_named_for_a_case_whose_only_author_is_disabled(world: SimpleNamespace) -> None:
    answer = _name(world, "c3", "ana-2")
    assert answer.status_code == 204, answer.text
    assert world.cases.grants["c3"]["ana-2"].value == "author"
    assert world.audit.entries[-1]["action"] == "name_an_author"


def test_a_case_with_an_author_is_refused_and_left_alone(world: SimpleNamespace) -> None:
    answer = _name(world, "c4", "ana-2")
    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "has_an_author"
    assert "ana-2" not in world.cases.grants["c4"]


def test_another_units_case_is_not_found(world: SimpleNamespace) -> None:
    answer = _name(world, "c9", "ana-2")
    assert answer.status_code == 404 and world.cases.grants["c9"] == {}
    assert _name(world, "nope", "ana-2").status_code == 404


def test_a_service_account_is_not_named_an_author(world: SimpleNamespace) -> None:
    answer = _name(world, "c3", "robot")
    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "service_account"
    assert "robot" not in world.cases.grants["c3"]


# --- a team as a dataset's owner (`_owners_allowed`, Make live's and Change owner…'s) -----------------


def _owners(world: SimpleNamespace, setting: str, people: list[str], team: str | None) -> Any:
    import asyncio

    from services.api.app import OwnerNeeded, _owners_allowed

    from schemas.dataset_model import DatasetOwners

    class _Setting:
        async def owner_setting(self) -> str:
            return setting

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        custom_roles=world.roles, principal_names=_People())))  # fmt: skip
    try:
        return asyncio.run(_owners_allowed(request, _Setting(), DatasetOwners(people=people, team=team)))  # type: ignore[arg-type]
    except OwnerNeeded as refused:
        return f"refused: {refused}"


def test_a_team_that_exists_owns_by_its_id_or_name_as_the_setting_allows(world: SimpleNamespace) -> None:
    world.roles.teams_of["r1"] = Team(role_id="r1", display_name="Intel", mailbox="i@example.org")
    assert _owners(world, "people_and_teams", ["ana-1"], "Intel") == ["ana-1", "team:r1"]
    assert _owners(world, "teams_only", [], "r1") == ["team:r1"]
    assert _owners(world, "teams_only", ["ana-1"], "r1").startswith("refused: Admin › System allows teams only")
    assert _owners(world, "people_only", [], "r1").startswith("refused: Admin › System allows people only")
    assert _owners(world, "people_and_teams", [], "Nobody").startswith("refused: there is no team Nobody")


# --- the reviewer's findings (L2.5 lane review) -------------------------------------------------------


def test_items_left_in_another_unit_keep_the_person_enabled_and_the_transfers_stand(
    world: SimpleNamespace,
) -> None:
    """Each unit's administrator transfers their own unit's share; the disable waits for both, and
    the refusal says another unit's items exist, never how many (rule 7)."""
    world.admin_people.items["ana-1"] = ITEMS[:1]
    world.admin_people.elsewhere["ana-1"] = 2
    assert world.client.get("/v1/admin/people/ana-1/disable-plan", headers=_as("adm-1")).status_code == 200
    answer = _disable(world, [{"kind": "case_author", "id": "c1", "to": "ana-2"}])
    assert answer.status_code == 409, answer.text
    detail = answer.json()["detail"]
    assert detail["error"] == "other_unit" and "those stand" in detail["message"]
    assert "2" not in detail["message"].replace("1 transferred", "")
    assert world.admin_people.moved == [("case_author", "c1", "ana-2")]
    assert world.directory.disabled == []
    world.admin_people.elsewhere["ana-1"] = 0
    assert _disable(world, []).status_code == 200 and world.directory.disabled == ["ana-1"]


def test_a_case_never_goes_to_a_person_of_another_unit(world: SimpleNamespace) -> None:
    world.admin_people.items["ana-1"] = ITEMS[:1]
    PEOPLE["ana-2"] = PEOPLE["ana-2"].model_copy(update={"org_unit": "unit-2"})
    answer = _disable(world, [{"kind": "case_author", "id": "c1", "to": "ana-2"}])
    assert answer.status_code == 409 and "another unit" in answer.json()["detail"]["message"]


def test_a_disable_the_identity_provider_refuses_after_the_transfers_says_they_stand(
    world: SimpleNamespace,
) -> None:
    world.admin_people.items["ana-1"] = ITEMS[:1]
    world.directory.refuse = True
    answer = _disable(world, [{"kind": "case_author", "id": "c1", "to": "ana-2"}])
    assert answer.status_code == 502
    # The account is still enabled, so its covers stay (the orchestrator's review of L2.5b).
    assert "end_covers" not in world.admin_people.order
    detail = answer.json()["detail"]
    assert detail["error"] == "disable_incomplete" and "and those stand" in detail["message"]
    assert [e["action"] for e in world.audit.entries][-1] == "disable_person_incomplete"


def test_a_lead_or_cover_cannot_have_the_teams_role_taken_away(world: SimpleNamespace) -> None:
    world.roles.teams_of["r1"] = Team(role_id="r1", display_name="Intel", mailbox="i@example.org",
                                      lead="ana-1", cover="ana-2",
                                      cover_until=T0.date() + timedelta(days=3))  # fmt: skip
    for who in ("ana-1", "ana-2"):
        answer = _give(world, "adm-1", who, ["analyst"])
        assert answer.status_code == 409 and answer.json()["detail"]["error"] == "lead_leaves_team"
        assert "role:r1" in PEOPLE[who].roles


def test_removing_the_last_people_manager_through_a_custom_role_is_refused(
    world: SimpleNamespace,
) -> None:
    world.roles.seed("r3", "People desk", [Right.MANAGE_PEOPLE])
    _person("ppl-2", ["role:r3"])
    for pid in ("adm-2", "ppl-1"):
        PEOPLE[pid] = PEOPLE[pid].model_copy(update={"enabled": False})
    # adm-1 is the caller and may not remove themselves; ppl-2 is the other manager.
    PEOPLE["adm-1"] = PEOPLE["adm-1"].model_copy(update={"enabled": False})
    answer = world.client.delete("/v1/admin/people/ppl-2", headers=_as("adm-1"))
    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "locks_out_administrators"
    assert "ppl-2" in PEOPLE


def test_a_teams_lead_or_cover_is_not_removed(world: SimpleNamespace) -> None:
    world.roles.teams_of["r1"] = Team(role_id="r1", display_name="Intel", mailbox="i@example.org",
                                      lead="ana-1")  # fmt: skip
    answer = world.client.delete("/v1/admin/people/ana-1", headers=_as("adm-1"))
    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "lead_leaves_team"
    assert "ana-1" in PEOPLE


# --- an open socket reads its principal afresh (round 2's finding 4) ---------------------------------


def test_an_open_socket_reads_custom_rights_and_its_level_afresh_at_each_message(
    world: SimpleNamespace,
) -> None:
    """`_admission`, asked before each message the delta socket acts on: a custom role's rights as
    they are now, and the case level as it is now; a close code closes the socket."""
    import asyncio

    from services.api.app import _admission
    from services.api.investigations import InvestigationNotFoundError

    class _Level:
        revoked = False

        async def get_authorized(self, case_id: str, principal: Principal, *, need: Any) -> Any:
            if self.revoked:
                raise InvestigationNotFoundError(case_id)
            return None

    level = _Level()
    app_ = SimpleNamespace(state=SimpleNamespace(custom_roles=world.roles, investigations=level))
    raw = Principal(id="ana-1", clearance="SECRET", org_unit="unit-1", roles=["role:r1"])
    admitted = _admission(app_, raw, "c1")
    first = asyncio.run(admitted())
    assert first is not None and "right:read_reports" in first.roles
    world.roles.roles["r1"] = world.roles.roles["r1"].model_copy(update={"rights": [Right.INVESTIGATE]})
    second = asyncio.run(admitted())
    assert second is not None and "right:read_reports" not in second.roles
    level.revoked = True
    assert asyncio.run(admitted()) == 1008  # the level taken away: closed, 1008


def test_a_clients_service_account_is_never_listed_so_never_given_roles_or_items(
    world: SimpleNamespace,
) -> None:
    """Round 2's finding 7: the directory drops `service-account-*`, so such an account is no
    person to give roles to (404) nor to transfer to (refused), whatever the checks after."""
    assert _give(world, "adm-1", "sa-1", ["analyst"]).status_code == 404
    world.admin_people.items["ana-1"] = ITEMS[:1]
    answer = _disable(world, [{"kind": "case_author", "id": "c1", "to": "sa-1"}])
    assert answer.status_code == 409 and "not a person the directory holds" in answer.json()["detail"]["message"]


# --- round 2 of the independent review --------------------------------------------------------------


@pytest.mark.parametrize("roles", [["osprey-admin"], ["right:administer_system"], ["role:r9"]],
                         ids=["admin-role", "single-right", "custom-role"])  # fmt: skip
def test_a_people_manager_alone_cannot_invite_an_administrator(
    world: SimpleNamespace, roles: list[str]
) -> None:
    """Finding 1: an invitation is a giving of roles; `_may_give` holds it as it holds the roles
    route, before the identity provider is asked."""
    world.roles.seed("r9", "Admin desk", [Right.ADMINISTER_SYSTEM])
    invite = {"username": "newcomer", "first_name": "New", "last_name": "Comer",
              "clearance": "OFFICIAL", "org_unit": "unit-1", "roles": roles}  # fmt: skip
    answer = world.client.post("/v1/admin/people", json=invite, headers=_as("ppl-1"))
    assert answer.status_code == 409, answer.text
    assert answer.json()["detail"]["error"] == "beyond_your_rights"
    assert world.directory.invited == []
    fine = world.client.post("/v1/admin/people", json={**invite, "roles": ["analyst"]},
                             headers=_as("ppl-1"))  # fmt: skip
    assert fine.status_code == 201, fine.text


def test_an_invitation_with_a_custom_role_that_does_not_exist_is_refused(world: SimpleNamespace) -> None:
    invite = {"username": "newcomer", "first_name": "New", "last_name": "Comer",
              "clearance": "OFFICIAL", "org_unit": "unit-1", "roles": ["role:nope"]}  # fmt: skip
    assert world.client.post("/v1/admin/people", json=invite, headers=_as("adm-1")).status_code == 422
    assert world.directory.invited == []


def test_a_people_manager_alone_cannot_add_an_administration_right_to_a_role_even_their_own(
    world: SimpleNamespace,
) -> None:
    """Finding 2: the giver rule at `change_role_route`, for a role the editor holds too."""
    world.roles.seed("r3", "People desk", [Right.MANAGE_PEOPLE])
    _person("ppl-2", ["role:r3"])
    answer = world.client.put("/v1/admin/roles/r3", headers=_as("ppl-2"),
                              json={"name": "People desk", "rights": ["manage_people", "administer_system"]})  # fmt: skip
    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "beyond_your_rights"
    assert world.roles.roles["r3"].version == 1


def test_an_administration_right_through_a_custom_role_needs_its_holder(world: SimpleNamespace) -> None:
    """Finding 2: at the people route, the right arriving through `role:<id>`."""
    world.roles.seed("r9", "Admin desk", [Right.ADMINISTER_SYSTEM])
    answer = _give(world, "ppl-1", "eng-1", ["data_engineer", "role:r9"])
    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "beyond_your_rights"
    assert PEOPLE["eng-1"].roles == ["data_engineer"]


def test_two_overlapping_changes_cannot_together_leave_nobody_managing_people(
    world: SimpleNamespace,
) -> None:
    """Finding 3: each change alone keeps a people manager; overlapping, the second must see the
    first. adm-1 (built-in Admin) and ppl-2 (through role r3) are the only managers: one request
    takes adm-1's Admin role away, the other takes manage_people out of r3."""
    import asyncio

    import httpx

    for pid in ("adm-2", "ppl-1"):
        PEOPLE[pid] = PEOPLE[pid].model_copy(update={"enabled": False})
    world.roles.seed("r3", "People desk", [Right.MANAGE_PEOPLE])
    _person("ppl-2", ["role:r3"])
    world.directory.write_delay = 0.2

    async def both() -> list[int]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            first = client.put("/v1/admin/people/adm-1/roles", json={"roles": ["analyst"]},
                               headers=_as("ppl-2"))  # fmt: skip
            second = client.put("/v1/admin/roles/r3", headers=_as("adm-1"),
                                json={"name": "People desk", "rights": ["investigate"]})  # fmt: skip
            answers = await asyncio.gather(first, second)
        return [a.status_code for a in answers]

    codes = asyncio.run(both())
    assert sorted(codes) == [200, 409], codes
    managers = [p for p in PEOPLE.values() if p.enabled and (
        "osprey-admin" in p.roles or ("role:r3" in p.roles
                                      and Right.MANAGE_PEOPLE in world.roles.roles["r3"].rights))]  # fmt: skip
    assert managers, "nobody is left who can manage people"


def test_a_disable_reads_the_lock_out_fresh_not_from_the_callers_token(world: SimpleNamespace) -> None:
    """Finding 3: the caller's token says Admin, but the directory no longer does; disabling the
    last manager is refused."""
    for pid in ("adm-1", "adm-2"):
        PEOPLE[pid] = PEOPLE[pid].model_copy(update={"roles": ["analyst"]})
    answer = _disable(world, [], who="ppl-1")
    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "locks_out_administrators"


def test_another_units_person_is_not_named_an_author(world: SimpleNamespace) -> None:
    """Finding 5: as Disable holds a case's recipient to its unit (V4)."""
    PEOPLE["ana-2"] = PEOPLE["ana-2"].model_copy(update={"org_unit": "unit-2"})
    answer = _name(world, "c3", "ana-2")
    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "other_unit"
    assert "ana-2" not in world.cases.grants["c3"]


@pytest.mark.parametrize(("hours_ago", "named"), [(25, False), (23, True)], ids=["stale", "fresh"])
def test_a_person_whose_access_is_a_day_old_is_not_named_an_author(
    world: SimpleNamespace, hours_ago: int, named: bool
) -> None:
    """ADR-148 Amendment 8 (the orchestrator's second review, note 13): on Entra ID a unit read
    from a token over a day ago does not place a person in the case's unit, as for a transfer."""
    from datetime import UTC, datetime, timedelta

    read = datetime.now(UTC) - timedelta(hours=hours_ago)
    PEOPLE["ana-2"] = PEOPLE["ana-2"].model_copy(update={"access_read_at": read})
    answer = _name(world, "c3", "ana-2")
    if named:
        assert answer.status_code == 204, answer.text
    else:
        assert answer.status_code == 409 and answer.json()["detail"]["error"] == "access_out_of_date"
        assert "over a day ago" in answer.json()["detail"]["message"]
        assert "ana-2" not in world.cases.grants["c3"]


def test_an_author_of_another_unit_does_not_count_as_the_cases_author(world: SimpleNamespace) -> None:
    """Finding 5: c4's Author moved to another unit answers for nothing, so it may be given one."""
    PEOPLE["ana-1"] = PEOPLE["ana-1"].model_copy(update={"org_unit": "unit-2"})
    assert _name(world, "c4", "ana-2").status_code == 204


def test_a_team_name_another_team_holds_is_refused(world: SimpleNamespace) -> None:
    """Finding 8: a team is named by its display name at Make live, so no two teams share one."""
    world.roles.teams_of["r2"] = Team(role_id="r2", display_name="Intel", mailbox="x@example.org")
    answer = _team(world)
    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "team_name_taken"


def test_a_cases_highest_is_the_highest_it_reads_or_the_schemes_for_none_or_unknown() -> None:
    from services.api.admin_people import case_highest

    order = ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"]
    assert case_highest(["OFFICIAL", "OFFICIAL-SENSITIVE", "OFFICIAL"], order) == "OFFICIAL-SENSITIVE"
    assert case_highest([], order) == "SECRET"
    assert case_highest(["OFFICIAL", "TOP SECRET"], order) == "SECRET"
