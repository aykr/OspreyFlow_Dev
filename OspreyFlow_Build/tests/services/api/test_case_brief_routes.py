"""The case brief's routes — ADR-128 decision 3. Fakes behind `app.dependency_overrides`, never a live
Postgres or Valkey, as `test_history_routes.py` does. The service's own rules are
`test_case_brief.py`; what belongs here is the wiring: who may call each route (read at Viewer, every
edit at Author), what each edit writes to the audit stream and to the History, and what each
refusal looks like on the wire.

Every route of a case gets its own access-control test (`CLAUDE.md` rule 4), so the write routes are
tried below as an Editor, as a Viewer and as someone with no level, each one by name."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_case_brief,
    get_history,
    get_investigations,
    get_principal,
    get_valkey,
    get_working_set,
)
from services.api.case_brief import MAX_REQUIREMENTS, CaseBriefService
from services.api.history import HistoryStep
from services.api.history_labels import BRIEF_EDITED
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)
from services.api.working_set.models import DeltaSnapshot
from services.api.working_set.service import Restored

from schemas.domain import Principal

from .case_brief_fakes import Readable, make_service

AUTHOR = Principal(id="author-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
EDITOR = Principal(id="editor-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
VIEWER = Principal(id="viewer-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
STRANGER = Principal(id="stranger-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
#: The Author's account, but a role that holds no `share_case`: the right is refused on its own.
AUTHOR_WITHOUT_THE_RIGHT = Principal(
    id="author-1", clearance="OFFICIAL", org_unit="unit-1", roles=["reports_viewer"]
)

LEVELS: dict[str, AccessLevel] = {
    "author-1": AccessLevel.AUTHOR,
    "editor-1": AccessLevel.EDITOR,
    "viewer-1": AccessLevel.VIEWER,
}
_CASE = Investigation(
    id="inv-1",
    name="A case",
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
    created_by="author-1",
    owning_unit="unit-1",
)
P = "/v1/investigations/inv-1/brief"


class _LevelAware:
    """Holds a level per account on `inv-1` and applies it as the real store does: no level is a
    404 identical to a case that does not exist, a level too low is a 403."""

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        held = LEVELS.get(principal.id)
        if investigation_id != "inv-1" or held is None:
            raise InvestigationNotFoundError(investigation_id)
        if held.rank < need.rank:
            raise InsufficientAccessError(f"{need.value} needed")
        return _CASE


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)

    @property
    def actions(self) -> list[object]:
        return [r["action"] for r in self.records]


class _History:
    def __init__(self) -> None:
        self.steps: list[dict[str, object]] = []

    async def last_seq(self, investigation_id: str) -> int:
        return 7

    async def record_step(self, investigation_id: str, **kwargs: object) -> object:
        self.steps.append({"investigation_id": investigation_id, **kwargs})
        return object()

    async def get_step(self, investigation_id: str, step_id: str) -> HistoryStep:
        label = {"brief-step": BRIEF_EDITED, "canvas-step": "Seeded"}[step_id]
        return HistoryStep(
            id=step_id,
            investigation_id=investigation_id,
            seq=3,
            label=label,
            created_at=datetime(2026, 10, 26, tzinfo=UTC),
            created_by="author-1",
            nodes=[],
            edges=[],
        )


class _Working:
    def __init__(self) -> None:
        self.restored: list[str] = []

    async def restore(self, investigation_id: str, nodes: list, edges: list, principal: Principal):  # type: ignore[no-untyped-def,type-arg]
        self.restored.append(investigation_id)
        snapshot = DeltaSnapshot(seq=9, nodes=[], edges=[])
        return Restored(published=snapshot, response=snapshot)


class _Valkey:
    async def publish(self, channel: str, message: str) -> int:
        return 1


class _Rig:
    def __init__(self) -> None:
        self.audit = _Audit()
        self.history = _History()
        self.readable = Readable()
        self.service, self.store, _ = make_service(self.readable)
        self.principal = AUTHOR
        self.client = TestClient(app, raise_server_exceptions=False)
        app.dependency_overrides[get_investigations] = lambda: _LevelAware()
        app.dependency_overrides[get_principal] = lambda: self.principal
        app.dependency_overrides[get_audit] = lambda: self.audit
        app.dependency_overrides[get_history] = lambda: self.history
        self.working = _Working()
        app.dependency_overrides[get_working_set] = lambda: self.working
        app.dependency_overrides[get_valkey] = lambda: _Valkey()
        self.serve(self.service)

    def serve(self, service: CaseBriefService) -> None:
        app.dependency_overrides[get_case_brief] = lambda: service

    def as_(self, principal: Principal) -> _Rig:
        self.principal = principal
        return self


@pytest.fixture
def rig():  # type: ignore[no-untyped-def]
    made = _Rig()
    try:
        yield made
    finally:
        app.dependency_overrides.clear()


def _with_one_requirement(rig: _Rig) -> str:
    rig.readable.allow("trend", "t1", "Throw-overs by week", AUTHOR, VIEWER)
    created = rig.client.post(f"{P}/requirements", json={"text": "Who orchestrates?"})
    assert created.status_code == 201
    rig.audit.records.clear()
    rig.history.steps.clear()
    return str(created.json()["requirements"][0]["id"])


# --- who may call what ----------------------------------------------------------------------

#: Every route that changes the brief: (method, path under the brief, body). Each is Author's.
WRITES = [
    ("PUT", "/priority", {"text": "A priority"}),
    ("POST", "/requirements", {"text": "A requirement"}),
    ("PUT", "/requirements/req-1", {"text": "Changed"}),
    ("DELETE", "/requirements/req-1", None),
    ("PUT", "/requirements/req-1/status", {"status": "answered"}),
    ("POST", "/requirements/req-1/attachments", {"kind": "trend", "id": "t1"}),
    ("DELETE", "/requirements/req-1/attachments/trend/t1", None),
]


def _send(client: TestClient, method: str, path: str, body: object) -> Any:
    return client.request(method, f"{P}{path}", json=body)


def test_a_viewer_reads_the_brief(rig: _Rig) -> None:
    rig.as_(AUTHOR)
    rig.client.put(f"{P}/priority", json={"text": "Who is orchestrating the throw-overs?"})
    rig.as_(VIEWER)
    response = rig.client.get(P)
    assert response.status_code == 200
    assert response.json() == {
        "priority": "Who is orchestrating the throw-overs?",
        "requirements": [],
    }


def test_an_editor_reads_the_brief_too(rig: _Rig) -> None:
    assert rig.as_(EDITOR).client.get(P).status_code == 200


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
@pytest.mark.parametrize("who", [EDITOR, VIEWER], ids=["editor", "viewer"])
def test_a_non_author_cannot_edit_the_brief_and_nothing_is_written(
    rig: _Rig, method: str, path: str, body: object, who: Principal
) -> None:
    """The ADR's test: a non-Author's edit is refused. Refused with a 403 (they can see the case
    exists), audited as a denial, and neither the brief nor the History moved."""
    rig.readable.allow("trend", "t1", "T", AUTHOR, VIEWER, EDITOR)
    rig.as_(AUTHOR).client.post(f"{P}/requirements", json={"text": "Seeded by the Author"})
    before = rig.store.rows["inv-1"].model_dump_json()
    rig.audit.records.clear()
    rig.history.steps.clear()

    response = _send(rig.as_(who).client, method, path, body)

    assert response.status_code == 403
    assert rig.store.rows["inv-1"].model_dump_json() == before
    assert rig.history.steps == []
    assert rig.audit.actions == ["access_denied"]


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
def test_someone_with_no_level_gets_the_same_404_as_a_case_that_does_not_exist(
    rig: _Rig, method: str, path: str, body: object
) -> None:
    rig.readable.allow("trend", "t1", "T", AUTHOR, STRANGER)
    shown = _send(rig.as_(STRANGER).client, method, path, body)
    elsewhere = rig.client.request(
        method, f"/v1/investigations/no-such-case/brief{path}", json=body
    )
    assert shown.status_code == elsewhere.status_code == 404
    assert shown.json() == elsewhere.json()
    assert rig.store.rows == {}
    assert rig.history.steps == []
    assert "access_denied" in rig.audit.actions


def test_someone_with_no_level_cannot_read_the_brief_either(rig: _Rig) -> None:
    rig.as_(AUTHOR).client.put(f"{P}/priority", json={"text": "Secret"})
    shown = rig.as_(STRANGER).client.get(P)
    elsewhere = rig.client.get("/v1/investigations/no-such-case/brief")
    assert shown.status_code == 404
    assert shown.json() == elsewhere.json()
    assert "Secret" not in shown.text


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
def test_an_author_without_the_share_case_right_is_refused_on_every_edit(
    rig: _Rig, method: str, path: str, body: object
) -> None:
    response = _send(rig.as_(AUTHOR_WITHOUT_THE_RIGHT).client, method, path, body)
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "right_required"
    assert rig.store.rows == {}


# --- what an edit writes: the answer, the audit stream, the History -------------------------


def test_setting_the_priority_answers_with_the_brief_is_audited_and_enters_the_history(
    rig: _Rig,
) -> None:
    response = rig.client.put(f"{P}/priority", json={"text": "Who is orchestrating?"})
    assert response.status_code == 200
    assert response.json()["priority"] == "Who is orchestrating?"
    [record] = rig.audit.records
    assert record["action"] == "case_brief_set_priority"
    assert record["investigation_id"] == "inv-1"
    assert record["principal"] == AUTHOR
    [step] = rig.history.steps
    assert step["label"] == BRIEF_EDITED == "Edited the brief"
    assert step["created_by"] == "author-1"
    assert step["investigation_id"] == "inv-1"


def test_a_history_step_of_the_brief_holds_no_canvas_snapshot(rig: _Rig) -> None:
    """An edit to the brief is not a state of the canvas: its step carries no nodes or links, so it
    is not restorable and cannot empty the canvas by being restored."""
    rig.client.put(f"{P}/priority", json={"text": "x"})
    [step] = rig.history.steps
    assert step["nodes"] == [] and step["edges"] == []
    assert step["seq"] == 7


def test_adding_a_requirement_is_audited_by_its_id_and_enters_the_history(rig: _Rig) -> None:
    response = rig.client.post(f"{P}/requirements", json={"text": "Who orchestrates?"})
    assert response.status_code == 201
    requirement = response.json()["requirements"][0]
    assert (requirement["text"], requirement["status"], requirement["attachments"]) == (
        "Who orchestrates?",
        "open",
        [],
    )
    [record] = rig.audit.records
    assert record["action"] == "case_brief_add_requirement"
    assert record["resolved_query"] == {"requirement_id": requirement["id"]}
    assert [s["label"] for s in rig.history.steps] == [BRIEF_EDITED]


def test_editing_a_requirement_is_audited_and_enters_the_history(rig: _Rig) -> None:
    requirement_id = _with_one_requirement(rig)
    response = rig.client.put(f"{P}/requirements/{requirement_id}", json={"text": "Who, exactly?"})
    assert response.status_code == 200
    assert response.json()["requirements"][0]["text"] == "Who, exactly?"
    [record] = rig.audit.records
    assert record["action"] == "case_brief_edit_requirement"
    assert record["resolved_query"] == {"requirement_id": requirement_id}
    assert [s["label"] for s in rig.history.steps] == [BRIEF_EDITED]


def test_marking_a_requirement_answered_is_audited_with_the_new_status_and_enters_the_history(
    rig: _Rig,
) -> None:
    requirement_id = _with_one_requirement(rig)
    response = rig.client.put(
        f"{P}/requirements/{requirement_id}/status", json={"status": "answered"}
    )
    assert response.status_code == 200
    assert response.json()["requirements"][0]["status"] == "answered"
    [record] = rig.audit.records
    assert record["action"] == "case_brief_set_status"
    assert record["resolved_query"] == {"requirement_id": requirement_id, "status": "answered"}
    assert record["principal"] == AUTHOR
    assert [s["label"] for s in rig.history.steps] == [BRIEF_EDITED]


def test_removing_a_requirement_is_audited_and_enters_the_history(rig: _Rig) -> None:
    requirement_id = _with_one_requirement(rig)
    response = rig.client.delete(f"{P}/requirements/{requirement_id}")
    assert response.status_code == 200
    assert response.json()["requirements"] == []
    [record] = rig.audit.records
    assert record["action"] == "case_brief_remove_requirement"
    assert [s["label"] for s in rig.history.steps] == [BRIEF_EDITED]


def test_each_edit_the_author_makes_is_one_history_step_in_order(rig: _Rig) -> None:
    """The ADR's test: History shows each edit."""
    rig.client.put(f"{P}/priority", json={"text": "P"})
    created = rig.client.post(f"{P}/requirements", json={"text": "R"})
    requirement_id = created.json()["requirements"][0]["id"]
    rig.client.put(f"{P}/requirements/{requirement_id}", json={"text": "R2"})
    rig.client.put(f"{P}/requirements/{requirement_id}/status", json={"status": "answered"})
    rig.client.delete(f"{P}/requirements/{requirement_id}")
    assert [s["label"] for s in rig.history.steps] == [BRIEF_EDITED] * 5
    assert rig.audit.actions == [
        "case_brief_set_priority",
        "case_brief_add_requirement",
        "case_brief_edit_requirement",
        "case_brief_set_status",
        "case_brief_remove_requirement",
    ]


