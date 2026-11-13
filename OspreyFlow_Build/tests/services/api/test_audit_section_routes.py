"""Admin › Audit's route and Operations' ageing routes, L2.6 (`06_DECISIONS.md` ADR-145 decisions 9
and 10, Amendment 3 decision 1; ADR-112 Amendment 7 decision 7; ADR-146 Amendment 2). The real app,
`require_right`, `_authorize` and the routes run; the stream's SQL (the unit filter) runs on real
Postgres in `test_audit_section_store.py`, so the reader here stands in only for its rows.

What a mistake would do, and the case that catches it (each shown red at its call site,
`process/lanes/admin/L2.6_RED_RECORD.md`):

- a route answered without its right: `test_every_route_refuses_without_its_right`;
- an entry's words shown to a reader whose own read would not show them (an assertion's node, a
  dataset's words to a holder of `read_audit` alone): `test_an_entrys_withheld_words_stay_withheld`;
- the rule audit read around `readable_rule_audit` (its withheld entries served):
  `test_the_rule_audit_is_served_as_its_own_read_withholds_it`;
- the rule audit served to an Author who is not the administrator:
  `test_the_rule_audit_needs_the_administrators_role`;
- the engines' history to a holder of `read_audit` alone: `test_the_engines_history_is_only_for_a_holder_of_manage_models`;
- the rule audit of another unit's case, or of a case the reader may not manage, served:
  `test_the_rule_audit_of_a_case_the_reader_may_not_manage_is_not_found`;
- a filter widening the rule audit (paging before narrowing): `test_rule_audit_filters_narrow_after_withholding`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import app as app_module
from services.api.app import app
from services.api.audit_section import StreamFilters, StreamRow
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.promotion_ageing import (
    InMemoryAgeingStore,
    NoPromotionsYet,
    PendingPromotion,
    may_review,
)

from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal, RuleAuditEntry, RuleAuditPage

from tests.services.api.test_principal_names import idp  # noqa: F401 - the fixture, used by name
from schemas.rights import ADMIN as ADMIN_RIGHTS

T0 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
TOKENS: dict[str, Principal] = {}


def _token(pid: str, roles: list[str], unit: str = "unit-1") -> None:
    TOKENS[pid] = Principal(id=pid, clearance="SECRET", org_unit=unit, roles=roles)


class _Resolver:
    async def resolve_principal(self, token: str) -> Principal:
        return self.resolve(token)

    def resolve(self, token: str) -> Principal:
        return TOKENS[token]


class _Reader:
    """Stands in for the stream's rows (its SQL is `test_audit_section_store.py`'s)."""

    def __init__(self) -> None:
        self.rows: list[StreamRow] = []
        self.models: list[Any] = []
        self.asked: list[tuple[Principal, StreamFilters]] = []
        self.cases: list[bool] = []
        self.unit_of: dict[str, str] = {}
        #: The lists' clearance each read was asked with (`stream`, then `writers`).
        self.lists_cleared: list[Any] = []
        self.writers_lists_cleared: list[Any] = []

    async def stream(self, reader: Principal, filters: StreamFilters, *, offset: int,
                     limit: int, rights: Any = frozenset(), cases: bool = False,
                     lists_cleared: Any = None) -> tuple[list[StreamRow], int]:  # fmt: skip
        self.asked.append((reader, filters))
        self.cases.append(cases)
        self.lists_cleared.append(lists_cleared)
        return self.rows[offset : offset + limit], len(self.rows)

    async def model_history(self, filters: StreamFilters, *, offset: int, limit: int) -> Any:
        rows = [e for e in self.models if filters.who is None or e.who in filters.who]
        return rows[offset : offset + limit], len(rows)

    async def writers(self, reader: Principal, *, cases: bool, lists_cleared: Any = None) -> set[str]:
        """As the real read narrows them (`test_audit_section_store.py` holds its SQL): the reader's
        unit's writers alone, and a case's writers only with `cases`; a row's unit is
        `unit_of`'s, the reader's own unless a test says otherwise."""
        self.writers_lists_cleared.append(lists_cleared)
        return {
            r.principal_id for r in self.rows
            if self.unit_of.get(r.principal_id, reader.org_unit) == reader.org_unit
            and (cases or r.investigation_id is None)
        }  # fmt: skip

    async def model_writers(self) -> set[str]:
        return {e.who for e in self.models}

    async def units_from(self) -> datetime | None:
        return T0


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.rule_entries: list[RuleAuditEntry] = []

    async def record(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)

    async def list_for_case(self, case_id: str, actions: Any) -> list[RuleAuditEntry]:
        return list(self.rule_entries)


class _Cases:
    """As the real store refuses: a case of another unit, or one where the reader holds no level,
    is not found; the administrator's safety net finds only their own unit's (ADR-052 §4)."""

    def __init__(self) -> None:
        self.made = {
            cid: Investigation(id=cid, name=name, created_at=T0, created_by="seed", owning_unit=unit)
            for cid, name, unit in (("c1", "Op Kestrel", "unit-1"), ("c9", "Elsewhere", "unit-2"))
        }  # fmt: skip
        self.authors = {"c1": {"ana-1"}, "c9": set()}

    async def get_authorized(self, case_id: str, principal: Principal, need: Any = None) -> Any:
        case = self.made.get(case_id)
        if case is None or case.owning_unit != principal.org_unit:
            raise InvestigationNotFoundError(case_id)
        if principal.id not in self.authors[case_id]:
            raise InvestigationNotFoundError(case_id)
        return case

    async def get_for_access_admin(self, case_id: str, principal: Principal) -> Any:
        case = self.made.get(case_id)
        if case is None or case.owning_unit != principal.org_unit:
            raise InvestigationNotFoundError(case_id)
        return case


class _Names:
    """A directory that names every account but the `nameless-` ones, and records what it was
    asked (ADR-106 decision 3: only accounts the page serves)."""

    def __init__(self) -> None:
        self.asked: list[set[str]] = []

    async def display_names(self, ids: Any) -> dict[str, str]:
        ids = set(ids)
        self.asked.append(ids)
        return {i: f"Name {i}" for i in ids if not i.startswith("nameless-")}

    full_names = display_names


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    TOKENS.clear()
    _token("adm-1", ["osprey-admin"])
    _token("aud-1", ["right:read_audit"])
    _token("aud-r", ["right:read_audit", "right:read_rule_audit"])
    _token("ops-1", ["right:operate_schedules", "right:review_promotions"])
    _token("ana-1", ["analyst"])
    _token("adm-9", ["osprey-admin"], unit="unit-2")
    reader, audit, ageing = _Reader(), _Audit(), InMemoryAgeingStore()
    state = {"principal_resolver": _Resolver(), "audit_section": reader, "audit": audit,
             "investigations": _Cases(), "principal_names": _Names(), "custom_roles": None,
             "promotion_ageing": ageing, "waiting_promotions": NoPromotionsYet(),
             "graph": object(), "analytics": object(), "alerts_store": object(),
             "handling_scheme": load_uk_le_scheme()}  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)

    async def _with_packs(case: Any, *_: Any) -> Any:
        return case

    monkeypatch.setattr(app_module, "with_derived_packs", _with_packs)
    yield SimpleNamespace(client=TestClient(app), reader=reader, audit=audit, ageing=ageing,
                          monkeypatch=monkeypatch, cases_=state["investigations"])  # fmt: skip


def _as(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


def _row(action: str, detail: dict[str, Any], case: str | None = "c1",
         who: str = "ana-1") -> StreamRow:  # fmt: skip
    return StreamRow(recorded_at=T0, principal_id=who, action=action, investigation_id=case,
                     case_name="Op Kestrel" if case else None, resolved_query=detail,
                     result_cardinality=7)  # fmt: skip


#: Each route, each right it declares, and the roles that together pass every check it declares.
ROUTES: list[tuple[str, str, dict[str, Any] | None, list[str], list[str]]] = [
    ("GET", "/v1/admin/audit", None, ["read_audit"], ["right:read_audit"]),
    ("GET", "/v1/admin/audit/models", None, ["read_audit", "manage_models"],
     ["right:read_audit", "right:manage_models"]),
    ("GET", "/v1/admin/audit/rules?case=c1", None, ["read_audit"], ["osprey-admin"]),
    ("GET", "/v1/admin/operations/ageing", None, ["operate_schedules"], ["right:operate_schedules"]),
    ("PUT", "/v1/admin/settings/promotion-alert-days", {"alert_after_days": 4},
     ["operate_schedules"], ["right:operate_schedules"]),
]  # fmt: skip
EVERY = ["administer_system", "manage_people", "manage_dashboards", "manage_ontology",
         "manage_models", "read_rule_audit", "read_audit", "operate_schedules"]  # fmt: skip


@pytest.mark.parametrize(("method", "path", "body", "rights", "passes"), ROUTES)
def test_every_route_refuses_without_its_right(
    world: SimpleNamespace, method: str, path: str, body: Any, rights: list[str],
    passes: list[str],
) -> None:  # fmt: skip
    """Each right a route declares is refused without it, holding every other right and the
    administrator role (so the refusal is that right's); the roles in `passes` are answered."""
    _readable(world, [])
    for right in rights:
        _token("almost", ["osprey-admin", *(f"right:{r}" for r in EVERY if r != right)])
        if right in {r.value for r in ADMIN_RIGHTS}:
            # The administrator's role gives the right itself; refuse it with single rights alone.
            _token("almost", [f"right:{r}" for r in EVERY if r != right])
        answer = world.client.request(method, path, json=body, headers=_as("almost"))
        assert answer.status_code == 403, (right, answer.text)
        detail = answer.json()["detail"]
        assert detail == {"error": "right_required", "right": right}, (right, detail)
    _token("holder", passes)
    assert world.client.request(method, path, json=body, headers=_as("holder")).status_code == 200


def test_each_audit_route_declares_every_check_it_makes() -> None:
    """Declared, so the rights table, the place test and the section test see each (rule 12).
    `read_rule_audit` cannot be refused over HTTP apart from the administrator's role, which
    confers it, so its proof is that the route declares it."""
    from fastapi.routing import APIRoute

    from tests.services.api.test_place_routes import _checks

    routes = {r.endpoint.__name__: r for r in app.routes if isinstance(r, APIRoute)}
    assert _checks(routes["read_audit_section"]) == {"read_audit"}
    assert _checks(routes["read_audit_section_rules"]) == {
        "read_audit", "read_rule_audit", "role:osprey-admin"}  # fmt: skip
    assert _checks(routes["read_audit_section_models"]) == {"read_audit", "manage_models"}


def test_the_rule_audit_needs_the_administrators_role(world: SimpleNamespace) -> None:
    """The owner's ruling returns the rule audit to Admin › Audit for the Administrator: a holder
    of both rights who is an Author of the case, but not the administrator, is refused."""
    _readable(world, [_rule_entry("rule_deployed", 1)])
    _token("author", ["right:read_audit", "right:read_rule_audit"])
    world.cases_.authors["c1"].add("author")
    refused = world.client.get("/v1/admin/audit/rules?case=c1", headers=_as("author"))
    assert refused.status_code == 403
    assert "osprey-admin" in str(refused.json()["detail"])


def test_the_stream_is_read_as_the_reader_with_filters_passed_through(world: SimpleNamespace) -> None:
    world.reader.rows = [_row("search", {}), _row("search", {}, who="eng-1")]
    answer = world.client.get(
        "/v1/admin/audit?who=Name%20ana-1&kind=assertions&case=c9&dataset=ds-b"
        "&since=2026-11-01T00:00:00Z&until=2026-11-09T00:00:00Z",
        headers=_as("adm-1"),
    )
    assert answer.status_code == 200
    [(reader, filters)] = world.reader.asked
    assert reader.id == "adm-1" and reader.org_unit == "unit-1"
    # The person is chosen by name and stands for the accounts of that name the reader may read.
    assert (filters.who, filters.kind, filters.investigation_id, filters.dataset_id) == (
        ("ana-1",), "assertions", "c9", "ds-b")  # fmt: skip
    assert answer.json()["people"] == ["Name ana-1", "Name eng-1"]
    # A name standing for no account the reader may read narrows to nothing, never widens.
    world.client.get("/v1/admin/audit?who=Name%20zed-9", headers=_as("adm-1"))
    assert world.reader.asked[-1][1].who == ()
    assert answer.json()["note"].startswith("Entries about another unit's cases are not shown")
    assert world.audit.entries[-1]["action"] == "read_audit_section"
    bad = world.client.get("/v1/admin/audit?kind=everything", headers=_as("adm-1"))
    assert bad.status_code == 422


def test_an_entrys_withheld_words_stay_withheld(world: SimpleNamespace) -> None:
    world.reader.rows = [
        _row("confirm_node", {"node_ids": ["n-secret"], "query": "J. Doe"}),
        _row("set_person_roles", {"user_id": "ana-2", "roles": ["analyst"]}, case=None),
        _row("set_dataset_egress", {"dataset_id": "ds-a", "egress": "none"}, case=None),
        _row("search", {"text": "J. Doe"}),
    ]
    full = world.client.get("/v1/admin/audit", headers=_as("adm-1")).json()["entries"]
    by_action = {e["action"]: e for e in full}
    # An analyst's assertion and a read: their words name nodes and queries, withheld even from the
    # deployment's administrator, and their counts with them.
    for action in ("confirm_node", "search"):
        assert by_action[action]["detail"] is None, action
        assert by_action[action]["words_withheld"] is True
        assert by_action[action]["result_cardinality"] is None
        assert "J. Doe" not in str(by_action[action])
    # People and roles, and Datasets: the words their own sections show this administrator.
    assert by_action["set_person_roles"]["detail"] == {"person": "Name ana-2", "roles": ["analyst"]}
    # Only words named as plain words pass (`egress` is not one); never an account's id.
    assert by_action["set_dataset_egress"]["detail"] == {"dataset_id": "ds-a"}
    assert by_action["confirm_node"]["who"] == "Name ana-1"
    # A holder of read_audit alone holds neither section: every entry's words withheld.
    alone = world.client.get("/v1/admin/audit", headers=_as("aud-1")).json()["entries"]
    assert [e["detail"] for e in alone] == [None, None, None, None]
    assert all(e["words_withheld"] for e in alone)


def _rule_entry(action: str, minutes: int, who: str = "ana-1", **detail: Any) -> RuleAuditEntry:
    return RuleAuditEntry(recorded_at=T0 + timedelta(minutes=minutes), principal_id=who,
                          action=action, detail=detail, result_cardinality=1)  # fmt: skip


def _readable(world: SimpleNamespace, served: list[RuleAuditEntry]) -> list[dict[str, Any]]:
    """`readable_rule_audit` as it decides for this reader: it serves `served`; the store itself
    holds more (`world.audit.rule_entries`)."""
    calls: list[dict[str, Any]] = []

    async def _spy(audit: Any, graph: Any, case_id: str, reader: Principal, **kw: Any) -> Any:
        calls.append({"case": case_id, "reader": reader.id, **kw})
        return RuleAuditPage(entries=served, total=len(served))

    world.monkeypatch.setattr(app_module, "readable_rule_audit", _spy)
    return calls


def test_the_rule_audit_is_served_as_its_own_read_withholds_it(world: SimpleNamespace) -> None:
    secret = _rule_entry("rule_fired", 2, alert_id="al-2", words="Structuring by J. Doe")
    kept = _rule_entry("rule_deployed", 1, rule_id="r1")
    world.audit.rule_entries = [secret, kept]
    calls = _readable(world, [kept])
    answer = world.client.get("/v1/admin/audit/rules?case=c1", headers=_as("adm-1"))
    assert answer.status_code == 200, answer.text
    page = answer.json()
    assert [e["action"] for e in page["entries"]] == ["rule_deployed"] and page["total"] == 1
    assert "J. Doe" not in answer.text
    assert calls[0]["case"] == "c1" and calls[0]["reader"] == "adm-1"
    assert page["entries"][0]["held_in"] == "rules" and page["entries"][0]["case_name"] == "Op Kestrel"
    # The administrator reached it through the safety net, which is audited as the route's is.
    assert any(e["action"] == "access_admin_override" for e in world.audit.entries)


def test_the_rule_audit_of_a_case_the_reader_may_not_manage_is_not_found(
    world: SimpleNamespace,
) -> None:
    _readable(world, [_rule_entry("rule_deployed", 1)])
    # Another unit's case, for this unit's administrator; and for that unit's, a case not theirs.
    assert world.client.get("/v1/admin/audit/rules?case=c9",
                            headers=_as("adm-1")).status_code == 404  # fmt: skip
    assert world.client.get("/v1/admin/audit/rules?case=c1",
                            headers=_as("adm-9")).status_code == 404  # fmt: skip
    # A holder of read_audit and read_rule_audit who is not the administrator.
    assert world.client.get("/v1/admin/audit/rules?case=c1",
                            headers=_as("aud-r")).status_code == 403  # fmt: skip
    # read_audit without read_rule_audit.
    refused = world.client.get("/v1/admin/audit/rules?case=c1", headers=_as("aud-1"))
    assert refused.status_code == 403
    assert refused.json()["detail"]["right"] == "read_rule_audit"
    # No case chosen.
    assert world.client.get("/v1/admin/audit/rules", headers=_as("adm-1")).status_code == 422


def test_rule_audit_filters_narrow_after_withholding(world: SimpleNamespace) -> None:
    served = [_rule_entry("rule_evaluated", m, who="ana-1" if m % 2 else "eng-1") for m in range(6)]
    served.reverse()  # newest first, as the read serves them
    calls = _readable(world, served)
    answer = world.client.get("/v1/admin/audit/rules?case=c1&who=Name%20eng-1&limit=2",
                              headers=_as("adm-1")).json()  # fmt: skip
    assert answer["total"] == 3
    assert [e["who"] for e in answer["entries"]] == ["Name eng-1", "Name eng-1"]
    # The whole readable audit was asked for, so paging never happens before the filter.
    assert calls[0]["offset"] == 0 and calls[0]["limit"] >= 10**6


def test_the_engines_history_is_only_for_a_holder_of_manage_models(world: SimpleNamespace) -> None:
    """The orchestrator's ruling: the history names people of every unit, so a holder of
    `read_audit` alone, of any unit, is refused it; one holding `manage_models` too reads it."""
    for who, unit in (("aud-1", "unit-1"), ("aud-9", "unit-2")):
        _token(who, ["right:read_audit"], unit=unit)
        refused = world.client.get("/v1/admin/audit/models", headers=_as(who))
        assert refused.status_code == 403
        assert refused.json()["detail"] == {"error": "right_required", "right": "manage_models"}
    _token("mod-1", ["right:read_audit", "right:manage_models"], unit="unit-2")
    answer = world.client.get("/v1/admin/audit/models", headers=_as("mod-1"))
    assert answer.status_code == 200 and answer.json()["total"] == 0


class _Waiting:
    recorded = True

    def __init__(self, proposers: tuple[str, ...] | list[str] = ("ana-1",)) -> None:
        self.readers: list[str] = []
        self.proposers = list(proposers)

    async def waiting_for_review(self, reader: Principal) -> list[PendingPromotion]:
        """As L3.4's store must (`test_waiting_promotions_contract.py`): filtered in its own read
        to those who `may_review` (rule 3); `ops-1` is ds-a's Author holding review_promotions."""
        self.readers.append(reader.id)
        return [p for p in self._all()
                if may_review(reader.id, reader.roles, reader.clearance, reader.org_unit, p,
                              ["ops-1"])]  # fmt: skip

    def _all(self) -> list[PendingPromotion]:
        return [PendingPromotion(items_marking=None, promotion_id=f"p{n}", load_id="load-7", dataset_id="ds-a",
                                 dataset_name="Prison records", dataset_unit="unit-1",
                                 proposed_by=who, proposed_at=datetime.now(UTC) - timedelta(days=4, minutes=1))
                for n, who in enumerate(self.proposers, 1)]  # fmt: skip

    async def all_waiting(self) -> list[PendingPromotion]:
        return []


def test_operations_ageing_says_what_ages_and_lists_promotions_as_the_reader(
    world: SimpleNamespace,
) -> None:
    before = world.client.get("/v1/admin/operations/ageing", headers=_as("ops-1")).json()
    assert before["promotions_recorded"] is False and before["waiting"] == []
    assert before["alert_after_days"] == 3
    assert before["rules"][0]["what"] == "A promotion waiting for review"
    waiting = _Waiting()
    world.monkeypatch.setattr(app.state, "waiting_promotions", waiting)
    put = world.client.put("/v1/admin/settings/promotion-alert-days", json={"alert_after_days": 5},
                           headers=_as("ops-1"))  # fmt: skip
    assert put.status_code == 200
    assert world.audit.entries[-1]["resolved_query"] == {"before": 3, "after": 5}
    after = world.client.get("/v1/admin/operations/ageing", headers=_as("ops-1")).json()
    assert waiting.readers == ["ops-1"]  # read as the reader, so L3.4's store filters (rule 3)
    [row] = after["waiting"]
    assert (row["age_days"], row["overdue"], after["alert_after_days"]) == (4, False, 5)
    for days in (0, 91):
        assert world.client.put("/v1/admin/settings/promotion-alert-days",
                                json={"alert_after_days": days},
                                headers=_as("ops-1")).status_code == 422  # fmt: skip


def test_case_entries_are_read_only_for_the_units_administrator(world: SimpleNamespace) -> None:
    """ADR-052 §4: only `osprey-admin` sees the unit's cases without a level; a holder of
    `read_audit` alone is read no case's entry, and told so."""
    admin = world.client.get("/v1/admin/audit", headers=_as("adm-1")).json()
    alone = world.client.get("/v1/admin/audit", headers=_as("aud-1")).json()
    assert world.reader.cases == [True, False]
    assert alone["note"].startswith("You hold read_audit but are not your unit's administrator")
    assert admin["note"] != alone["note"]


def test_every_kinds_action_is_one_the_conduit_records() -> None:
    """Each action a kind lists is written somewhere by the Conduit or the Studio (its own lists in
    `audit_section.py` left out), so a kind's filter matches what is recorded (red with one
    misspelt)."""
    import pathlib

    from services.api.audit_section import AWAITED_ACTIONS, KIND_ACTIONS, READS_AND_OTHER

    core = pathlib.Path(__file__).resolve().parents[4] / "OspreyFlow_Core"
    source = "\n".join(
        p.read_text() for tree in ("services", "scripts") for p in (core / tree).rglob("*.py")
        if p.name != "audit_section.py"
    )  # fmt: skip
    named = [*(a for actions in KIND_ACTIONS.values() for a in actions), *READS_AND_OTHER]
    missing = [a for a in named if f'"{a}"' not in source and a not in AWAITED_ACTIONS]
    assert missing == []
    # Classified ahead of case's L3.4, and classified as loads and promotions.
    assert AWAITED_ACTIONS <= set(KIND_ACTIONS["loads_and_promotions"])


#: The identity provider's accounts for the id test, as Keycloak represents them: some with name
#: parts, and some with only a username, which is its identifier and must never be served.
_ACCOUNTS: dict[str, dict[str, object]] = {
    "kc-u2": {"firstName": "Kim", "lastName": "Lee", "username": "login-u2", "enabled": True},
    "lead-a": {"firstName": "Lee", "lastName": "Ann", "username": "uname-lead-a", "enabled": True},
    "own-a": {"firstName": "Owen", "lastName": "Hart", "username": "uname-own-a", "enabled": True},
    "from-1": {"firstName": "Fran", "lastName": "Ode", "username": "uname-from-1", "enabled": True},
    "prop-1": {"firstName": "Pat", "lastName": "Ross", "username": "uname-prop-1", "enabled": True},
    "mod-w": {"firstName": "Mo", "lastName": "Dell", "username": "uname-mod-w", "enabled": True},
    # Only a username: the real directory's `display_names` falls back to it.
    "nameless-w1": {"username": "uname-w1", "enabled": True},
    "nameless-u1": {"username": "uname-u1", "enabled": True},
    "nameless-r1": {"username": "uname-r1", "enabled": True},
    "nameless-m1": {"username": "uname-m1", "enabled": True},
    "nameless-p2": {"username": "uname-p2", "enabled": True},
}


@pytest.fixture
def directory(monkeypatch: pytest.MonkeyPatch, idp: tuple[str, Any]) -> Any:
    """The real `PrincipalNameDirectory` over `test_principal_names`' identity-provider fixture,
    which refuses as Keycloak does, holding `_ACCOUNTS` (rule 15: not a stand-in that never falls
    back to a username)."""
    from services.api.principal_names import PrincipalNameDirectory

    from tests.services.api import test_principal_names as idp_fixture

    monkeypatch.setattr(idp_fixture, "ACCOUNTS", _ACCOUNTS)
    return PrincipalNameDirectory(idp_fixture._settings(idp[0]))


#: Every place an account's id is written into an entry the Conduit may serve: who wrote it, and
#: the People-and-roles and Datasets words that name a person (ADR-106 Amendment 1, rule 7).
PLANTED = [
    "nameless-w1", "nameless-u1", "kc-u2", "login-u2", "sub-u2", "idp-u2", "nameless-u3",
    "login-u3", "u3@mail.example", "grp-1", "lead-a", "nameless-lead-b", "nameless-cover-a",
    "own-a", "nameless-own-b", "nameless-home-1", "from-1", "nameless-to-1", "nameless-acct-1",
    "nameless-r1", "mod-w", "nameless-m1", "prop-1", "nameless-p2",
    # The identity provider's usernames, served by `display_names` for an account with no name.
    "uname-w1", "uname-u1", "uname-r1", "uname-m1", "uname-p2", "uname-lead-a", "uname-own-a",
    "uname-from-1", "uname-prop-1", "uname-mod-w", "grp-team-7",
]  # fmt: skip


def test_no_account_id_reaches_the_glass(world: SimpleNamespace, directory: Any) -> None:
    """Rule 7 and ADR-106 Amendment 1: each id planted where the Conduit records one, and each
    route's whole response searched for it. Who acted is a name or fixed words; a person in the
    words is a name; an identity provider's subject, username or email is never served."""
    from services.api.audit_section import NO_NAME

    from schemas.admin import AuditSectionEntry

    world.monkeypatch.setattr(app.state, "principal_names", directory)
    world.reader.rows = [
        _row("set_person_roles", {"user_id": "nameless-u1", "roles": ["analyst"]}, None,
             who="nameless-w1"),
        _row("link_organisation_account", {"user_id": "kc-u2", "username": "login-u2",
             "subject": "sub-u2", "provider_username": "idp-u2"}, None, who="kc-u2"),
        _row("remove_person", {"user_id": "nameless-u3", "username": "login-u3",
             "name": "Ola Moss", "email": "u3@mail.example"}, None),
        _row("set_team_lead", {"role_id": "grp-1", "before": "lead-a", "after": "nameless-lead-b"},
             None),
        _row("set_team_cover", {"role_id": "grp-1", "before": ["nameless-cover-a", "2026-12-01"],
             "after": [None, ""]}, None),
        _row("change_dataset_owners", {"dataset_id": "ds-a", "before": ["own-a"],
             "after": ["nameless-own-b"]}, None),
        _row("make_home_case", {"dataset_id": "ds-a", "owners": ["nameless-home-1"]}, None),
        _row("transfer_owned_item", {"from": "from-1", "to": "nameless-to-1", "kind": "board",
             "id": "b-1"}, None),
        _row("grant_access", {"account": "nameless-acct-1", "level": "author"}),
        _row("revoke_access", {"account": "team:grp-team-7"}),
    ]  # fmt: skip
    world.reader.models = [
        AuditSectionEntry(recorded_at=T0, who=w, action="engine_changed", kind="models",
                          held_in="models", detail={"engine": "ner"})  # fmt: skip
        for w in ("mod-w", "nameless-m1")
    ]
    _readable(world, [_rule_entry("rule_deployed", 1, who="nameless-r1")])
    world.monkeypatch.setattr(app.state, "waiting_promotions", _Waiting(
        proposers=["prop-1", "nameless-p2"]))  # fmt: skip
    _token("all", ["osprey-admin", "right:manage_models", "right:operate_schedules"])
    answers = [
        world.client.get(path, headers=_as("all"))
        for path in ("/v1/admin/audit", "/v1/admin/audit/rules?case=c1", "/v1/admin/audit/models",
                     "/v1/admin/operations/ageing")
    ]  # fmt: skip
    assert [a.status_code for a in answers] == [200, 200, 200, 200], [a.text for a in answers]
    for answer in answers:
        assert [i for i in PLANTED if i in answer.text] == [], answer.request.url
    stream = answers[0].json()
    by_action = {e["action"]: e for e in stream["entries"]}
    assert by_action["set_person_roles"]["who"] == NO_NAME
    assert by_action["link_organisation_account"]["detail"] == {"person": "Kim Lee"}
    assert by_action["remove_person"]["detail"] == {"person": NO_NAME, "name": "Ola Moss"}
    assert by_action["set_team_lead"]["detail"] == {"before": "Lee Ann", "after": NO_NAME}
    assert by_action["change_dataset_owners"]["detail"]["before"] == ["Owen Hart"]
    assert by_action["transfer_owned_item"]["detail"]["from"] == "Fran Ode"
    assert by_action["revoke_access"]["detail"] == {"person": "A team"}
    assert stream["people"] == ["Kim Lee"]  # an account with no name is not offered
    assert [p["proposed_by_name"] for p in answers[3].json()["waiting"]] == ["Pat Ross", NO_NAME]


def test_an_overdue_alert_is_read_without_its_other_recipients() -> None:
    """L2.7's *Needs you* reads `alerts_for`: who else was alerted is not that person's."""
    import asyncio

    from services.api.promotion_ageing import InMemoryAgeingStore

    from schemas.admin import PromotionOverdueAlert

    from services.api.promotion_ageing import PendingPromotion

    store = InMemoryAgeingStore()
    promotion = PendingPromotion(items_marking=None, promotion_id="p1", load_id="load-7", dataset_id="ds-a",
                                 dataset_name="Prison records", dataset_unit="unit-1",
                                 proposed_by="ana-1", proposed_at=T0)  # fmt: skip
    asyncio.run(store.raise_once(PromotionOverdueAlert(
        promotion_id="p1", load_id="load-7", dataset_id="ds-a", raised_at=T0,
        recipients=["rev-1", "adm-2"],
        words="Promotion load-7 into Prison records has waited 3 days."), promotion))  # fmt: skip

    async def still(p: Any) -> list[str]:
        return ["rev-1", "adm-2"]

    [notice] = asyncio.run(store.alerts_for("rev-1", still))
    assert "adm-2" not in notice.model_dump_json() and "recipients" not in notice.model_dump()
    assert "proposed_by" not in notice.model_dump() and "ana-1" not in notice.model_dump_json()


def test_the_note_names_the_deployments_own_date(world: SimpleNamespace) -> None:
    """Item 9: entries written before this deployment's audit recorded units are named by its own
    date, not a fixed one."""
    world.monkeypatch.setattr(world.reader, "units_from",
                              _async(datetime(2027, 3, 4, 23, 30, tzinfo=UTC)))  # fmt: skip
    for who in ("adm-1", "aud-1"):
        note = world.client.get("/v1/admin/audit", headers=_as(who)).json()["note"]
        assert "written before 4 March 2027" in note and "8 November 2026" not in note, note


def _async(value: Any) -> Any:
    async def answer(*_: Any, **__: Any) -> Any:
        return value

    return answer


def test_operations_ageing_lists_no_other_units_promotions(world: SimpleNamespace) -> None:
    """Item 5: the ageing read passes its own reader to the store, which filters by unit: an
    `operate_schedules` holder of another unit is listed none (red with the reader replaced)."""
    waiting = _Waiting()
    world.monkeypatch.setattr(app.state, "waiting_promotions", waiting)
    _token("ops-9", ["right:operate_schedules", "right:review_promotions"], unit="unit-2")
    other = world.client.get("/v1/admin/operations/ageing", headers=_as("ops-9")).json()
    own = world.client.get("/v1/admin/operations/ageing", headers=_as("ops-1")).json()
    assert other["waiting"] == [] and [p["promotion_id"] for p in own["waiting"]] == ["p1"]
    assert waiting.readers == ["ops-9", "ops-1"]


def test_a_person_filter_of_one_bare_string_is_refused() -> None:
    """A bare id would be read as its letters (`ANY(['a','n','a',...])`), a filter that matches
    nothing and so passes for narrowing: refused where the filter is read."""
    import asyncio

    from services.api.audit_section import AuditSectionReader

    class _NoPool:
        def acquire(self) -> Any:
            raise AssertionError("never reached: the filter is refused first")

    reader = AuditSectionReader(_NoPool())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="never one string"):
        asyncio.run(reader.stream(TOKENS.get("x") or Principal(id="x", clearance="SECRET",
                                  org_unit="u", roles=[]), StreamFilters(who="ana-b"),  # type: ignore[arg-type]
                                  offset=0, limit=1))  # fmt: skip


