"""ADR-130 decision 1: a hotlist alert explains itself, read at display time (rule 3).

Hermetic: the graph and the hotlist store are doubles, and each double REFUSES what the real one
refuses (a node the reader cannot read is `None`; a hotlist another principal owns raises
`HotlistNotFoundError`), so these cases can fail for the reason they claim. The real store and graph
are exercised in `test_alert_view_explains_live.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from services.api.hotlists import HotlistNotFoundError
from services.api.watch_routes import alert_to_view

from schemas.domain import (
    Alert,
    AlertMode,
    AuditStub,
    Handling,
    Hotlist,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

WHEN = datetime(2026, 10, 1, tzinfo=UTC)
OWNER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
STRANGER = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1")


def _node(node_id: str, sources: list[tuple[str, str]], *, node_type: str = "Endpoint") -> Node:
    return Node(
        id=node_id,
        type=node_type,
        properties={"value_normalised": "+447700900640"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[
                SourceRef(document_id=d, locator=loc, excerpt_hash="a" * 64) for d, loc in sources
            ],
            first_seen=WHEN,
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=WHEN, created_by="test"),
    )


class _Graph:
    """Returns a node only to a principal in `readers`: a hidden node is `None`, as in the port."""

    def __init__(self, nodes: dict[str, Node], readers: set[str]) -> None:
        self._nodes, self._readers = nodes, readers

    async def get_node(self, node_id: str, principal: Principal) -> Node | None:
        return self._nodes.get(node_id) if principal.id in self._readers else None


class _Hotlists:
    """Refuses another principal's hotlist exactly as `HotlistStore.get_authorized` does."""

    def __init__(self, hotlist: Hotlist) -> None:
        self._hotlist = hotlist

    async def get_authorized(self, hotlist_id: str, principal: Principal) -> Hotlist:
        if hotlist_id != self._hotlist.id or principal.id != self._hotlist.owner_id:
            raise HotlistNotFoundError(hotlist_id)
        return self._hotlist


def _hotlist(*, typed: str | None = "07700 900640", canonical: bool | None = True) -> Hotlist:
    return Hotlist(
        id="hl-1",
        identifier="+447700900640",
        identifier_typed=typed,
        identifier_canonical=canonical,
        owner_id=OWNER.id,
        review_date=date(2027, 1, 31),
        created_at=WHEN,
    )


def _alert(node_ids: list[str], *, rule_id: str = "hotlist:hl-1") -> Alert:
    return Alert(
        id="alert-1",
        rule_id=rule_id,
        owner_id=OWNER.id,
        mode=AlertMode.FULL,
        referent_node_ids=node_ids,
        created_at=WHEN,
    )


async def _view(alert: Alert, principal: Principal, graph: Any, hotlists: Any = None) -> Any:
    return await alert_to_view(alert, principal, graph, hotlists_store=hotlists)


async def test_the_owner_sees_the_hotlist_as_typed_and_its_review_date() -> None:
    graph = _Graph({"n1": _node("n1", [("a/b/calls.csv", "row 3")])}, {OWNER.id})
    view = await _view(_alert(["n1"]), OWNER, graph, _Hotlists(_hotlist()))
    assert view.hotlist is not None
    assert view.hotlist.identifier == "07700 900640"
    assert view.hotlist.kept_as_written is False
    assert view.hotlist.review_date == date(2027, 1, 31)


async def test_the_stored_identifier_is_shown_when_untyped_and_kept_as_written_is_said() -> None:
    graph = _Graph({"n1": _node("n1", [("calls.csv", "row 3")])}, {OWNER.id})
    hotlists = _Hotlists(_hotlist(typed=None, canonical=False))
    view = await _view(_alert(["n1"]), OWNER, graph, hotlists)
    assert view.hotlist is not None
    assert view.hotlist.identifier == "+447700900640"
    assert view.hotlist.kept_as_written is True


async def test_a_reader_who_does_not_own_the_hotlist_gets_no_hotlist_at_all() -> None:
    graph = _Graph({"n1": _node("n1", [("calls.csv", "row 3")])}, {OWNER.id, STRANGER.id})
    view = await _view(_alert(["n1"]), STRANGER, graph, _Hotlists(_hotlist()))
    assert view.hotlist is None
    wire = view.model_dump_json()
    assert "07700" not in wire and '"hotlist":null' in wire


async def test_a_rule_that_is_not_a_hotlist_has_no_hotlist_and_the_store_is_not_asked() -> None:
    class _Boom:
        async def get_authorized(self, hotlist_id: str, principal: Principal) -> Hotlist:
            raise AssertionError("the store must not be read for a non-hotlist rule")

    graph = _Graph({"n1": _node("n1", [("calls.csv", "row 3")])}, {OWNER.id})
    view = await _view(_alert(["n1"], rule_id="monitor:m-1"), OWNER, graph, _Boom())
    assert view.hotlist is None


