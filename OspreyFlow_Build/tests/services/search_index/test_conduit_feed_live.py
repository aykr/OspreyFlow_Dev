"""ADR-150 Amendment 4, live: where no worker workload is rendered (local-lite, Small), the Conduit
feeds the search index itself, beside its in-Conduit job loop; and a rebuild leaves the outbox
rows it covered, which the feed then drains.

Found on the GOV.UK rebuild of 16 November 2026
(`process/lanes/demo/REPORT_2026-11-16_v060.md`): only `worker_main` started `run_indexer`,
Small renders no worker, so nothing drained the outboxes and, past
`search_service.PENDING_LIMIT`, case search fell back to exact identifiers for good.

The first case is at the real call site: a real `uvicorn services.api.app:app`, told what
Small's render tells it (`OSPREY_JOB_WORKER=conduit`, OpenSearch's address), with no worker
process anywhere, against the leased stack's real ArcadeDB, Postgres, Valkey and OpenSearch. No
fake indexer, no hand-called `drain_once` (rule 15): what refuses a write here is what refuses
it in a deployment.

Needs a lease (`stack_lease.sh live`), its ports pinned. The Conduit opens the `ospreyflow`
database (`run_resources` names it), so this file writes its own nodes there, under ids and a
dataset of its own, and deletes them and their outbox rows in teardown, after the Conduit is
stopped. Its index alias is its own, deleted after it."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import threading
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from opensearchpy import AsyncOpenSearch, NotFoundError

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Provenance, ProvenanceState, SourceRef
from services.api.config import PostgresConfig
from services.api.review import ExtractionCandidateStore
from services.search_index.client import SearchIndexConfig, search_client
from services.search_index.indexer import SearchIndexer, ensure_index
from services.search_index.rebuild import rebuild
from services.search_index.run import LEASE_SECONDS
from tests.services.api.test_statelessness import _ConduitInstance
from tests.services.search_index.test_feed_live import CaseTexts

pytestmark = pytest.mark.store

ONTOLOGY = load_default_ontology()
WHEN = datetime(2026, 1, 1, tzinfo=UTC)
SOURCE = SourceRef(document_id="files/people.csv", locator="row 1", excerpt_hash="e" * 64)
PROVENANCE = Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=WHEN)
HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
)
DATASET = "Z3004ZZ"
#: ADR-150 Amendment 3 point 3: a search straight after a write asks again for up to 30 s (and M6's
#: alarm is a p95 over 30 s). The lag measured is printed on every run, a pass included.
SEARCHABLE_WITHIN = 30.0
#: The backlog: large enough that its drain spans many polls, so the rate is measured over seconds,
#: not one poll (Amendment 4's measured line). Written in transactions of `CHUNK`.
BACKLOG = 10_000
CHUNK = 2_000
#: How often the sampler reads the outbox while the feed drains it.
POLL_SECONDS = 0.1
#: The wait for the backlog, from the whole outbox at the start, so rows other live files left
#: ahead of this file's (the CI job runs the pid and poc seeds first) never make it flake: a dead
#: holder's lease runs out (`LEASE_SECONDS`), then every row ahead and its own drain at a floor
#: rate an eighth of the one measured on stack b (about 1,960 rows a second at 5734c16).
FLOOR_ROWS_PER_SECOND = 250.0


def _person(family_name: str) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(), type="Person", properties={"family_name": family_name},
        provenance=PROVENANCE, handling=HANDLING, created_by="loader-1", created_at=WHEN,
        datasets=[DATASET],
    )  # fmt: skip


async def _written(graph: GraphArcadeDBAdapter, nodes: Sequence[NodeWrite]) -> list[str]:
    tx = await graph.begin_transaction()
    ids = await graph.upsert_nodes(list(nodes), tx)
    await graph.commit_transaction(tx)
    return [str(i) for i in ids]


async def _pending(client: ArcadeDBClient, ids: Sequence[str]) -> int:
    """How many of these nodes' rows the graph's outbox still holds (ADR-150 decision 1)."""
    rows = await client.sql(
        "SELECT count(*) AS n FROM IndexPending WHERE node_id IN :ids", params={"ids": list(ids)}
    )
    return int(rows[0]["n"]) if rows else 0


async def _found_by_name(search: AsyncOpenSearch, alias: str, name: str) -> list[str]:
    """The node documents a name search finds, as the query side's close-name band reads `names`."""
    try:
        await search.indices.refresh(index=alias)
        hits = await search.search(
            index=alias,
            body={
                "query": {
                    "bool": {
                        "filter": [{"term": {"kind": "node"}}],
                        "must": [{"match": {"names": name}}],
                    }
                }
            },  # fmt: skip
        )
    except NotFoundError:  # the feed has not made the index yet
        return []
    return [h["_source"]["node_id"] for h in hits["hits"]["hits"]]


