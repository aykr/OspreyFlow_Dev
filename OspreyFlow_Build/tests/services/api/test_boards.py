"""Drawing boards through the real app (ADR-143 decisions 4 to 7; Amendments 2 and 3; L3.3): the
real `get_principal`, which scopes each reader to the case's read set (its source and its analyst
layer), the case's own level checks and rights, and a graph that holds what is written and refuses what the
adapter refuses (`board_fakes.BoardGraph`).

Case K (Alice its Author, Bob an Editor at OFFICIAL, Rita a Viewer) and case B (Carol its Author)
read the same source dataset, whose highest allowed marking is OFFICIAL-SENSITIVE.

What a mistake here would do, and the case that catches it (each shown red in
`process/lanes/case/L3.3_RED_RECORD.md`):

- a drawn item readable outside its case (rule 3):
  `test_a_drawn_item_is_never_readable_outside_its_case`, red with case K's layer in case B's read
  set (`test_the_outside_check_fails_with_case_ks_layer_in_case_bs_read_set`);
- a board route reachable by someone with no level on the case, a member of another case reading
  the same source included, or telling them the case exists (rule 4):
  `test_every_board_route_refuses_a_non_member_as_a_missing_case`;
- a drawn item written into the source, or without its author, board, case, grading and source
  (decision 4): `test_a_drawn_item_is_attributed_graded_and_in_the_layer`, red with the writer
  aiming at the source (`test_the_layer_check_fails_with_the_writer_aimed_at_the_source`);
- an item above the case's ceiling written (Amendment 2 decision 3):
  `test_an_item_above_the_ceiling_is_refused_in_words`, red with the ceiling check bypassed
  (`test_the_ceiling_check_fails_with_the_ceiling_bypassed`);
- a drawing with no case not making its dataset, case and board, or its items going to a layer
  (Amendment 2 decision 5; Amendment 3 decision 1):
  `test_a_drawing_with_no_case_makes_its_dataset_case_and_board`, red with the writer aiming at a
  layer (`test_the_drawn_dataset_check_fails_with_the_writer_aimed_at_a_layer`);
- no watch set, a watch outliving its item, or a watch shown to a reader who may not see its item
  (Amendment 2 decision 8): `test_drawing_sets_a_watch_and_withdrawing_ends_it` and
  `test_a_watch_on_an_item_the_reader_may_not_see_is_withheld_whole`, red with every watch listed
  (`test_the_withheld_check_fails_with_every_watch_listed`);
- matching merging two items in storage (rule 6): `test_same_writes_one_link_and_merges_nothing`,
  red with the writer merging (`test_the_merge_check_fails_with_the_writer_merging`);
- a picture of a drawn item written into the source, or shown to someone not cleared for it
  (ADR-105 Amendment 3): `test_a_pictures_document_and_link_are_in_the_layer_with_its_marking`;
- someone else's item edited or withdrawn, a marking lowered, a link left resting on a withdrawn
  node: `test_only_the_author_edits_or_withdraws_and_never_lowers_a_marking` and
  `test_withdrawing_a_node_takes_its_links_and_keeps_everything_in_the_store`;
- someone drawing on another's board, or without the right: `test_only_the_boards_creator_draws`
  and `test_drawing_needs_the_right_and_reading_needs_investigate`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from adapters.media_objectstore import reference_for
from adapters.media_objectstore.testing import InMemoryMediaStore
from fastapi.testclient import TestClient
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import SAME_AS, Node, NodeWrite, Principal
from services.api import boards as boards_module
from services.api.app import app
from services.api.board_store import InMemoryBoardItemStore
from services.api.boards import Boards
from services.api.case_views import InMemoryCaseViewStore
from services.api.dataset_scope import DrawnOnItsBoard, stamping
from services.api.datasets import COMPOSITE, DRAWN, Dataset, InMemoryDatasetStore
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)
from services.api.target_models import CORE_TYPES_FOR_TESTS, InMemoryTargetModelStore
from services.api.working_set.service import WorkingSetService

from .board_fakes import BoardGraph
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import node

UNIT = "unit-1"
SCHEME = load_uk_le_scheme()
ONTOLOGY = load_deployment_ontology()
PEOPLE = {
    "alice": Principal(
        id="alice", clearance="SECRET", org_unit=UNIT, roles=["analyst"]
    ),
    "bob": Principal(id="bob", clearance="OFFICIAL", org_unit=UNIT, roles=["analyst"]),
    "carol": Principal(
        id="carol", clearance="SECRET", org_unit=UNIT, roles=["analyst"]
    ),
    "rita": Principal(
        id="rita", clearance="SECRET", org_unit=UNIT, roles=["reports_viewer"]
    ),
    # A custom role holding `draw_on_boards` alone, without `investigate` (finding 6).
    "dora": Principal(
        id="dora", clearance="SECRET", org_unit=UNIT, roles=["right:draw_on_boards"]
    ),
}
K, B = "case-k", "case-b"
GRADE = {"source": "B", "intelligence": "2", "handling": "1"}


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return PEOPLE[token]


class _Cases:
    """Cases and their grants; a level is held only by a grant. `create` makes a home case."""

    def __init__(self) -> None:
        self.made: dict[str, Investigation] = {}
        self.grants: dict[str, dict[str, AccessLevel]] = {}

    def seed(self, case_id: str, grants: dict[str, AccessLevel]) -> None:
        self.made[case_id] = Investigation(
            id=case_id, name=case_id, created_at=datetime(2026, 11, 1, tzinfo=UTC),
            created_by="seed", owning_unit=UNIT,
        )  # fmt: skip
        self.grants[case_id] = dict(grants)

    async def create(
        self, principal: Principal, *, name: str, **_: Any
    ) -> Investigation:
        case_id = f"home-{len(self.made)}"
        self.seed(case_id, {principal.id: AccessLevel.AUTHOR})
        return self.made[case_id]

    async def get_authorized(
        self, case_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        held = self.grants.get(case_id, {}).get(principal.id)
        if held is None:
            raise InvestigationNotFoundError(case_id)
        if held.rank < need.rank:
            raise InsufficientAccessError(case_id)
        return self.made[case_id]

    async def list_for(
        self, principal: Principal
    ) -> list[tuple[Investigation, AccessLevel]]:
        return [
            (self.made[c], g[principal.id])
            for c, g in self.grants.items()
            if principal.id in g
        ]

    async def hidden_tab_ids(self, principal: Principal) -> set[str]:
        return set()


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def _loaded(node_id: str, marking: str = "OFFICIAL", **properties: Any) -> Node:
    return node(node_id, marking).model_copy(
        update={"properties": properties, "datasets": ["src"]}
    )


IMAGE_REF = reference_for(b"\x89PNG loaded", "image/png")


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    datasets = InMemoryDatasetStore()
    datasets.add(
        Dataset(id="src", name="Prison intel", owning_unit=UNIT, created_by="eng",
                created_at=datetime(2026, 11, 1, tzinfo=UTC),
                highest_marking="OFFICIAL-SENSITIVE")
    )  # fmt: skip
    datasets.cases[K] = ["src"]
    datasets.cases[B] = ["src"]
    cases = _Cases()
    cases.seed(K, {"alice": AccessLevel.AUTHOR, "bob": AccessLevel.EDITOR,
                   "rita": AccessLevel.VIEWER, "dora": AccessLevel.EDITOR})  # fmt: skip
    cases.seed(B, {"carol": AccessLevel.AUTHOR})
    image = _loaded("img-1").model_copy(
        update={"type": "Document",
                "properties": {"title": "photo.png", "media_kind": "image",
                               "object_ref": IMAGE_REF}}
    )  # fmt: skip
    graph = BoardGraph(
        ONTOLOGY,
        nodes=[
            _loaded("p-loaded", family_name="Mercer", nino="AB123456C"),
            _loaded("p-secret", "SECRET", family_name="Hidden"),
            image,
        ],
    )
    media = InMemoryMediaStore()
    media.files[IMAGE_REF] = b"\x89PNG loaded"
    held = SimpleNamespace(
        datasets=datasets, cases=cases, graph=graph, views=InMemoryCaseViewStore(),
        items=InMemoryBoardItemStore(), audit=_Audit(), media=media,
        models=InMemoryTargetModelStore(core_types=CORE_TYPES_FOR_TESTS),
    )  # fmt: skip
    state = {
        "principal_resolver": _Resolver(), "investigations": cases, "datasets": datasets,
        # The Conduit's own graph: the stamping wrapper (its last-word refusals, `withdraw_drawn`)
        # over the fake that holds what is written.
        "audit": held.audit, "graph": stamping(graph, registry=datasets),
        "case_views": held.views,
        "board_items": held.items, "media": media, "target_models": held.models,
        "handling_scheme": SCHEME, "ontology": ONTOLOGY,
        "working_set": WorkingSetService(graph, FakeWorkingSetStore(), SCHEME),
    }  # fmt: skip
    for key, value in state.items():
        monkeypatch.setattr(app.state, key, value, raising=False)
    yield held


def _as(who: str) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {who}"})


def _board(who: str = "alice", case: str = K, **body: Any) -> str:
    answer = _as(who).post(
        f"/v1/investigations/{case}/boards", json={"name": "Wing B", **body}
    )
    assert answer.status_code == 201, answer.text
    return str(answer.json()["id"])


def _item(board: str, who: str = "alice", case: str = K, **over: Any) -> dict[str, Any]:
    body = {
        "type": "Person",
        "label": "Unknown male “Tall”",
        "marking": "OFFICIAL",
        "grading": GRADE,
        "source_note": "Wing officer report, 4 Nov",
        "x": 0.2,
        "y": 0.3,
        "properties": {"family_name": "Tall"},
    }
    body.update(over)
    answer = _as(who).post(f"/v1/investigations/{case}/boards/{board}/items", json=body)
    assert answer.status_code == 201, answer.text
    return dict(answer.json())


def _link(board: str, source: str, target: str, **over: Any) -> Any:
    body = {
        "type": "ASSOCIATE_OF",
        "label": "seen together",
        "marking": "OFFICIAL",
        "grading": GRADE,
        "source_note": "Visits log",
        "source": source,
        "target": target,
    }
    body.update(over)
    return _as("alice").post(f"/v1/investigations/{K}/boards/{board}/links", json=body)


# --- rule 3: a drawn item is never readable outside its case ---------------------------------


def _drawn_in_k(world: SimpleNamespace) -> tuple[str, str, str]:
    """Alice draws a person on a board of K, from a selection holding the loaded Mercer, and links
    the two: the board, the drawn node and the link."""
    board = _board(start="selection", node_ids=["p-loaded"])
    drawn = _item(board)["element_id"]
    linked = _link(board, drawn, "p-loaded")
    assert linked.status_code == 201, linked.text
    return board, drawn, linked.json()["element_id"]


def _carol_sees_it_from_b(drawn: str) -> bool:
    """Carol, in case B (the same source), saves a view naming the drawn id and opens it."""
    saved = _as("carol").post(f"/v1/investigations/{B}/views",
                              json={"name": "probe", "node_ids": [drawn, "p-loaded"]})  # fmt: skip
    assert saved.status_code == 201, saved.text
    opened = _as("carol").get(f"/v1/investigations/{B}/views/{saved.json()['id']}")
    assert opened.status_code == 200, opened.text
    shown = {n["id"] for n in opened.json()["nodes"]}
    drawn_links = [e for e in opened.json()["edges"] if e["provenance"].get("drawn")]
    return drawn in shown or bool(drawn_links)


def test_a_drawn_item_is_never_readable_outside_its_case(
    world: SimpleNamespace,
) -> None:
    board, drawn, link = _drawn_in_k(world)
    assert not _carol_sees_it_from_b(drawn)
    # Nor its link from the loaded node it rests on: B's view of Mercer and the drawn id shows
    # no link, and B's own board routes do not find K's board.
    assert _as("carol").get(f"/v1/investigations/{B}/boards/{board}").status_code == 404
    assert _as("carol").get(f"/v1/investigations/{B}/boards").json() == []
    assert _as("carol").get(f"/v1/investigations/{B}/drawn-watches").json() == []
    # Alice, in K, sees both.
    opened = _as("alice").get(f"/v1/investigations/{K}/boards/{board}").json()
    assert drawn in opened["drawn"] and link in opened["drawn"]


def test_the_outside_check_fails_with_case_ks_layer_in_case_bs_read_set(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the plant is the read set's own call site, `DatasetStore.ids_of_case` (what
    `scope_to_case` reads), answering case B with K's layer in it."""
    _, drawn, _ = _drawn_in_k(world)
    real = InMemoryDatasetStore.ids_of_case

    async def leaking(self: InMemoryDatasetStore, investigation_id: str) -> list[str]:
        held = await real(self, investigation_id)
        layer = await self.layer_of_case(K)
        return [*held, layer] if investigation_id == B and layer else held

    monkeypatch.setattr(InMemoryDatasetStore, "ids_of_case", leaking)
    assert _carol_sees_it_from_b(drawn)


