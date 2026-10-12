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

from tests.test_seed_internal import SUBS, Runner, _enron_from_build, _seed_call  # noqa: F401 — autouse


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


def test_the_library_default_is_still_the_upsert_path() -> None:
    """`write_graph` itself still defaults to upsert for its other callers; the Enron and PaySim
    seeds ask for bulk (ADR-058 Amendment 5, below)."""
    graph = BulkGraph()
    _write(graph)
    assert graph.calls == [("upsert_nodes", 3), ("upsert_edges", 7)]


# --- the seed command ---


def _go(repo: Path, dataset: str = "paysim", **kw: Any) -> Runner:
    runner = Runner()
    seed_internal.seed_internal(
        dataset,
        repo,
        run=runner,
        lookup_subs=lambda directory: SUBS,
        api_running=lambda compose: False,
        permitted=lambda name, use: True,
        **kw,
    )
    return runner


def _method_sent(runner: Runner) -> str | None:
    call = _seed_call(runner)
    return call[call.index("--method") + 1] if "--method" in call else None


@pytest.mark.parametrize("dataset", ["paysim", "enron"])
def test_enron_and_paysim_load_in_bulk_unless_upsert_is_asked_for(repo: Path, dataset: str) -> None:
    """ADR-058 Amendment 5 (owner, 5 October 2026): `make seed-enron` and `make seed-paysim` load
    in bulk. Catches the flag not arriving (a 'bulk' run that is an upsert run), and the way back
    to upsert being lost. The method is always sent, so the script's own default cannot decide."""
    (repo.parent / "OspreyFlow_Data" / "Enron_Mails" / "a").mkdir(parents=True, exist_ok=True)
    assert _method_sent(_go(repo, dataset)) == "bulk"
    assert _method_sent(_go(repo, dataset, method="upsert")) == "upsert"
    call = _seed_call(_go(repo, method="bulk", vault="paysim-perftst"))
    assert call[call.index("--vault") + 1] == "paysim-perftst"


def test_the_synthetic_seeds_are_not_sent_a_method(repo: Path) -> None:
    assert _method_sent(_go(repo, "hmp")) is None


def test_method_is_refused_for_a_dataset_that_cannot_take_it(repo: Path) -> None:
    """Catches `--method bulk` on a seed that would ignore it, and so run slowly while saying it
    did not."""
    runner = Runner()
    with pytest.raises(seed_internal.SeedRefused, match="not built for hmp"):
        seed_internal.seed_internal(
            "hmp",
            repo,
            run=runner,
            lookup_subs=lambda directory: SUBS,
            api_running=lambda compose: False,
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
        compare_vaults=("paysim", "paysim-perftst"),
    )
    call = _seed_call(runner)
    assert call[-3:] == ["scripts.compare_vaults", "paysim", "paysim-perftst"]
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
        seed_internal.main(["paysim", "--method", "bulk", "--vault", "paysim-perftst"])
        == 0
    )
    assert seen["method"] == "bulk" and seen["vault"] == "paysim-perftst"
    seen.clear()
    assert (
        seed_internal.main(["paysim", "--compare-vaults", "paysim", "paysim-perftst"])
        == 0
    )
    assert (
        seen["compare_vaults"] == ("paysim", "paysim-perftst")
        and seen["dataset"] == "paysim"
    )
    assert seed_internal.main(["paysim", "--method", "fast"]) == 2
    assert seed_internal.main(["paysim", "--compare-vaults", "paysim"]) == 2


def test_the_spike_runs_in_the_deployment_network_and_touches_no_case(
    repo: Path,
) -> None:
    """Seen: run from the host the spike could not reach the store (it is only published inside
    the deployment's network). Catches a spike that stops the Conduit, makes a case or asks for the
    demo accounts, and one that never reaches the container."""
    runner = Runner()
    seed_internal.seed_internal(
        "paysim",
        repo,
        run=runner,
        lookup_subs=lambda directory: {},
        api_running=lambda compose: True,
        spike_bulk_transport=True,
    )
    call = _seed_call(runner)
    assert call[-2:] == ["-m", "scripts.spike_bulk_transport"]
    assert "--case-name" not in call and "--vault" not in call
    assert not any("stop" in c for c in runner.calls)


def test_the_spike_flag_is_refused_for_a_dataset_that_cannot_take_it_and_parsed_from_the_command_line(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches the flag silently ignored on another dataset, or `make`'s line not knowing it."""
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
            spike_bulk_transport=True,
        )
    assert runner.calls == []
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        seed_internal, "seed_internal", lambda d, **kw: seen.update(kw) or []
    )
    assert seed_internal.main(["paysim", "--spike-bulk-transport"]) == 0
    assert seen["spike_bulk_transport"] is True


def _every_container_run(repo: Path) -> list[tuple[str, list[str]]]:
    """One container run of each kind `seed_internal` can start, as the argv it sent."""
    (repo.parent / "OspreyFlow_Data" / "PaySIM_Dataset").mkdir(
        parents=True, exist_ok=True
    )
    kinds: dict[str, dict[str, Any]] = {
        "seed": {},
        "bulk seed": {"method": "bulk", "vault": "paysim-perftst"},
        "inspect": {"inspect": True},
        "repair": {"restore_missing": True},
        "compare": {"compare_vaults": ("paysim", "paysim-perftst")},
        "spike": {"spike_bulk_transport": True},
        "lookup probe": {"probe_lookup_cost": True},
        "clear shared stores": {
            "clear_shared_stores": True,
            "vault": "paysim",
            "stop_api": True,
        },
    }
    found = []
    for kind, kwargs in kinds.items():
        runner = Runner()
        seed_internal.seed_internal(
            "paysim",
            repo,
            run=runner,
            lookup_subs=lambda directory: SUBS,
            api_running=lambda compose: False,
            **kwargs,
        )
        found.append((kind, _seed_call(runner)))
    return found