PERSON = f"`{groovy_identifier(physical_type_name('Person'))}`"


async def _outbox_total(client: ArcadeDBClient) -> int:
    """Every row of the graph's outbox, this file's and any other's."""
    rows = await client.sql("SELECT count(*) AS n FROM IndexPending")
    return int(rows[0]["n"]) if rows else 0


async def _lease_holder() -> str:
    """Who holds the indexer's lease in the stack's Valkey (`run.LEASE_KEY`)."""
    from valkey.asyncio import Valkey

    from services.api.config import ValkeyConfig
    from services.search_index.run import LEASE_KEY

    client = Valkey(**ValkeyConfig.from_env().client_kwargs())
    try:
        held = await client.get(LEASE_KEY)
    finally:
        await client.aclose()
    return held.decode() if isinstance(held, bytes) else str(held or "")


async def _remove(client: ArcadeDBClient, ids: Sequence[str]) -> None:
    """This file's own nodes and outbox rows, and nothing else of the shared database: the ids it
    wrote, and any node of its own dataset an earlier run left (a run killed before teardown)."""
    left = await client.sql(
        f"SELECT id FROM {PERSON} WHERE datasets CONTAINS :dataset", params={"dataset": DATASET}
    )
    ids = sorted({*ids, *(str(r["id"]) for r in left)})
    if ids:
        await client.sql("DELETE FROM IndexPending WHERE node_id IN :ids", params={"ids": ids})
        await client.sql(f"DELETE FROM {PERSON} WHERE id IN :ids", params={"ids": ids})


@dataclass
class Sample:
    at: float
    own: int  # this file's backlog rows still pending
    total: int  # every row of the outbox


def _sample_until_drained(ids: Sequence[str], until: float, out: list[Sample]) -> None:
    """In a thread of its own, from before the Conduit is spawned: the outbox read every
    `POLL_SECONDS` until this file's rows are gone or `until` passes."""

    async def sample() -> None:
        client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
        try:
            while time.monotonic() < until:
                own, total = await _pending(client, ids), await _outbox_total(client)
                out.append(Sample(time.monotonic(), own, total))
                if own == 0:
                    return
                await asyncio.sleep(POLL_SECONDS)
        finally:
            await client.aclose()

    asyncio.run(sample())


def _drain_rate(samples: Sequence[Sample]) -> tuple[float, float, int] | None:
    """Rows cleared from the whole outbox a second, between the last poll before the feed reached
    this file's rows and the first poll after it had cleared them all: (rate, seconds, rows).
    None where no poll fell before the feed reached them."""
    full = [x for x in samples if x.own == BACKLOG]
    done = [x for x in samples if x.own == 0]
    if not full or not done:
        return None
    a, b = full[-1], done[0]
    seconds, rows = b.at - a.at, a.total - b.total
    return (rows / seconds if seconds > 0 else 0.0), seconds, rows


