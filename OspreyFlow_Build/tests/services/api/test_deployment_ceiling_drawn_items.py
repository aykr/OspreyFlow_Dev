"""ADR-148 decision 10 at the six places a board writes (SE1; C039, C071): a drawn item or board
picture marked above the deployment's highest marking is refused before anything is kept, with the
refusal documents already get (422 `above_the_deployments_highest_marking`), in words that say the
deployment's limit and never the item's content.

The six write sites: *Add to board* (declare), a drawn link, an edit that raises the marking, a
*Same* / *Not the same* decision, an uploaded picture, and a chosen picture.

**What "kept" means here.** `world.graph` records every write that lands (`node_writes`,
`edge_writes`) and `world.media` every file it is given. The store's own backstop
(`refuse_writes_above_the_ceiling`, which reads `OSPREY_HIGHEST_MARKING`) is switched off, and the
case's own dataset sets no ceiling, so the only thing that can refuse is the board's early check
against the Conduit's ceiling (`app.state.deployment_ceiling`). Left on, the backstop would refuse
the four graph writes by itself and these cases would prove nothing about the early check
(`CLAUDE.md` rule 15); it cannot, in any case, un-keep a picture's bytes, which `Boards.upload_picture`
put in the media store before the graph refused its Document (C071).

Controls (rule 15): an item *at* the ceiling is accepted at every site, and so is one above it where
the deployment sets no ceiling.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from ontology.handling import load_uk_le_scheme
from services.api.app import app
from services.ingest.ceiling import DeploymentCeiling

from .test_boards import (  # noqa: F401  (`world` is a fixture)
    GRADE,
    K,
    SCHEME,
    _as,
    _board,
    _item,
    _link,
    _loaded,
    world,
)

CEILING = "OFFICIAL-SENSITIVE"
ABOVE = "SECRET"
#: Content that must never be echoed: the item's label, its source note, a file's name, a name.
LABEL = "SYN-CEILING-LABEL"
NOTE = "SYN-CEILING-NOTE"
FILE = "SYN-CEILING-FILE.png"
NAME = "SYN-CEILING-NAME"
NEVER_ECHOED = (LABEL, NOTE, FILE, NAME)


def _set_ceiling(monkeypatch: pytest.MonkeyPatch, marking: str) -> None:
    monkeypatch.setattr(
        app.state,
        "deployment_ceiling",
        DeploymentCeiling(marking=marking, scheme=load_uk_le_scheme()),
        raising=False,
    )


@pytest.fixture
def held(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:  # noqa: F811
    """`test_boards`' world with the case's dataset setting no ceiling of its own and the store's
    backstop off, so the deployment's ceiling is the only one in play; the media store records
    every file it is given."""
    monkeypatch.delenv("OSPREY_HIGHEST_MARKING", raising=False)
    src = world.datasets.datasets["src"]
    world.datasets.datasets["src"] = src.model_copy(update={"highest_marking": None})
    # One loaded person at each marking, for a decision to be made against.
    for marking in (CEILING, ABOVE):
        world.graph._graph_nodes[f"p-{marking}"] = _loaded(
            f"p-{marking}", marking, family_name=NAME
        )
    world.puts = []
    real_put = world.media.put

    async def recording_put(data: bytes, content_type: str) -> str:
        world.puts.append(data)
        return await real_put(data, content_type)

    monkeypatch.setattr(world.media, "put", recording_put)
    _set_ceiling(monkeypatch, CEILING)
    return world


# --- the six write sites: each sets itself up at OFFICIAL, then tries `marking` --------------------


def _declare(world: SimpleNamespace, marking: str) -> Any:
    board = _board()
    return _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/items",
        json={"type": "Person", "label": LABEL, "marking": marking, "grading": GRADE,
              "source_note": NOTE, "properties": {"family_name": NAME}},
    )  # fmt: skip


def _draw_link(world: SimpleNamespace, marking: str) -> Any:
    board = _board()
    ends = [_item(board, label=LABEL, source_note=NOTE)["element_id"] for _ in range(2)]
    return _link(board, ends[0], ends[1], marking=marking, label=LABEL, source_note=NOTE)


def _edit(world: SimpleNamespace, marking: str) -> Any:
    board = _board()
    item = _item(board, label=LABEL, source_note=NOTE)
    return _as("alice").patch(
        f"/v1/investigations/{K}/board-items/{item['item_id']}",
        json={"marking": marking, "label": LABEL},
    )


def _decide(world: SimpleNamespace, marking: str) -> Any:
    """The decision is marked as both ends together, so the loaded end carries `marking`."""
    loaded = f"p-{marking}"
    board = _board(start="selection", node_ids=[loaded])
    drawn = _item(board, label=LABEL, source_note=NOTE)["element_id"]
    return _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/matches",
        json={"drawn": drawn, "loaded": loaded, "same": True},
    )


def _upload(world: SimpleNamespace, marking: str) -> Any:
    board = _board()
    drawn = _item(board, label=LABEL, source_note=NOTE)["element_id"]
    return _as("alice").put(
        f"/v1/investigations/{K}/boards/{board}/nodes/{drawn}/picture",
        params={"name": FILE, "marking": marking, "source_note": NOTE},
        content=b"\x89PNG SYN-CEILING-BYTES",
    )


def _choose(world: SimpleNamespace, marking: str) -> Any:
    board = _board()
    drawn = _item(board, label=LABEL, source_note=NOTE)["element_id"]
    return _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/nodes/{drawn}/picture",
        json={"document_id": "img-1", "marking": marking},
    )


SITES: dict[str, Callable[[SimpleNamespace, str], Any]] = {
    "declare": _declare,
    "link": _draw_link,
    "edit": _edit,
    "decide": _decide,
    "upload_picture": _upload,
    "choose_picture": _choose,
}
#: What a site writes into the graph when it is accepted: nodes, edges.
WRITES = {
    "declare": (1, 0),
    "link": (0, 1),
    "edit": (1, 0),
    "decide": (0, 1),
    "upload_picture": (1, 1),
    "choose_picture": (0, 1),
}


def _written(world: SimpleNamespace) -> tuple[int, int]:
    return len(world.graph.node_writes), len(world.graph.edge_writes)


@pytest.mark.parametrize("site", SITES)
def test_a_drawn_item_or_picture_above_the_ceiling_is_refused_before_anything_is_kept(
    held: SimpleNamespace, site: str
) -> None:
    # The site's setup draws at OFFICIAL, under the ceiling: only the attempt is judged.
    answer = SITES[site](held, ABOVE)
    setup_nodes, setup_edges = _setup_writes(site)
    assert answer.status_code == 422, answer.text
    body = answer.json()
    assert body["error"] == "above_the_deployments_highest_marking", answer.text
    # The words say the deployment's limit, never the item's marking or content.
    assert CEILING in body["detail"]
    for text in (answer.text, str(body)):
        assert ABOVE not in text
        for content in NEVER_ECHOED:
            assert content not in text
    # Nothing kept: no bytes in the media store, and only what the setup itself drew in the graph.
    assert held.puts == []
    assert dict(held.media.files).keys() == {_image_ref()}
    assert _written(held) == (setup_nodes, setup_edges)
    assert not [e for e in held.graph.edges() if e.type in ("DEPICTS", "SAME_AS")]


def _image_ref() -> str:
    from .test_boards import IMAGE_REF

    return IMAGE_REF


def _setup_writes(site: str) -> tuple[int, int]:
    """The (nodes, edges) a site's own setup draws before its attempt, at OFFICIAL."""
    return {
        "declare": (0, 0),
        "link": (2, 0),
        "edit": (1, 0),
        "decide": (1, 0),
        "upload_picture": (1, 0),
        "choose_picture": (1, 0),
    }[site]