BOARD_ROUTES = [
    ("get", "boards", None),
    ("post", "boards", {"name": "x"}),
    ("get", "boards/{board}", None),
    ("post", "boards/{board}/share", None),
    ("delete", "boards/{board}", None),
    ("post", "boards/{board}/items", {"type": "Person", "label": "x", "marking": "OFFICIAL",
                                      "grading": GRADE, "source_note": "n"}),
    ("post", "boards/{board}/links", {"type": "ASSOCIATE_OF", "label": "x", "marking": "OFFICIAL",
                                      "grading": GRADE, "source_note": "n", "source": "a",
                                      "target": "b"}),
    ("put", "boards/{board}/layout", {"positions": {}}),
    ("patch", "board-items/{item}", {"label": "y"}),
    ("post", "board-items/{item}/withdraw", None),
    ("get", "boards/{board}/matches", None),
    ("post", "boards/{board}/matches", {"drawn": "a", "loaded": "b", "same": True}),
    ("post", "boards/{board}/nodes/{node}/picture", {"document_id": "img-1",
                                                     "marking": "OFFICIAL"}),
    ("put", "boards/{board}/nodes/{node}/picture",
     {"params": {"name": "x.png", "marking": "OFFICIAL", "source_note": "n"}, "content": b"png"}),
    ("get", "boards/{board}/pictures", None),
    ("get", "boards/{board}/nodes/{node}/picture", None),
    ("get", "drawn-watches", None),
]  # fmt: skip


@pytest.mark.parametrize(("method", "path", "body"), BOARD_ROUTES)
def test_every_board_route_refuses_a_non_member_as_a_missing_case(
    world: SimpleNamespace, method: str, path: str, body: Any
) -> None:
    """Carol is a member of B, which reads the same source; to K's routes she is a stranger, and
    each answers her exactly as for a case that does not exist (one refusal, ADR-099 decision 5)."""
    board, drawn, _ = _drawn_in_k(world)
    item = next(iter(world.items.items))
    filled = path.format(board=board, item=item, node=drawn)

    def ask(case: str) -> Any:
        kwargs: dict[str, Any] = {}
        if isinstance(body, dict) and "params" in body:
            kwargs = dict(body)  # an upload: its query and its bytes, as the Glass sends them
        elif body is not None:
            kwargs = {"json": body}
        return getattr(_as("carol"), method)(
            f"/v1/investigations/{case}/{filled}", **kwargs
        )

    stranger, missing = ask(K), ask("no-such-case")
    assert stranger.status_code == missing.status_code == 404, (
        stranger.text,
        missing.text,
    )
    assert stranger.json() == missing.json()


# --- decision 4: attributed, graded, sourced, in the layer ------------------------------------


def test_a_drawn_item_is_attributed_graded_and_in_the_layer(
    world: SimpleNamespace,
) -> None:
    board = _board()
    made = _item(board)
    drawn = world.graph.node(made["element_id"])
    layer = await_layer(world)
    assert drawn.datasets == [layer] and "src" not in drawn.datasets
    assertion = drawn.provenance.drawn
    assert assertion is not None
    assert assertion.provenance_class == "analyst_drawn"
    assert (assertion.asserted_by, assertion.board_id, assertion.case_id) == (
        "alice",
        board,
        K,
    )
    assert assertion.item_id == made["item_id"]
    assert (
        assertion.grading.source == "B"
        and assertion.source_note == "Wing officer report, 4 Nov"
    )
    assert drawn.handling.classification == "OFFICIAL"
    assert (
        drawn.provenance.state == "asserted"
    )  # asserted by its author, not inferred (rule 5)
    audit = [r for r in world.audit.records if r["action"] == "draw_item"]
    assert audit and audit[0]["resolved_query"]["item_id"] == made["item_id"]


