"""The two datasets the Prison Intelligence Dataset's generator writes into (ADR-120 D6, ADR-099).

What each test would catch if it failed:

- a dataset the generator names but `SEED_DATASETS` does not hold: ADR-099 Amendment 6 makes the
  stamping graph refuse a write naming an unregistered dataset, so the seed would stop at its
  first write; and `scripts.stamp_datasets` would never register it for a deployment loaded before;
- a `source` that another seed's stamping rule also matches: `scripts.stamp_datasets` stamps by
  provenance `document_id` (the source, or `<source>:<anything>`), so one seed's elements would be
  stamped into another's dataset, and a case reading one would show the other's data;
- an id, name, source or case name that two seeds share: the same failure by a plainer route.

Pure: no store, no network. The stamping graph is wrapped round a fake that records what reaches it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.dataset_scope import UnknownDatasetError, stamping

from demo_fixtures import pid_plan, pid_writes
from demo_fixtures.datasets import PID, PID_SCALE, SEED_DATASETS, SeedDataset
from schemas.domain import Handling, NodeWrite, Provenance, ProvenanceState, SourceRef

WHEN = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)


class Registry:
    """What the dataset store answers: the ids it holds, as `scripts.stamp_datasets` registers the
    seeds' (every one of `SEED_DATASETS`)."""

    def __init__(self, seeds: Sequence[SeedDataset]) -> None:
        self.held = {seed.id for seed in seeds}

    async def known(self, dataset_ids: Sequence[str]) -> set[str]:
        return {d for d in dataset_ids if d in self.held}


class RecordingGraph:
    """Records what reaches the store. It has no bulk capability, so `stamping` returns the plain
    stamping graph."""

    def __init__(self) -> None:
        self.nodes: list[NodeWrite] = []

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: Any) -> list[str]:
        self.nodes.extend(nodes)
        return [n.id for n in nodes]


def _node(node_id: str) -> NodeWrite:
    return NodeWrite(
        id=node_id,
        type="Person",
        properties={"family_name": "Test"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="test", locator="x", excerpt_hash="")],
            first_seen=WHEN,
        ),
        handling=Handling(
            classification="OFFICIAL",
            handling_code="P",
            originator="fenwick-moor-security",
            owning_unit="fenwick-moor-security",
        ),
        created_by="test",
        created_at=WHEN,
    )


def _stamp_rule_matches(seed: SeedDataset, document_id: str) -> bool:
    """`scripts.stamp_datasets`'s predicate: the seed's source, or the source and a colon and
    anything."""
    return document_id == seed.source or document_id.startswith(f"{seed.source}:")


def _source_documents(profile: str, dataset: str) -> set[str]:
    plan = pid_plan.build_plan("demo" if profile == "demo" else "scale")
    nodes, edges = pid_writes.writes(plan, "chapter9", dataset=dataset, created_at=WHEN)
    return {s.document_id for w in (*nodes, *edges) for s in w.provenance.sources}


def test_the_two_datasets_are_the_ones_adr_120_d6_names() -> None:
    assert (PID.id, PID.name, PID.source, PID.case_name) == (
        "prison-intelligence",
        "Prison Intelligence Dataset (synthetic)",
        "pid-generator",
        "Prison Intelligence Dataset (synthetic demo)",
    )
    assert (PID_SCALE.id, PID_SCALE.name, PID_SCALE.source, PID_SCALE.case_name) == (
        "prison-intelligence-scale",
        "Prison Intelligence Dataset: scale cohort (synthetic)",
        "pid-scale-generator",
        "Prison Intelligence Dataset: scale cohort (synthetic demo)",
    )
    assert PID in SEED_DATASETS and PID_SCALE in SEED_DATASETS


def test_no_two_seeds_share_an_id_a_name_a_source_or_a_case_name() -> None:
    for field in ("id", "name", "source", "case_name"):
        values = [getattr(seed, field) for seed in SEED_DATASETS if getattr(seed, field)]
        assert len(values) == len(set(values)), f"two seeds share a {field}: {values}"


def _has_wildcard(source: str) -> bool:
    return any(ch in source for ch in "%?_")


def test_no_seeds_source_carries_a_like_wildcard() -> None:
    """The pattern side of `stamp_datasets`' rule is `<source>:%`: a `%` or `_` (and `?`, in case
    the store reads it as one) in a source would match more than the seed's own documents, so the
    colon rule would not hold as the SQL applies it. Only a source can carry one; ids are
    compared, not matched."""
    for seed in SEED_DATASETS:
        assert not _has_wildcard(seed.source), f"{seed.id}: source {seed.source!r}"
    # Shown able to fail: the generator's sources with an underscore in place of a hyphen.
    assert _has_wildcard(PID.source.replace("-", "_"))
    assert _has_wildcard(PID_SCALE.source + "%")
    assert not _has_wildcard(PID.source) and not _has_wildcard(PID_SCALE.source)


def test_what_the_generator_writes_is_stamped_into_its_own_dataset_and_no_other() -> None:
    for profile, seed in (("demo", PID), ("scale", PID_SCALE)):
        documents = _source_documents(profile, seed.id)
        assert documents, profile
        for document_id in documents:
            matched = [s.id for s in SEED_DATASETS if _stamp_rule_matches(s, document_id)]
            assert matched == [seed.id], f"{document_id!r} is stamped into {matched}"
    # Shown able to fail: the document id the scale cohort would write if it used the demo's source
    # ("pid-generator:" and its own dataset id) is stamped into the demo's dataset, not its own.
    wrong = f"{PID.source}:{PID_SCALE.id}"
    assert [s.id for s in SEED_DATASETS if _stamp_rule_matches(s, wrong)] == [PID.id]


async def test_a_write_into_each_dataset_is_accepted_when_it_is_registered() -> None:
    for seed in (PID, PID_SCALE):
        inner = RecordingGraph()
        graph = stamping(inner, dataset=seed.id, registry=Registry(SEED_DATASETS))  # type: ignore[arg-type]
        await graph.upsert_nodes([_node("n-1")], "tx")
        assert [n.datasets for n in inner.nodes] == [[seed.id]]


async def test_a_write_into_an_unregistered_dataset_is_refused_and_reaches_nothing() -> None:
    """The control: the refusal exists, so the accepted case above is a real acceptance."""
    inner = RecordingGraph()
    registry = Registry(SEED_DATASETS)
    graph = stamping(inner, dataset="prison-intelligence-unregistered", registry=registry)  # type: ignore[arg-type]
    with pytest.raises(UnknownDatasetError, match="prison-intelligence-unregistered"):
        await graph.upsert_nodes([_node("n-1")], "tx")
    assert inner.nodes == []


async def test_a_registry_without_the_pid_refuses_its_writes() -> None:
    """Shown able to fail: the same acceptance case, with `PID` left out of the registered seeds
    (what removing it from `SEED_DATASETS` does), is refused; likewise `PID_SCALE`."""
    for left_out in (PID, PID_SCALE):
        seeds = [s for s in SEED_DATASETS if s is not left_out]
        assert left_out not in seeds
        inner = RecordingGraph()
        graph = stamping(inner, dataset=left_out.id, registry=Registry(seeds))  # type: ignore[arg-type]
        with pytest.raises(UnknownDatasetError, match=left_out.id):
            await graph.upsert_nodes([_node("n-1")], "tx")
        assert inner.nodes == []
