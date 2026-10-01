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


def test_inspect_needs_no_case_and_reads_the_record_it_is_given() -> None:
    """Read-only mode must not require (or create) a case."""
    args = _parse_args(["--inspect", "--inspect-record", "#169:80"])
    assert args.inspect is True and args.inspect_record == "#169:80"
    with pytest.raises(SystemExit):
        _parse_args([])


def test_reset_graph_database_is_read_from_the_command_line_and_off_by_default() -> None:
    assert _parse_args(["--case-name", "x", "--reset-graph-database"]).reset_graph_database is True
    assert _parse_args(["--case-name", "x"]).reset_graph_database is False


def test_a_vault_moves_the_graph_database_and_the_analytics_file_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a graph that goes to the vault while the events still go to the shared file."""
    from scripts import seed_paysim

    monkeypatch.setenv("ARCADEDB_DATABASE", "ospreyflow")
    plain = _parse_args(["--case-name", "x", "--analytics-db-path", "/d/analytics.duckdb"])
    assert seed_paysim._locations(plain) == ("ospreyflow", "/d/analytics.duckdb")
    vaulted = _parse_args(
        ["--case-name", "x", "--analytics-db-path", "/d/analytics.duckdb", "--vault", "paysim"]
    )
    assert seed_paysim._locations(vaulted) == (
        "vault_paysim",
        "/d/vaults/paysim/analytics.duckdb",
    )


def test_a_bad_vault_id_is_refused_before_anything_is_touched() -> None:
    import asyncio

    from scripts import seed_paysim

    args = _parse_args(["--case-name", "x", "--vault", "../x"])
    assert asyncio.run(seed_paysim._run(args)) == 2


# --- stray edge records: the repair and the check after a load (ADR-056 Amendment 16) ---


def test_the_repair_needs_no_case_and_removes_nothing_unless_told_to() -> None:
    """Catches a repair that demands a case, or one that deletes by default."""
    args = _parse_args(["--repair-strays", "--vault", "paysim"])
    assert args.repair_strays is True and args.apply is False and args.repair_limit is None
    applied = _parse_args(["--repair-strays", "--apply", "--repair-limit", "1"])
    assert applied.apply is True and applied.repair_limit == 1
    with pytest.raises(SystemExit):
        _parse_args(["--apply"])  # an apply with nothing to apply


def test_the_restore_is_its_own_mode_and_the_two_modes_are_not_mixed() -> None:
    """Catches `--restore-missing` demanding a case, an `--apply` that goes with nothing, and both
    modes at once (two sets of writes in one run, one of them unreviewed)."""
    args = _parse_args(["--restore-missing", "--vault", "paysim"])
    assert args.restore_missing is True and args.apply is False
    assert _parse_args(["--restore-missing", "--apply"]).apply is True
    with pytest.raises(SystemExit):
        _parse_args(["--restore-missing", "--repair-strays"])


class _Cfg:
    """Stands in for the client: remembers which database it was pointed at."""

    seen: dict[str, object]

    def __init__(self, config: object) -> None:
        type(self).seen["database"] = getattr(config, "database", None)

    async def aclose(self) -> None:
        type(self).seen["closed"] = True


def _patched(monkeypatch: pytest.MonkeyPatch, **names: object) -> dict[str, object]:
    from scripts import seed_paysim

    seen: dict[str, object] = {}
    _Cfg.seen = seen
    monkeypatch.setattr(seed_paysim, "ArcadeDBClient", _Cfg)
    for name, value in names.items():
        monkeypatch.setattr(seed_paysim, name, value)
    return seen


def _edges() -> dict[str, object]:
    return {"paysim-tx-1": type("E", (), {"source": "paysim-acct-a"})()}


def test_the_repair_runs_against_the_vaults_own_database_for_this_seeds_own_ids(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catches a repair pointed at the shared database, at another seed's ids, one that applies
    when it was asked for a dry run, or one given no list of what the dataset writes."""
    import asyncio

    from scripts import seed_paysim
    from scripts.seed_support import RepairReport

    captured: dict[str, object] = {}

    async def fake_repair(client: object, **kw: object) -> RepairReport:
        captured.update(kw)
        return RepairReport(planned=[("paysim-tx-1", ["#1:1", "#1:2"])])

    seen = _patched(
        monkeypatch,
        repair_ids_stored_twice=fake_repair,
        _edges_to_write=lambda args, principal, source: _edges(),
        scope_and_source=lambda args, in_checkout: Path("x.csv"),
    )
    args = _parse_args(["--repair-strays", "--vault", "paysim", "--repair-limit", "3"])
    assert asyncio.run(seed_paysim._run(args)) == 0
    assert seen["database"] == "vault_paysim" and seen["closed"] is True
    assert captured["prefix"] == "paysim-tx-" and captured["apply"] is False
    assert captured["limit"] == 3 and captured["expected"] == {"paysim-tx-1": "paysim-acct-a"}
    assert callable(captured["rewrite"]) and "dry run" in capsys.readouterr().out