def test_the_layer_check_fails_with_the_writer_aimed_at_the_source(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the plant is `Boards.into`, the one place a drawing's dataset is chosen."""
    real = Boards.into

    async def into_the_source(self: Boards, case_id: str) -> Any:
        held = await real(self, case_id)
        return boards_module.Into(
            "src", held.ceiling, held.watched, drawn_dataset=False
        )

    monkeypatch.setattr(Boards, "into", into_the_source)
    made = _item(_board())
    assert world.graph.node(made["element_id"]).datasets == ["src"]


# --- Amendment 2 decision 3: the ceiling ------------------------------------------------------


def _nothing_written(world: SimpleNamespace, before: int) -> None:
    assert len(world.graph.node_writes) + len(world.graph.edge_writes) == before
    assert not [i for i in world.items.items.values()]
    assert not world.items.watches
    # Not even the case's layer: the ceiling is judged before the layer could be made.
    assert not [
        d for d in world.datasets.datasets.values() if d.kind == "analyst_layer"
    ]


def test_an_item_above_the_ceiling_is_refused_in_words(world: SimpleNamespace) -> None:
    board = _board()
    before = len(world.graph.node_writes) + len(world.graph.edge_writes)
    answer = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/items",
        json={"type": "Person", "label": "x", "marking": "SECRET", "grading": GRADE,
              "source_note": "n", "properties": {"family_name": "x"}},
    )  # fmt: skip
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "above_the_ceiling"
    assert "OFFICIAL-SENSITIVE" in answer.json()["detail"]
    _nothing_written(world, before)


def test_an_item_above_the_drawers_clearance_is_refused_too(
    world: SimpleNamespace,
) -> None:
    board = _board("bob")
    answer = _as("bob").post(
        f"/v1/investigations/{K}/boards/{board}/items",
        json={"type": "Person", "label": "x", "marking": "OFFICIAL-SENSITIVE", "grading": GRADE,
              "source_note": "n", "properties": {"family_name": "x"}},
    )  # fmt: skip
    assert (
        answer.status_code == 409 and answer.json()["error"] == "above_your_clearance"
    )


def test_the_ceiling_check_fails_with_the_ceiling_bypassed(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the plant is `Boards.ceiling`, the case's ceiling as every drawing reads it, set to
    the deployment's highest."""

    async def no_ceiling(self: Boards, case_id: str) -> str:
        return "SECRET"

    board = _board()
    drawn = _item(board)
    monkeypatch.setattr(Boards, "ceiling", no_ceiling)
    answer = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/items",
        json={"type": "Person", "label": "x", "marking": "SECRET", "grading": GRADE,
              "source_note": "n", "properties": {"family_name": "x"}},
    )  # fmt: skip
    assert answer.status_code == 201
    # The edit, the upload and the choice read the same ceiling: each goes through with it gone.
    assert _edit_to_secret(drawn["item_id"]).status_code == 200
    assert _upload_secret(board, drawn["element_id"]).status_code == 201
    assert _choose_secret(board, drawn["element_id"]).status_code == 201


def _edit_to_secret(item: str) -> Any:
    return _as("alice").patch(f"/v1/investigations/{K}/board-items/{item}",
                              json={"marking": "SECRET"})  # fmt: skip


def _upload_secret(board: str, node_id: str) -> Any:
    return _as("alice").put(
        f"/v1/investigations/{K}/boards/{board}/nodes/{node_id}/picture",
        params={"name": "x.png", "marking": "SECRET", "source_note": "n"}, content=b"png",
    )  # fmt: skip


def _choose_secret(board: str, node_id: str) -> Any:
    return _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/nodes/{node_id}/picture",
        json={"document_id": "img-1", "marking": "SECRET"},
    )


def test_an_edit_an_upload_and_a_choice_above_the_ceiling_are_refused_in_words(
    world: SimpleNamespace,
) -> None:
    board = _board()
    drawn = _item(board)
    files = dict(world.media.files)
    for answer in (
        _edit_to_secret(drawn["item_id"]),
        _upload_secret(board, drawn["element_id"]),
        _choose_secret(board, drawn["element_id"]),
    ):
        assert answer.status_code == 409, answer.text
        assert answer.json()["error"] == "above_the_ceiling"
        assert "OFFICIAL-SENSITIVE" in answer.json()["detail"]
    assert world.graph.node(drawn["element_id"]).handling.classification == "OFFICIAL"
    assert world.media.files == files
    assert not [e for e in world.graph.edges() if e.type == "DEPICTS"]


# --- Amendment 2 decision 5, Amendment 3 decision 1: a drawing with no case --------------------


def _start_drawing() -> dict[str, Any]:
    answer = _as("alice").post(
        "/v1/drawings",
        json={"name": "Night visits", "highest_marking": "OFFICIAL-SENSITIVE"},
    )
    assert answer.status_code == 201, answer.text
    return dict(answer.json())


def test_a_drawing_with_no_case_makes_its_dataset_case_and_board(
    world: SimpleNamespace,
) -> None:
    made = _start_drawing()
    dataset = world.datasets.datasets[made["dataset_id"]]
    assert dataset.kind == DRAWN and dataset.name == "Night visits"
    home = made["investigation_id"]
    assert world.cases.grants[home] == {"alice": AccessLevel.AUTHOR}
    assert made["board"]["case_id"] == home
    item = _item(made["board"]["id"], case=home)
    drawn = world.graph.node(item["element_id"])
    # Written to the drawn dataset and to no layer: the home case's own layer (made with it, for
    # what is marked by hand) holds nothing drawn.
    assert drawn.datasets == [made["dataset_id"]]
    assert await_layer(world, home) not in drawn.datasets
    # Its ceiling is the drawn dataset's own.
    refused = _as("alice").post(
        f"/v1/investigations/{home}/boards/{made['board']['id']}/items",
        json={"type": "Person", "label": "x", "marking": "SECRET", "grading": GRADE,
              "source_note": "n", "properties": {"family_name": "x"}},
    )  # fmt: skip
    assert refused.status_code == 409 and refused.json()["error"] == "above_the_ceiling"


