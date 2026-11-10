"""ADR-147 Amendment 1, decision 2: both command-line builds register the gazetteer's dataset only
once its places are committed, and say the points' words after the load: `python -m
scripts.build_local_basemap` (`_run`) and `ospreyflow map build` (`map_admin._build_here`). A build
that fails after the load registers nothing, so no empty dataset is left for a case's Author to add.

The stores are stood in (offline): a graph that records its commit and rollback, and the dataset
registration recorded where it is called. What runs is each build's own sequence.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import scripts.build_local_basemap as script
from services.api import map_admin, map_places

from adapters.graph_arcadedb import adapter as graph_adapter_module
from adapters.graph_arcadedb import client as graph_client_module


class _Events:
    def __init__(self) -> None:
        self.seen: list[str] = []


class _Client:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    async def create_database_if_absent(self) -> None:
        pass

    async def aclose(self) -> None:
        pass


def _graph_class(events: _Events) -> type:
    class _Graph:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def apply_schema(self, _ontology: object) -> None:
            pass

        async def begin_transaction(self) -> str:
            events.seen.append("begin")
            return "tx-1"

        async def commit_transaction(self, _tx: str) -> None:
            events.seen.append("commit")

        async def rollback_transaction(self, _tx: str) -> None:
            events.seen.append("rollback")

    return _Graph


def _recording_registration(events: _Events) -> Callable[..., Any]:
    async def register(region: str, *, by: str, unit: str) -> object:
        events.seen.append(f"register {region} for {unit}")
        return object()

    return register


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> _Events:
    events = _Events()
    monkeypatch.setattr(
        map_places, "register_gazetteer_dataset_from_env", _recording_registration(events)
    )
    async def check(unit: str, *, region: str) -> None:
        events.seen.append(f"check {unit}")
        if unit == "unit-nowhere":
            raise map_places.UnknownUnit(f"No case or dataset ... {unit!r}")

    monkeypatch.setattr(map_places, "check_unit_from_env", check)

    async def refresh(_graph: object, _scheme: object, gazetteer: str) -> int:
        events.seen.append(f"refresh {gazetteer}")
        return 0

    monkeypatch.setattr(map_places, "refresh_case_copies_from_env", refresh)
    monkeypatch.setattr(script, "ArcadeDBClient", _Client)
    monkeypatch.setattr(script, "GraphArcadeDBAdapter", _graph_class(events))
    monkeypatch.setattr(graph_client_module, "ArcadeDBClient", _Client)
    monkeypatch.setattr(graph_adapter_module, "GraphArcadeDBAdapter", _graph_class(events))
    real_print = print

    def printing(*args: Any, **kwargs: Any) -> None:
        if args and args[0] == map_places.NO_POINTS_HERE:
            events.seen.append("points words")
        real_print(*args, **kwargs)

    monkeypatch.setattr("builtins.print", printing)
    return events


def _script_args(*unit: str) -> argparse.Namespace:
    return script._parse_args(
        [
            *(unit or ("--unit", "unit-7")),
            "--region",
            "rutland",
            "--output-dir",
            "/tmp/unused",
            "--planetiler-jar",
            "/tmp/unused.jar",
        ]
    )


class _Report:
    nodes_created, nodes_referenced, rejections = 3, 0, []


class _Result:
    pmtiles_path = Path("/tmp/unused/rutland.pmtiles")
    gazetteer_report = _Report()


async def test_the_script_registers_after_the_places_commit(
    events: _Events, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def build(**kwargs: Any) -> _Result:
        events.seen.append(f"load into {kwargs['gazetteer_dataset']}")
        return _Result()

    monkeypatch.setattr(script, "build_local_basemap", build)
    assert await script._run(_script_args()) == 0
    assert events.seen == [
        "check unit-7", "begin", "load into gazetteer-osm-rutland", "commit", "points words",
        "register rutland for unit-7", "refresh gazetteer-osm-rutland",
    ]  # fmt: skip


async def test_the_script_registers_nothing_when_the_build_fails(
    events: _Events, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def build(**_kwargs: Any) -> _Result:
        events.seen.append("load")
        raise RuntimeError("planetiler stopped")

    monkeypatch.setattr(script, "build_local_basemap", build)
    with pytest.raises(RuntimeError):
        await script._run(_script_args())
    assert events.seen == ["check unit-7", "begin", "load", "rollback"]


@pytest.mark.parametrize("fails", [False, True], ids=["finished", "failed-after-load"])
async def test_the_cli_build_registers_after_the_places_commit(
    events: _Events, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fails: bool
) -> None:
    async def load_gazetteer(*_args: Any, **kwargs: Any) -> _Report:
        events.seen.append(f"load into {kwargs['dataset']}")
        return _Report()

    async def build_basemap(
        _admin: object, *, load_places: Any, settle: Any, **_kwargs: Any
    ) -> tuple[str, int, int, int]:
        counts = await load_places(tmp_path / "rutland.osm.pbf")
        if fails:
            raise RuntimeError("planetiler stopped")
        await settle()
        return ("rutland.pmtiles", *counts)

    monkeypatch.setattr(script, "load_gazetteer", load_gazetteer)
    monkeypatch.setattr(map_admin, "build_basemap", build_basemap)
    code = await map_admin._build_here(object(), "cli:owner", "rutland", "unit-7")  # type: ignore[arg-type]
    if fails:
        assert code == 1
        assert events.seen == ["check unit-7", "begin", "load into gazetteer-osm-rutland", "rollback"]
    else:
        assert code == 0
        assert events.seen == [
            "check unit-7", "begin", "load into gazetteer-osm-rutland", "commit", "points words",
            "register rutland for unit-7", "refresh gazetteer-osm-rutland",
        ]  # fmt: skip


async def test_the_script_needs_a_unit_and_refuses_an_unknown_one_before_anything_is_built(
    events: _Events, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR-147 Amendment 2 (the owner's ruling 8): the unit is the build's setting, refused in words
    before the graph is opened."""

    async def build(**_kwargs: Any) -> _Result:
        events.seen.append("load")
        return _Result()

    monkeypatch.setattr(script, "build_local_basemap", build)
    assert await script._run(script._parse_args([
        "--region", "rutland", "--output-dir", "/tmp/unused", "--planetiler-jar", "/tmp/u.jar",
    ])) == 2  # fmt: skip
    assert "--unit" in capsys.readouterr().err
    assert await script._run(_script_args("--unit", "unit-nowhere")) == 1
    assert events.seen == ["check unit-nowhere"]


async def test_the_cli_build_refuses_an_unknown_unit_before_anything_is_built(
    events: _Events,
) -> None:
    code = await map_admin._build_here(object(), "cli:owner", "rutland", "unit-nowhere")  # type: ignore[arg-type]
    assert (code, events.seen) == (1, ["check unit-nowhere"])