def test_the_picker_offers_no_case_writer_to_a_reader_who_is_not_the_administrator(
    world: SimpleNamespace,
) -> None:
    """The picker's names are asked of `writers` with the same `cases` the stream is read with:
    a `read_audit` holder who is not the unit's administrator reads no case's entries (ADR-052 §4),
    so is offered no one who wrote only about cases. Red with `cases=True` forced at the route's
    call to `writers`."""
    world.reader.rows = [_row("search", {}, case="c1", who="case-only"),
                         _row("list_people", {}, case=None, who="plain-1")]  # fmt: skip
    plain = world.client.get("/v1/admin/audit", headers=_as("aud-1"))
    assert plain.status_code == 200
    assert plain.json()["people"] == ["Name plain-1"]
    admin = world.client.get("/v1/admin/audit", headers=_as("adm-1"))
    assert admin.json()["people"] == ["Name case-only", "Name plain-1"]


def test_a_sources_governance_words_stay_withheld(world: SimpleNamespace) -> None:
    """*Datasets* shows its entries' words to `administer_system`, but a source's governance edit
    writes words no Admin read serves: its handling, its legal basis (free text) and the pipelines
    and drafts that follow. Shown only as the source and dataset it names. Red with any of them
    back among the plain words."""
    world.reader.rows = [_row("edit_dataset_source_governance", {
        "dataset_id": "ds-a", "source_id": "src-1",
        "handling_before": {"classification": "OFFICIAL"},
        "handling_after": {"classification": "SECRET"},
        "legal_basis_before": "RIPA s.28", "legal_basis_after": "Operation Nightjar warrant 7",
        "pipelines_needing_attention": ["pipe-1"], "drafts_following": ["draft-1"],
    }, case=None)]  # fmt: skip
    [entry] = world.client.get("/v1/admin/audit", headers=_as("adm-1")).json()["entries"]
    assert entry["detail"] == {"dataset_id": "ds-a", "source_id": "src-1"}
    assert "Nightjar" not in str(entry) and "pipe-1" not in str(entry)



