"""v0.6.0 item 10 (the owner, 15 November 2026): the Great Britain basemap built as a step of the demo's
install, its gazetteer settlements only. Three faults platform found, each held here offline:

1. The gazetteer loaded every place in one ArcadeDB transaction (`map_admin._build_here` and the Admin
   route). It now commits a batch at a time (`GAZETTEER_BATCH`), each batch rolled back alone if it
   fails, and the counts summed.
2. planetiler ran with the JVM's own default heap. It is now given `-Xmx` explicitly.
3. `ospreyflow map build` never wrote the places' points: the analytics store is the Conduit's, an
   embedded DuckDB file one process holds at a time. The command line now opens it the way the
   Conduit does (`analytics_store.open_analytics`), so a build run while the Conduit is stopped (the
   install step) writes the points; while the Conduit holds the store, the open is refused, and the
   build goes on and says so, as before.

The stores are stood in: a graph that records its transactions, and an analytics opener that refuses
while another holder has the file, as DuckDB's lock does (rule 15: the fake refuses what the real one
refuses).
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest
import scripts.build_local_basemap as script
from schemas.ingest import LoadReport
from services.api import analytics_store, map_admin, map_places

from tests.test_gazetteer_build_registration_order import _Events, events  # noqa: F401


class _Graph:
    def __init__(self) -> None:
        self.seen: list[str] = []
        self._n = 0

    async def begin_transaction(self) -> str:
        self._n += 1
        self.seen.append(f"begin tx-{self._n}")
        return f"tx-{self._n}"

    async def commit_transaction(self, tx: str) -> None:
        self.seen.append(f"commit {tx}")

    async def rollback_transaction(self, tx: str) -> None:
        self.seen.append(f"rollback {tx}")


def _rows(count: int) -> Iterator[dict[str, str]]:
    for i in range(count):
        yield {"osm_id": str(i), "name": f"Place {i}", "lat": "51.5", "lon": "-0.1"}


def _recording_recipe(graph: _Graph, fail_on_batch: int | None = None) -> Any:
    calls = {"n": 0}

    async def run_recipe(_recipe: object, rows: Any, *, tx: str, load_id: str, **_: Any) -> Any:
        calls["n"] += 1
        rows = list(rows)
        graph.seen.append(f"load {len(rows)} on {tx}")
        if calls["n"] == fail_on_batch:
            raise RuntimeError("ArcadeDB refused the batch")
        report = LoadReport(load_id=load_id, recipe_id="osm", recipe_version=1,
                            rows_read=len(rows), nodes_created=len(rows))  # fmt: skip
        return report, []

    return run_recipe


async def _load(graph: _Graph, monkeypatch: pytest.MonkeyPatch, rows: int, **recipe: Any) -> Any:
    monkeypatch.setattr(script, "read_osm_places", lambda _path: _rows(rows))
    monkeypatch.setattr(script, "run_recipe", _recording_recipe(graph, **recipe))
    monkeypatch.setattr(script, "GAZETTEER_BATCH", 1000)
    return await script.load_gazetteer(
        Path("/unused.osm.pbf"), graph=graph, ontology=object(), principal=_principal(),  # type: ignore[arg-type]
        load_id="load-osm-gazetteer-test", dataset="gazetteer-osm-test",
    )  # fmt: skip


def _principal() -> Any:
    from schemas.domain import Principal

    return Principal(id="system", clearance="OFFICIAL", org_unit="unit-1")


async def test_the_gazetteer_commits_a_batch_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = _Graph()
    report = await _load(graph, monkeypatch, 2_500)
    assert graph.seen == [
        "begin tx-1", "load 1000 on tx-1", "commit tx-1",
        "begin tx-2", "load 1000 on tx-2", "commit tx-2",
        "begin tx-3", "load 500 on tx-3", "commit tx-3",
    ]  # fmt: skip
    assert (report.rows_read, report.nodes_created) == (2_500, 2_500)


async def test_a_failed_batch_is_rolled_back_alone_and_the_load_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _Graph()
    with pytest.raises(RuntimeError, match="refused the batch"):
        await _load(graph, monkeypatch, 2_500, fail_on_batch=2)
    assert graph.seen == [
        "begin tx-1", "load 1000 on tx-1", "commit tx-1",
        "begin tx-2", "load 1000 on tx-2", "rollback tx-2",
    ]  # fmt: skip


def test_planetiler_is_given_its_heap_explicitly(tmp_path: Path) -> None:
    """Without `-Xmx` the JVM takes a quarter of the machine's memory, which on the demo's server is
    neither what was measured nor bounded beside the running demo."""
    jar = tmp_path / "planetiler.jar"
    jar.write_bytes(b"")
    captured: list[list[str]] = []

    def run(argv: list[str], *, check: bool) -> subprocess.CompletedProcess[bytes]:
        captured.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    script.run_planetiler(tmp_path / "x.osm.pbf", tmp_path / "x.pmtiles", jar_path=jar,
                          subprocess_run=run)  # fmt: skip
    assert captured[1][:3] == ["java", f"-Xmx{script.PLANETILER_HEAP}", "-jar"]
    script.run_planetiler(tmp_path / "x.osm.pbf", tmp_path / "x.pmtiles", jar_path=jar,
                          subprocess_run=run, heap="3g")  # fmt: skip
    assert captured[3][:3] == ["java", "-Xmx3g", "-jar"]


class _Analytics:
    """Stands in for the store `load_gazetteer` writes points into."""


def _opener(held_elsewhere: bool, seen: list[str]) -> Any:
    async def open_analytics(engine: str, *, duckdb_path: str, handling_scheme: object) -> Any:
        seen.append(f"open {engine}")
        if held_elsewhere:
            # DuckDB's own refusal when another process holds the file.
            raise duckdb.IOException(f'IO Error: Could not set lock on file "{duckdb_path}"')

        async def close() -> None:
            seen.append("close analytics")

        return _Analytics(), close

    return open_analytics


@pytest.mark.parametrize("conduit_running", [False, True], ids=["conduit-stopped", "conduit-running"])
async def test_the_cli_build_writes_the_points_when_it_can_open_the_store(
    events: _Events,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    conduit_running: bool,
) -> None:
    given: dict[str, Any] = {}

    async def load_gazetteer(*_args: Any, **kwargs: Any) -> Any:
        given.update(kwargs)
        events.seen.append(f"load into {kwargs['dataset']}")
        return LoadReport(load_id="l", recipe_id="osm", recipe_version=1, nodes_created=3)

    async def build_basemap(
        _admin: object, *, load_places: Any, settle: Any, **_kwargs: Any
    ) -> tuple[str, int, int, int]:
        counts = await load_places(tmp_path / "rutland.osm.pbf")
        await settle()
        return ("rutland.pmtiles", *counts)

    monkeypatch.setattr(script, "load_gazetteer", load_gazetteer)
    monkeypatch.setattr(map_admin, "build_basemap", build_basemap)
    monkeypatch.setattr(analytics_store, "open_analytics", _opener(conduit_running, events.seen))
    code = await map_admin._build_here(object(), "cli:owner", "rutland", "unit-7")  # type: ignore[arg-type]
    assert code == 0
    # The load opens and commits its own batches: the command line holds no transaction of its own.
    assert "tx" not in given or given["tx"] is None
    if conduit_running:
        assert given["analytics"] is None
        assert "points words" in events.seen
    else:
        assert isinstance(given["analytics"], _Analytics)
        assert "points words" not in events.seen
        assert events.seen[-1] == "close analytics"
    assert events.seen[:3] == ["check unit-7", "open duckdb", "load into gazetteer-osm-rutland"]
    assert map_places.NO_POINTS_HERE.startswith("The places' points were not written")