async def test_fired_on_names_the_type_the_label_and_the_files_with_their_rows() -> None:
    sources = [("in/pid_seized_comms_batch2.csv", "row 3")]
    sources += [("in/pid_pin_calls.csv", f"row {i}") for i in range(10, 12)]
    graph = _Graph({"n1": _node("n1", sources)}, {OWNER.id})
    view = await _view(_alert(["n1"]), OWNER, graph, _Hotlists(_hotlist()))
    (fired,) = view.fired_on
    assert fired.type == "Endpoint" and fired.label == "+447700900640"
    assert [(f.name, f.row, f.rows) for f in fired.files] == [
        ("pid_seized_comms_batch2.csv", 3, None),
        ("pid_pin_calls.csv", None, 2),
    ]
    assert fired.more_files == 0


async def test_the_same_row_cited_twice_is_one_row() -> None:
    graph = _Graph({"n1": _node("n1", [("x.csv", "row 7"), ("x.csv", "row 7")])}, {OWNER.id})
    view = await _view(_alert(["n1"]), OWNER, graph, None)
    (f,) = view.fired_on[0].files
    assert (f.name, f.row, f.rows) == ("x.csv", 7, None)


async def test_a_thousand_rows_in_one_file_are_counted_not_listed() -> None:
    sources = [("calls.csv", f"row {i}") for i in range(1, 2014)]
    graph = _Graph({"n1": _node("n1", sources)}, {OWNER.id})
    view = await _view(_alert(["n1"]), OWNER, graph, None)
    (f,) = view.fired_on[0].files
    assert (f.name, f.row, f.rows) == ("calls.csv", None, 2013)


async def test_more_than_five_files_are_five_in_first_seen_order_and_the_rest_are_counted() -> None:
    sources = [(f"d/file{i}.csv", "row 1") for i in (3, 1, 2, 7, 5, 6, 4)]
    sources.append(("d/file3.csv", "row 9"))  # a later row of a file already seen: not a new file
    graph = _Graph({"n1": _node("n1", sources)}, {OWNER.id})
    view = await _view(_alert(["n1"]), OWNER, graph, None)
    fired = view.fired_on[0]
    names = [f.name for f in fired.files]
    assert names == ["file3.csv", "file1.csv", "file2.csv", "file7.csv", "file5.csv"]
    assert fired.more_files == 2
    assert fired.files[0].rows == 2


async def test_a_matched_node_in_each_referent_gets_its_own_entry() -> None:
    nodes = {"n1": _node("n1", [("a.csv", "row 1")]), "n2": _node("n2", [("b.csv", "row 2")])}
    view = await _view(_alert(["n1", "n2"]), OWNER, _Graph(nodes, {OWNER.id}), None)
    assert [f.files[0].name for f in view.fired_on] == ["a.csv", "b.csv"]


async def test_a_hidden_node_gives_no_fired_on_no_name_and_no_count() -> None:
    nodes = {"n1": _node("n1", [("secret_file.csv", "row 3")])}
    graph = _Graph(nodes, readers=set())  # the reader can no longer read it
    view = await _view(_alert(["n1"]), OWNER, graph, _Hotlists(_hotlist()))
    assert view.evidence_available is False and view.referent_node_ids == []
    assert view.fired_on is None
    wire = view.model_dump_json()
    assert "secret_file" not in wire and "+447700900640" not in wire and "more_files" not in wire


async def test_one_hidden_referent_withdraws_every_referents_detail() -> None:
    nodes = {"n1": _node("n1", [("a.csv", "row 1")]), "n2": _node("n2", [("b.csv", "row 2")])}

    class _OneHidden(_Graph):
        async def get_node(self, node_id: str, principal: Principal) -> Node | None:
            return None if node_id == "n2" else await super().get_node(node_id, principal)

    view = await _view(_alert(["n1", "n2"]), OWNER, _OneHidden(nodes, {OWNER.id}), None)
    assert view.fired_on is None and "a.csv" not in view.model_dump_json()


async def test_a_notify_stub_alert_has_no_fired_on() -> None:
    alert = Alert(
        id="alert-2", rule_id="hotlist:hl-1", owner_id=OWNER.id, mode=AlertMode.NOTIFY_STUB,
        created_at=WHEN,
    )  # fmt: skip
    view = await _view(alert, OWNER, _Graph({}, {OWNER.id}), _Hotlists(_hotlist()))
    assert view.fired_on is None