def test_a_refused_edit_writes_no_audit_record_of_an_edit_and_no_history_step(rig: _Rig) -> None:
    for _ in range(MAX_REQUIREMENTS):
        rig.client.post(f"{P}/requirements", json={"text": "r"})
    rig.audit.records.clear()
    rig.history.steps.clear()
    response = rig.client.post(f"{P}/requirements", json={"text": "one too many"})
    assert response.status_code == 409
    assert rig.audit.records == [] and rig.history.steps == []


def test_the_audit_record_of_an_edit_never_carries_the_text(rig: _Rig) -> None:
    rig.client.put(f"{P}/priority", json={"text": "A sentence about a person"})
    rig.client.post(f"{P}/requirements", json={"text": "Another about the same person"})
    assert "person" not in str(rig.audit.records).replace("principal", "")


# --- attachments ----------------------------------------------------------------------------


def test_attaching_shows_the_title_to_the_author_and_is_audited_by_kind_and_id(rig: _Rig) -> None:
    requirement_id = _with_one_requirement(rig)
    response = rig.client.post(
        f"{P}/requirements/{requirement_id}/attachments", json={"kind": "trend", "id": "t1"}
    )
    assert response.status_code == 200
    assert response.json()["requirements"][0]["attachments"] == [
        {"kind": "trend", "id": "t1", "title": "Throw-overs by week"}
    ]
    [record] = rig.audit.records
    assert record["action"] == "case_brief_attach"
    assert record["resolved_query"] == {
        "requirement_id": requirement_id,
        "kind": "trend",
        "id": "t1",
    }


