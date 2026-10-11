"""ADR-052 §7, stage 2: the listing route and the access routes, through the real level
dependencies with an in-memory store that applies the same rules the real one does (the real
store's SQL is `test_investigation_access_store.py`'s, against Postgres)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_investigations,
    get_principal,
    get_principal_names,
)
from services.api.investigations import (
    AccessHistoryEntry,
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)

from schemas.domain import Principal

ALICE = Principal(id="alice", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
BOB = Principal(id="bob", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
EVE = Principal(id="eve", clearance="OFFICIAL", org_unit="unit-2", roles=["analyst"])
ROOT = Principal(id="root", clearance="OFFICIAL", org_unit="unit-1", roles=["osprey-admin"])
NOT_ADMIN = Principal(id="mallory", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])


class _Store:
    def __init__(self) -> None:
        self.case = Investigation(
            id="inv-1",
            name="Shared case",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="alice",
            owning_unit="unit-1",
        )
        self.grants: dict[str, AccessLevel] = {"alice": AccessLevel.AUTHOR}
        self.unit: AccessLevel | None = None
        self.history: list[AccessHistoryEntry] = []

    def _level(self, principal: Principal) -> AccessLevel | None:
        held = [v for v in (self.grants.get(principal.id), self.unit) if v is not None]
        return max(held, key=lambda level: level.rank) if held else None

    def _note(self, by: Principal, action: str, subject: str, level: AccessLevel | None) -> None:
        self.history.append(
            AccessHistoryEntry(
                changed_at=datetime(2026, 1, 2, tzinfo=UTC),
                changed_by=by.id,
                action=action,
                subject=subject,
                level=None if level is None else level.value,
            )
        )

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        level = self._level(principal)
        if investigation_id != "inv-1" or principal.org_unit != "unit-1" or level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError("too low")
        return self.case

    async def get_for_access_admin(
        self, investigation_id: str, principal: Principal
    ) -> Investigation:
        if investigation_id != "inv-1" or principal.org_unit != "unit-1":
            raise InvestigationNotFoundError(investigation_id)
        return self.case

    async def effective_level(self, investigation_id: str, principal: Principal):  # type: ignore[no-untyped-def]
        return self._level(principal) if principal.org_unit == "unit-1" else None

    async def list_for(self, principal: Principal):  # type: ignore[no-untyped-def]
        level = self._level(principal) if principal.org_unit == "unit-1" else None
        return [] if level is None else [(self.case, level)]

    async def hidden_tab_ids(self, principal: Principal) -> set[str]:
        return set()

    async def list_grants(self, investigation_id: str) -> dict[str, AccessLevel]:
        return dict(self.grants)

    async def unit_level(self, investigation_id: str) -> AccessLevel | None:
        return self.unit

    async def set_grant(self, investigation_id, account_id, level, *, by) -> None:  # type: ignore[no-untyped-def]
        self.grants[account_id] = level
        self._note(by, "grant", account_id, level)

    async def remove_grant(self, investigation_id, account_id, *, by) -> None:  # type: ignore[no-untyped-def]
        self.grants.pop(account_id, None)
        self._note(by, "revoke", account_id, None)

    async def set_unit_level(self, investigation_id, level, *, by) -> None:  # type: ignore[no-untyped-def]
        self.unit = level
        self._note(by, "unit_level", "unit-1", level)

    async def rename(self, investigation_id, name, *, by) -> None:  # type: ignore[no-untyped-def]
        self.case = self.case.model_copy(update={"name": name.strip()})
        self._note(by, "rename", name.strip(), None)

    async def access_history(self, investigation_id: str) -> list[AccessHistoryEntry]:
        return list(self.history)


class _Audit:
    async def record(self, **kwargs: object) -> None:
        return None


class _Names:
    """ADR-106's directory: names an id only when asked, and records what it was asked."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def display_names(self, ids):  # type: ignore[no-untyped-def]
        ids = list(ids)
        self.asked.extend(ids)
        known = {"alice": "Alice Author", "bob": "Bob Viewer"}
        return {i: known[i] for i in ids if i in known}


@pytest.fixture
def store() -> _Store:
    return _Store()


def _as(principal: Principal, store: _Store, names: _Names | None = None) -> TestClient:
    names = names or _Names()
    app.dependency_overrides[get_investigations] = lambda: store
    app.dependency_overrides[get_principal_names] = lambda: names
    app.dependency_overrides[get_principal] = lambda: principal
    app.dependency_overrides[get_audit] = lambda: _Audit()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear():  # type: ignore[no-untyped-def]
    yield
    app.dependency_overrides.clear()


