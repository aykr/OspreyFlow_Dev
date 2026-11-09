"""A subscribed deployment-wide list read by a published pipeline's run, against the real stores: the
Postgres list store and the leased stack's object store, through `pipeline_run` →
`staged_run.prepare_staged_load` → `staging_catalogue.run_staging` (ADR-140 Amendment 16; CARRIES row
36's "a live test through run_staging"; rule 15: the in-memory twin and the local store stand in for
these in `test_subscribed_lookup_call_sites.py`, and a fake proves less than the store).

What a mistake would do, and the case that catches it:
- the run handing the engine no subscriptions, so a subscribed list's Lookup is refused at the run though
  it saved and published (the defect at main) —
  `test_a_run_reads_a_subscribed_list_from_the_real_stores`, red with `pipeline_run`'s
  `subscribed=` taken out (`process/lanes/studio-b/l1.8/red-live-fix-round.txt`);
- the real store's subscriptions widening what a run reads: a list another dataset subscribes to read by
  this one — `test_another_dataset_s_subscription_is_refused_by_the_real_stores`.

Live: skipped, never run, without a lease's `MINIO_ENDPOINT` and `OSPREY_LANE` (or CI's live job). Each
case removes what it wrote: its list row (the subscriptions and imports go with it, `ON DELETE CASCADE`)
and its bucket.
"""

from __future__ import annotations

import dataclasses
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pyarrow.fs as pa_fs
import pytest
from services.api.config import PostgresConfig
from services.api.list_connector import ParquetListRows, PostgresListStore, deployment_reference
from services.ingest.recipe_rules import RecipeRuleError
from services.ingest.staging import ObjectStorageConfig

from schemas.list_connector import BlankListMapping, DeploymentListInput
from tests.ingest.recipe_test_support import ValidatingGraph
from tests.ingest.test_phase7_exit_live import _answers
from tests.ingest.test_staged_pipeline_run import LOADER
from tests.ingest.test_staged_run import ONTOLOGY, SCHEME
from tests.services.api.test_studio_staging_routes import _Models
from tests.services.api.test_subscribed_lookup_call_sites import (
    REFUSED,
    ROWS,
    _reading_the_deployment_list,
    published,
)

#: The Lookup reads its list by this name, so the run's list must hold it; one per stack at a time.
NAME = "establishments"


def _on_record() -> bool:
    endpoint = os.environ.get("MINIO_ENDPOINT", "")
    lane = bool(os.environ.get("OSPREY_LANE")) or os.environ.get("CI") == "true"
    return bool(endpoint) and lane and _answers(endpoint)


@pytest.fixture
def storage() -> Iterator[ObjectStorageConfig]:
    """A bucket of the run's own on the object store a lease pins (never the default on 9000, rule
    14), removed after."""
    if not _on_record():
        pytest.skip("live: run under a lease, or in CI's live job, with its MINIO_ENDPOINT")
    config = dataclasses.replace(
        ObjectStorageConfig.from_env(), bucket=f"studio-b-l18-{uuid.uuid4().hex[:12]}"
    )
    yield config
    fs = pa_fs.S3FileSystem(
        endpoint_override=config.endpoint, access_key=config.access_key,
        secret_key=config.secret_key, scheme="https" if config.use_ssl else "http",
        allow_bucket_deletion=True,
    )  # fmt: skip
    if fs.get_file_info(config.bucket).type != pa_fs.FileType.NotFound:
        fs.delete_dir(config.bucket)


@pytest.fixture
async def lists() -> AsyncIterator[PostgresListStore]:
    """The real list store, its `establishments` row the case's own: refused to start over another's
    (never deleted, rule 14), and removed after."""
    if not _on_record():
        pytest.skip("live: run under a lease, or in CI's live job")
    dsn = PostgresConfig.from_env().dsn
    made = await PostgresListStore.connect(dsn)
    conn = await asyncpg.connect(dsn)
    held = await conn.fetchval("SELECT count(*) FROM deployment_lists WHERE name = $1", NAME)
    if held:
        await conn.close()
        await made.close()
        pytest.fail(f"a deployment list named {NAME!r} is already on this stack; left as found")
    try:
        yield made
    finally:
        await conn.execute("DELETE FROM deployment_lists WHERE name = $1", NAME)
        await conn.close()
        await made.close()


async def _list(lists: PostgresListStore, storage: ObjectStorageConfig, subscriber: str) -> str:
    made = await lists.add(
        DeploymentListInput(name=NAME, template="blank", location="establishments.csv",
                            mapping=BlankListMapping(ref="ref", primary_name="primary_name")),
        "admin-1",
    )  # fmt: skip
    ParquetListRows(storage).write(deployment_reference(made, 1), ROWS)
    assert await lists.apply_version(made.id, previous=0, version=1, digest="d", entries=len(ROWS),
                                     at=made.created_at)  # fmt: skip
    await lists.subscribe(subscriber, made.id, "author-1")
    assert await lists.subscribed(subscriber) == [made.id]
    return made.id


async def _run(
    tmp_path: Path, lists: PostgresListStore, storage: ObjectStorageConfig, graph: ValidatingGraph
):  # type: ignore[no-untyped-def]
    from services.api.pipeline_run import run_published_pipeline

    draft, repo = await published(tmp_path, _reading_the_deployment_list)
    return await run_published_pipeline(
        draft, LOADER, graph=graph, ontology=ONTOLOGY, scheme=SCHEME,  # type: ignore[arg-type]
        load_id=f"run-{uuid.uuid4().hex[:8]}", investigation_scope="case-1", repo_root=repo,
        recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
        target_models=_Models([]), staging_storage=storage,  # type: ignore[arg-type]
        list_store=lists,
    )  # fmt: skip


async def test_a_run_reads_a_subscribed_list_from_the_real_stores(
    lists: PostgresListStore, storage: ObjectStorageConfig, tmp_path: Path
) -> None:
    await _list(lists, storage, subscriber="pid")
    graph = ValidatingGraph(ONTOLOGY)
    report = await _run(tmp_path, lists, storage, graph)
    [branch] = report.branches
    lookup = next(s for s in branch.report.staging_steps if s.step == "with_establishment")
    assert lookup.rows_in == 6 and lookup.unmatched == 1  # XXX, kept with no establishment
    assert graph.committed_nodes
    titles = " ".join(str(n.properties.get("title", "")) for n in graph.committed_nodes)
    assert "HMP Fenwick Moor" in titles, titles


async def test_another_dataset_s_subscription_is_refused_by_the_real_stores(
    lists: PostgresListStore, storage: ObjectStorageConfig, tmp_path: Path
) -> None:
    await _list(lists, storage, subscriber="other-dataset")
    assert await lists.subscribed("pid") == []
    graph = ValidatingGraph(ONTOLOGY)
    with pytest.raises(RecipeRuleError) as refused:
        await _run(tmp_path, lists, storage, graph)
    assert refused.value.problems == [REFUSED]
    assert not graph.committed_nodes
