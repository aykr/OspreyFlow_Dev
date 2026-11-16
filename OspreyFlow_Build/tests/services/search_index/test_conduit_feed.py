"""ADR-150 Amendment 4, offline: where the Conduit feeds the search index, and that it starts the
feed as the worker does. The feed itself, a write searchable through a real Conduit, is
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

    network = (
        {"network": {"public_origin": "https://osprey.example.org"}} if profile == "small" else {}
    )
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


def test_local_lite_as_rendered_feeds_the_index_exactly_where_it_runs_an_opensearch() -> None:
    """Both ways, from the render itself: the Conduit feeds where the compose file runs an
    `opensearch` service, and never where it runs none (`search: postgres-fulltext`)."""
    import yaml
    from harness.render import render

    from schemas.deployment import OspreyConfig
    from services.api.app import index_feed_in_conduit

    for search in ("opensearch", "postgres-fulltext"):
        config = OspreyConfig.model_validate(
            {"profile": "local-lite", "components": {"search": search}}
        )
        artefacts = render(config, allow_unpinned=True).artefacts
        services = yaml.safe_load(artefacts["compose.yaml"])["services"]
        lines = artefacts["deployment.env"].splitlines()
        env = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
        assert env.get("OSPREY_JOB_WORKER") == "conduit"
        assert index_feed_in_conduit(env) is ("opensearch" in services), search


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


def test_the_one_way_check_names_a_second_feed(tmp_path: Path) -> None:
    path = tmp_path / "planted_feed.py"
    path.write_text("async def f(i, s, me, stop):\n    await run_indexer(i, s, me, stop)\n")
    assert _calls(path, "run_indexer") == 1


async def test_a_feed_s_close_stops_it_and_closes_what_it_opened() -> None:
    """`IndexFeed.close`: the stop is set, the batch in hand is waited for, and every close in
    `closing` is awaited, in order."""
    import asyncio

    from services.search_index.run import IndexFeed

    stop = asyncio.Event()
    closed: list[str] = []

    async def drain() -> None:
        await stop.wait()

    async def close_client() -> None:
        closed.append("client")

    feed = IndexFeed(asyncio.create_task(drain()), stop, "alias", [close_client])
    await feed.close(timeout=5)
    assert stop.is_set() and feed.task.done() and not feed.task.cancelled()
    assert closed == ["client"]


async def test_a_feed_past_its_bound_is_cancelled_and_still_closes_its_client() -> None:
    """A batch slower than the bound is cancelled (its rows stay in the outbox), and the client is
    closed all the same: a shutdown never waits on OpenSearch past `JOB_LOOP_STOP_SECONDS`."""
    import asyncio

    from services.search_index.run import IndexFeed

    closed: list[str] = []

    async def slow_batch() -> None:
        await asyncio.sleep(3600)  # a batch that ignores the stop

    async def close_client() -> None:
        closed.append("client")

    feed = IndexFeed(asyncio.create_task(slow_batch()), asyncio.Event(), "alias", [close_client])
    await asyncio.wait_for(feed.close(timeout=0.05), timeout=5)
    assert feed.task.cancelled()
    assert closed == ["client"]


async def test_refused_search_settings_start_the_conduit_without_a_feed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A setting the client refuses (here an unknown signing, `SearchIndexConfigError` from the real
    `SearchIndexConfig.from_env`) is logged in its own words and the Conduit starts with no feed,
    as the query side falls back on the same setting: never a start that fails on it."""
    import logging

    from services.api.app import conduit_index_feed

    environ = {"OPENSEARCH_HOST": "opensearch", "OPENSEARCH_SIGNING": "rot13"}
    with caplog.at_level(logging.ERROR, logger="services.api.app"):
        assert conduit_index_feed(None, None, None, None, environ=environ) is None
    (record,) = [r for r in caplog.records if r.name == "services.api.app"]
    assert record.levelno == logging.ERROR
    assert "cannot feed the search index" in record.getMessage()
    assert "OPENSEARCH_SIGNING is 'rot13'" in record.getMessage()


