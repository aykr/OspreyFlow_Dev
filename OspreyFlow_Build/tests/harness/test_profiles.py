"""The stores sized to the server's memory (ADR-114 Amendment 33 decision 6; drop 2, unit 5):
`harness/profiles.py`'s arithmetic, against the amendment's own table.

| Setting | Rule from `M` GiB | 32 | 64 | 128 |
| --- | --- | --- | --- | --- |
| ArcadeDB `-Xmx` | 0.4 × M, at least 8, at most 31 | 12 | 25 | 31 |
| OpenSearch `-Xms` = `-Xmx` | M ÷ 16, at least 0.5, at most 8 | 2 | 4 | 8 |
| PostgreSQL `shared_buffers` | M ÷ 32, at least 0.25, at most 4; `effective_cache_size` 3 × | 1 | 2 | 4 |
"""

from __future__ import annotations

import pytest
from harness import profiles
from harness.profiles import (
    LITE_STORE_MEMORY,
    PROFILE_FLOORS,
    StoreMemory,
    store_memory,
)
from pydantic import ValidationError

from schemas.deployment import OspreyConfig, ResourcesConfig


@pytest.mark.parametrize(
    ("memory", "graph", "search", "shared", "cache"),
    [(32, 12, 2048, 1024, 3072), (64, 25, 4096, 2048, 6144), (128, 31, 8192, 4096, 12288)],
)
def test_heaps_follow_the_servers_memory_at_32_64_and_128_gib(
    memory: int, graph: int, search: int, shared: int, cache: int
) -> None:
    sized = store_memory(ResourcesConfig(memory_gib=memory))
    assert sized == StoreMemory(
        graph_heap_gib=graph,
        search_heap_mib=search,
        postgres_shared_buffers_mib=shared,
        postgres_effective_cache_mib=cache,
    )


def test_the_graph_heap_never_exceeds_31_gib() -> None:
    """Above 31 GiB the JVM loses compressed object pointers, so a larger heap holds less."""
    for memory in (78, 100, 256, 1024):
        assert store_memory(ResourcesConfig(memory_gib=memory)).graph_heap_gib == 31
    with pytest.raises(ValidationError):
        ResourcesConfig(memory_gib=256, graph_heap_gib=32)


def test_opensearch_xms_equals_xmx() -> None:
    for memory in (16, 32, 48, 64, 200):
        options = store_memory(ResourcesConfig(memory_gib=memory)).search_java_opts
        low, high = options.split()
        assert low.startswith("-Xms") and high.startswith("-Xmx")
        assert low[4:] == high[4:], options


def test_an_override_in_osprey_yaml_wins() -> None:
    sized = store_memory(
        ResourcesConfig(memory_gib=64, graph_heap_gib=20, search_heap_gib=1.5,
                        postgres_shared_buffers_gib=0.5)
    )  # fmt: skip
    assert (sized.graph_heap_gib, sized.search_heap_mib, sized.postgres_shared_buffers_mib) == (
        20, 1536, 512)  # fmt: skip
    # effective_cache_size follows the shared buffers it is given.
    assert sized.postgres_effective_cache_mib == 1536


def test_lite_without_resources_keeps_todays_values() -> None:
    """Decision 6: unsized, every store keeps today's values — ArcadeDB half the 16 GB floor,
    OpenSearch 512 MiB, PostgreSQL the image's own settings — and resources are refused on Lite."""
    assert store_memory(ResourcesConfig()) == LITE_STORE_MEMORY
    assert LITE_STORE_MEMORY.graph_heap_gib == 8
    assert LITE_STORE_MEMORY.search_java_opts == "-Xms512m -Xmx512m"
    assert LITE_STORE_MEMORY.postgres_shared_buffers_mib is None
    assert LITE_STORE_MEMORY.graph_java_opts == profiles.arcadedb_java_memory_opts()
    with pytest.raises(ValidationError, match="resources"):
        OspreyConfig.model_validate({"resources": {"memory_gib": 64}})


def test_the_sized_heaps_leave_the_reserve() -> None:
    """The three stores together take at most half the server from the floor up, leaving the
    rest to Ollama (about 3.5 GiB with a model loaded), Keycloak, Valkey, the Conduit and the
    operating system — arithmetic, as `harness/profiles.py` says of its own figures."""
    for memory in range(30, 513):
        sized = store_memory(ResourcesConfig(memory_gib=memory))
        total = (sized.graph_heap_gib * 1024 + sized.search_heap_mib
                 + (sized.postgres_shared_buffers_mib or 0)) / 1024  # fmt: skip
        assert total <= memory / 2, (memory, total)


def test_the_server_floor_is_thirty_gib() -> None:
    """Decision 6 and the owner's answer 16: a server for Small is a nominal 32 GB one, 30 GiB as
    Docker reports it — the doctor's floor, and Preflight's for the small profile."""
    assert PROFILE_FLOORS["small"] == 30 * 1024**3
    assert PROFILE_FLOORS["local-lite"] == 16 * 1024**3


def test_stores_sized_beyond_the_server_are_refused_in_words() -> None:
    """An override that would hand the stores more than the server can give them is refused
    before anything is rendered: measured, PostgreSQL does not refuse shared buffers above its
    container's memory (it reserves them and is killed later), so the check is ours
    (`test_render_memory.py` has the real stores)."""
    with pytest.raises(ValidationError) as refused:
        ResourcesConfig(memory_gib=32, graph_heap_gib=31, search_heap_gib=8)
    assert "memory_gib" in str(refused.value) and "32" in str(refused.value)