def test_detaching_is_audited_and_the_attachment_goes(rig: _Rig) -> None:
    requirement_id = _with_one_requirement(rig)
    rig.client.post(
        f"{P}/requirements/{requirement_id}/attachments", json={"kind": "trend", "id": "t1"}
    )
    rig.audit.records.clear()
    response = rig.client.delete(f"{P}/requirements/{requirement_id}/attachments/trend/t1")
    assert response.status_code == 200
    assert response.json()["requirements"][0]["attachments"] == []
    [record] = rig.audit.records
    assert record["action"] == "case_brief_detach"


def test_an_attach_or_detach_writes_no_history_step(rig: _Rig) -> None:
    """Rule 3: History is shown to every reader. A step for an attach would tell a reader who may
    not read the attachment that something they cannot see changed, which is a trace. The attach and
    the detach are audited, which no reader sees; text, status and removal are History steps."""
    requirement_id = _with_one_requirement(rig)
    rig.client.post(
        f"{P}/requirements/{requirement_id}/attachments", json={"kind": "trend", "id": "t1"}
    )
    rig.client.delete(f"{P}/requirements/{requirement_id}/attachments/trend/t1")
    assert rig.history.steps == []
    assert rig.audit.actions == ["case_brief_attach", "case_brief_detach"]


