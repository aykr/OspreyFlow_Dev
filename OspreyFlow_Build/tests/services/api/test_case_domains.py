"""A case's domain packs (`06_DECISIONS.md` ADR-126 decisions 1 and 2, unit D1): chosen when the
case is made, changed by an Author, listed to everyone who can see the case, taken by a branch.
Route behaviour through the real level dependencies with an in-memory store that applies the rules
the real one does (the real store's SQL is `test_investigation_access_store.py`'s, against
Postgres).

What a mistake here would do, and the case that catches it:

- a POST that dropped the packs would leave every new case reading as POLE
  (`test_a_case_made_with_packs_keeps_them_sorted_and_without_repeats`);
- a POST that took an unknown pack would store a value the model does not know
  (`test_an_unknown_pack_is_refused_at_the_post_and_no_case_is_made`);
- a "none ticked" form read as "never chosen" would let a reseed overwrite the choice
  (`test_a_case_made_without_a_choice_is_never_chosen_and_one_made_with_none_is`);
- a listing without the packs would leave the Glass unable to read the setting
  (`test_the_case_list_carries_each_cases_packs`);
- a PATCH open to an Editor, or one that answered an outsider with anything but a 404
  (`test_only_an_author_changes_the_packs`);
- a change nobody can see afterwards (`test_a_change_of_packs_is_audited_and_kept_in_the_history`);
- a PATCH that lost the blank-name refusal (`test_the_patch_keeps_the_blank_name_refusal`);
- a branch, or an alert's jump, taking the wrong case's packs
  (`test_an_alert_jump_takes_the_packs_of_its_own_case_not_the_alerts`).
"""

from __future__ import annotations

import ast
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api import app as app_module
from services.api import investigations as investigations_module
from services.api.app import (
    app,
    get_alerts_store,
    get_audit,
    get_datasets,
    get_graph,
    get_history,
    get_investigations,
    get_principal,
    get_valkey,
    get_working_set,
)
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.investigations import (
    AccessHistoryEntry,
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
    InvestigationStore,
)
from services.api.working_set.models import DeltaAdd, ExpansionOutcome

from schemas.domain import Alert, AlertMode, Principal