@pytest.mark.parametrize("site", SITES)
def test_an_item_at_the_ceiling_is_accepted_and_kept(held: SimpleNamespace, site: str) -> None:
    answer = SITES[site](held, CEILING)
    assert answer.status_code in (200, 201), answer.text
    setup_nodes, setup_edges = _setup_writes(site)
    wrote_nodes, wrote_edges = WRITES[site]
    assert _written(held) == (setup_nodes + wrote_nodes, setup_edges + wrote_edges)
    assert len(held.puts) == (1 if site == "upload_picture" else 0)


@pytest.mark.parametrize("site", SITES)
def test_with_no_ceiling_set_nothing_changes(
    held: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, site: str
) -> None:
    """The deployment's highest is the scheme's own: no ceiling, so SECRET is drawn as before."""
    _set_ceiling(monkeypatch, SCHEME.classification[-1])
    answer = SITES[site](held, ABOVE)
    assert answer.status_code in (200, 201), answer.text
    setup_nodes, setup_edges = _setup_writes(site)
    wrote_nodes, wrote_edges = WRITES[site]
    assert _written(held) == (setup_nodes + wrote_nodes, setup_edges + wrote_edges)
    assert len(held.puts) == (1 if site == "upload_picture" else 0)


def test_with_no_ceiling_held_on_the_app_the_environments_is_read(
    held: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A start that has not read a ceiling falls back to the rendered `OSPREY_HIGHEST_MARKING`, as
    the documents route does. The picture is the case that shows it: the store's backstop (now on,
    with the environment set) cannot un-keep bytes, only the early check keeps them out."""
    monkeypatch.delattr(app.state, "deployment_ceiling", raising=False)
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", CEILING)
    answer = _upload(held, ABOVE)
    assert answer.status_code == 422, answer.text
    assert answer.json()["error"] == "above_the_deployments_highest_marking"
    assert held.puts == []