def test_the_list_offers_only_cases_the_account_holds_a_level_on_with_that_level(
    store: _Store,
) -> None:
    store.grants["bob"] = AccessLevel.VIEWER

    bobs = _as(BOB, store).get("/v1/investigations").json()
    eves = _as(EVE, store).get("/v1/investigations").json()

    assert [(c["id"], c["name"], c["level"]) for c in bobs] == [("inv-1", "Shared case", "viewer")]
    assert eves == []


def test_an_author_reads_the_whole_access_list_and_a_viewer_only_their_own_level(
    store: _Store,
) -> None:
    store.grants["bob"] = AccessLevel.VIEWER
    store.unit = AccessLevel.VIEWER

    author_view = _as(ALICE, store).get("/v1/investigations/inv-1/access").json()
    viewer_view = _as(BOB, store).get("/v1/investigations/inv-1/access").json()

    assert author_view["your_level"] == "author"
    assert author_view["unit_level"] == "viewer"
    assert author_view["grants"] == {"alice": "author", "bob": "viewer"}
    assert viewer_view == {
        "your_level": "viewer",
        "unit_level": None,
        "grants": None,
        "names": None,
    }


def test_an_author_sees_the_grantees_names_and_nobody_else_is_named(store: _Store) -> None:
    """The Share panel shows people by name (ADR-106): only the ids already in the Author's own
    grants are looked up, and a Viewer — who is not served the grants — causes no lookup at all."""
    store.grants["bob"] = AccessLevel.VIEWER
    store.grants["service-account-x"] = AccessLevel.VIEWER
    names = _Names()

    author_view = _as(ALICE, store, names).get("/v1/investigations/inv-1/access").json()

    assert author_view["names"] == {"alice": "Alice Author", "bob": "Bob Viewer"}, (
        "an id with no name is absent"
    )
    assert sorted(names.asked) == ["alice", "bob", "service-account-x"]
    names.asked.clear()
    _as(BOB, store, names).get("/v1/investigations/inv-1/access")
    assert names.asked == [], "a Viewer is served no grants, so no names are resolved for them"


def test_an_author_grants_and_revokes_and_sets_the_unit_wide_level(store: _Store) -> None:
    client = _as(ALICE, store)

    assert (
        client.put(
            "/v1/investigations/inv-1/access/grants/bob", json={"level": "editor"}
        ).status_code
        == 204
    )
    assert store.grants["bob"] is AccessLevel.EDITOR
    assert (
        client.put("/v1/investigations/inv-1/access", json={"unit_level": "viewer"}).status_code
        == 204
    )
    assert store.unit is AccessLevel.VIEWER
    assert (
        client.put("/v1/investigations/inv-1/access", json={"unit_level": None}).status_code == 204
    )
    assert store.unit is None
    assert client.delete("/v1/investigations/inv-1/access/grants/bob").status_code == 204
    assert "bob" not in store.grants


def test_a_unit_wide_level_can_be_viewer_or_editor_but_never_author(store: _Store) -> None:
    response = _as(ALICE, store).put(
        "/v1/investigations/inv-1/access", json={"unit_level": "author"}
    )

    assert response.status_code == 422
    assert store.unit is None


def test_an_editor_cannot_manage_access_and_gets_a_403(store: _Store) -> None:
    store.grants["bob"] = AccessLevel.EDITOR
    client = _as(BOB, store)

    put = client.put("/v1/investigations/inv-1/access/grants/bob", json={"level": "author"})
    delete = client.delete("/v1/investigations/inv-1/access/grants/alice")

    assert put.status_code == delete.status_code == 403
    assert store.grants == {"alice": AccessLevel.AUTHOR, "bob": AccessLevel.EDITOR}


def test_an_account_with_no_level_cannot_tell_the_access_routes_exist(store: _Store) -> None:
    response = _as(BOB, store).put(
        "/v1/investigations/inv-1/access/grants/bob", json={"level": "author"}
    )

    assert response.status_code == 404


def test_the_administrator_can_manage_access_to_a_stranded_case_without_reading_it(
    store: _Store,
) -> None:
    client = _as(ROOT, store)

    assert (
        client.put(
            "/v1/investigations/inv-1/access/grants/bob", json={"level": "author"}
        ).status_code
        == 204
    )
    assert store.grants["bob"] is AccessLevel.AUTHOR
    # The safety net is not a way in: reading the case still needs a level.
    assert client.get("/v1/investigations/inv-1").status_code == 404


def test_holding_no_administrator_role_is_not_the_safety_net(store: _Store) -> None:
    response = _as(NOT_ADMIN, store).put(
        "/v1/investigations/inv-1/access/grants/mallory", json={"level": "author"}
    )

    assert response.status_code == 404
    assert "mallory" not in store.grants