ALICE = Principal(id="alice", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
BOB = Principal(id="bob", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
VIV = Principal(id="viv", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
EVE = Principal(id="eve", clearance="OFFICIAL", org_unit="unit-2", roles=["analyst"])


class _Cases:
    """Cases by id, the levels held on each, the access history, and what `create` was asked for."""

    def __init__(self) -> None:
        self.cases: dict[str, Investigation] = {}
        self.grants: dict[tuple[str, str], AccessLevel] = {}
        self.history: list[tuple[str, AccessHistoryEntry]] = []
        #: What each `create` call was given for `domains`: None is "never chosen" (SQL NULL).
        self.asked_domains: list[list[str] | None] = []
        self.names_set: list[str] = []
        #: The case is removed by someone else after the first write of a request. A single store
        #: call has no "after the first write", so `change` is refused outright.
        self.removed_mid_request = False
        self._writes = 0
        self._n = 0

    def seed_case(
        self, case_id: str, *, owner: Principal, domains: list[str] | None = None, name: str = "C"
    ) -> Investigation:
        case = Investigation(
            id=case_id,
            name=name,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by=owner.id,
            owning_unit=owner.org_unit,
            domains=domains or [],  # type: ignore[arg-type]
            domains_chosen=domains is not None,
        )
        self.cases[case_id] = case
        self.grants[(case_id, owner.id)] = AccessLevel.AUTHOR
        return case

    async def create(
        self,
        principal: Principal,
        *,
        name: str,
        branched_from: str | None = None,
        domains: list[str] | None = None,
    ) -> Investigation:
        self.asked_domains.append(None if domains is None else list(domains))
        self._n += 1
        case = Investigation(
            id=f"new-{self._n}",
            name=name,
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
            created_by=principal.id,
            owning_unit=principal.org_unit,
            branched_from=branched_from,
            domains=domains or [],  # type: ignore[arg-type]
            domains_chosen=domains is not None,
        )
        self.cases[case.id] = case
        self.grants[(case.id, principal.id)] = AccessLevel.AUTHOR
        return case

    def _level(self, case_id: str, principal: Principal) -> AccessLevel | None:
        case = self.cases.get(case_id)
        if case is None or case.owning_unit != principal.org_unit:
            return None
        return self.grants.get((case_id, principal.id))

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        level = self._level(investigation_id, principal)
        if level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError("too low")
        return self.cases[investigation_id]

    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        held = [(c, self._level(c.id, principal)) for c in self.cases.values()]
        return [(c, lv) for c, lv in held if lv is not None]

    async def hidden_tab_ids(self, principal: Principal) -> set[str]:
        return set()

    def _write(self) -> None:
        if self.removed_mid_request and self._writes >= 1:
            raise InvestigationNotFoundError("removed between the steps")
        self._writes += 1

    async def change(
        self,
        investigation_id: str,
        *,
        name: str | None = None,
        domains: list[str] | None = None,
        by: Principal,
    ) -> None:
        """Both changes or neither, as the real store's one transaction does."""
        if self.removed_mid_request:
            raise InvestigationNotFoundError(investigation_id)
        if name is not None:
            self.names_set.append(name)
            case = self.cases[investigation_id]
            self.cases[investigation_id] = case.model_copy(update={"name": name.strip()})
        if domains is not None:
            await self._set_domains(investigation_id, domains, by)

    async def rename(self, investigation_id: str, name: str, *, by: Principal) -> None:
        self._write()
        self.names_set.append(name)
        case = self.cases[investigation_id]
        self.cases[investigation_id] = case.model_copy(update={"name": name.strip()})

    async def set_domains(
        self, investigation_id: str, domains: list[str], *, by: Principal
    ) -> None:
        self._write()
        await self._set_domains(investigation_id, domains, by)

    async def _set_domains(self, investigation_id: str, domains: list[str], by: Principal) -> None:
        case = self.cases[investigation_id]
        # Validated as the real store validates: through the model, which refuses an unknown pack.
        self.cases[investigation_id] = Investigation(
            **{**case.model_dump(), "domains": domains, "domains_chosen": True}
        )
        self.history.append(
            (
                investigation_id,
                AccessHistoryEntry(
                    changed_at=datetime(2026, 1, 3, tzinfo=UTC),
                    changed_by=by.id,
                    action="domains",
                    subject=",".join(self.cases[investigation_id].domains) or "pole",
                ),
            )
        )


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


@pytest.fixture
def cases() -> _Cases:
    held = _Cases()
    held.seed_case("inv-1", owner=ALICE, domains=["fibo"])
    held.grants[("inv-1", "bob")] = AccessLevel.EDITOR
    held.grants[("inv-1", "viv")] = AccessLevel.VIEWER
    return held


@pytest.fixture
def audit() -> _Audit:
    return _Audit()


def _as(principal: Principal, cases: _Cases, audit: _Audit) -> TestClient:
    datasets = InMemoryDatasetStore()
    datasets.add(
        Dataset(
            id="d1",
            name="One",
            owning_unit=principal.org_unit,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="seed",
        )
    )
    app.dependency_overrides[get_investigations] = lambda: cases
    app.dependency_overrides[get_principal] = lambda: principal
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_datasets] = lambda: datasets
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear():  # type: ignore[no-untyped-def]
    yield
    app.dependency_overrides.clear()


# --- the POST ---------------------------------------------------------------------------------


def test_a_case_made_with_packs_keeps_them_sorted_and_without_repeats(
    cases: _Cases, audit: _Audit
) -> None:
    client = _as(ALICE, cases, audit)

    made = client.post(
        "/v1/investigations", json={"name": "Mixed", "domains": ["niem", "fibo", "niem"]}
    )

    assert made.status_code == 201, made.text
    assert made.json()["domains"] == ["fibo", "niem"]
    assert cases.asked_domains == [["niem", "fibo", "niem"]], (
        "the route hands the store what the form sent; the store's model sorts and dedupes"
    )
    assert cases.cases[made.json()["id"]].domains == ["fibo", "niem"]


def test_an_unknown_pack_is_refused_at_the_post_and_no_case_is_made(
    cases: _Cases, audit: _Audit
) -> None:
    client = _as(ALICE, cases, audit)

    refused = client.post("/v1/investigations", json={"name": "X", "domains": ["fibo", "gone"]})

    assert refused.status_code == 422
    assert cases.asked_domains == []
    assert [c for c in cases.cases if c != "inv-1"] == []


def test_a_case_made_without_a_choice_is_never_chosen_and_one_made_with_none_is(
    cases: _Cases, audit: _Audit
) -> None:
    client = _as(ALICE, cases, audit)

    unchosen = client.post("/v1/investigations", json={"name": "A"})
    bare = client.post("/v1/investigations")
    pole = client.post("/v1/investigations", json={"name": "B", "domains": []})

    assert [unchosen.status_code, bare.status_code, pole.status_code] == [201, 201, 201]
    assert unchosen.json()["domains"] == [] and pole.json()["domains"] == []
    assert cases.asked_domains == [None, None, []], (
        "no field is NULL (never chosen); an empty list is a choice of POLE"
    )


# --- the listing ------------------------------------------------------------------------------


def test_the_case_list_carries_each_cases_packs(cases: _Cases, audit: _Audit) -> None:
    cases.seed_case("inv-2", owner=ALICE, domains=["fibo", "niem"], name="Second")
    cases.seed_case("inv-3", owner=ALICE, name="Third")

    listed = _as(ALICE, cases, audit).get("/v1/investigations").json()

    assert {row["id"]: row["domains"] for row in listed} == {
        "inv-1": ["fibo"],
        "inv-2": ["fibo", "niem"],
        "inv-3": [],
    }


def test_a_viewer_may_see_the_setting(cases: _Cases, audit: _Audit) -> None:
    """Every reader of the case may see what kind of case it is (decision 1, "Who sees it")."""
    listed = _as(VIV, cases, audit).get("/v1/investigations").json()

    assert [(row["id"], row["level"], row["domains"]) for row in listed] == [
        ("inv-1", "viewer", ["fibo"])
    ]


# --- the PATCH --------------------------------------------------------------------------------


def test_an_author_changes_the_packs_and_the_response_carries_them(
    cases: _Cases, audit: _Audit
) -> None:
    response = _as(ALICE, cases, audit).patch(
        "/v1/investigations/inv-1", json={"domains": ["stix", "niem"]}
    )

    assert response.status_code == 200, response.text
    assert response.json()["domains"] == ["niem", "stix"]
    assert response.json()["name"] == "C"
    assert cases.cases["inv-1"].domains == ["niem", "stix"]
    assert cases.names_set == []


def test_an_author_may_choose_the_core_model_alone(cases: _Cases, audit: _Audit) -> None:
    response = _as(ALICE, cases, audit).patch("/v1/investigations/inv-1", json={"domains": []})

    assert response.status_code == 200, response.text
    assert response.json()["domains"] == []
    assert cases.cases["inv-1"].domains == []
    assert [h[1].action for h in cases.history] == ["domains"], (
        "an empty list is a change, not 'nothing given'"
    )


def test_a_name_and_packs_may_change_together(cases: _Cases, audit: _Audit) -> None:
    response = _as(ALICE, cases, audit).patch(
        "/v1/investigations/inv-1", json={"name": " Renamed ", "domains": ["niem"]}
    )

    assert response.status_code == 200, response.text
    assert (response.json()["name"], response.json()["domains"]) == ("Renamed", ["niem"])
    assert (cases.cases["inv-1"].name, cases.cases["inv-1"].domains) == ("Renamed", ["niem"])


def test_a_rename_alone_returns_the_packs_it_left_alone(cases: _Cases, audit: _Audit) -> None:
    response = _as(ALICE, cases, audit).patch("/v1/investigations/inv-1", json={"name": "New"})

    assert response.status_code == 200, response.text
    assert (response.json()["name"], response.json()["domains"]) == ("New", ["fibo"])
    assert cases.history == [], "a rename touches no packs"


def test_only_an_author_changes_the_packs(cases: _Cases, audit: _Audit) -> None:
    body = {"domains": ["stix"]}

    editor = _as(BOB, cases, audit).patch("/v1/investigations/inv-1", json=body)
    viewer = _as(VIV, cases, audit).patch("/v1/investigations/inv-1", json=body)
    outsider = _as(EVE, cases, audit).patch("/v1/investigations/inv-1", json=body)
    missing = _as(EVE, cases, audit).patch("/v1/investigations/nope", json=body)

    assert editor.status_code == 403
    assert viewer.status_code == 403
    assert outsider.status_code == 404
    assert (outsider.status_code, outsider.json()) == (missing.status_code, missing.json()), (
        "another unit's case and no case at all answer alike"
    )
    assert cases.cases["inv-1"].domains == ["fibo"]
    assert cases.history == []


def test_a_change_of_packs_is_audited_and_kept_in_the_history(cases: _Cases, audit: _Audit) -> None:
    _as(ALICE, cases, audit).patch("/v1/investigations/inv-1", json={"domains": ["niem", "fibo"]})

    changed = [r for r in audit.records if r["action"] == "set_case_domains"]
    assert len(changed) == 1
    assert changed[0]["investigation_id"] == "inv-1"
    assert changed[0]["resolved_query"] == {"before": ["fibo"], "after": ["fibo", "niem"]}
    assert [(h[0], h[1].action, h[1].subject, h[1].changed_by) for h in cases.history] == [
        ("inv-1", "domains", "fibo,niem", "alice")
    ]


def test_a_patch_of_name_and_packs_is_atomic_when_the_case_goes_between_the_steps(
    cases: _Cases, audit: _Audit
) -> None:
    """The case is removed after the first write of the request. Nothing may be committed or
    audited: a rename that stuck while the packs were refused would be half a change."""
    cases.removed_mid_request = True

    response = _as(ALICE, cases, audit).patch(
        "/v1/investigations/inv-1", json={"name": "Renamed", "domains": ["niem"]}
    )

    assert response.status_code == 404
    assert cases.cases["inv-1"].name == "C"
    assert cases.cases["inv-1"].domains == ["fibo"]
    assert cases.history == []
    assert audit.records == []


def test_the_audit_of_a_never_chosen_case_says_none_and_of_a_pole_case_says_empty(
    cases: _Cases, audit: _Audit
) -> None:
    """`before` is the stored value, so "never chosen" (NULL) is not reported as POLE."""
    cases.seed_case("never", owner=ALICE, domains=None)
    cases.seed_case("pole", owner=ALICE, domains=[])
    client = _as(ALICE, cases, audit)

    client.patch("/v1/investigations/never", json={"domains": ["niem"]})
    client.patch("/v1/investigations/pole", json={"domains": ["niem"]})

    befores = {r["investigation_id"]: r["resolved_query"] for r in audit.records}
    assert befores == {
        "never": {"before": None, "after": ["niem"]},
        "pole": {"before": [], "after": ["niem"]},
    }


def test_the_patch_keeps_the_blank_name_refusal(cases: _Cases, audit: _Audit) -> None:
    client = _as(ALICE, cases, audit)

    blank = client.patch("/v1/investigations/inv-1", json={"name": "  "})
    blank_with_packs = client.patch(
        "/v1/investigations/inv-1", json={"name": "  ", "domains": ["stix"]}
    )

    assert blank.status_code == blank_with_packs.status_code == 422
    assert cases.cases["inv-1"].name == "C"
    assert cases.cases["inv-1"].domains == ["fibo"], "a refused request changes nothing"


def test_the_patch_refuses_an_empty_request_and_an_unknown_pack(
    cases: _Cases, audit: _Audit
) -> None:
    client = _as(ALICE, cases, audit)

    nothing = client.patch("/v1/investigations/inv-1", json={})
    nulls = client.patch("/v1/investigations/inv-1", json={"name": None, "domains": None})
    unknown = client.patch("/v1/investigations/inv-1", json={"domains": ["fibo", "gone"]})

    assert nothing.status_code == nulls.status_code == unknown.status_code == 422
    assert cases.cases["inv-1"].domains == ["fibo"]
    assert audit.records == []


# --- inheritance ------------------------------------------------------------------------------


class _Alerts:
    def __init__(self, alert: Alert) -> None:
        self.alert = alert

    async def get_authorized(self, alert_id: str, principal: Principal) -> Alert:
        return self.alert


class _Delta:
    async def seed(self, *args: object, **kwargs: object) -> ExpansionOutcome:
        return ExpansionOutcome(delta=DeltaAdd(seq=1, nodes=[], edges=[]), filtered_count=0)

    async def current_membership(self, investigation_id: str):  # type: ignore[no-untyped-def]
        return [], []


class _History:
    async def record_step(self, investigation_id: str, **kwargs: object) -> object:
        return object()


class _Valkey:
    async def publish(self, channel: str, message: str) -> int:
        return 1


@pytest.mark.parametrize("alert_case", ["inv-other", None])
def test_an_alert_jump_takes_the_packs_of_its_own_case_not_the_alerts(
    cases: _Cases, audit: _Audit, monkeypatch: pytest.MonkeyPatch, alert_case: str | None
) -> None:
    """The jumper is not authorised against `alert.investigation_id`, and it may be None, so the
    branch takes the packs of the case the route authorised (ADR-126 decision 1). The alert's own
    case here carries a different set, which the jump must never read."""
    cases.seed_case("inv-other", owner=EVE, domains=["stix"], name="Other unit's")
    cases.seed_case("inv-2", owner=ALICE, domains=["fibo", "niem"], name="The jumper's case")
    alert = Alert(
        id="al-1",
        rule_id="r-1",
        owner_id="alice",
        mode=AlertMode.FULL,
        referent_node_ids=[],
        investigation_id=alert_case,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    async def _no_referents(*args: object, **kwargs: object) -> tuple[list[object], int]:
        return [], 0

    monkeypatch.setattr(app_module, "fetch_jumpable_referents", _no_referents)
    client = _as(ALICE, cases, audit)
    app.dependency_overrides[get_alerts_store] = lambda: _Alerts(alert)
    app.dependency_overrides[get_graph] = lambda: object()
    app.dependency_overrides[get_working_set] = lambda: _Delta()
    app.dependency_overrides[get_history] = lambda: _History()
    app.dependency_overrides[get_valkey] = lambda: _Valkey()

    jumped = client.post("/v1/investigations/inv-2/alerts/al-1/jump")

    assert jumped.status_code == 201, jumped.text
    assert jumped.json()["investigation"]["domains"] == ["fibo", "niem"]
    assert cases.asked_domains == [["fibo", "niem"]]


# --- the store's read side, without Postgres ---------------------------------------------------


def _row(domains: list[str] | None, **extra: object) -> dict[str, object]:
    """A row as every column list in the store returns it."""
    return {
        "id": "inv-row",
        "name": "Row",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "created_by": "alice",
        "owning_unit": "unit-1",
        "branched_from": None,
        "domains": domains,
        "grant_level": "author",
        "unit_level": None,
        **extra,
    }


def test_a_row_with_null_reads_as_the_empty_list() -> None:
    found = InvestigationStore._parse_level_row(_row(None))

    assert found is not None and found[0].domains == []


def test_a_row_with_packs_reads_them_sorted_and_without_repeats() -> None:
    found = InvestigationStore._parse_level_row(_row(["niem", "fibo", "niem"]))

    assert found is not None and found[0].domains == ["fibo", "niem"]


def test_a_stored_pack_the_model_does_not_know_is_dropped_with_a_warning_not_an_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Written by hand, or left by a removed pack. A strict read would make the case unreadable by
    every route, since each reads it through `get_authorized`."""
    with caplog.at_level(logging.WARNING, logger="services.api.investigations"):
        found = InvestigationStore._parse_level_row(_row(["fibo", "gone"]))

    assert found is not None
    assert found[0].domains == ["fibo"]
    warned = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warned) == 1 and "gone" in warned[0] and "inv-row" in warned[0]


def test_a_case_whose_every_stored_pack_is_unknown_reads_as_the_core_model() -> None:
    found = InvestigationStore._parse_level_row(_row(["gone", "also-gone"]))

    assert found is not None and found[0].domains == []


def test_a_row_says_whether_anyone_chose_and_a_branch_inherits_the_stored_value() -> None:
    """NULL and `{}` both read as `[]`; only the flag tells them apart, and
    `domains_to_inherit` is what a branch is created with."""
    never = InvestigationStore._parse_level_row(_row(None))
    pole = InvestigationStore._parse_level_row(_row([]))
    mixed = InvestigationStore._parse_level_row(_row(["niem"]))

    assert never is not None and pole is not None and mixed is not None
    assert never[0].domains == pole[0].domains == []
    assert (never[0].domains_chosen, pole[0].domains_chosen) == (False, True)
    assert never[0].domains_to_inherit() is None
    assert pole[0].domains_to_inherit() == []
    assert mixed[0].domains_to_inherit() == ["niem"]
    assert "domains_chosen" not in never[0].model_dump(), "not on the wire"


def test_the_model_itself_refuses_an_unknown_pack() -> None:
    """On the way in, the model is strict; only the read side drops."""
    with pytest.raises(ValueError, match="domains"):
        Investigation(
            id="x",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="a",
            owning_unit="u",
            domains=["gone"],  # type: ignore[list-item]
        )


def _case_column_lists() -> tuple[list[str], list[str]]:
    """The column list of every SELECT from, and every INSERT into, the `investigations` table in
    `services/api/investigations.py`, read from the module's own source as the strings the code
    sends (the `_LEVEL_SQL` constant and the literals in each method), so a list added tomorrow is
    held to the same rule."""
    tree = ast.parse(Path(investigations_module.__file__).read_text(encoding="utf-8"))
    selects: list[str] = []
    inserts: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        text = node.value
        if text.startswith(("SELECT id,", "SELECT i.id,")) and " FROM investigations" in text:
            selects.append(text.split(" FROM ", 1)[0])
        elif text.startswith("INSERT INTO investigations ("):
            inserts.append(text.split(")", 1)[0])
    return selects, inserts


def test_every_column_list_on_the_cases_table_carries_domains() -> None:
    """ADR-126 decision 1: `get`, `_LEVEL_SQL`, `get_authorized`, `list_for`, `get_for_access_admin`
    (which the record's list did not name) and the INSERT. A list that left the column out would
    read every case as POLE, or store none of what was chosen."""
    selects, inserts = _case_column_lists()

    assert len(selects) == 5, f"expected the five case reads; found {selects}"
    assert len(inserts) == 1
    for columns in [*selects, *inserts]:
        assert "domains" in columns, columns


@pytest.mark.parametrize(
    ("parent_domains", "inherited"), [(None, None), ([], []), (["fibo", "niem"], ["fibo", "niem"])]
)
def test_an_alert_jump_inherits_the_stored_value_exactly(
    cases: _Cases,
    audit: _Audit,
    monkeypatch: pytest.MonkeyPatch,
    parent_domains: list[str] | None,
    inherited: list[str] | None,
) -> None:
    """ADR-126 decision 2: a never-chosen case (NULL) gives a never-chosen branch, and a case
    chosen as POLE (`{}`) gives `{}`. The read-side list is `[]` for both, so inheriting it would
    turn every branch of an unchosen case into a chosen POLE one."""
    cases.seed_case("inv-2", owner=ALICE, domains=parent_domains, name="Parent")
    alert = Alert(
        id="al-1",
        rule_id="r-1",
        owner_id="alice",
        mode=AlertMode.FULL,
        referent_node_ids=[],
        investigation_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    async def _no_referents(*args: object, **kwargs: object) -> tuple[list[object], int]:
        return [], 0

    monkeypatch.setattr(app_module, "fetch_jumpable_referents", _no_referents)
    client = _as(ALICE, cases, audit)
    app.dependency_overrides[get_alerts_store] = lambda: _Alerts(alert)
    app.dependency_overrides[get_graph] = lambda: object()
    app.dependency_overrides[get_working_set] = lambda: _Delta()
    app.dependency_overrides[get_history] = lambda: _History()
    app.dependency_overrides[get_valkey] = lambda: _Valkey()

    assert client.post("/v1/investigations/inv-2/alerts/al-1/jump").status_code == 201
    assert cases.asked_domains == [inherited]
