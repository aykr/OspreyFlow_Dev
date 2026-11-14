"""The CARRIES row "an upgrade must rebuild when the mapping changes" at `ospreyflow start --build`
(`scripts/refresh.py`; ADR-150 decision 4 and Amendment 2). Install, update and restore make the
search index again from the graph once the services are up; `start --build` did not, so a Lite
deployment brought to v0.5.2 from its own checkout kept an index made without the mapping's
fingerprint, the indexer wrote nothing to it and search stayed on the exact-identifier fallback
(the orchestrator, 14 November 2026, on osprey-small, rebuilt by hand). Now it rebuilds where
compose renders OpenSearch, after every `up` and restart, and says so in words when it cannot. A
deployment that renders no OpenSearch has nothing to rebuild.

Drives the real `scripts.refresh.refresh` with the compose commands recorded, as `test_refresh.py`
does, so nothing reaches Docker."""

from __future__ import annotations

from pathlib import Path

import pytest
from harness import search_rebuild
from scripts import refresh

from tests.test_refresh import Recorder, Registrar, repo  # noqa: F401

OPENSEARCH = (
    "services:\n"
    "  api:\n    image: osprey/api\n"
    "  opensearch:\n    image: opensearchproject/opensearch:2.19.1\n"
)


def _compose(repo: Path, text: str) -> None:  # noqa: F811
    (repo / "deploy/generated/local-lite/compose.yaml").write_text(text, encoding="utf-8")


def _rebuilds(calls: list[list[str]]) -> list[int]:
    return [
        i
        for i, c in enumerate(calls)
        if c[-len(search_rebuild.REBUILD) :] == search_rebuild.REBUILD
    ]


def test_start_build_rebuilds_the_index_after_every_up_where_compose_renders_opensearch(
    repo: Path,  # noqa: F811
) -> None:
    _compose(repo, OPENSEARCH)
    (repo / "apps/workspace/src/design/tokens.css").write_text(":root {}\n", encoding="utf-8")
    run = Recorder()
    refresh.refresh(repo, run=run, register=Registrar())
    rebuilt = _rebuilds(run.calls)
    assert len(rebuilt) == 1, run.calls
    ups = [i for i, c in enumerate(run.calls) if "up" in c]
    assert ups and max(ups) < rebuilt[0], "after the last up, so the Conduit is healthy"
    restarts = [i for i, c in enumerate(run.calls) if "restart" in c]
    assert restarts and max(restarts) < rebuilt[0], "after the theme's restart too"
    argv = run.calls[rebuilt[0]]
    out = repo / "deploy" / "generated" / "local-lite"
    assert argv[argv.index("-f") + 1] == str(out / "compose.yaml")
    assert argv[argv.index("--env-file") + 1] == str(out / "deployment.env")


def test_start_build_without_opensearch_rebuilds_nothing(repo: Path) -> None:  # noqa: F811
    run = Recorder()
    refresh.refresh(repo, run=run, register=Registrar())
    assert not _rebuilds(run.calls)


def test_a_rebuild_that_fails_says_search_stays_on_exact_identifiers_and_the_stack_is_up(
    repo: Path,  # noqa: F811
) -> None:
    _compose(repo, OPENSEARCH)
    register = Registrar()
    with pytest.raises(refresh.RefreshFailed) as failed:
        refresh.refresh(
            repo, run=Recorder(fail_on="scripts.rebuild_search_index"), register=register
        )
    said = str(failed.value)
    assert "search index" in said and "exact identifiers" in said, said
    assert "ospreyflow start --build" in said, "says what to run again"
    assert register.calls, "the sign-in accounts are registered whatever the rebuild does"
