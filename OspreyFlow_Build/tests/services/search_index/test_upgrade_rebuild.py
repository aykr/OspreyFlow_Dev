"""ADR-150 Amendment 2, the behaviour each path's rebuild is for: an upgrade from a v0.5.1 shape
leaves an index made without this version's mapping fingerprint behind the alias, so the indexer
writes nothing to it (`MappingOutOfDate`) and the outbox stays full: search never leaves the
fallback. Once the rebuild install, update, restore and the cloud-platform INSTALL now run has
moved the alias to an index made from the graph, the indexer drains. Against `FakeOpenSearch`,
which refuses what OpenSearch refuses. The paths' own wiring is held by
`tests/harness/test_apply_search_rebuild.py`, `test_update_apply.py` and
`test_cloud_platform_search_rebuild.py`."""

from __future__ import annotations

import pytest
from services.search_index.indexer import MappingOutOfDate, SearchIndexer, ensure_index
from services.search_index.mapping import index_body
from services.search_index.rebuild import rebuild

from tests.services.search_index.fake_opensearch import FakeOpenSearch
from tests.services.search_index.test_refused import ALIAS, SCHEMA, _Graph, _person, _Texts


async def _v051(client: FakeOpenSearch) -> None:
    """The alias's index as v0.5.1 made it: this version's fields, no fingerprint in `_meta`."""
    body = index_body()
    body.get("mappings", {}).pop("_meta", None)
    await client.indices.create(index=f"{ALIAS}-v051", body=body)
    await client.indices.put_alias(index=f"{ALIAS}-v051", name=ALIAS)


async def test_an_upgrade_s_old_index_holds_the_indexer_until_a_rebuild_then_it_drains() -> None:
    client = FakeOpenSearch()
    await _v051(client)
    graph = _Graph([_person("p1", "Kestral"), _person("p2", "Ravenscar")])
    indexer = SearchIndexer(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    # As on main after an upgrade: the indexer's start refuses the index; a drain writes nothing.
    with pytest.raises(MappingOutOfDate):
        await ensure_index(client, ALIAS)  # type: ignore[arg-type]
    with pytest.raises(MappingOutOfDate):
        await indexer.drain_once()
    assert graph.pending == ["p1", "p2"], "the outbox kept: nothing reached the index"
    # The path's rebuild: a new index from the graph, the alias moved to it.
    built = await rebuild(graph, _Texts(), client, ALIAS, SCHEMA)  # type: ignore[arg-type]
    assert built.nodes == 2
    await ensure_index(client, ALIAS)  # type: ignore[arg-type]
    await indexer.drain_once()
    assert graph.pending == []
    assert {d for i in client.resolve(ALIAS) for d in client.docs[i]} >= {"p1", "p2"}