def test_a_conduit_with_no_worker_feeds_the_index_and_its_outbox_falls(jwks_url: str) -> None:
    """Small's shape: the Conduit drains the job streams itself and nothing else runs. A backlog
    written before it started drains, this Conduit holds the indexer's lease, a write made while
    it runs becomes searchable, and it stops on SIGTERM within its own bound. Red on 236e31e:
    nothing starts `run_indexer` in the Conduit, so the backlog's rows stay and no document is
    ever written."""
    alias = f"test-conduit-feed-{uuid.uuid4().hex[:10]}"
    tag = uuid.uuid4().hex[:8]
    arcadedb = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    graph = GraphArcadeDBAdapter(arcadedb, load_uk_le_scheme())
    search = search_client(
        SearchIndexConfig.from_env({**os.environ, "OSPREY_SEARCH_INDEX_ALIAS": alias})
    )
    written: list[str] = []
    conduit: _ConduitInstance | None = None

    async def setup() -> list[str]:
        await arcadedb.create_database_if_absent()
        await graph.apply_schema(ONTOLOGY)
        await _remove(arcadedb, [])  # what an earlier run of this file left, if anything
        ids: list[str] = []
        for start in range(0, BACKLOG, CHUNK):
            people = [_person(f"Backlog{tag}{n}") for n in range(start, start + CHUNK)]
            ids += await _written(graph, people)
        return ids

    async def write_and_find() -> tuple[str, list[str], float]:
        name = f"Quillon{tag}"
        (node,) = await _written(graph, [_person(name)])
        written.append(node)
        started = time.monotonic()
        found = await _found_by_name(search, alias, name)
        while node not in found and time.monotonic() - started < SEARCHABLE_WITHIN:
            await asyncio.sleep(0.25)
            found = await _found_by_name(search, alias, name)
        return node, found, time.monotonic() - started

    loop = asyncio.new_event_loop()
    try:
        backlog = loop.run_until_complete(setup())
        written.extend(backlog)
        assert loop.run_until_complete(_pending(arcadedb, backlog)) == BACKLOG
        ahead = loop.run_until_complete(_outbox_total(arcadedb))
        within = LEASE_SECONDS + 30.0 + ahead / FLOOR_ROWS_PER_SECOND
        samples: list[Sample] = []
        sampler = threading.Thread(
            target=_sample_until_drained,
            args=(backlog, time.monotonic() + 60.0 + within, samples),
            daemon=True,
        )
        sampler.start()
        conduit = _ConduitInstance(
            jwks_url,
            extra_env={
                # What Small's render tells its Conduit (`harness.render`, deployment.env): the job
                # loop is the Conduit's, and where OpenSearch is; the lease pins only its port.
                "OSPREY_JOB_WORKER": "conduit",
                "OPENSEARCH_HOST": os.environ.get("OPENSEARCH_HOST") or "localhost",
                "OSPREY_SEARCH_INDEX_ALIAS": alias,
            },
        )
        sampler.join(timeout=60.0 + within + 30.0)
        left = samples[-1].own if samples else BACKLOG
        print(f"\nthe outbox held {ahead} rows at the start, this file's {BACKLOG} among them; "
              f"waited at most {within:.0f} s")  # fmt: skip
        assert left == 0, (
            f"{left} of the backlog's {BACKLOG} outbox rows still pending after {within:.0f} s: "
            "nothing in a Conduit with no worker feeds the search index"
        )
        measured = _drain_rate(samples)
        if measured is None:
            print("the drain rate was not measured: no poll fell before the feed reached the rows")
        else:
            rate, seconds, rows = measured
            print(f"the feed cleared {rows} outbox rows in {seconds:.2f} s, {rate:.0f} rows/s "
                  f"(polled every {POLL_SECONDS} s, from the last poll before it reached this "
                  "file's rows to the first after it had cleared them)")  # fmt: skip
        # The feeder was this Conduit process, and no stray one on the stack's Valkey.
        holder = loop.run_until_complete(_lease_holder())
        expected = f"conduit-{socket.gethostname()}-{conduit._process.pid}"  # noqa: SLF001
        assert holder == expected, f"the indexer's lease is held by {holder!r}, not {expected!r}"
        node, found, lag = loop.run_until_complete(write_and_find())
        print(f"a write was found {lag:.2f} s after it committed, each search after a forced "
              "refresh (a real search waits up to the index's 1 s refresh more)")  # fmt: skip
        assert node in found, f"the write was not searchable within {SEARCHABLE_WITHIN:.0f} s"
        assert loop.run_until_complete(_pending(arcadedb, [node])) == 0

        # Stopped at shutdown: the feed ends with the job loop, under one deadline, so SIGTERM
        # ends the process. uvicorn (0.29 on) re-raises the signal once shutdown is done.
        process = conduit._process  # noqa: SLF001
        process.send_signal(signal.SIGTERM)
        try:
            code: int | None = process.wait(timeout=30)
        except Exception:  # noqa: BLE001 - said below
            code = None
        assert code in (0, -signal.SIGTERM), (
            f"the Conduit did not stop on SIGTERM within 30 s ({code!r})"
        )
    finally:
        if conduit is not None:
            conduit.kill()
        loop.run_until_complete(_remove(arcadedb, written))
        loop.run_until_complete(search.indices.delete(index=f"{alias}*", ignore_unavailable=True))
        loop.run_until_complete(search.close())
        loop.run_until_complete(arcadedb.aclose())
        loop.close()