def test_the_drawn_dataset_check_fails_with_the_writer_aimed_at_a_layer(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def always_a_layer(self: Boards, case_id: str) -> Any:
        layer = (await boards_module.analyst_writes_into())[0]
        return boards_module.Into(layer, "SECRET", None, drawn_dataset=False)

    made = _start_drawing()
    monkeypatch.setattr(Boards, "into", always_a_layer)
    item = _item(made["board"]["id"], case=made["investigation_id"])
    assert world.graph.node(item["element_id"]).datasets != [made["dataset_id"]]


# --- Amendment 2 decision 8: watches ----------------------------------------------------------


def _watches(who: str) -> list[dict[str, Any]]:
    answer = _as(who).get(f"/v1/investigations/{K}/drawn-watches")
    assert answer.status_code == 200, answer.text
    return list(answer.json())


def test_drawing_sets_a_watch_and_withdrawing_ends_it(world: SimpleNamespace) -> None:
    board = _board()
    made = _item(board)
    (watch,) = _watches("alice")
    assert (watch["item_id"], watch["owner"], watch["kind"]) == (
        made["item_id"],
        "alice",
        "drawn_watch",
    )
    assert watch["dataset_id"] == "src"  # on the case's dataset
    withdrawn = _as("alice").post(
        f"/v1/investigations/{K}/board-items/{made['item_id']}/withdraw"
    )
    assert withdrawn.status_code == 200 and withdrawn.json()["watches_ended"] == 1
    assert _watches("alice") == []


def test_a_watch_on_an_item_the_reader_may_not_see_is_withheld_whole(
    world: SimpleNamespace,
) -> None:
    board = _board()
    _item(board, marking="OFFICIAL")
    sensitive = _item(board, marking="OFFICIAL-SENSITIVE")
    assert len(_watches("alice")) == 2
    bobs = _watches("bob")
    assert len(bobs) == 1 and sensitive["item_id"] not in str(bobs)


def test_the_withheld_check_fails_with_every_watch_listed(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def every_watch(self: Boards, case_id: str, principal: Principal) -> Any:
        return await self.items.active_watches(case_id)

    monkeypatch.setattr(Boards, "watches", every_watch)
    board = _board()
    _item(board, marking="OFFICIAL")
    _item(board, marking="OFFICIAL-SENSITIVE")
    assert len(_watches("bob")) == 2


# --- decision 6, rule 6: matching ---------------------------------------------------------------


def _drawn_mercer(world: SimpleNamespace) -> tuple[str, str]:
    board = _board(start="selection", node_ids=["p-loaded"])
    made = _item(board, label="Mercer", properties={"family_name": "Mercer"})
    return board, made["element_id"]


def test_same_writes_one_link_and_merges_nothing(world: SimpleNamespace) -> None:
    board, drawn = _drawn_mercer(world)
    before = world.graph.node("p-loaded")
    suggested = (
        _as("alice").get(f"/v1/investigations/{K}/boards/{board}/matches").json()
    )
    (pair,) = suggested["suggestions"]
    assert (pair["drawn"], pair["loaded"]["id"], pair["state"]) == (
        drawn,
        "p-loaded",
        "inferred",
    )
    # A suggestion acts on nothing by itself (rule 5).
    assert not [e for e in world.graph.edges() if e.type == SAME_AS]
    decided = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/matches",
        json={"drawn": drawn, "loaded": "p-loaded", "same": True},
    )
    assert decided.status_code == 201, decided.text
    (same,) = [e for e in world.graph.edges() if e.type == SAME_AS]
    assert (same.source, same.target, same.properties["score"]) == (
        drawn,
        "p-loaded",
        1.0,
    )
    assert same.datasets == [await_layer(world)]
    # Two nodes still, the loaded one exactly as it was.
    assert world.graph.node("p-loaded") == before
    assert world.graph.node(drawn).id == drawn
    # Decided: no longer suggested.
    again = _as("alice").get(f"/v1/investigations/{K}/boards/{board}/matches").json()
    assert again["suggestions"] == []


def await_layer(world: SimpleNamespace, case: str = K) -> str:
    (layer,) = [d.id for d in world.datasets.datasets.values() if d.kind == "analyst_layer"
                and d.layer_of == case]  # fmt: skip
    return layer


def test_the_merge_check_fails_with_the_writer_merging(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the plant is `match_writes`, the one place a decision's writes are made: it
    writes the drawn node under the loaded node's id, a merge in storage."""
    real = boards_module.match_writes

    def merging(drawn: Node, loaded: Node, **kwargs: Any) -> Any:
        _nodes, edges = real(drawn, loaded, **kwargs)
        merged = NodeWrite(
            id=loaded.id, type=drawn.type, properties=drawn.properties,
            provenance=drawn.provenance, handling=drawn.handling, created_by="alice",
            created_at=datetime.now(UTC), datasets=drawn.datasets,
        )  # fmt: skip
        return [merged], edges

    monkeypatch.setattr(boards_module, "match_writes", merging)
    board, drawn = _drawn_mercer(world)
    before = world.graph.node("p-loaded")
    _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/matches",
        json={"drawn": drawn, "loaded": "p-loaded", "same": True},
    )
    assert world.graph.node("p-loaded") != before


# --- decision 7: pictures ---------------------------------------------------------------------


def test_a_pictures_document_and_link_are_in_the_layer_with_its_marking(
    world: SimpleNamespace,
) -> None:
    board = _board()
    _as("alice").post(f"/v1/investigations/{K}/boards/{board}/share")
    drawn = _item(board)["element_id"]
    uploaded = _as("alice").put(
        f"/v1/investigations/{K}/boards/{board}/nodes/{drawn}/picture",
        params={
            "name": "tall.png",
            "marking": "OFFICIAL-SENSITIVE",
            "source_note": "Gate camera",
        },
        content=b"\x89PNG drawn",
    )
    assert uploaded.status_code == 201, uploaded.text
    layer = await_layer(world)
    (depicts,) = [e for e in world.graph.edges() if e.type == "DEPICTS"]
    document = world.graph.node(depicts.source)
    assert depicts.datasets == [layer] and document.datasets == [layer]
    assert depicts.handling.classification == "OFFICIAL-SENSITIVE"
    pictures = (
        _as("alice").get(f"/v1/investigations/{K}/boards/{board}/pictures").json()
    )
    assert pictures == {"pictures": {drawn: document.id}}
    file = _as("alice").get(
        f"/v1/investigations/{K}/boards/{board}/nodes/{drawn}/picture"
    )
    assert file.status_code == 200 and file.content == b"\x89PNG drawn"
    # Bob, at OFFICIAL, sees the drawn item and no picture.
    assert _as("bob").get(f"/v1/investigations/{K}/boards/{board}/pictures").json() == {
        "pictures": {}
    }
    hidden = _as("bob").get(
        f"/v1/investigations/{K}/boards/{board}/nodes/{drawn}/picture"
    )
    assert hidden.status_code == 404


def test_a_picture_the_case_holds_is_linked_in_the_layer_and_stays_in_its_dataset(
    world: SimpleNamespace,
) -> None:
    board = _board()
    drawn = _item(board)["element_id"]
    chosen = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/nodes/{drawn}/picture",
        json={"document_id": "img-1", "marking": "OFFICIAL"},
    )
    assert chosen.status_code == 201, chosen.text
    (depicts,) = [e for e in world.graph.edges() if e.type == "DEPICTS"]
    assert depicts.datasets == [await_layer(world)]
    assert world.graph.node("img-1").datasets == ["src"]


# --- decision 5: the author's own, withdrawal ---------------------------------------------------


def test_only_the_author_edits_or_withdraws_and_never_lowers_a_marking(
    world: SimpleNamespace,
) -> None:
    board = _board()
    made = _item(board, marking="OFFICIAL-SENSITIVE")
    _as("alice").post(f"/v1/investigations/{K}/boards/{board}/share")
    item = made["item_id"]
    # Bob is an Editor of K, at OFFICIAL: the item is not one he may see, so it is not found.
    assert _as("bob").patch(f"/v1/investigations/{K}/board-items/{item}",
                            json={"label": "y"}).status_code == 404  # fmt: skip
    mine = _item(_board("bob"), "bob")
    refused = _as("alice").post(
        f"/v1/investigations/{K}/board-items/{mine['item_id']}/withdraw"
    )
    assert refused.status_code == 403 and refused.json()["error"] == "not_your_item"
    lowered = _as("alice").patch(f"/v1/investigations/{K}/board-items/{item}",
                                 json={"marking": "OFFICIAL"})  # fmt: skip
    assert (
        lowered.status_code == 409
        and lowered.json()["error"] == "marking_never_lowered"
    )
    edited = _as("alice").patch(
        f"/v1/investigations/{K}/board-items/{item}",
        json={"label": "Tall man", "grading": {**GRADE, "source": "A"}},
    )
    assert edited.status_code == 200, edited.text
    drawn = world.graph.node(made["element_id"]).provenance.drawn
    assert (
        drawn is not None and drawn.label == "Tall man" and drawn.grading.source == "A"
    )


def test_withdrawing_a_node_takes_its_links_and_keeps_everything_in_the_store(
    world: SimpleNamespace,
) -> None:
    board, drawn, link = _drawn_in_k(world)
    (item,) = [i.item_id for i in world.items.items.values() if i.element_id == drawn]
    answer = _as("alice").post(f"/v1/investigations/{K}/board-items/{item}/withdraw")
    assert answer.status_code == 200, answer.text
    assert answer.json()["nodes"] == [drawn] and answer.json()["links"] == [link]
    opened = _as("alice").get(f"/v1/investigations/{K}/boards/{board}").json()
    assert drawn not in opened["drawn"] and link not in opened["drawn"]
    # Kept, reverted, never deleted; the loaded end untouched.
    assert world.graph.node(drawn).audit.reverted
    assert world.graph.node(drawn).audit.withdrawn_by_load == f"board-withdrawal:{item}"
    assert not world.graph.node("p-loaded").audit.reverted


def test_deleting_a_board_leaves_what_was_drawn(world: SimpleNamespace) -> None:
    board = _board()
    drawn = _item(board)["element_id"]
    assert (
        _as("alice").delete(f"/v1/investigations/{K}/boards/{board}").status_code == 204
    )
    assert not world.graph.node(drawn).audit.reverted
    assert len(_watches("alice")) == 1


