"""ADR-055 §5: the seed refuses without the file, and from anything that is not a checkout."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.seed_paysim import FILE_NAME, NotProvisionedError, resolve_source

from demo_fixtures.paysim import COLUMNS


def test_the_seed_refuses_when_the_file_is_not_there(tmp_path: Path) -> None:
    with pytest.raises(NotProvisionedError, match="dataset not provisioned"):
        resolve_source(tmp_path, is_checkout=True)


def test_the_seed_refuses_from_a_bundle_even_when_the_file_is_there(tmp_path: Path) -> None:
    folder = tmp_path / "PaySIM_Dataset"
    folder.mkdir()
    (folder / FILE_NAME).write_text("x", encoding="utf-8")

    with pytest.raises(NotProvisionedError, match="checkout"):
        resolve_source(tmp_path, is_checkout=False)


def test_the_seed_finds_the_file_under_the_data_folder_from_a_checkout(tmp_path: Path) -> None:
    folder = tmp_path / "PaySIM_Dataset"
    folder.mkdir()
    (folder / FILE_NAME).write_text("x", encoding="utf-8")

    assert resolve_source(tmp_path, is_checkout=True) == folder / FILE_NAME


# --- running inside the deployment (ADR-055 Amendment 2) ---

from scripts.seed_paysim import _parse_args, scope_and_source  # noqa: E402


def test_the_seed_needs_either_a_case_to_make_or_a_scope_to_write_into() -> None:
    with pytest.raises(SystemExit):
        _parse_args([])
    assert _parse_args(["--investigation-scope", "abc"]).investigation_scope == "abc"
    assert _parse_args(["--case-name", "PaySim"]).case_name == "PaySim"


def test_grants_and_the_attestation_are_read_from_the_command_line() -> None:
    args = _parse_args(
        [
            "--case-name",
            "PaySim",
            "--grant",
            "a=author",
            "--grant",
            "b=editor",
            "--attested-checkout",
        ]
    )
    assert args.grant == ["a=author", "b=editor"]
    assert args.attested_checkout is True
    assert _parse_args(["--case-name", "x"]).attested_checkout is False


def test_a_seed_run_inside_a_container_refuses_without_the_hosts_attestation(
    tmp_path: Path,
) -> None:
    """The container has no `.git`, so the seed cannot tell a checkout from a bundle itself. The
    host-side command checks and says so with `--attested-checkout`; without it the container's own
    answer stands: not a checkout, refuse (ADR-035 §C1)."""
    folder = tmp_path / "PaySIM_Dataset"
    folder.mkdir()
    (folder / FILE_NAME).write_text("x", encoding="utf-8")

    with pytest.raises(NotProvisionedError, match="checkout"):
        scope_and_source(
            _parse_args(["--case-name", "x", "--data-dir", str(tmp_path)]),
            in_checkout=False,
        )
    assert (
        scope_and_source(
            _parse_args(["--case-name", "x", "--data-dir", str(tmp_path), "--attested-checkout"]),
            in_checkout=False,
        )
        == folder / FILE_NAME
    )


# --- the graph phase reports progress (it can take hours on a real ArcadeDB) ---


class _FakeGraph:
    def __init__(self) -> None:
        self.nodes = 0
        self.edges = 0

    async def get_node(self, node_id: str, principal: object) -> None:
        return None

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, tx: str) -> None: ...

    async def rollback_transaction(self, tx: str) -> None: ...

    async def upsert_nodes(self, nodes: list[object], tx: str) -> list[str]:
        self.nodes += len(nodes)
        return []

    async def upsert_edges(self, edges: list[object], tx: str) -> list[str]:
        self.edges += len(edges)
        return []


def test_the_graph_phase_prints_progress_for_nodes_and_for_edges(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Seen: five hours with a single line of output, so nobody could tell slow from stuck.
    Catches a graph load that writes silently."""
    import asyncio

    from scripts import seed_paysim

    from schemas.domain import Principal

    header = ",".join(COLUMNS)
    rows = [f"1,TRANSFER,10,C{i},0,0,M{i},0,0,1,0" for i in range(120)]  # step..isFlaggedFraud
    source = tmp_path / "log.csv"
    source.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    graph = _FakeGraph()

    asyncio.run(
        seed_paysim._load_graph(
            graph, source, Principal(id="s", clearance="OFFICIAL", org_unit="u")
        )  # type: ignore[arg-type]
    )

    shown = capsys.readouterr().out
    assert (graph.nodes, graph.edges) == (240, 120)
    assert "accounts written" in shown and "transactions written" in shown
    assert "240" in shown and "120" in shown


class _HalfLoadedGraph(_FakeGraph):
    async def get_node(self, node_id: str, principal: object) -> object:
        return object()


def _one_fraud_row(tmp_path: Path) -> Path:
    header = ",".join(COLUMNS)
    source = tmp_path / "one.csv"
    source.write_text(header + "\n1,TRANSFER,10,C1,0,0,M1,0,0,1,0\n", encoding="utf-8")
    return source


def test_a_graph_that_already_has_the_accounts_is_refused_and_says_how_to_replace_it(
    tmp_path: Path,
) -> None:
    """Catches a re-run silently writing over a finished load (transactions would be counted twice),
    and a refusal that leaves the owner of an interrupted run with no way forward."""
    import asyncio

    from scripts import seed_paysim

    from schemas.domain import Principal

    graph = _HalfLoadedGraph()
    with pytest.raises(NotProvisionedError, match="--replace-graph"):
        asyncio.run(
            seed_paysim._load_graph(
                graph,  # type: ignore[arg-type]
                _one_fraud_row(tmp_path),
                Principal(id="s", clearance="OFFICIAL", org_unit="u"),
            )
        )
    assert (graph.nodes, graph.edges) == (0, 0)


def test_the_graph_sample_limits_what_is_written(tmp_path: Path) -> None:
    """Catches --graph-fraud-rows being parsed but never reaching the selection."""
    import asyncio

    from scripts import seed_paysim

    from schemas.domain import Principal

    header = ",".join(COLUMNS)
    rows = [f"1,TRANSFER,10,C{i},0,0,M{i},0,0,1,0" for i in range(10)]
    source = tmp_path / "ten.csv"
    source.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    graph = _FakeGraph()

    asyncio.run(
        seed_paysim._load_graph(
            graph,  # type: ignore[arg-type]
            source,
            Principal(id="s", clearance="OFFICIAL", org_unit="u"),
            fraud_rows=3,
        )
    )

    assert (graph.nodes, graph.edges) == (6, 3)


def test_replace_graph_and_the_sample_size_are_read_from_the_command_line() -> None:
    args = _parse_args(["--case-name", "x", "--replace-graph", "--graph-fraud-rows", "500"])
    assert args.replace_graph is True and args.graph_fraud_rows == 500
    plain = _parse_args(["--case-name", "x"])
    assert plain.replace_graph is False and plain.graph_fraud_rows is None