def test_a_viewer_reads_what_they_may_and_not_what_they_may_not_through_the_route(
    rig: _Rig,
) -> None:
    """Rule 3, over the wire: the Viewer's response for a brief with an attachment only the Author
    may read equals, byte for byte, the response for a brief without it."""
    rig.readable.allow("pattern", "authors-own", "The Author's pattern", AUTHOR)
    rig.readable.allow("trend", "t1", "Throw-overs by week", AUTHOR, VIEWER)
    plain_readable = Readable()
    plain_readable.allow("trend", "t1", "Throw-overs by week", AUTHOR, VIEWER)
    plain_service, _, _ = make_service(plain_readable)

    def build(client: TestClient) -> None:
        client.put(f"{P}/priority", json={"text": "Who is orchestrating?"})
        client.post(f"{P}/requirements", json={"text": "Who orchestrates?"})
        client.post(f"{P}/requirements", json={"text": "Where and when?"})
        client.post(f"{P}/requirements/req-1/attachments", json={"kind": "trend", "id": "t1"})

    rig.as_(AUTHOR)
    build(rig.client)
    attached = rig.client.post(
        f"{P}/requirements/req-2/attachments", json={"kind": "pattern", "id": "authors-own"}
    )
    assert attached.status_code == 200
    assert [a["title"] for a in attached.json()["requirements"][1]["attachments"]] == [
        "The Author's pattern"
    ]
    with_hidden = rig.as_(VIEWER).client.get(P)

    rig.serve(plain_service)
    build(rig.as_(AUTHOR).client)
    without = rig.as_(VIEWER).client.get(P)

    assert with_hidden.status_code == without.status_code == 200
    assert with_hidden.content == without.content
    assert "authors-own" not in with_hidden.text and "Author's pattern" not in with_hidden.text