# --- who draws ------------------------------------------------------------------------------


def test_only_the_boards_creator_draws(world: SimpleNamespace) -> None:
    board = _board()
    _as("alice").post(f"/v1/investigations/{K}/boards/{board}/share")
    opened = _as("bob").get(f"/v1/investigations/{K}/boards/{board}")
    assert opened.status_code == 200 and opened.json()["may_draw"] is False
    answer = _as("bob").post(
        f"/v1/investigations/{K}/boards/{board}/items",
        json={"type": "Person", "label": "x", "marking": "OFFICIAL", "grading": GRADE,
              "source_note": "n", "properties": {"family_name": "x"}},
    )  # fmt: skip
    assert (
        answer.status_code == 403 and answer.json()["error"] == "not_the_boards_creator"
    )


def test_a_private_board_is_invisible_to_another_member(world: SimpleNamespace) -> None:
    board = _board()
    assert _as("bob").get(f"/v1/investigations/{K}/boards").json() == []
    assert _as("bob").get(f"/v1/investigations/{K}/boards/{board}").status_code == 404
    # And a board is not a view: the views list does not show it.
    assert _as("alice").get(f"/v1/investigations/{K}/views").json() == []


def test_drawing_needs_the_right_and_reading_needs_investigate(
    world: SimpleNamespace,
) -> None:
    board = _board()
    _as("alice").post(f"/v1/investigations/{K}/boards/{board}/share")
    answer = _as("rita").post(f"/v1/investigations/{K}/boards", json={"name": "x"})
    assert answer.status_code == 403
    assert _as("rita").get(f"/v1/investigations/{K}/boards").status_code == 403


def test_a_type_outside_the_model_and_a_link_off_the_board_are_refused(
    world: SimpleNamespace,
) -> None:
    board = _board()
    answer = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/items",
        json={"type": "Alert", "label": "x", "marking": "OFFICIAL", "grading": GRADE,
              "source_note": "n", "properties": {"family_name": "x"}},
    )  # fmt: skip
    assert answer.status_code == 422 and answer.json()["error"] == "not_in_the_model"
    drawn = _item(board)["element_id"]
    off = _link(board, drawn, "p-loaded")  # Mercer is not on this blank board
    assert off.status_code == 422 and off.json()["error"] == "ends_not_on_the_board"


def test_moving_keeps_the_boards_layout_for_items_on_it(world: SimpleNamespace) -> None:
    board = _board(start="selection", node_ids=["p-loaded", "p-secret"])
    drawn = _item(board)["element_id"]
    moved = _as("alice").put(
        f"/v1/investigations/{K}/boards/{board}/layout",
        json={"positions": {drawn: {"x": 0.7, "y": 0.1}, "p-loaded": {"x": 0.5, "y": 0.5},
                            "not-on-it": {"x": 0, "y": 0}}},
    )  # fmt: skip
    assert moved.status_code == 204, moved.text
    layout = _as("alice").get(f"/v1/investigations/{K}/boards/{board}").json()["layout"]
    assert layout[drawn] == {"x": 0.7, "y": 0.1} and "not-on-it" not in layout


# --- the lane review's round 1 ------------------------------------------------------------------


def _drawn_link(world: SimpleNamespace) -> tuple[str, str, str]:
    board = _board(start="selection", node_ids=["p-loaded"])
    drawn = _item(board)["element_id"]
    made = _link(board, drawn, "p-loaded").json()
    return board, made["item_id"], made["element_id"]


def test_a_drawn_links_marking_is_kept_and_no_second_link_is_left(
    world: SimpleNamespace,
) -> None:
    """Review finding 3: a link written again at another marking is another audience, so the store
    would make a second link and leave the first live. The edit is refused in words; a label or
    grading edit lands on the same link."""
    _, item, link = _drawn_link(world)
    raised = _as("alice").patch(f"/v1/investigations/{K}/board-items/{item}",
                                json={"marking": "OFFICIAL-SENSITIVE"})  # fmt: skip
    assert raised.status_code == 409 and raised.json()["error"] == "link_marking_kept"
    relabelled = _as("alice").patch(f"/v1/investigations/{K}/board-items/{item}",
                                    json={"label": "seen at the gate"})  # fmt: skip
    assert relabelled.status_code == 200, relabelled.text
    live = [
        e
        for e in world.graph.edges()
        if e.type == "ASSOCIATE_OF" and not e.audit.reverted
    ]
    assert [e.id for e in live] == [link]
    assert live[0].provenance.drawn is not None
    assert live[0].provenance.drawn.label == "seen at the gate"


def test_the_fake_makes_a_second_link_for_another_audience_as_the_store_does(
    world: SimpleNamespace,
) -> None:
    """Rule 15: the stand-in refuses what ArcadeDB refuses. A write of a taken link id at a new
    marking is a second link under a new id, the first left live: what the refusal above prevents."""
    _, _, link = _drawn_link(world)
    (held,) = [e for e in world.graph.edges() if e.id == link]
    import asyncio

    from schemas.domain import EdgeWrite
    from services.api.dataset_scope import case_datasets  # noqa: F401 (a request is not needed)

    async def rewrite() -> list[str]:
        tx = await world.graph.begin_transaction()
        ids = await world.graph.upsert_edges(
            [EdgeWrite(id=held.id, type=held.type, source=held.source, target=held.target,
                       provenance=held.provenance,
                       handling=held.handling.model_copy(update={"classification": "OFFICIAL-SENSITIVE"}),
                       created_by="alice", created_at=datetime.now(UTC), datasets=held.datasets)],
            tx,
        )  # fmt: skip
        await world.graph.commit_transaction(tx)
        return ids

    (written,) = asyncio.run(rewrite())
    assert written != link
    assert {e.id for e in world.graph.edges() if e.type == "ASSOCIATE_OF"} == {
        link,
        written,
    }


def test_an_edit_with_no_marking_of_the_scheme_or_no_source_is_refused_in_words(
    world: SimpleNamespace,
) -> None:
    board = _board()
    item = _item(board)["item_id"]
    for body, code in (
        ({"marking": "TOP-SECRET"}, "not_a_marking"),
        ({"source_note": ""}, "no_source"),
    ):
        answer = _as("alice").patch(
            f"/v1/investigations/{K}/board-items/{item}", json=body
        )
        assert answer.status_code == 422 and answer.json()["error"] == code, answer.text


def test_a_match_above_the_ceiling_is_refused(world: SimpleNamespace) -> None:
    """Review finding 5: a decision's link is marked as both ends together, within the ceiling."""
    board = _board(start="selection", node_ids=["p-secret"])
    drawn = _item(board)["element_id"]
    answer = _as("alice").post(f"/v1/investigations/{K}/boards/{board}/matches",
                               json={"drawn": drawn, "loaded": "p-secret", "same": True})  # fmt: skip
    assert answer.status_code == 409 and answer.json()["error"] == "above_the_ceiling"
    assert not [e for e in world.graph.edges() if e.type == SAME_AS]


def test_a_decision_reaches_only_this_boards_drawn_items(
    world: SimpleNamespace,
) -> None:
    mine = _board(start="selection", node_ids=["p-loaded"])
    other = _board()
    drawn_elsewhere = _item(
        other, label="Mercer", properties={"family_name": "Mercer"}
    )["element_id"]
    answer = _as("alice").post(f"/v1/investigations/{K}/boards/{mine}/matches",
                               json={"drawn": drawn_elsewhere, "loaded": "p-loaded", "same": True})  # fmt: skip
    assert answer.status_code == 404


def test_a_picture_for_a_type_with_none_is_refused_before_the_file_is_kept(
    world: SimpleNamespace,
) -> None:
    board = _board()
    event = _item(board, type="Event", properties={})["element_id"]
    before = dict(world.media.files)
    answer = _as("alice").put(
        f"/v1/investigations/{K}/boards/{board}/nodes/{event}/picture",
        params={"name": "x.png", "marking": "OFFICIAL", "source_note": "n"}, content=b"png",
    )  # fmt: skip
    assert (
        answer.status_code == 422
        and answer.json()["error"] == "no_picture_for_this_type"
    )
    assert world.media.files == before
    assert not [r for r in world.audit.records if r["action"] == "set_drawn_picture"]


