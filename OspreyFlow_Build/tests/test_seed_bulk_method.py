"""`--method bulk` on a seed: the edges go through the bulk loader, stored pairs are merged by
upsert, and an adapter without the capability is refused rather than silently run the old way
(ADR-058 D1, D3, D9). Each test names what it catches.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from ports.graph import BulkEdgeResult
from scripts import seed_internal, seed_support

from tests.test_seed_internal import SUBS, Runner, _seed_call


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A checkout, as `test_seed_internal` builds one."""
    (tmp_path / ".git").mkdir()
    core = tmp_path / "OspreyFlow_Core"
    out = core / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text("OSPREY_KEYCLOAK_PORT=8081\n", encoding="utf-8")
    (core / "scripts").mkdir()
    (tmp_path / "OspreyFlow_Data" / "PaySIM_Dataset").mkdir(parents=True)
    return core


class Graph:
    """Records the calls; `bulk_load_edges` is offered only by `BulkGraph`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.open: set[str] = set()

    async def begin_transaction(self) -> str:
        self.open.add("tx")
        return "tx"

    async def commit_transaction(self, tx: str) -> None:
        self.open.remove(tx)

    async def rollback_transaction(self, tx: str) -> None:
        self.open.discard(tx)

    async def upsert_nodes(self, nodes: list[Any], tx: str) -> list[str]:
        assert tx in self.open, "a write outside a transaction"
        self.calls.append(("upsert_nodes", len(nodes)))
        return []

    async def upsert_edges(self, edges: list[Any], tx: str) -> list[str]:
        assert tx in self.open, "a write outside a transaction"
        self.calls.append(("upsert_edges", len(edges)))
        return []


class BulkGraph(Graph):
    def __init__(self, collisions: int = 0) -> None:
        super().__init__()
        self.collisions = collisions

    async def bulk_load_edges(
        self, edges: Any, *, chunk_size: int = 500, progress: Any = None
    ) -> BulkEdgeResult:
        assert not self.open, (
            "the nodes must be committed before the edges are bulk loaded"
        )
        assert ("upsert_nodes", 3) in self.calls, "the endpoints must exist first"
        self.calls.append(("bulk_load_edges", len(edges)))
        if progress:
            progress(len(edges), len(edges))
        stored = list(edges)[: self.collisions]
        written = [f"e{i}" for i in range(len(edges) - self.collisions)]
        return BulkEdgeResult(
            written=written, collisions=stored, received=len(edges), chunks=1
        )


def _write(graph: Any, nodes: int = 3, edges: int = 7, **kw: Any) -> None:
    asyncio.run(
        seed_support.write_graph(
            graph,
            list(range(nodes)),
            list(range(edges)),
            chunk=40,
            nouns=("accounts", "transactions"),
            **kw,
        )
    )


def test_bulk_writes_nodes_by_upsert_then_every_edge_through_the_loader_once() -> None:
    """Catches edges also going through `upsert_edges` (written twice, merged into doubled
    occurrences), or going through neither, or the loader running before its endpoints exist."""
    graph = BulkGraph()
    _write(graph, method="bulk")
    assert graph.calls == [("upsert_nodes", 3), ("bulk_load_edges", 7)]


def test_a_stored_pair_comes_back_and_is_merged_by_upsert_not_dropped(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Catches collisions dropped (a pair already stored silently losing the new occurrences) or
    written by the bulk path (a second record for the pair), and the report not saying so."""
    graph = BulkGraph(collisions=3)
    _write(graph, method="bulk")
    assert graph.calls == [
        ("upsert_nodes", 3),
        ("bulk_load_edges", 7),
        ("upsert_edges", 3),
    ]
    assert "3 already stored" in capsys.readouterr().out


def test_the_report_says_how_many_repeated_pairs_were_merged_before_writing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Catches a count that hides the aggregation: received less written less collisions."""

    class Merging(BulkGraph):
        async def bulk_load_edges(self, edges: Any, **kw: Any) -> BulkEdgeResult:
            return BulkEdgeResult(
                written=["a", "b", "c"], collisions=[], received=7, chunks=1
            )

    _write(Merging(), method="bulk")
    assert "4 repeated pair(s) merged before writing" in capsys.readouterr().out


def test_an_adapter_without_the_capability_is_refused_before_anything_is_written() -> (
    None
):
    """Catches a seed that asked for the new method quietly running the old one and reporting
    the new one's timings, or half-writing the nodes before noticing."""
    graph = Graph()
    with pytest.raises(seed_support.BulkUnavailable):
        _write(graph, method="bulk")
    assert graph.calls == []