@pytest.fixture
async def rebuilt_world() -> AsyncIterator[
    tuple[GraphArcadeDBAdapter, CaseTexts, AsyncOpenSearch, str]
]:
    alias = f"test-conduit-rebuild-{uuid.uuid4().hex[:10]}"
    client = search_client(
        SearchIndexConfig.from_env({**os.environ, "OSPREY_SEARCH_INDEX_ALIAS": alias})
    )
    store = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
    texts = CaseTexts(store)
    try:
        async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
            await ensure_index(client, alias)
            yield graph, texts, client, alias
    finally:
        await texts.remove_own()
        await client.indices.delete(index=f"{alias}*", ignore_unavailable=True)
        await client.close()
        await store.close()


async def test_a_rebuild_leaves_the_outbox_it_covered_and_the_feed_drains_it(
    rebuilt_world: tuple[GraphArcadeDBAdapter, CaseTexts, AsyncOpenSearch, str],
) -> None:
    """Amendment 4 point 3: a rebuild never clears the outbox, even the rows its own read covered (a
    batch the feed read before the rebuild and writes after the swap would otherwise land an older
    state with nothing left to mend it); the feed drains them after it, idempotently. Planted red:
    a rebuild that clears its rows (`process/lanes/rules-b/v061p/plants.py`)."""
    graph, texts, client, alias = rebuilt_world
    ids = await _written(graph, [_person(f"Covered{n}") for n in range(5)])
    pending_before = len(await graph.pending_index(1000))
    assert pending_before >= len(ids)

    built = await rebuild(graph, texts, client, alias, ONTOLOGY)
    await client.indices.refresh(index=alias)
    assert built.nodes >= len(ids)
    for node in ids:
        assert (await client.get(index=alias, id=node))["found"]
    # The rows the rebuild covered are still there, in order, after it.
    left = {row.node_id for row in await graph.pending_index(1000)}
    assert set(ids) <= left, "a rebuild cleared outbox rows: ADR-150 decision 4 leaves them"

    # And the feed drains them, changing nothing the rebuild wrote.
    indexer = SearchIndexer(graph, texts, client, alias, ONTOLOGY)
    while await indexer.drain_once():
        pass
    await client.indices.refresh(index=alias)
    assert await graph.pending_index(1000) == []
    for node in ids:
        assert (await client.get(index=alias, id=node))["_source"]["node_id"] == node