def test_a_second_picture_supersedes_the_first_and_both_are_audited_first(
    world: SimpleNamespace,
) -> None:
    board = _board()
    drawn = _item(board)["element_id"]
    for data in (b"first", b"second"):
        answer = _as("alice").put(
            f"/v1/investigations/{K}/boards/{board}/nodes/{drawn}/picture",
            params={"name": "tall.png", "marking": "OFFICIAL", "source_note": "Gate camera"},
            content=data,
        )  # fmt: skip
        assert answer.status_code == 201, answer.text
    live = [
        e
        for e in world.graph.edges()
        if e.type == "DEPICTS" and e.audit.superseded_by is None
    ]
    assert len(live) == 1
    file = _as("alice").get(
        f"/v1/investigations/{K}/boards/{board}/nodes/{drawn}/picture"
    )
    assert file.content == b"second"
    document = world.graph.node(live[0].source)
    assert document.provenance.sources[0].locator == "Gate camera"
    assert (
        len([r for r in world.audit.records if r["action"] == "set_drawn_picture"]) == 2
    )


def test_a_drawn_nodes_picture_is_refused_on_the_canvas_route(
    world: SimpleNamespace,
) -> None:
    """Review finding 2: ADR-105's own path would stamp the Document and its link into the source;
    for a drawn node it refuses, before any file is kept."""
    import asyncio

    from schemas.domain import Handling
    from services.api.entity_pictures import EntityPictureService

    drawn_id = _item(_board())["element_id"]
    drawn = world.graph.node(drawn_id)
    service = EntityPictureService(
        app.state.working_set, app.state.graph, world.media, ONTOLOGY, scheme=SCHEME
    )

    async def entity() -> Node:
        return drawn

    before = dict(world.media.files)
    with pytest.raises(DrawnOnItsBoard):
        asyncio.run(
            service._attach(
                K,
                entity,
                PEOPLE["alice"],
                name="tall.png",
                data=b"png",
                handling=Handling(
                    classification="OFFICIAL",
                    handling_code="P",
                    originator=UNIT,
                    owning_unit=UNIT,
                ),
                legal_basis=None,
            )  # fmt: skip
        )
    assert world.media.files == before
    assert not [e for e in world.graph.edges() if e.type == "DEPICTS"]


