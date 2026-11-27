"""SE9h (security, Conduit; the owner's ruling of 27 November 2026 on GR1f1's question 8): a case's
access read and datasets read write an audit row, as the case's other reads do.

**The sibling copied is `GET /v1/investigations/{id}` (`app.get_investigation`).** Its granted read
writes the principal, the case's id, `resolved_query={}` and `result_cardinality=1` under an action
of its own; its refusal at the case's level is `_authorize`'s `access_denied` row (cardinality 0,
`{}` where the case reads as missing, `{"needed": …}` where the refusal is a 403). Every expected
row here is read from that sibling run over the same stores, never written down alone.

The real app, `require_right`, the level gate and the routes run; the stores are stand-ins that
refuse as the real ones do (rule 15): another unit, no level and no such case all read as missing.

Each case asserts the whole list of rows written, so a second row fails it as a missing one does."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_datasets,
    get_investigations,
    get_principal,
    get_principal_names,
    get_target_models,
)
from services.api.audit import AuditWriteError
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.investigations import AccessLevel, Investigation, InvestigationNotFoundError
from services.api.target_models import InMemoryTargetModelStore

from schemas.domain import Principal
from schemas.rights import Right, rights_for

CASE = "case-1"
NO_SUCH_CASE = "case-that-is-not"


def _person(name: str, *, unit: str = "unit-1", roles: tuple[str, ...] = ("analyst",)) -> Principal:
    return Principal(id=name, clearance="OFFICIAL", org_unit=unit, roles=list(roles))


AUTHOR = _person("alice")
VIEWER = _person("bob")
NO_LEVEL = _person("carol")
OTHER_UNIT = _person("eve", unit="unit-2")
ADMIN_WITHOUT_A_LEVEL = _person("root", roles=("osprey-admin",))
#: A level on the case and no right at all: the access route refuses them, the datasets route
#: answers them none (ADR-099 Amendment 11).
VIEWER_WITHOUT_A_RIGHT = _person("dan", roles=())

#: The two reads, each with the action its granted read is recorded under.
READS = {"access": "get_investigation_access", "datasets": "get_investigation_datasets"}

#: Who the case's level refuses, and on which case: each is a 404, one answer for all.
REFUSED_AT_THE_LEVEL = {
    "no level on the case": (NO_LEVEL, CASE),
    "another unit": (OTHER_UNIT, CASE),
    "the unit's administrator with no level": (ADMIN_WITHOUT_A_LEVEL, CASE),
    "no such case": (AUTHOR, NO_SUCH_CASE),
}


class _Cases:
    """The investigation store's four reads these routes make."""

    def __init__(self) -> None:
        self.case = Investigation(
            id=CASE,
            name="A case with a name that must not reach a row",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by=AUTHOR.id,
            owning_unit="unit-1",
        )
        self.grants = {
            AUTHOR.id: AccessLevel.AUTHOR,
            VIEWER.id: AccessLevel.VIEWER,
            VIEWER_WITHOUT_A_RIGHT.id: AccessLevel.VIEWER,
        }
        self.asked: list[str] = []

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        self.asked.append(investigation_id)
        level = self.grants.get(principal.id)
        if investigation_id != CASE or principal.org_unit != "unit-1" or level is None:
            raise InvestigationNotFoundError(investigation_id)
        assert level.rank >= need.rank
        return self.case

    async def effective_level(
        self, investigation_id: str, principal: Principal
    ) -> AccessLevel | None:
        return self.grants.get(principal.id)

    async def list_grants(self, investigation_id: str) -> dict[str, AccessLevel]:
        return dict(self.grants)

    async def unit_level(self, investigation_id: str) -> AccessLevel | None:
        return AccessLevel.VIEWER


class _Names:
    async def display_names(self, ids: Any) -> dict[str, str]:
        return {i: f"Name of {i}" for i in ids}


class _Audit:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.down = False

    async def record(self, **kwargs: Any) -> None:
        if self.down:
            raise AuditWriteError("the audit stream is down")
        self.rows.append(kwargs)


def _datasets() -> InMemoryDatasetStore:
    held = InMemoryDatasetStore()
    for dataset_id, name in (("ds-a", "Fixture Corp"), ("ds-b", "Second fixture")):
        held.add(
            Dataset(
                id=dataset_id,
                name=name,
                owning_unit="unit-1",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                created_by="test",
            )
        )
    # Two datasets, so a row carrying their count would not read as the sibling's 1.
    held.cases[CASE] = ["ds-a", "ds-b"]
    return held


class _World:
    def __init__(self) -> None:
        self.cases = _Cases()
        self.audit = _Audit()
        self.datasets = _datasets()
        self.models = InMemoryTargetModelStore(core_types=frozenset())
        self.who = AUTHOR
        app.dependency_overrides[get_investigations] = lambda: self.cases
        app.dependency_overrides[get_audit] = lambda: self.audit
        app.dependency_overrides[get_datasets] = lambda: self.datasets
        app.dependency_overrides[get_target_models] = lambda: self.models
        app.dependency_overrides[get_principal_names] = _Names
        app.dependency_overrides[get_principal] = lambda: self.who
        self.client = TestClient(app, raise_server_exceptions=False)

    def get(self, who: Principal, case: str, read: str = "") -> tuple[Any, list[dict[str, Any]]]:
        """The answer, and every audit row this one request wrote."""
        self.who = who
        self.audit.rows.clear()
        path = f"/v1/investigations/{case}" + (f"/{read}" if read else "")
        response = self.client.get(path)
        return response, list(self.audit.rows)