def test_the_author_is_refused_an_attachment_they_cannot_read_in_the_same_words_as_a_missing_one(
    rig: _Rig,
) -> None:
    rig.readable.allow("pattern", "someone-elses", "Hidden", VIEWER)
    requirement_id = _with_one_requirement(rig)
    url = f"{P}/requirements/{requirement_id}/attachments"
    unreadable = rig.client.post(url, json={"kind": "pattern", "id": "someone-elses"})
    absent = rig.client.post(url, json={"kind": "pattern", "id": "no-such-pattern"})
    assert unreadable.status_code == absent.status_code == 404
    assert unreadable.json() == absent.json()
    assert unreadable.json()["error"] == "attachment_not_found"
    assert rig.audit.records == [] and rig.history.steps == []


def test_an_attachment_of_an_unknown_kind_is_refused_before_anything_is_looked_up(
    rig: _Rig,
) -> None:
    requirement_id = _with_one_requirement(rig)
    response = rig.client.post(
        f"{P}/requirements/{requirement_id}/attachments", json={"kind": "document", "id": "d1"}
    )
    assert response.status_code == 422


# --- the wire's refusals --------------------------------------------------------------------


def test_a_status_smuggled_into_an_add_an_edit_or_the_priority_is_refused_not_ignored(
    rig: _Rig,
) -> None:
    """Rule 5 at the door: only the status route sets a status, so the other bodies refuse the
    field instead of quietly dropping it."""
    requirement_id = _with_one_requirement(rig)
    added = rig.client.post(f"{P}/requirements", json={"text": "x", "status": "answered"})
    edited = rig.client.put(
        f"{P}/requirements/{requirement_id}", json={"text": "x", "status": "answered"}
    )
    prioritised = rig.client.put(f"{P}/priority", json={"text": "x", "status": "answered"})
    assert added.status_code == edited.status_code == prioritised.status_code == 422
    assert rig.store.rows["inv-1"].requirements[0].status == "open"
    assert len(rig.store.rows["inv-1"].requirements) == 1


def test_a_status_other_than_open_or_answered_is_refused(rig: _Rig) -> None:
    requirement_id = _with_one_requirement(rig)
    response = rig.client.put(
        f"{P}/requirements/{requirement_id}/status", json={"status": "verified"}
    )
    assert response.status_code == 422
    assert rig.store.rows["inv-1"].requirements[0].status == "open"


def test_an_unknown_requirement_is_a_404_with_its_own_code(rig: _Rig) -> None:
    for method, path, body in [
        ("PUT", "/requirements/nope", {"text": "x"}),
        ("DELETE", "/requirements/nope", None),
        ("PUT", "/requirements/nope/status", {"status": "answered"}),
        ("POST", "/requirements/nope/attachments", {"kind": "trend", "id": "t1"}),
        ("DELETE", "/requirements/nope/attachments/trend/t1", None),
    ]:
        response = _send(rig.client, method, path, body)
        assert response.status_code == 404, (method, path)
        assert response.json()["error"] == "requirement_not_found"


def test_the_twenty_first_requirement_is_a_409_naming_the_limit(rig: _Rig) -> None:
    for n in range(MAX_REQUIREMENTS):
        assert rig.client.post(f"{P}/requirements", json={"text": f"r{n}"}).status_code == 201
    response = rig.client.post(f"{P}/requirements", json={"text": "one too many"})
    assert response.status_code == 409
    assert response.json()["error"] == "too_many_requirements"
    assert "20" in response.json()["detail"]


def test_an_empty_or_over_long_text_is_a_422_with_the_sentence(rig: _Rig) -> None:
    empty = rig.client.post(f"{P}/requirements", json={"text": "  "})
    long = rig.client.put(f"{P}/priority", json={"text": "x" * 5000})
    assert empty.status_code == long.status_code == 422
    assert empty.json()["error"] == long.json()["error"] == "invalid_brief_text"
    assert "at most" in long.json()["detail"]
    assert rig.store.rows == {}


# --- a brief step is in the History but is not a state of the canvas -------------------------


def test_a_brief_step_cannot_be_restored_and_a_canvas_step_still_can(rig: _Rig) -> None:
    """Restoring a step replaces the canvas with the step's snapshot; a brief edit holds none, so
    restoring it would empty the canvas. The refusal is specific to the brief's label."""
    refused = rig.client.post("/v1/investigations/inv-1/history/brief-step")
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "step_not_restorable"
    assert rig.working.restored == []
    assert "restore_history_step" not in rig.audit.actions

    allowed = rig.client.post("/v1/investigations/inv-1/history/canvas-step")
    assert allowed.status_code == 200
    assert rig.working.restored == ["inv-1"]
