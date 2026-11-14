"""The expand preview's `link_count`: how many links of the asked type the reader may see at the node
(ADR-098 Amendment 8; the right-click menu's "Expand by link type" shows it per type, and folds a type
with none into one line).

It is read from the adapter's own expand (rule 3: access is the adapter's, in the traversal), and
counted here only over what that read returned: a link of the asked type, at a node asked about, whose
far end the read returned too. A link already on the canvas counts (it is a link the node has, not a node
the expansion would add, which is what the old figure was). A stored item the reader may not read never
moves it (ADR-124 decision 2), and a link the read returned with its far end left out is not one they can
follow, so it is not counted either.
"""

from __future__ import annotations

import pytest
from schemas.domain import Edge, ExpandRequest, Subgraph

from .test_cap_counts_the_readers_view import CASE, HIDDEN_KINDS, _case
from .test_visible_link import OFFICIAL_READER, SECRET_READER, edge, node

ASKED = ExpandRequest(node_ids=["a"], depth=1, edge_types=["ASSOCIATED_WITH"])


def _typed(edge_id: str, source: str, target: str, edge_type: str, classification: str = "OFFICIAL") -> Edge:
    return edge(edge_id, source, target, classification).model_copy(update={"type": edge_type})


@pytest.mark.parametrize("kind", HIDDEN_KINDS)
async def test_the_link_count_is_equal_with_and_without_a_hidden_stored_item(kind: str) -> None:
    expansion = Subgraph(nodes=[node("a"), node("b"), node("c")], edges=[edge("a-b", "a", "b"), edge("a-c", "a", "c")])
    service, _, _ = await _case(kind, expansion)
    plain, _, _ = await _case("nothing hidden", expansion)

    preview = await service.expand_preview(CASE, ASKED, OFFICIAL_READER)

    assert preview.link_count == (await plain.expand_preview(CASE, ASKED, OFFICIAL_READER)).link_count == 2


async def test_a_link_already_on_the_canvas_is_counted() -> None:
    """a-b is in the case's working set already: the expansion would add nothing, and the node still has it."""
    expansion = Subgraph(nodes=[node("a"), node("b")], edges=[edge("a-b", "a", "b")])
    service, _, _ = await _case("nothing hidden", expansion)

    preview = await service.expand_preview(CASE, ASKED, OFFICIAL_READER)

    assert preview.candidate_node_count == 2 and preview.link_count == 1


async def test_only_links_of_the_asked_type_at_the_asked_node_are_counted() -> None:
    """The fake returns its expansion whatever is asked, as a read of every type would: the count is the
    asked type's, at the node, and a link between two neighbours is not the node's."""
    expansion = Subgraph(
        nodes=[node("a"), node("b"), node("c")],
        edges=[edge("a-b", "a", "b"), _typed("a-c", "a", "c", "USES"), edge("b-c", "b", "c")],
    )
    service, _, _ = await _case("nothing hidden", expansion)

    assert (await service.expand_preview(CASE, ASKED, OFFICIAL_READER)).link_count == 1
    every_type = ExpandRequest(node_ids=["a"], depth=1)
    assert (await service.expand_preview(CASE, every_type, OFFICIAL_READER)).link_count == 2


async def test_a_link_whose_far_end_the_read_left_out_is_not_counted() -> None:
    """The adapter leaves out a node the reader may not read; a link to it, if returned, is no link they can follow."""
    expansion = Subgraph(nodes=[node("a"), node("b")], edges=[edge("a-b", "a", "b"), edge("a-s", "a", "s")])
    service, _, _ = await _case("nothing hidden", expansion)

    assert (await service.expand_preview(CASE, ASKED, OFFICIAL_READER)).link_count == 1


async def test_a_reader_cleared_for_more_is_counted_with_it() -> None:
    """Not zero for everyone: the count is the read's, so a reader whose read returns more counts more."""
    official = Subgraph(nodes=[node("a"), node("b")], edges=[edge("a-b", "a", "b")])
    cleared = Subgraph(nodes=[node("a"), node("b"), node("s", "SECRET")],
                       edges=[edge("a-b", "a", "b"), edge("a-s", "a", "s", "SECRET")])
    low, _, _ = await _case("nothing hidden", official)
    high, _, _ = await _case("nothing hidden", cleared)

    assert (await low.expand_preview(CASE, ASKED, OFFICIAL_READER)).link_count == 1
    assert (await high.expand_preview(CASE, ASKED, SECRET_READER)).link_count == 2