def test_an_error_other_than_a_refused_setting_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a refused setting is caught: a defect in starting the feed stops the Conduit's start,
    rather than leave it unfed and silent, as v0.6.0 was."""
    import services.api.app as app_module

    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("a defect in the feed's start")

    monkeypatch.setattr(app_module, "start_index_feed", broken)
    with pytest.raises(RuntimeError, match="a defect"):
        app_module.conduit_index_feed(None, None, None, None, environ={"OPENSEARCH_HOST": "x"})


async def test_the_job_loop_and_the_feed_stop_under_one_deadline() -> None:
    """`stop_background`: both stops set at once, and a job and a batch that each ignore the stop
    are both cancelled by one deadline, not one each (Amendment 4: inside Docker's 10 s grace)."""
    import asyncio
    import time

    from services.api.app import JOB_LOOP_STOP_SECONDS, stop_background
    from services.search_index.run import IndexFeed

    async def ignores_its_stop() -> None:
        await asyncio.sleep(3600)

    closed: list[str] = []

    async def close_client() -> None:
        closed.append("client")

    loop_stop = asyncio.Event()
    job = asyncio.create_task(ignores_its_stop())
    feed = IndexFeed(asyncio.create_task(ignores_its_stop()), asyncio.Event(), "a", [close_client])
    started = time.monotonic()
    await stop_background(job, loop_stop, feed, seconds=0.4)
    took = time.monotonic() - started
    await asyncio.sleep(0)  # let the cancelled job end
    assert loop_stop.is_set() and feed.stop.is_set()
    assert job.cancelled() and feed.task.cancelled() and closed == ["client"]
    assert took < 0.4 + 0.25, f"two deadlines, not one: {took:.2f} s"
    assert JOB_LOOP_STOP_SECONDS <= 8.0, (
        "the shared deadline must leave Docker's 10 s grace a margin"
    )


async def test_the_feed_sees_its_stop_at_once_not_after_the_job_loop() -> None:
    """The feed's stop is set with the loop's, so its batch finishes while the loop's job does,
    not only after the loop has been waited for (`IndexFeed.close` would set it then too)."""
    import asyncio
    import time

    from services.api.app import stop_background
    from services.search_index.run import IndexFeed

    stop = asyncio.Event()
    saw: list[float] = []

    async def feed_batch() -> None:
        await stop.wait()
        saw.append(time.monotonic())

    async def slow_job() -> None:
        await asyncio.sleep(3600)

    started = time.monotonic()
    feed = IndexFeed(asyncio.create_task(feed_batch()), stop, "alias", [])
    await stop_background(asyncio.create_task(slow_job()), asyncio.Event(), feed, seconds=0.5)
    assert saw and saw[0] - started < 0.2, "the feed saw its stop only after the job loop's wait"


def test_the_lifespan_starts_the_feed_last_and_stops_it_before_the_stores() -> None:
    """Read from the lifespan's own source: the feed is started at the `try` (nothing can raise
    between its start and the `finally` that stops it), and `stop_background` is awaited before the
    first store is closed (the text store the feed reads)."""
    source = (CORE / "services/api/app.py").read_text(encoding="utf-8")
    body = source[source.index("async def lifespan(") :]
    start = body.index("conduit_index_feed(")
    try_yield = body.index("    try:\n        yield\n")
    between = body[start:try_yield]
    # Only the feed's own statement lies between its start and the `try`.
    assert between.rstrip().endswith("if index_feed_in_conduit()\n        else None\n    )")
    assert between.count("\n    )") == 1 and "create_task" not in between
    after = body[try_yield:]
    stop = after.find("await stop_background(job_loop_task, job_loop_stop, index_feed)")
    first_store = after.find("await investigations.close()")
    assert -1 not in (stop, first_store) and stop < first_store


def test_cloud_platform_s_conduit_is_never_told_to_run_the_loop_or_feed() -> None:
    """The managed-OpenSearch shape: its render gives the Conduit `OSPREY_JOB_WORKER=service`, so
    with its domain's address set it still never feeds beside the worker."""
    import yaml
    from harness.render import render

    from schemas.deployment import OspreyConfig
    from services.api.app import index_feed_in_conduit
    from tools.cp_policy_check import FIXTURES, _resolver

    fixture = FIXTURES / "development.yaml"
    config = OspreyConfig.model_validate(yaml.safe_load(fixture.read_text()))
    values = yaml.safe_load(render(config, resolver=_resolver).artefacts["values.yaml"])
    env = {**values["environment"], "OPENSEARCH_URL": "https://search.example.org"}
    assert values["environment"].get("OSPREY_JOB_WORKER") == "service"
    assert index_feed_in_conduit(env) is False