def test_the_administrator_of_another_unit_finds_nothing(store: _Store) -> None:
    other_admin = Principal(
        id="root2", clearance="OFFICIAL", org_unit="unit-2", roles=["osprey-admin"]
    )

    response = _as(other_admin, store).put(
        "/v1/investigations/inv-1/access/grants/root2", json={"level": "author"}
    )

    assert response.status_code == 404


def test_an_author_renames_the_case_and_a_blank_name_is_refused(store: _Store) -> None:
    client = _as(ALICE, store)

    assert client.patch("/v1/investigations/inv-1", json={"name": " Renamed "}).status_code == 200
    assert store.case.name == "Renamed"
    assert client.patch("/v1/investigations/inv-1", json={"name": "  "}).status_code == 422


def test_every_change_is_readable_in_the_history_by_an_author(store: _Store) -> None:
    client = _as(ALICE, store)
    client.put("/v1/investigations/inv-1/access/grants/bob", json={"level": "viewer"})

    history = client.get("/v1/investigations/inv-1/access/history").json()

    assert [(h["action"], h["subject"], h["level"], h["changed_by"]) for h in history] == [
        ("grant", "bob", "viewer", "alice")
    ]


def test_a_grantee_name_must_be_a_plain_non_empty_account_name(store: _Store) -> None:
    client = _as(ALICE, store)

    blank = client.put("/v1/investigations/inv-1/access/grants/%20", json={"level": "viewer"})
    too_long = client.put(
        "/v1/investigations/inv-1/access/grants/" + "x" * 300, json={"level": "viewer"}
    )
    bad_level = client.put("/v1/investigations/inv-1/access/grants/bob", json={"level": "root"})

    assert blank.status_code == too_long.status_code == bad_level.status_code == 422
    assert set(store.grants) == {"alice"}


# --- removing a case (ADR-052 Amendment 7) ---


def _with_remove(store: _Store) -> _Store:
    async def remove(investigation_id, *, by) -> None:  # type: ignore[no-untyped-def]
        store.removed = True
        store._note(by, "remove", investigation_id, None)

    store.remove = remove  # type: ignore[attr-defined]
    store.removed = False  # type: ignore[attr-defined]
    return store


def test_an_author_removes_the_case_with_a_204_and_it_is_recorded(store: _Store) -> None:
    _with_remove(store)

    response = _as(ALICE, store).delete("/v1/investigations/inv-1")

    assert response.status_code == 204
    assert store.removed  # type: ignore[attr-defined]
    assert store.history[-1].action == "remove"
    assert store.history[-1].changed_by == "alice"


def test_an_editor_or_viewer_cannot_remove_a_case_and_gets_a_403(store: _Store) -> None:
    _with_remove(store)
    store.grants["bob"] = AccessLevel.EDITOR

    assert _as(BOB, store).delete("/v1/investigations/inv-1").status_code == 403
    store.grants["bob"] = AccessLevel.VIEWER
    assert _as(BOB, store).delete("/v1/investigations/inv-1").status_code == 403
    assert not store.removed  # type: ignore[attr-defined]


def test_an_account_with_no_level_cannot_tell_the_case_exists_when_it_tries_to_remove_it(
    store: _Store,
) -> None:
    _with_remove(store)
    assert _as(EVE, store).delete("/v1/investigations/inv-1").status_code == 404
    assert _as(NOT_ADMIN, store).delete("/v1/investigations/inv-1").status_code == 404
    assert not store.removed  # type: ignore[attr-defined]


def test_the_administrator_of_the_cases_own_unit_can_remove_a_stranded_case(
    store: _Store,
) -> None:
    """Reading of ADR-052 §4: the safety net that lets an administrator manage a case's access
    also lets them remove a case no Author is left to remove (the blank cases the old Glass made).
    It confers no read access."""
    _with_remove(store)
    store.grants.clear()

    response = _as(ROOT, store).delete("/v1/investigations/inv-1")

    assert response.status_code == 204
    assert store.history[-1].changed_by == "root"
    assert _as(ROOT, store).get("/v1/investigations/inv-1/access/history").status_code == 200


def test_the_administrator_of_another_unit_cannot_remove_it(store: _Store) -> None:
    _with_remove(store)
    other_admin = Principal(
        id="root2", clearance="OFFICIAL", org_unit="unit-2", roles=["osprey-admin"]
    )
    assert _as(other_admin, store).delete("/v1/investigations/inv-1").status_code == 404
    assert not store.removed  # type: ignore[attr-defined]