@pytest.mark.parametrize("action", ["add_dataset_gazetteer", "remove_dataset_gazetteer"])
def test_a_gazetteer_s_addition_shows_its_dataset_alone(world: SimpleNamespace, action: str) -> None:
    """Platform's P5 (ADR-147 Amendment 2): a gazetteer added to a dataset or removed is filed under
    *Datasets*, whose words `administer_system` is shown, as the dataset it names alone: the
    gazetteer's id, which says which regions a unit has built, is no plain word. Red with
    `gazetteer` among the plain words, or the action filed where its words are withheld."""
    world.reader.rows = [_row(action, {
        "dataset_id": "ds-a", "gazetteer": "gazetteer-osm-rutland",
    }, case=None)]  # fmt: skip
    [entry] = world.client.get("/v1/admin/audit", headers=_as("adm-1")).json()["entries"]
    assert entry["detail"] == {"dataset_id": "ds-a"}
    assert "rutland" not in str(entry)


def test_recipients_are_asked_of_the_dataset_as_it_stands_now() -> None:
    """`_promotion_recipients`, which the sweep and every read of `alerts_for` ask, reads the
    dataset's unit and marking now, not as the promotion recorded them: a dataset moved to another
    unit and marked SECRET since alerts that unit's cleared administrator alone, and one no longer
    held alerts no one. Red with the promotion's recorded unit and marking used."""
    import asyncio

    from ontology.handling import HandlingScheme
    from services.api.app import _promotion_recipients
    from services.api.datasets import Dataset

    from schemas.admin import PersonAccount

    recorded = PendingPromotion(items_marking=None, promotion_id="p1", load_id="load-7", dataset_id="ds-a",
                                dataset_name="Prison records", dataset_unit="unit-1",
                                proposed_by="ana-1", proposed_at=T0)  # fmt: skip
    now = Dataset(id="ds-a", name="Prison records", owning_unit="unit-2", created_at=T0,
                  created_by="seed", highest_marking="SECRET")  # fmt: skip

    class _Datasets:
        held: dict[str, Dataset] = {"ds-a": now}

        async def egress_of(self, ids: Any) -> dict[str, Dataset]:
            return {i: self.held[i] for i in ids if i in self.held}

        async def home_case_of(self, dataset_id: str) -> None:
            return None

    def _adm(pid: str, unit: str, clearance: str) -> PersonAccount:
        return PersonAccount(id=pid, username=pid, name=pid, enabled=True, roles=["osprey-admin"],
                             org_unit=unit, clearance=clearance)  # fmt: skip

    class _People:
        async def list_people(self) -> list[PersonAccount]:
            return [_adm("adm-1", "unit-1", "SECRET"), _adm("adm-2", "unit-2", "SECRET"),
                    _adm("adm-2low", "unit-2", "OFFICIAL")]  # fmt: skip

    datasets = _Datasets()
    state = SimpleNamespace(
        datasets=datasets, identity_admin=_People(), custom_roles=None, investigations=None,
        handling_scheme=HandlingScheme(name="t", classification=["OFFICIAL", "SECRET"],
                                       handling_codes={}, action_codes={}, sanitisation_codes={}),
    )  # fmt: skip
    fake = SimpleNamespace(state=state)
    assert asyncio.run(_promotion_recipients(fake, recorded)) == ["adm-2"]  # type: ignore[arg-type]
    datasets.held = {}
    assert asyncio.run(_promotion_recipients(fake, recorded)) == []  # type: ignore[arg-type]


