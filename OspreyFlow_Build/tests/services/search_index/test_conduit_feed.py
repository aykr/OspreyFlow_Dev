"""ADR-150 Amendment 4, offline: where the Conduit feeds the search index, and that it starts the feed
as the worker does. The feed itself, a write searchable through a real Conduit, is
`test_conduit_feed_live.py`'s.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[4] / "OspreyFlow_Core"


@pytest.mark.parametrize(
    ("job_worker", "opensearch", "feeds"),
    [
        ("conduit", {"OPENSEARCH_HOST": "opensearch"}, True),
        ("conduit", {"OPENSEARCH_URL": "https://search.example.org"}, True),
        ("conduit", {}, False),  # no index: nothing to feed (postgres-fulltext)
        ("service", {"OPENSEARCH_HOST": "opensearch"}, False),  # the worker feeds it
        (None, {"OPENSEARCH_HOST": "opensearch"}, False),  # a test app, or an older render
    ],
    ids=["conduit-host", "conduit-url", "conduit-no-index", "worker", "unset"],
)
def test_the_conduit_feeds_the_index_only_where_it_runs_the_job_loop_and_there_is_one(
    job_worker: str | None, opensearch: dict[str, str], feeds: bool
) -> None:
    from services.api.app import index_feed_in_conduit

    environ = {**opensearch, **({"OSPREY_JOB_WORKER": job_worker} if job_worker else {})}
    assert index_feed_in_conduit(environ) is feeds


def _rendered_env(profile: str) -> dict[str, str]:
    from harness.render import render

    from schemas.deployment import OspreyConfig

    network = {"network": {"public_origin": "https://osprey.example.org"}} if profile == "small" else {}
    artefacts = render(OspreyConfig.model_validate({"profile": profile, **network}),
                       allow_unpinned=True).artefacts  # fmt: skip
    lines = artefacts["deployment.env"].splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def test_small_as_rendered_has_its_conduit_feed_the_index() -> None:
    """The GOV.UK demo's shape (16 November 2026): Small renders no worker and an OpenSearch, so its
    Conduit is the index's only feeder. Red before Amendment 4: nothing was."""
    from services.api.app import index_feed_in_conduit

    env = _rendered_env("small")
    assert env.get("OPENSEARCH_HOST") and env.get("OSPREY_JOB_WORKER") == "conduit"
    assert index_feed_in_conduit(env) is True


def test_local_lite_as_rendered_feeds_the_index_where_it_runs_an_opensearch() -> None:
    from services.api.app import index_feed_in_conduit
    from services.search_index.run import configured

    env = _rendered_env("local-lite")
    assert env.get("OSPREY_JOB_WORKER") == "conduit"
    assert index_feed_in_conduit(env) is configured(env)


def test_cluster_s_conduit_never_feeds_beside_its_worker() -> None:
    import yaml
    from harness.render import render

    from services.api.app import index_feed_in_conduit
    from tests.harness.test_cluster_render import _resolver, cluster_config

    values = yaml.safe_load(render(cluster_config(), resolver=_resolver).artefacts["values.yaml"])
    env = {**values["environment"], "OPENSEARCH_HOST": "opensearch"}
    assert index_feed_in_conduit(env) is False


def test_no_feed_is_started_where_no_opensearch_is_configured() -> None:
    """None, before any client is made or any task started: `start_index_feed` touches none of
    its arguments when there is no index."""
    from services.search_index.run import start_index_feed

    feed = start_index_feed(None, None, None, "me", None, environ={})  # type: ignore[arg-type]
    assert feed is None


def _calls(path: Path, name: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and ((isinstance(node.func, ast.Name) and node.func.id == name)
             or (isinstance(node.func, ast.Attribute) and node.func.attr == name))
    )  # fmt: skip


def test_the_worker_and_the_conduit_start_the_feed_one_way() -> None:
    """Both through `start_index_feed`, and neither builds an indexer or runs `run_indexer` of its
    own, so the Conduit's feed is the worker's: the same lease, the same client, the same close."""
    for rel in ("services/api/app.py", "services/api/worker_main.py"):
        path = CORE / rel
        assert _calls(path, "start_index_feed") == 1, rel
        assert _calls(path, "run_indexer") == 0, rel
        assert _calls(path, "SearchIndexer") == 0, rel


def test_the_one_way_check_names_a_second_feed() -> None:
    planted = "async def f(i, s, me, stop):\n    await run_indexer(i, s, me, stop)\n"
    path = Path(__file__).with_name("_planted_feed.py")
    try:
        path.write_text(planted, encoding="utf-8")
        assert _calls(path, "run_indexer") == 1
    finally:
        path.unlink(missing_ok=True)