def test_every_container_run_takes_the_checkouts_packages_as_well_as_its_scripts(
    repo: Path,
) -> None:
    """Seen: the spike, and any seed importing `seed_support`, died with `cannot import name
    'BulkGraphLoader' from 'ports.graph'`, because the container ran the image's older copy of
    `packages/` beside the checkout's newer `scripts/`. Catches any kind of run that mounts the
    scripts and not the packages they import."""
    runs = _every_container_run(repo)
    assert len(runs) == 8
    for kind, call in runs:
        assert f"{repo}/scripts:/app/scripts:ro" in call, kind
        assert f"{repo}/packages:/app/packages:ro" in call, kind


def test_the_spike_edge_count_reaches_the_container_and_is_bounded(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches `--spike-edges` never arriving (a 10,000-edge run that is a 1,000-edge one), a
    count the spike was not built for, and the flag used on its own."""
    runner = Runner()
    kw: dict[str, Any] = {
        "run": runner,
        "lookup_subs": lambda directory: SUBS,
        "api_running": lambda compose: False,
    }
    seed_internal.seed_internal(
        "paysim", repo, spike_bulk_transport=True, spike_edges=10000, **kw
    )
    call = _seed_call(runner)
    assert call[call.index("--edges") + 1] == "10000"
    for bad in (50, 1_000_000):
        with pytest.raises(seed_internal.SeedRefused, match="100 to 100000"):
            seed_internal.seed_internal(
                "paysim", repo, spike_bulk_transport=True, spike_edges=bad, **kw
            )
    with pytest.raises(seed_internal.SeedRefused, match="only goes with"):
        seed_internal.seed_internal("paysim", repo, spike_edges=1000, **kw)
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        seed_internal, "seed_internal", lambda d, **k: seen.update(k) or []
    )
    assert (
        seed_internal.main(
            ["paysim", "--spike-bulk-transport", "--spike-edges", "10000"]
        )
        == 0
    )
    assert seen["spike_edges"] == 10000
    assert (
        seed_internal.main(
            ["paysim", "--spike-bulk-transport", "--spike-edges", "lots"]
        )
        == 2
    )


def test_the_bulk_chunk_is_the_size_that_left_no_more_strays_than_upsert() -> None:
    """The one measured reason for the number (ADR-058 Amendment 4). Catches it being raised for
    speed without a run that shows the strays do not rise."""
    assert seed_support.BULK_CHUNK == 100


def test_the_lookup_probe_runs_in_the_deployment_and_takes_its_sizes(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches a probe that stops the Conduit, makes a case or opens a vault; sizes that never
    arrive or that the probe was not built for; the sizes flag used alone; and a command line that
    does not know either flag."""
    kw: dict[str, Any] = {
        "lookup_subs": lambda directory: SUBS,
        "api_running": lambda compose: True,
    }
    runner = Runner()
    seed_internal.seed_internal(
        "paysim", repo, run=runner, probe_lookup_cost=True, **kw
    )
    call = _seed_call(runner)
    assert "scripts.probe_lookup_cost" in call and "--sizes" not in call
    assert "--case-name" not in call and "--vault" not in call
    assert not any("stop" in c for c in runner.calls)
    runner = Runner()
    seed_internal.seed_internal(
        "paysim",
        repo,
        run=runner,
        probe_lookup_cost=True,
        probe_sizes="2000,10000",
        **kw,
    )
    call = _seed_call(runner)
    assert call[call.index("--sizes") + 1] == "2000,10000"
    for bad in ("50,1000", "1000", "5000,1000", "1000,x", "1000,99999", "1,2,3,4,5,6"):
        with pytest.raises(seed_internal.SeedRefused, match="--probe-sizes"):
            seed_internal.seed_internal(
                "paysim",
                repo,
                run=Runner(),
                probe_lookup_cost=True,
                probe_sizes=bad,
                **kw,
            )
    with pytest.raises(seed_internal.SeedRefused, match="only goes with"):
        seed_internal.seed_internal(
            "paysim", repo, run=Runner(), probe_sizes="1000,5000", **kw
        )
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        seed_internal, "seed_internal", lambda d, **k: seen.update(k) or []
    )
    assert (
        seed_internal.main(
            ["paysim", "--probe-lookup-cost", "--probe-sizes", "1000,5000"]
        )
        == 0
    )
    assert seen["probe_lookup_cost"] is True and seen["probe_sizes"] == "1000,5000"
    assert seed_internal.main(["paysim", "--probe-lookup-cost", "--probe-sizes"]) == 2


@pytest.mark.parametrize("module", ["internal_demos.seed_enron", "scripts.seed_paysim"])
def test_run_directly_the_enron_and_paysim_seeds_default_to_bulk(module: str) -> None:
    """A direct run of either script defaults as `seed_internal` does, so it is not slower."""
    import importlib

    parse = importlib.import_module(module)._parse_args
    required = ["--case-name", "A case"]
    assert parse(required).method == "bulk"
    assert parse([*required, "--method", "upsert"]).method == "upsert"