def test_the_stream_and_its_picker_are_read_with_the_readers_own_lists_clearance(
    world: SimpleNamespace,
) -> None:
    """ADR-146 Amendment 7 (the orchestrator's re-check of lane/rules-lists at 6bfc8d6, must 3): an
    entry naming a screening list is read only by a reader cleared for the list, in the read
    (`audit_section._lists_clause`, its SQL proven in `test_audit_section_store.py`). The route asks
    both the stream and the picker's writers with the reader's own `ListClearance`, never none and
    never another's. Red with the route asking without it: None, which clears no list."""
    from services.api.screening import ListClearance

    scheme = load_uk_le_scheme()
    TOKENS["adm-low"] = Principal(id="adm-low", clearance="OFFICIAL", org_unit="unit-1",
                                  roles=["osprey-admin"], receivable_handling_codes=["R"])  # fmt: skip
    for who in ("adm-1", "adm-low"):
        response = world.client.get("/v1/admin/audit", headers=_as(who))
        assert response.status_code == 200, response.text
    # Each reader's own: the SECRET administrator's, then the OFFICIAL one's who may receive R, so a
    # route asking with one fixed clearance (the first reader's, or the scheme's whole) is red too.
    expected = [ListClearance.of(TOKENS["adm-1"], scheme), ListClearance.of(TOKENS["adm-low"], scheme)]
    assert expected[0] != expected[1]
    assert world.reader.lists_cleared == expected and world.reader.writers_lists_cleared == expected
