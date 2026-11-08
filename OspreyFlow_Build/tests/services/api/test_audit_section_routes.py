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
from services.api.promotion_ageing import InMemoryAgeingStore, NoPromotionsYet, PendingPromotion

from schemas.domain import Principal, RuleAuditEntry, RuleAuditPage
from schemas.rights import ADMIN as ADMIN_RIGHTS

T0 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
TOKENS: dict[str, Principal] = {}


def _token(pid: str, roles: list[str], unit: str = "unit-1") -> None:
    TOKENS[pid] = Principal(id=pid, clearance="SECRET", org_unit=unit, roles=roles)


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return TOKENS[token]


class _Reader:
    """Stands in for the stream's rows (its SQL is `test_audit_section_store.py`'s)."""

    def __init__(self) -> None:
        self.rows: list[StreamRow] = []
        self.asked: list[tuple[Principal, StreamFilters]] = []
        self.cases: list[bool] = []

    async def stream(self, reader: Principal, filters: StreamFilters, *, offset: int,
                     limit: int, rights: Any = frozenset(),
                     cases: bool = False) -> tuple[list[StreamRow], int]:  # fmt: skip
        self.asked.append((reader, filters))
        self.cases.append(cases)
        return self.rows[offset : offset + limit], len(self.rows)

    async def model_history(self, filters: StreamFilters, *, offset: int, limit: int) -> Any:
        return [], 0


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
    async def display_names(self, ids: Any) -> dict[str, str]:
        return {i: f"Name {i}" for i in ids}


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    TOKENS.clear()
    _token("adm-1", ["osprey-admin"])
    _token("aud-1", ["right:read_audit"])
    _token("aud-r", ["right:read_audit", "right:read_rule_audit"])
    _token("ops-1", ["right:operate_schedules"])
    _token("ana-1", ["analyst"])
    _token("adm-9", ["osprey-admin"], unit="unit-2")
    reader, audit, ageing = _Reader(), _Audit(), InMemoryAgeingStore()
    state = {"principal_resolver": _Resolver(), "audit_section": reader, "audit": audit,
             "investigations": _Cases(), "principal_names": _Names(), "custom_roles": None,
             "promotion_ageing": ageing, "waiting_promotions": NoPromotionsYet(),
             "graph": object(), "analytics": object(), "alerts_store": object()}  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)

    async def _with_packs(case: Any, *_: Any) -> Any:
        return case

    monkeypatch.setattr(app_module, "with_derived_packs", _with_packs)
    yield SimpleNamespace(client=TestClient(app), reader=reader, audit=audit, ageing=ageing,
                          monkeypatch=monkeypatch, cases_=state["investigations"])  # fmt: skip


def _as(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


def _row(action: str, detail: dict[str, Any], case: str | None = "c1") -> StreamRow:
    return StreamRow(recorded_at=T0, principal_id="ana-1", action=action, investigation_id=case,
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
    answer = world.client.get(
        "/v1/admin/audit?who=ana-1&kind=assertions&case=c9&dataset=ds-b"
        "&since=2026-11-01T00:00:00Z&until=2026-11-09T00:00:00Z",
        headers=_as("adm-1"),
    )
    assert answer.status_code == 200
    [(reader, filters)] = world.reader.asked
    assert reader.id == "adm-1" and reader.org_unit == "unit-1"
    assert (filters.who, filters.kind, filters.investigation_id, filters.dataset_id) == (
        "ana-1", "assertions", "c9", "ds-b")  # fmt: skip
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
    assert by_action["set_person_roles"]["detail"] == {"user_id": "ana-2", "roles": ["analyst"]}
    assert by_action["set_dataset_egress"]["detail"] == {"dataset_id": "ds-a", "egress": "none"}
    assert by_action["confirm_node"]["principal_name"] == "Name ana-1"
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
    answer = world.client.get("/v1/admin/audit/rules?case=c1&who=eng-1&limit=2",
                              headers=_as("adm-1")).json()  # fmt: skip
    assert answer["total"] == 3
    assert [e["principal_id"] for e in answer["entries"]] == ["eng-1", "eng-1"]
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

    def __init__(self) -> None:
        self.readers: list[str] = []

    async def waiting_for_review(self, reader: Principal) -> list[PendingPromotion]:
        self.readers.append(reader.id)
        return [PendingPromotion(promotion_id="p1", load_id="load-7", dataset_id="ds-a",
                                 dataset_name="Prison records", dataset_unit="unit-1",
                                 proposed_by="ana-1", proposed_at=datetime.now(UTC) - timedelta(days=4, minutes=1))]  # fmt: skip

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

    from services.api.audit_section import KIND_ACTIONS

    core = pathlib.Path(__file__).resolve().parents[4] / "OspreyFlow_Core/services"
    source = "\n".join(p.read_text() for p in core.rglob("*.py") if p.name != "audit_section.py")
    missing = [a for actions in KIND_ACTIONS.values() for a in actions if f'"{a}"' not in source]
    assert missing == []
