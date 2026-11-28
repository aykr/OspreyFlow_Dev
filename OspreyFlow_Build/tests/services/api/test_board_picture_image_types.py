"""A board's picture is only ever an image (SE9g; the owner's ruling of 27 November 2026, GG4f2's
question 3b). Pure: the real routes over `test_boards`' world, whose graph is
`board_fakes.BoardGraph`.

A Document's `media_kind` does not say what its file is: the file is served by its stored
reference. So `choose_picture` refuses, with `not_a_picture`, any Document whose stored reference is
not one of the four picture types, and `picture_file` answers as none, exactly as for an item with
no picture, for such a Document chosen before. Both are decided on the stored reference, never on a
file's name: here every name says the opposite of its reference.

Every refused file is in the media store, so nothing but the check keeps it from being served (a
reference with no extension is one the store itself refuses; it must still answer as none).

The two checks are tested apart (rule 15). The `choose` cases never read the file. The
already-chosen cases choose a PNG through the real route and then change only the Document's stored
reference, so they stand whatever `choose_picture` refuses.
"""

from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.entity_pictures import PICTURE_TYPES

from adapters.media_objectstore import reference_for

from .test_boards import K, _as, _board, _item, _loaded, world  # noqa: F401  (the fixture)

DOCUMENT_ID = "doc-chosen"
DATA = b"the stored file's bytes"
HASH = sha256(DATA).hexdigest()

#: The four picture types, each with the reference the store makes for it.
PICTURES = ("image/png", "image/jpeg", "image/gif", "image/webp")

#: What is no picture, by its stored reference. `.html` and `.svg` are names the store's own rule
#: accepts and would hand back, though it makes neither today; `.tif` is one it does make, for an
#: image the Glass cannot draw. `None` is a Document with no reference at all.
NOT_PICTURES: dict[str, str | None] = {
    "pdf": reference_for(DATA, "application/pdf"),
    "html": f"media/{HASH}.html",
    "svg": f"media/{HASH}.svg",
    "tif": reference_for(DATA, "image/tiff"),
    "no-extension": f"media/{HASH}",
    "no-reference": None,
}


def _hold(world: SimpleNamespace, ref: str | None, title: str) -> None:  # noqa: F811
    """An image Document the case holds in its source, under `title`, its file at `ref`."""
    properties = {"title": title, "media_kind": "image"}
    if ref is not None:
        properties["object_ref"] = ref
        world.media.files[ref] = DATA
    held = _loaded(DOCUMENT_ID).model_copy(update={"type": "Document", "properties": properties})
    world.graph._graph_nodes[DOCUMENT_ID] = held


def _url(board: str, node_id: str) -> str:
    return f"/v1/investigations/{K}/boards/{board}/nodes/{node_id}/picture"


def _choose(board: str, node_id: str) -> Any:
    return _as("alice").post(
        _url(board, node_id), json={"document_id": DOCUMENT_ID, "marking": "OFFICIAL"}
    )


def _file(board: str, node_id: str) -> Any:
    return _as("alice").get(_url(board, node_id))


def _shown(board: str) -> dict[str, str]:
    answer = _as("alice").get(f"/v1/investigations/{K}/boards/{board}/pictures")
    assert answer.status_code == 200, answer.text
    return dict(answer.json()["pictures"])


def _answered(answer: Any) -> tuple[int, str, bytes]:
    return answer.status_code, answer.headers["content-type"], answer.content


def test_the_picture_types_are_the_four() -> None:
    """The list the checks are read from (`PICTURE_TYPES`) holds these four and no other."""
    assert set(PICTURE_TYPES.values()) == set(PICTURES)


@pytest.mark.parametrize("content_type", PICTURES)
def test_each_picture_type_is_chosen_and_served(
    world: SimpleNamespace,  # noqa: F811
    content_type: str,
) -> None:
    # Its name says it is no picture: the reference decides.
    _hold(world, reference_for(DATA, content_type), title="report.pdf")
    board = _board()
    drawn = _item(board)["element_id"]
    chosen = _choose(board, drawn)
    assert chosen.status_code == 201, chosen.text
    assert _shown(board) == {drawn: DOCUMENT_ID}
    assert _answered(_file(board, drawn)) == (200, content_type, DATA)


@pytest.mark.parametrize("kind", NOT_PICTURES)
def test_choose_picture_refuses_what_is_no_picture(
    world: SimpleNamespace,  # noqa: F811
    kind: str,
) -> None:
    # Its name says it is a picture: the reference decides.
    _hold(world, NOT_PICTURES[kind], title="photo.png")
    board = _board()
    drawn = _item(board)["element_id"]
    links = len(world.graph.edge_writes)
    items = len(world.items.items)

    refused = _choose(board, drawn)

    assert refused.status_code == 422, refused.text
    assert refused.json() == {
        "error": "not_a_picture",
        "detail": "that is not a picture this case holds",
    }
    # Refused before anything: no link, no item on the board, no audit of a choice.
    assert len(world.graph.edge_writes) == links
    assert len(world.items.items) == items
    assert not [r for r in world.audit.records if r["action"] == "choose_drawn_picture"]


@pytest.mark.parametrize("kind", NOT_PICTURES)
def test_picture_file_answers_as_none_for_one_already_chosen(
    world: SimpleNamespace,  # noqa: F811
    kind: str,
) -> None:
    _hold(world, reference_for(DATA, "image/png"), title="photo.png")
    board = _board()
    drawn = _item(board)["element_id"]
    none = _answered(_file(board, drawn))  # this item, while it has no picture
    assert none[0] == 404 and b"item_not_found" in none[2]
    chosen = _choose(board, drawn)
    assert chosen.status_code == 201, chosen.text
    assert _file(board, drawn).status_code == 200

    # As one chosen before this part: the link and the board's item stand, and the Document's
    # stored reference is no picture's.
    _hold(world, NOT_PICTURES[kind], title="photo.png")

    assert _answered(_file(board, drawn)) == none
