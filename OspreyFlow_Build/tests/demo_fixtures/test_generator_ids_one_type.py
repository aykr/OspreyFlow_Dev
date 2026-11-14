"""No demo generator gives one id two types (CARRIES, "A type refusal stops a reseed"; ADR-124
Amendment 18). Since am18, `upsert_nodes` refuses a write onto an id another type holds. So a
generator that gave one id two types, in one plan or across the packs, would stop a seed or a
reseed rather than, as before, lose the write in silence.

The generators whose ids persist from one seed to the next are those that make them from a key:
- `pid_plan.node_id`, for prison-intelligence and prison-intelligence-scale;
- `cyber_intrusion`, from its STIX ids;
- `fixture_corp`'s fixed names.

hmp's and operation-ledger's ids are new each run (`new_node_id`), and paysim and enron clear their
own rows before writing, so none of theirs can meet an earlier one.

The audit of 14 November 2026 (`process/lanes/studio/reseed-types/AUDIT.md`) built every version of
`pid_plan.py` since `node_id` existed, both profiles, and found no id on two types across them. The
two other generators have never changed. This test keeps today's generators so: shown red by
`test_the_check_finds_a_key_hashed_without_its_kind`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

import pytest

from demo_fixtures import cyber_intrusion, fixture_corp, pid_plan
from schemas.domain import NodeWrite


def _two_types(pairs: Iterable[tuple[str, str]]) -> dict[str, set[str]]:
    seen: dict[str, set[str]] = defaultdict(set)
    for node_id, node_type in pairs:
        seen[node_id].add(node_type)
    return {k: v for k, v in seen.items() if len(v) > 1}


def _pid(
    profile: pid_plan.Profile, node_id: Callable[[str], str] = pid_plan.node_id
) -> list[tuple[str, str]]:
    return [(node_id(e.key), e.entity_type) for e in pid_plan.build_plan(profile).entities]


class _Recording:
    """Just enough of a graph for `build_path_spokes`: it keeps what is written."""

    def __init__(self) -> None:
        self.nodes: list[NodeWrite] = []

    async def upsert_nodes(self, nodes: list[NodeWrite], tx: Any = None) -> None:
        self.nodes.extend(nodes)

    async def upsert_edges(self, edges: list[Any], tx: Any = None) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        async def nothing(*args: Any, **kwargs: Any) -> None:
            return None

        return nothing


async def _fixture_corp() -> list[tuple[str, str]]:
    pairs = [
        (n.id, n.type)
        for p in fixture_corp.generate_resolution_persons()
        for n in (p.node_a, p.node_b)
    ]
    pairs += [(n.id, n.type) for n in fixture_corp.generate_community_rings().nodes]
    graph = _Recording()
    await fixture_corp.build_path_spokes(graph)  # type: ignore[arg-type]
    return pairs + [(n.id, n.type) for n in graph.nodes]


def _cyber() -> list[tuple[str, str]]:
    return [(n.id, n.type) for n in cyber_intrusion.graph().nodes]


@pytest.mark.parametrize("profile", ["demo", "scale"])
def test_no_pid_id_has_two_types(profile: pid_plan.Profile) -> None:
    pairs = _pid(profile)
    assert len(pairs) > 1000, "the plan must not be empty"
    assert _two_types(pairs) == {}


async def test_no_fixture_corp_or_cyber_id_has_two_types() -> None:
    corp = await _fixture_corp()
    assert any(i.startswith("corp-path-spoke") for i, _ in corp), "the spokes must be counted"
    assert _two_types(corp) == {}
    assert _two_types(_cyber()) == {}


async def test_no_id_is_shared_between_packs() -> None:
    packs = {
        "pid": {i for p in ("demo", "scale") for i, _ in _pid(p)},
        "corp": {i for i, _ in await _fixture_corp()},
        "cyber": {i for i, _ in _cyber()},
    }
    names = sorted(packs)
    for a in names:
        for b in names[names.index(a) + 1 :]:
            assert packs[a].isdisjoint(packs[b]), (a, b)
    # Within the PID packs, an id shared by the two profiles keeps its type in both.
    assert _two_types(_pid("demo") + _pid("scale")) == {}


def test_the_check_finds_a_key_hashed_without_its_kind() -> None:
    """Rule 15, at the shape `node_id` really has: one that hashed a key without its kind (`pin:X`
    and `cash:X` alike) would give a person's PIN and cash account one id, on two types."""
    import hashlib

    def without_kind(key: str) -> str:
        return "pid-" + hashlib.sha256(key.rsplit(":", 1)[-1].encode()).hexdigest()[:24]

    assert _two_types(_pid("demo", without_kind))
