"""ADR-150 decision 7 and ADR-114 Amendment 35 point 2: a deployment with an OpenSearch tells the
Conduit and the worker where it is, with the deployment's own index alias; one without says nothing.
A restore into a deployment with an OpenSearch ends by rebuilding the index from the graph, in the
Conduit's container; one without has nothing to rebuild."""

from __future__ import annotations

from pathlib import Path

import pytest
from harness import restore
from harness.render import load_config, render
from tools.layout import CORE

from schemas.deployment import OspreyConfig, SearchBackend
from tests.harness.test_render import FIXTURE_CONFIG, _fake_resolver


def _config(tmp_path: Path, search: SearchBackend) -> OspreyConfig:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    return loaded.model_copy(
        update={
            "components": loaded.components.model_copy(
                update={"source_path": str(CORE), "search": search}
            )
        }
    )


def _env(config: OspreyConfig) -> list[str]:
    return render(config, resolver=_fake_resolver).artefacts["deployment.env"].splitlines()


def test_a_deployment_with_opensearch_tells_the_conduit_and_worker_where_it_is(
    tmp_path: Path,
) -> None:
    env = _env(_config(tmp_path, SearchBackend.OPENSEARCH))
    assert "OPENSEARCH_HOST=opensearch" in env and "OPENSEARCH_PORT=9200" in env
    alias = [line for line in env if line.startswith("OSPREY_SEARCH_INDEX_ALIAS=")]
    assert len(alias) == 1 and alias[0].startswith("OSPREY_SEARCH_INDEX_ALIAS=ospreyflow-")


def test_a_deployment_without_opensearch_names_none(tmp_path: Path) -> None:
    env = _env(_config(tmp_path, SearchBackend.POSTGRES_FULLTEXT))
    assert not [line for line in env if line.startswith(("OPENSEARCH_", "OSPREY_SEARCH_INDEX"))]


@pytest.mark.parametrize(("services", "rebuilt"), [("opensearch: {}\n  api: {}", True),
                                                   ("api: {}", False)])  # fmt: skip
def test_a_restore_rebuilds_the_index_only_where_there_is_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, services: str, rebuilt: bool
) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text(f"name: osprey-small\nservices:\n  {services}\n", encoding="utf-8")
    ran: list[list[str]] = []
    monkeypatch.setattr(restore, "_run", lambda command, **_: ran.append(command) or "")
    restore.rebuild_search_index(compose)
    if rebuilt:
        assert ran and ran[0][-6:] == ["exec", "-T", "api", "python", "-m",
                                       "scripts.rebuild_search_index"][-6:]  # fmt: skip
    else:
        assert ran == []


def test_the_restore_rebuilds_after_every_store_is_back() -> None:
    """Called last in `run_restore`: the index is read from the restored graph and texts."""
    import inspect

    source = inspect.getsource(restore.run_restore)
    assert source.rstrip().splitlines()[-2].strip() == "rebuild_search_index(compose_file)"