def test_the_restore_runs_against_the_vaults_own_database_and_applies_only_when_told(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catches a restore that writes on a dry run, that goes to the shared database, or that never
    says how many edges it expected."""
    import asyncio

    from scripts import seed_paysim
    from scripts.seed_support import RepairReport

    captured: dict[str, object] = {}

    async def fake_restore(client: object, **kw: object) -> RepairReport:
        captured.update(kw)
        return RepairReport(planned=[("paysim-tx-1", [])])

    seen = _patched(
        monkeypatch,
        restore_missing_edges=fake_restore,
        _edges_to_write=lambda args, principal, source: _edges(),
        scope_and_source=lambda args, in_checkout: Path("x.csv"),
    )
    args = _parse_args(["--restore-missing", "--vault", "paysim"])
    assert asyncio.run(seed_paysim._run(args)) == 0
    assert seen["database"] == "vault_paysim" and captured["apply"] is False
    assert captured["expected"] == {"paysim-tx-1": "paysim-acct-a"}
    out = capsys.readouterr().out
    assert "dry run" in out and "1 edge" in out


def test_a_repair_that_hits_a_surprise_stops_and_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catches an anomaly that is swallowed and reported as success, in either mode."""
    import asyncio

    from scripts import seed_paysim
    from scripts.seed_support import RepairAnomaly

    async def fake(client: object, **kw: object) -> object:
        raise RepairAnomaly("paysim-tx-1: after writing it, 0 record(s) are stored")

    _patched(
        monkeypatch,
        repair_ids_stored_twice=fake,
        restore_missing_edges=fake,
        _edges_to_write=lambda args, principal, source: _edges(),
        scope_and_source=lambda args, in_checkout: Path("x.csv"),
    )
    for flag in ("--repair-strays", "--restore-missing"):
        assert asyncio.run(seed_paysim._run(_parse_args([flag, "--apply"]))) == 3
        assert "paysim-tx-1" in capsys.readouterr().err


def test_without_the_dataset_a_repair_refuses_before_touching_the_store(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catches a repair that carries on without the file it rewrites from."""
    import asyncio

    from scripts import seed_paysim

    def refuse(args: object, in_checkout: bool) -> Path:
        raise NotProvisionedError("dataset not provisioned")

    seen = _patched(monkeypatch, scope_and_source=refuse)
    args = _parse_args(["--restore-missing", "--apply", "--vault", "paysim"])
    assert asyncio.run(seed_paysim._run(args)) == 1
    assert "database" not in seen and "not provisioned" in capsys.readouterr().err


def test_the_edges_a_repair_rewrites_are_the_ones_the_load_writes(tmp_path: Path) -> None:
    """Catches a restore built from a different selection than the load (the full file instead of
    the fraud neighbourhood would write seven million edges), or ids that differ from the load's."""
    from scripts import seed_paysim

    from demo_fixtures.paysim import build_graph_writes, fraud_accounts, read_paysim
    from schemas.domain import Principal

    path = tmp_path / "rows.csv"
    header = ",".join(COLUMNS)
    rows = [
        "1,PAYMENT,10.0,C1,0,0,M1,0,0,0,0",
        "1,TRANSFER,500.0,C2,0,0,C3,0,0,1,0",
        "2,CASH_OUT,500.0,C3,0,0,C4,0,0,1,0",
        "3,PAYMENT,5.0,C9,0,0,M9,0,0,0,0",
    ]
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    assert COLUMNS[:2] == ("step", "type")  # the row layout above follows COLUMNS
    principal = Principal(id="paysim-seed-worker", clearance="OFFICIAL", org_unit="u")
    args = _parse_args(
        ["--restore-missing", "--graph-fraud-rows", "1", "--data-dir", str(tmp_path)]
    )
    found = seed_paysim._edges_to_write(args, principal, path)
    accounts = fraud_accounts(read_paysim(path), limit=1)
    touching = [r for r in read_paysim(path) if r.origin in accounts or r.destination in accounts]
    _, edges = build_graph_writes(touching, created_by=principal.id, handling=seed_paysim._HANDLING)
    assert set(found) == {e.id for e in edges} and 0 < len(found) < 4
    assert all(found[e.id].source == e.source for e in edges)