def test_an_unknown_method_is_refused_before_anything_is_written() -> None:
    """Catches a typo ('bulky') falling through to the default."""
    graph = BulkGraph()
    with pytest.raises(ValueError, match="bulky"):
        _write(graph, method="bulky")
    assert graph.calls == []


def test_the_default_is_still_the_upsert_path() -> None:
    """Catches the default changing before the bulk path is proved (ADR-058 D9)."""
    graph = BulkGraph()
    _write(graph)
    assert graph.calls == [("upsert_nodes", 3), ("upsert_edges", 7)]


# --- the seed command ---


def _go(repo: Path, **kw: Any) -> Runner:
    runner = Runner()
    seed_internal.seed_internal(
        "paysim",
        repo,
        run=runner,
        lookup_subs=lambda directory: SUBS,
        api_running=lambda compose: False,
        **kw,
    )
    return runner


def test_method_reaches_the_container_only_when_it_is_not_the_default(
    repo: Path,
) -> None:
    """Catches the flag never arriving (a 'bulk' run that is an upsert run), or being sent on every
    run."""
    assert "--method" not in _seed_call(_go(repo))
    call = _seed_call(_go(repo, method="bulk", vault="paysim-bulk"))
    assert call[call.index("--method") + 1] == "bulk"
    assert call[call.index("--vault") + 1] == "paysim-bulk"


def test_method_is_refused_for_a_dataset_that_cannot_take_it(repo: Path) -> None:
    """Catches `--method bulk` on a seed that would ignore it, and so run slowly while saying it
    did not."""
    (repo.parent / "OspreyFlow_Data" / "Enron_Mails" / "a").mkdir(parents=True)
    runner = Runner()
    with pytest.raises(seed_internal.SeedRefused, match="only built for paysim"):
        seed_internal.seed_internal(
            "enron",
            repo,
            run=runner,
            lookup_subs=lambda directory: SUBS,
            api_running=lambda compose: False,
            permitted=lambda name, use: True,
            method="bulk",
        )
    assert runner.calls == []
    with pytest.raises(seed_internal.SeedRefused, match="unknown --method"):
        _go(repo, method="bulky")


def test_compare_vaults_is_read_only_and_makes_no_case(repo: Path) -> None:
    """Catches a comparison that stops the Conduit, needs the demo accounts or makes a case."""
    runner = Runner()
    seed_internal.seed_internal(
        "paysim",
        repo,
        run=runner,
        lookup_subs=lambda directory: {},
        api_running=lambda compose: True,
        compare_vaults=("paysim", "paysim-bulk"),
    )
    call = _seed_call(runner)
    assert call[-3:] == ["scripts.compare_vaults", "paysim", "paysim-bulk"]
    assert "--case-name" not in call and not any("stop" in c for c in runner.calls)


def test_compare_vaults_refuses_a_name_that_is_not_a_vault_id(repo: Path) -> None:
    """Catches a name reaching the container unchecked."""
    runner = Runner()
    with pytest.raises(seed_internal.SeedRefused, match="not a vault id"):
        seed_internal.seed_internal(
            "paysim",
            repo,
            run=runner,
            lookup_subs=lambda directory: SUBS,
            api_running=lambda compose: False,
            compare_vaults=("paysim", "../etc"),
        )
    assert runner.calls == []


def test_the_command_line_takes_method_and_compare_vaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches `make`'s command line not knowing the flags, or the vault ids being read as the
    dataset name."""
    seen: dict[str, Any] = {}

    def fake(dataset: str, **kw: Any) -> list[str]:
        seen.update(kw, dataset=dataset)
        return []

    monkeypatch.setattr(seed_internal, "seed_internal", fake)
    assert (
        seed_internal.main(["paysim", "--method", "bulk", "--vault", "paysim-bulk"])
        == 0
    )
    assert seen["method"] == "bulk" and seen["vault"] == "paysim-bulk"
    seen.clear()
    assert (
        seed_internal.main(["paysim", "--compare-vaults", "paysim", "paysim-bulk"]) == 0
    )
    assert (
        seen["compare_vaults"] == ("paysim", "paysim-bulk")
        and seen["dataset"] == "paysim"
    )
    assert seed_internal.main(["paysim", "--method", "fast"]) == 2
    assert seed_internal.main(["paysim", "--compare-vaults", "paysim"]) == 2
