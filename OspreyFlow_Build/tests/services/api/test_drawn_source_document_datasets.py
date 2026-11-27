"""The dataset half of "may read" a drawn item's source document (ADR-143 Amendment 8 item 2; slice
GG4b, a security part; rules 3 and 4), through the real app over `board_fakes.BoardGraph`: the
case's datasets are changed in the dataset store, and each request's principal is scoped to the case
by the app itself (`scope_to_case`), as in a deployment.

**A** is Alice (SECRET), who draws an item and a link citing document **D**; **C** is Cleo
(SECRET), a Viewer of the case who did not draw. D sits in a dataset of its own. Both are cleared
for D throughout: only whether the case reads D's dataset changes, after drawing.

What fails if the rule is wrong (shown red with the fault planted,
`process/lanes/v062/GG4b_RED_RECORD.md`): A or C sent D once the case no longer reads D's dataset,
red with the document read asked with a copy of the reader's principal whose datasets are dropped
or widened.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.datasets import Dataset

from schemas.domain import AuditStub, Handling, Node, Principal, Provenance, SourceRef

from .test_boards import (  # noqa: F401 (`world` is a fixture)
    PEOPLE,
    UNIT,
    K,
    _as,
    _board,
    _item,
    _link,
    world,
)

D = "doc-in-the-statements"
STATEMENTS = "statements"
WHEN = datetime(2026, 11, 1, tzinfo=UTC)


def _document_in_a_dataset_of_its_own(world: SimpleNamespace) -> None:
    world.datasets.add(
        Dataset(
            id=STATEMENTS,
            name="Statements",
            owning_unit=UNIT,
            created_by="eng",
            created_at=WHEN,
            highest_marking="OFFICIAL-SENSITIVE",
        )
    )
    world.datasets.cases[K] = ["src", STATEMENTS]
    world.graph._graph_nodes[D] = Node(
        id=D,
        type="Document",
        properties={"title": "statement.txt"},
        provenance=Provenance(
            state="asserted",  # type: ignore[arg-type]
            sources=[SourceRef(document_id="files/s.txt", locator="whole", excerpt_hash="")],
            first_seen=WHEN,
        ),
        handling=Handling(
            classification="OFFICIAL-SENSITIVE",
            handling_code="P",
            originator=UNIT,
            owning_unit=UNIT,
        ),
        audit=AuditStub(created_at=WHEN, created_by="eng"),
        datasets=[STATEMENTS],
    )


def test_a_cleared_reader_whose_case_stops_reading_the_documents_dataset_is_not_sent_it(
    world: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        PEOPLE,
        "cleo",
        Principal(id="cleo", clearance="SECRET", org_unit=UNIT, roles=["analyst"]),
    )
    world.cases.grants[K]["cleo"] = world.cases.grants[K]["rita"]
    _document_in_a_dataset_of_its_own(world)
    board = _board(start="selection", node_ids=["p-loaded"])
    node_id = _item(board, source_document=D)["element_id"]
    linked = _link(board, node_id, "p-loaded", source_document=D)
    assert linked.status_code == 201, linked.text
    link_id = linked.json()["element_id"]
    shared = _as("alice").post(f"/v1/investigations/{K}/boards/{board}/share")
    assert shared.status_code == 200, shared.text

    def opened(who: str) -> tuple[str, dict[str, Any]]:
        answer = _as(who).get(f"/v1/investigations/{K}/boards/{board}")
        assert answer.status_code == 200, answer.text
        body = answer.json()
        drawn = {
            e["id"]: e["provenance"]
            for e in [*body["nodes"], *body["edges"]]
            if e["id"] in (node_id, link_id)
        }
        assert set(drawn) == {node_id, link_id}, "both drawn items are still sent"
        return answer.text, drawn

    for who in ("cleo", "alice"):
        _, drawn = opened(who)
        for provenance in drawn.values():
            assert provenance["drawn"]["source_document"] == D, who
            assert [s["document_id"] for s in provenance["sources"]] == [D], who

    world.datasets.cases[K] = ["src"]

    for who in ("cleo", "alice"):
        text, drawn = opened(who)
        assert D not in text, who
        for element_id, provenance in drawn.items():
            item_id = provenance["drawn"]["item_id"]
            assert provenance["drawn"].get("source_document") is None, (who, element_id)
            assert [s["document_id"] for s in provenance["sources"]] == [f"drawn:{item_id}"]
            assert provenance["sources_withheld"] is False, (who, element_id)