def test_a_drawn_link_is_not_changed_from_the_canvas(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding 8 (C15): ADR-113's link change refuses a drawn link, so only its author
    changes it, on its board."""
    import asyncio

    from services.api.link_changes import LinkChangeRequest, LinkChangeService

    _, _, link = _drawn_link(world)
    (edge,) = [e for e in world.graph.edges() if e.id == link]

    async def in_full(self: object, *args: object, **kwargs: object) -> object:
        return edge

    monkeypatch.setattr(LinkChangeService, "_in_full", in_full)
    for store in (
        "judgements_store",
        "alerts_store",
    ):  # the retract route's own, unused here
        monkeypatch.setattr(app.state, store, object(), raising=False)
    service = LinkChangeService.__new__(LinkChangeService)
    with pytest.raises(DrawnOnItsBoard):
        asyncio.run(
            service.change(K, link, PEOPLE["alice"], LinkChangeRequest(reason="wrong"))
        )
    retracted = _as("alice").post(f"/v1/investigations/{K}/nodes/{edge.source}/retract")
    assert (
        retracted.status_code == 409
        and retracted.json()["error"] == "drawn_on_its_board"
    )


def test_withdrawing_with_a_promoted_link_resting_on_it_is_refused(
    world: SimpleNamespace,
) -> None:
    board, item_link, link = _drawn_link(world)
    (node_item,) = [i.item_id for i in world.items.items.values() if i.kind == "node"]
    # As L3.4's promotion would leave it: the link's datasets gain the source.
    world.graph._graph_edges = [
        e.model_copy(update={"datasets": [*e.datasets, "src"]}) if e.id == link else e
        for e in world.graph._graph_edges
    ]
    answer = _as("alice").post(
        f"/v1/investigations/{K}/board-items/{node_item}/withdraw"
    )
    assert answer.status_code == 409 and answer.json()["error"] == "promoted"
    assert not [e for e in world.graph.edges() if e.audit.reverted]


def test_a_drawing_is_withdrawn_in_a_case_reading_a_composite(
    world: SimpleNamespace,
) -> None:
    """Review finding 4: a withdrawal is a write into the layer, which a case reading a composite
    may make (ADR-099 Amendment 15 item 2): through the graph's own `withdraw_drawn`, not a load's
    withdrawal, which a composite case refuses."""
    world.datasets.add(
        Dataset(id="comp", name="Both", owning_unit=UNIT, created_by="eng", kind=COMPOSITE,
                members=["src"], created_at=datetime(2026, 11, 1, tzinfo=UTC))
    )  # fmt: skip
    world.datasets.cases[K] = ["comp"]
    board = _board()
    made = _item(board)
    answer = _as("alice").post(
        f"/v1/investigations/{K}/board-items/{made['item_id']}/withdraw"
    )
    assert answer.status_code == 200, answer.text
    assert world.graph.node(made["element_id"]).audit.reverted


# --- review round 2 -----------------------------------------------------------------------------


def _edge(world: SimpleNamespace, edge_id: str) -> Any:
    (held,) = [e for e in world.graph.edges() if e.id == edge_id]
    return held


def _bobs_node_with_alices_hidden_link(world: SimpleNamespace) -> tuple[str, str, str]:
    """Bob (OFFICIAL) draws a person on his own board; Alice puts it on hers by a selection and
    links her own item to it at OFFICIAL-SENSITIVE, a link Bob may not see. Bob's item, his node,
    Alice's link."""
    bobs_board = _board("bob")
    bobs = _item(bobs_board, "bob")
    alices_board = _board(start="selection", node_ids=[bobs["element_id"]])
    mine = _item(alices_board)["element_id"]
    hidden = _link(alices_board, mine, bobs["element_id"], marking="OFFICIAL-SENSITIVE")
    assert hidden.status_code == 201, hidden.text
    return bobs["item_id"], bobs["element_id"], hidden.json()["element_id"]


def test_a_withdrawal_tells_nothing_of_a_link_the_withdrawer_may_not_see(
    world: SimpleNamespace,
) -> None:
    """Rule 3: Alice's hidden link goes with Bob's node, and is in the audit, but Bob's answer
    neither names it nor counts it, not even among the watches ended."""
    item, node_id, hidden = _bobs_node_with_alices_hidden_link(world)
    answer = _as("bob").post(f"/v1/investigations/{K}/board-items/{item}/withdraw")
    assert answer.status_code == 200, answer.text
    assert answer.json() == {"nodes": [node_id], "links": [], "pictures": [], "watches_ended": 1}
    assert hidden not in answer.text
    assert _edge(world, hidden).audit.reverted
    (row,) = [r for r in world.audit.records if r["action"] == "withdraw_drawn_item"]
    assert row["resolved_query"]["links"] == [hidden]


def test_a_withdrawal_names_its_picture_apart_from_its_links(world: SimpleNamespace) -> None:
    board = _board()
    made = _item(board)
    picture = _as("alice").put(
        f"/v1/investigations/{K}/boards/{board}/nodes/{made['element_id']}/picture",
        params={"name": "tall.png", "marking": "OFFICIAL", "source_note": "Gate camera"},
        content=b"png",
    )  # fmt: skip
    assert picture.status_code == 201, picture.text
    answer = _as("alice").post(f"/v1/investigations/{K}/board-items/{made['item_id']}/withdraw")
    assert answer.json()["links"] == []
    assert answer.json()["pictures"] == [picture.json()["element_id"]]
    assert _edge(world, picture.json()["element_id"]).audit.reverted
    shown = _as("alice").get(f"/v1/investigations/{K}/boards/{board}/pictures").json()
    assert shown == {"pictures": {}}


def test_every_picture_and_withdrawal_is_audited_before_anything_is_written(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-127 Amendment 27's order on each path: the audit row is there when the graph is first
    written (a row without a write records an attempt; never the reverse)."""
    seen: list[tuple[str, int]] = []
    real_depict = Boards._depict

    async def depict(self: Boards, *args: Any, **kwargs: Any) -> Any:
        seen.append(("depict", len(world.audit.records)))
        return await real_depict(self, *args, **kwargs)

    monkeypatch.setattr(Boards, "_depict", depict)
    board = _board()
    made = _item(board)
    before = len(world.audit.records)
    up = _as("alice").put(
        f"/v1/investigations/{K}/boards/{board}/nodes/{made['element_id']}/picture",
        params={"name": "tall.png", "marking": "OFFICIAL", "source_note": "Gate camera"},
        content=b"png",
    )  # fmt: skip
    assert up.status_code == 201, up.text
    chosen = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/nodes/{made['element_id']}/picture",
        json={"document_id": "img-1", "marking": "OFFICIAL"},
    )
    assert chosen.status_code == 201, chosen.text
    assert seen == [("depict", before + 1), ("depict", before + 2)]
    choice = world.audit.records[before + 1]
    assert choice["action"] == "choose_drawn_picture"
    assert choice["resolved_query"]["classification"] == "OFFICIAL"
    real_withdraw = type(world.graph).withdraw_elements
    at_withdrawal: list[int] = []

    async def withdraw_elements(self: Any, *args: Any, **kwargs: Any) -> Any:
        at_withdrawal.append(len(world.audit.records))
        return await real_withdraw(self, *args, **kwargs)

    monkeypatch.setattr(type(world.graph), "withdraw_elements", withdraw_elements)
    _as("alice").post(f"/v1/investigations/{K}/board-items/{made['item_id']}/withdraw")
    assert at_withdrawal == [before + 3]


def _canvas_pictures(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, *ids: str) -> None:
    """ADR-105's own routes, wired as the Conduit wires them, with `ids` in K's working set."""
    from services.api.app import get_valkey
    from services.api.entity_pictures import EntityPictureService

    store = app.state.working_set._store
    for element in ids:
        store._n(K)[element] = world.graph.node(element)
    monkeypatch.setattr(app.state, "entity_pictures", EntityPictureService(
        app.state.working_set, app.state.graph, world.media, ONTOLOGY, scheme=SCHEME,
    ), raising=False)  # fmt: skip

    class _Valkey:
        async def publish(self, *args: Any, **kwargs: Any) -> int:
            return 0

    app.dependency_overrides[get_valkey] = lambda: _Valkey()


def test_a_drawn_nodes_picture_is_neither_set_nor_removed_through_adr_105s_routes(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 03: on the canvas a drawn node's picture is refused, 409 `drawn_on_its_board`, on the
    real `PUT` and `DELETE …/nodes/{node}/picture`; nothing is kept or superseded."""
    from services.api.app import get_valkey

    board = _board()
    drawn = _item(board)["element_id"]
    given = _as("alice").put(
        f"/v1/investigations/{K}/boards/{board}/nodes/{drawn}/picture",
        params={"name": "tall.png", "marking": "OFFICIAL", "source_note": "Gate camera"},
        content=b"png",
    )  # fmt: skip
    assert given.status_code == 201
    _canvas_pictures(world, monkeypatch, drawn)
    try:
        files = dict(world.media.files)
        put = _as("alice").put(
            f"/v1/investigations/{K}/nodes/{drawn}/picture",
            params={"name": "x.png", "classification": "OFFICIAL", "legal_basis": "n"},
            content=b"png",
        )  # fmt: skip
        removed = _as("alice").delete(f"/v1/investigations/{K}/nodes/{drawn}/picture")
    finally:
        app.dependency_overrides.pop(get_valkey, None)
    for answer in (put, removed):
        assert answer.status_code == 409, answer.text
        assert answer.json()["error"] == "drawn_on_its_board"
    assert world.media.files == files
    live = [e for e in world.graph.edges() if e.type == "DEPICTS" and e.audit.superseded_by is None]
    assert [e.id for e in live] == [given.json()["element_id"]]


def test_a_reader_below_an_items_marking_sees_nothing_of_it_on_the_board(
    world: SimpleNamespace,
) -> None:
    """Rule 3 within the case: Bob (OFFICIAL) opens Alice's shared board and lists the boards; the
    OFFICIAL-SENSITIVE item and its suggestion are in none of it, not even counted as missing (the
    orchestrator's ruling: `missing` is what was lost, never what was never allowed)."""
    board = _board(start="selection", node_ids=["p-loaded"])
    _item(board)
    hidden = _item(board, label="Mercer", marking="OFFICIAL-SENSITIVE",
                   properties={"family_name": "Mercer"})["element_id"]  # fmt: skip
    assert _as("alice").post(f"/v1/investigations/{K}/boards/{board}/share").status_code == 200
    alices = _as("alice").get(f"/v1/investigations/{K}/boards/{board}/matches").json()
    assert hidden in str(alices)  # the suggestion is there for one who may see it
    opened = _as("bob").get(f"/v1/investigations/{K}/boards/{board}")
    assert opened.status_code == 200 and hidden not in opened.text
    assert opened.json()["missing"] == 0
    (listed,) = _as("bob").get(f"/v1/investigations/{K}/boards").json()
    assert listed["drawn"] == 1
    matches = _as("bob").get(f"/v1/investigations/{K}/boards/{board}/matches")
    assert hidden not in matches.text and matches.json()["suggestions"] == []


def test_a_board_from_a_view_keeps_only_what_its_maker_may_see_of_a_view_they_may_open(
    world: SimpleNamespace,
) -> None:
    saved = _as("alice").post(f"/v1/investigations/{K}/views",
                              json={"name": "both", "node_ids": ["p-loaded", "p-secret"]})  # fmt: skip
    assert saved.status_code == 201, saved.text
    view = saved.json()["id"]
    # Alice's private view is not Bob's to start from: answered as no view at all.
    refused = _as("bob").post(f"/v1/investigations/{K}/boards",
                              json={"name": "x", "start": "view", "view_id": view})  # fmt: skip
    missing = _as("bob").post(f"/v1/investigations/{K}/boards",
                              json={"name": "x", "start": "view", "view_id": "no-such-view"})  # fmt: skip
    assert refused.status_code == missing.status_code == 404
    assert refused.json() == missing.json()
    assert _as("alice").post(f"/v1/investigations/{K}/views/{view}/share").status_code == 200
    board = _board("bob", start="view", view_id=view)
    opened = _as("bob").get(f"/v1/investigations/{K}/boards/{board}").json()
    assert [n["id"] for n in opened["nodes"]] == ["p-loaded"]
    assert "p-secret" not in str(opened)
    held = next(v for v in world.views.views.values() if v.id == board)
    assert held.node_ids == ["p-loaded"]


def test_a_picture_is_given_only_to_a_node_on_the_board_it_is_given_through(
    world: SimpleNamespace,
) -> None:
    """A node drawn on board X is no subject of board Y's picture routes, unless Y holds it."""
    drawn = _item(_board())["element_id"]
    elsewhere = _board()
    for answer in (
        _as("alice").post(
            f"/v1/investigations/{K}/boards/{elsewhere}/nodes/{drawn}/picture",
            json={"document_id": "img-1", "marking": "OFFICIAL"},
        ),
        _as("alice").put(
            f"/v1/investigations/{K}/boards/{elsewhere}/nodes/{drawn}/picture",
            params={"name": "x.png", "marking": "OFFICIAL", "source_note": "n"}, content=b"png",
        ),  # fmt: skip
    ):
        assert answer.status_code == 404, answer.text
    assert not [e for e in world.graph.edges() if e.type == "DEPICTS"]
    holding = _board(start="selection", node_ids=[drawn])
    held = _as("alice").post(
        f"/v1/investigations/{K}/boards/{holding}/nodes/{drawn}/picture",
        json={"document_id": "img-1", "marking": "OFFICIAL"},
    )
    assert held.status_code == 201, held.text


# --- the orchestrator's independent review ------------------------------------------------------


def test_missing_counts_what_was_lost_and_never_what_was_never_allowed(
    world: SimpleNamespace,
) -> None:
    """Rule 3, the orchestrator's ruling: Bob opens Alice's shared board, which holds an item and a
    link he may not see; `missing` is 0. Alice's own board, whose reference was withdrawn since
    she placed it, says 1."""
    board = _board(start="selection", node_ids=["p-loaded"])
    mine = _item(board)["element_id"]
    hidden = _item(board, label="Hidden", marking="OFFICIAL-SENSITIVE",
                   properties={"family_name": "Hidden"})["element_id"]  # fmt: skip
    assert _link(board, mine, "p-loaded", marking="OFFICIAL-SENSITIVE").status_code == 201
    assert _as("alice").post(f"/v1/investigations/{K}/boards/{board}/share").status_code == 200
    assert _as("bob").get(f"/v1/investigations/{K}/boards/{board}").json()["missing"] == 0
    placed = _board(start="selection", node_ids=[mine, hidden])
    (item,) = [i.item_id for i in world.items.items.values() if i.element_id == mine]
    assert _as("alice").post(f"/v1/investigations/{K}/board-items/{item}/withdraw").status_code == 200
    assert _as("alice").get(f"/v1/investigations/{K}/boards/{placed}").json()["missing"] == 1


def test_the_ceiling_of_a_case_reading_a_composite_is_its_members(
    world: SimpleNamespace,
) -> None:
    """Finding 2: a composite sets no highest marking of its own; its members' strictest is the
    case's ceiling, never the deployment's highest."""
    world.datasets.add(
        Dataset(id="comp", name="Both", owning_unit=UNIT, created_by="eng", kind=COMPOSITE,
                members=["src"], created_at=datetime(2026, 11, 1, tzinfo=UTC))
    )  # fmt: skip
    world.datasets.cases[K] = ["comp"]
    board = _board()
    answer = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/items",
        json={"type": "Person", "label": "x", "marking": "SECRET", "grading": GRADE,
              "source_note": "n", "properties": {"family_name": "x"}},
    )  # fmt: skip
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "above_the_ceiling"
    assert "OFFICIAL-SENSITIVE" in answer.json()["detail"]


def test_a_match_goes_with_its_withdrawn_drawn_node(world: SimpleNamespace) -> None:
    """Finding 3: *Same* is registered on the board, so withdrawing the drawn node withdraws it."""
    board = _board(start="selection", node_ids=["p-loaded"])
    made = _item(board, label="Mercer", properties={"family_name": "Mercer"})
    decided = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/matches",
        json={"drawn": made["element_id"], "loaded": "p-loaded", "same": True},
    )
    assert decided.status_code == 201, decided.text
    edge = decided.json()["edge_id"]
    answer = _as("alice").post(f"/v1/investigations/{K}/board-items/{made['item_id']}/withdraw")
    assert edge in answer.json()["links"]
    assert _edge(world, edge).audit.reverted
    assert not world.graph.node("p-loaded").audit.reverted