@pytest.fixture
def world() -> Iterator[_World]:
    before = dict(app.dependency_overrides)
    yield _World()
    app.dependency_overrides.clear()
    app.dependency_overrides.update(before)


def test_the_sibling_writes_the_shape_this_file_copies(world: _World) -> None:
    """The reference itself, so a change to the sibling is seen here as that, not as a fault in
    either read."""
    granted, rows = world.get(VIEWER, CASE)
    assert granted.status_code == 200, granted.text
    assert rows == [
        {
            "principal": VIEWER,
            "action": "get_investigation",
            "investigation_id": CASE,
            "resolved_query": {},
            "result_cardinality": 1,
        }
    ]
    refused, rows = world.get(NO_LEVEL, CASE)
    assert refused.status_code == 404
    assert rows == [
        {
            "principal": NO_LEVEL,
            "action": "access_denied",
            "investigation_id": CASE,
            "resolved_query": {},
            "result_cardinality": 0,
        }
    ]


@pytest.mark.parametrize("who", [AUTHOR, VIEWER], ids=["an author", "a viewer"])
@pytest.mark.parametrize("read", sorted(READS))
def test_a_granted_read_writes_one_row_of_the_siblings_shape(
    world: _World, read: str, who: Principal
) -> None:
    """An Author's access read serves the grants and names and a Viewer's their own level alone;
    both are one row, which carries neither (the row is the sibling's but for its action)."""
    _, sibling = world.get(who, CASE)
    response, rows = world.get(who, CASE, read)
    assert response.status_code == 200, response.text
    assert rows == [{**sibling[0], "action": READS[read]}]


def test_the_granted_reads_still_answer_what_they_answered(world: _World) -> None:
    access, _ = world.get(AUTHOR, CASE, "access")
    assert access.json()["grants"] == {"alice": "author", "bob": "viewer", "dan": "viewer"}
    assert access.json()["names"]["bob"] == "Name of bob"
    own, _ = world.get(VIEWER, CASE, "access")
    assert own.json() == {
        "your_level": "viewer",
        "unit_level": None,
        "grants": None,
        "names": None,
    }
    datasets, _ = world.get(AUTHOR, CASE, "datasets")
    assert [d["id"] for d in datasets.json()] == ["ds-a", "ds-b"]


def test_a_datasets_read_answered_none_is_one_row_like_any_other(world: _World) -> None:
    """ADR-099 Amendment 11: a person holding no right is answered none, not refused, and the read
    is recorded as any other, with no count of what was kept from them."""
    response, rows = world.get(VIEWER_WITHOUT_A_RIGHT, CASE, "datasets")
    assert (response.status_code, response.json()) == (200, [])
    assert rows == [
        {
            "principal": VIEWER_WITHOUT_A_RIGHT,
            "action": READS["datasets"],
            "investigation_id": CASE,
            "resolved_query": {},
            "result_cardinality": 1,
        }
    ]


@pytest.mark.parametrize("refusal", sorted(REFUSED_AT_THE_LEVEL))
@pytest.mark.parametrize("read", sorted(READS))
def test_a_refusal_at_the_cases_level_writes_the_siblings_one_refusal_row(
    world: _World, read: str, refusal: str
) -> None:
    who, case = REFUSED_AT_THE_LEVEL[refusal]
    sibling_response, sibling = world.get(who, case)
    response, rows = world.get(who, case, read)
    assert (response.status_code, response.content) == (404, sibling_response.content)
    assert sibling_response.status_code == 404
    assert len(sibling) == 1
    assert rows == sibling


@pytest.mark.parametrize(
    ("who", "case"),
    [
        (VIEWER_WITHOUT_A_RIGHT, CASE),
        (_person("carol", roles=()), CASE),
        (_person("eve", unit="unit-2", roles=()), CASE),
        (VIEWER_WITHOUT_A_RIGHT, NO_SUCH_CASE),
    ],
    ids=["with a level", "with no level", "another unit", "no such case"],
)
def test_the_access_reads_refusal_for_want_of_the_right_writes_one_row(
    world: _World, who: Principal, case: str
) -> None:
    """The access route's other refusal, `share_case`'s 403, made before the case is looked for:
    the row is `access_denied` as the level's 403 is, saying what was needed. The answer and the
    row are the same whether or not the case exists or the person holds a level on it, and the
    case store is never asked."""
    assert Right.SHARE_CASE not in rights_for(who.roles)
    response, rows = world.get(who, case, "access")
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": {"error": "right_required", "right": "share_case"}}
    assert rows == [
        {
            "principal": who,
            "action": "access_denied",
            "investigation_id": case,
            "resolved_query": {"needed": "share_case"},
            "result_cardinality": 0,
        }
    ]
    assert world.cases.asked == []


@pytest.mark.parametrize(
    ("who", "read"),
    [
        (AUTHOR, "access"),
        (VIEWER, "access"),
        (VIEWER_WITHOUT_A_RIGHT, "access"),
        (NO_LEVEL, "access"),
        (AUTHOR, "datasets"),
        (VIEWER, "datasets"),
        (NO_LEVEL, "datasets"),
    ],
)
def test_with_the_audit_stream_down_neither_read_answers(
    world: _World, who: Principal, read: str
) -> None:
    """`spec/03` §8: the audit stream unavailable, reads are rejected. Nothing of the case is in
    the answer, so the row is written before the read is given, never after."""
    world.audit.down = True
    response, _ = world.get(who, CASE, read)
    assert response.status_code == 503, response.text
    assert response.json()["error"] == "audit_unavailable"
    for held in ("alice", "grants", "Fixture", "ds-a"):
        assert held not in response.text