def test_an_unseen_promoted_link_stays_and_tells_the_withdrawer_nothing(
    world: SimpleNamespace,
) -> None:
    """The orchestrator's ruling (a), for L3.4: Alice's link to Bob's node, promoted and hidden
    from Bob, stays when Bob withdraws his node; his answer is the one he gets with no such link."""
    from dataclasses import replace

    item, node_id, hidden = _bobs_node_with_alices_hidden_link(world)
    (link_item,) = [i for i in world.items.items.values() if i.element_id == hidden]
    world.items.items[link_item.item_id] = replace(link_item, promoted_at=datetime.now(UTC))
    answer = _as("bob").post(f"/v1/investigations/{K}/board-items/{item}/withdraw")
    assert answer.status_code == 200, answer.text
    assert answer.json() == {"nodes": [node_id], "links": [], "pictures": [], "watches_ended": 1}
    assert not _edge(world, hidden).audit.reverted
    assert world.items.items[link_item.item_id].withdrawn_at is None


def test_drawing_needs_investigate_too(world: SimpleNamespace) -> None:
    """Finding 6: a role with `draw_on_boards` alone would make a board it could not open."""
    answer = _as("dora").post(f"/v1/investigations/{K}/boards", json={"name": "x"})
    assert answer.status_code == 403, answer.text
    assert not world.views.views


def test_a_boards_start_and_its_items_boards_are_as_the_reader_may_know_them(
    world: SimpleNamespace,
) -> None:
    """Finding 7: a board started from what Bob may not see reads as blank to him; and the id of
    Alice's private board is in nothing Bob reads of the item she drew on it."""
    secret = _board(start="selection", node_ids=["p-secret"])
    assert _as("alice").post(f"/v1/investigations/{K}/boards/{secret}/share").status_code == 200
    (listed,) = [b for b in _as("bob").get(f"/v1/investigations/{K}/boards").json()
                 if b["id"] == secret]  # fmt: skip
    assert listed["start"] == "blank"
    private = _board()
    drawn = _item(private)["element_id"]
    bobs = _board("bob", start="selection", node_ids=[drawn])
    opened = _as("bob").get(f"/v1/investigations/{K}/boards/{bobs}")
    assert drawn in [n["id"] for n in opened.json()["nodes"]]
    assert private not in opened.text
    alices = _as("alice").get(f"/v1/investigations/{K}/boards/{private}").json()
    (node_seen,) = [n for n in alices["nodes"] if n["id"] == drawn]
    assert node_seen["provenance"]["drawn"]["board_id"] == private


def test_a_private_boards_id_is_on_no_other_members_canvas(world: SimpleNamespace) -> None:
    """Rule 3, the orchestrator's ruling on the review: through the canvas's own read (the
    working set's `sync`, what the socket sends on connect), and its `visible_node`, the board
    of Alice's drawn node is empty for Bob and kept for Alice, who made it."""
    import asyncio

    private = _board()
    drawn = world.graph.node(_item(private)["element_id"])
    service = app.state.working_set

    async def canvas(who: str) -> tuple[list[Any], Any]:
        await service.add_written(K, [drawn], [], PEOPLE["alice"])
        sent = await service.sync(K, PEOPLE[who], last_acknowledged_seq=None)
        nodes = [n for d in sent for n in getattr(d, "nodes", []) if n.id == drawn.id]
        return nodes, await service.visible_node(K, drawn.id, PEOPLE[who])

    bobs, bobs_one = asyncio.run(canvas("bob"))
    assert bobs and all(n.provenance.drawn.board_id == "" for n in bobs)
    assert bobs_one is not None and bobs_one.provenance.drawn.board_id == ""
    assert private not in str([n.model_dump() for n in bobs])
    alices, _ = asyncio.run(canvas("alice"))
    assert alices and all(n.provenance.drawn.board_id == private for n in alices)


# --- a proposal's own storage label is never a board's (rule 3, rule 7; found at L3.5) ----------


def test_a_board_neither_lists_nor_draws_under_a_proposals_storage_label(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A link type proposed in another case declares its own hidden storage type (`NAME__<id>`,
    ADR-090 Amendment 2) in the ontology every board reads. Listed, it would tell this case of
    that proposal and send its label to the Glass; and since `link` accepts what the list holds, a
    link could be drawn under it. Red with `link_types` listing hidden types."""
    base = ONTOLOGY.edge_type("ASSOCIATE_OF")
    assert base is not None
    label = "BRIBED__01PROPOSALOFANOTHERCASE"
    stored = base.model_copy(update={"name": label, "hidden": True, "analyst_defined": True})
    ontology = ONTOLOGY.model_copy(update={"edge_types": [*ONTOLOGY.edge_types, stored]})
    monkeypatch.setattr(app.state, "ontology", ontology, raising=False)
    board = _board()
    opened = _as("alice").get(f"/v1/investigations/{K}/boards/{board}")
    assert opened.status_code == 200, opened.text
    assert label not in opened.json()["link_types"]
    assert not [t for t in opened.json()["link_types"] if "__" in t]


def test_a_link_is_never_drawn_under_a_proposals_storage_label(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`link`'s own refusal of a hidden type, apart from the list: red with that refusal removed
    and the list made to hold hidden types (each check alone keeps the link out; both are planted
    together, `process/lanes/case-b/L3.5_RED_RECORD.md`)."""
    base = ONTOLOGY.edge_type("ASSOCIATE_OF")
    assert base is not None
    label = "BRIBED__01PROPOSALOFANOTHERCASE"
    stored = base.model_copy(update={"name": label, "hidden": True, "analyst_defined": True})
    ontology = ONTOLOGY.model_copy(update={"edge_types": [*ONTOLOGY.edge_types, stored]})
    monkeypatch.setattr(app.state, "ontology", ontology, raising=False)
    board = _board()
    one, two = _item(board)["element_id"], _item(board, label="Second")["element_id"]
    before = len(world.graph.edge_writes)
    answer = _link(board, one, two, type=label)
    assert answer.status_code == 422 and answer.json()["error"] == "not_in_the_model"
    assert len(world.graph.edge_writes) == before
