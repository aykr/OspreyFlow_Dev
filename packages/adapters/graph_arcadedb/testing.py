"""Test-only database lifecycle for the `GraphPort` conformance suite.

Not used by production code — the Conduit is configured with one long-lived
database. Every conformance test gets its own uniquely-named ArcadeDB
database, schema-applied and dropped on exit, so tests never interfere with
each other regardless of ordering or parallelism.

**This teardown cannot survive a hard kill.** The `finally` block below
runs `drop_database` for normal completion and for a raised exception, but
not for a SIGKILL or an OOM-kill of the test process or the ArcadeDB
server itself — an interrupted run leaves its `conformance_*` database
behind for good, since nothing else ever revisits it. This is exactly
what filled the dev ArcadeDB volume once already (three orphaned
`conformance_*` databases, ~3.5GB, `deploy/compose/dev.yaml`'s fourth
ArcadeDB note has the incident). `sweep_stale_conformance_databases`
below is the recovery — invoked from a session-scoped autouse fixture in
`tests/conformance/graph_port/conftest.py` — not a fix that makes this
`finally` reliable; a hard-killed run can still orphan a database between
sweeps.

**The sweep is safe sequentially; concurrently, only past its staleness
window.** A disclosed gap names an
artificial two-concurrent-conformance-process run as a real stress case
this build has hit before. Under it, an unconditional sweep would drop the
*other* session's still-running database mid-test, surfacing as an
arbitrary `ArcadeDBError` rather than what it is. The database name itself
now carries its own creation time (`conformance_{unix_ts}_{uuid}`), so the
sweep only drops one once `_STALENESS_WINDOW_SECONDS` has passed — long
enough that any legitimate concurrent run (measured: a clean full suite
takes ~4 minutes; a degraded one, ~30) has certainly finished, short
enough to still self-heal within a session. A name from before this fix
(bare `conformance_{uuid}`, no timestamp) parses as immediately stale —
correct, since nothing running today's code can still be creating that
shape, so any survivor is necessarily an old orphan.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ontology.handling import HandlingScheme
from schemas.domain import OntologySchema

from .adapter import GraphArcadeDBAdapter
from .client import ArcadeDBClient, ArcadeDBConfig

_STALE_DATABASE_PREFIX = "conformance_"

#: How long a `conformance_*` database must have existed before the sweep
#: will drop it — see this module's own docstring for the measurements
#: behind this number.
_STALENESS_WINDOW_SECONDS = 60 * 60


#: Every database this *process* created and has not yet dropped. Not a count of what is on the
#: server: a global count cannot tell this session's databases from a concurrent session's, and
#: would make the assertion below either wrong under concurrency or useless without it.
#:
#: **Round 13bb, 27 September 2026.** The teardown below has always been per test, in a `finally`,
#: and a full `make test-all` measured directly never held more than one at a time — so the
#: accumulation `07_BUILD_PLAN.md` Stage 2a suspected was not what exhausted the server (a 6GB
#: heap was; `harness/profiles.py` has that log). This set exists anyway, because "the fixture
#: drops what it created" was an invariant stated in a docstring and exercised by nothing —
#: `CLAUDE.md` rule 12's shape exactly, and the thing that would have made the accumulation
#: hypothesis checkable in round 13 rather than plausible.
_LIVE_CONFORMANCE_DATABASES: set[str] = set()


class LeakedConformanceDatabasesError(AssertionError):
    """Names every database the fixture created and did not drop — never a bare count, since the
    name carries its own creation time and so says which test run orphaned it."""

    def __init__(self, names: set[str]) -> None:
        self.names = frozenset(names)
        super().__init__(
            "the conformance fixture created database(s) it never dropped: "
            + ", ".join(sorted(names))
            + ". Each one stays resident in ArcadeDB's heap for the rest of the session and "
            "survives it on disk; `sweep_stale_conformance_databases` is the recovery, not a "
            "licence to leak."
        )


def assert_no_leaked_conformance_databases() -> None:
    """Called once at session end (`tests/conftest.py`'s `pytest_sessionfinish`). A no-op for a
    session that never used the fixture, which is every run of `make test`."""
    if _LIVE_CONFORMANCE_DATABASES:
        raise LeakedConformanceDatabasesError(_LIVE_CONFORMANCE_DATABASES)


@asynccontextmanager
async def arcadedb_adapter(
    ontology: OntologySchema, handling_scheme: HandlingScheme
) -> AsyncIterator[GraphArcadeDBAdapter]:
    database = f"{_STALE_DATABASE_PREFIX}{int(time.time())}_{uuid.uuid4().hex[:12]}"
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    try:
        await client.create_database_if_absent()
        _LIVE_CONFORMANCE_DATABASES.add(database)
        adapter = GraphArcadeDBAdapter(client, handling_scheme)
        await adapter.apply_schema(ontology)
        yield adapter
    finally:
        await client.drop_database()
        # Only after the drop actually returned. A `drop_database` that raised leaves the name in
        # the set, which is the case worth reporting — not one to swallow by discarding first.
        _LIVE_CONFORMANCE_DATABASES.discard(database)
        await client.aclose()


def _created_at(database_name: str) -> float:
    """The creation time encoded in a `conformance_{unix_ts}_{uuid}` name,
    or `0.0` (always stale) for a name that doesn't parse — see this
    module's own docstring for why that's the correct default rather than
    an error."""
    parts = database_name.split("_")
    if len(parts) != 3:
        return 0.0
    try:
        return float(parts[1])
    except ValueError:
        return 0.0


async def sweep_stale_conformance_databases(client: ArcadeDBClient) -> list[str]:
    """Drops every `conformance_*` database on the server older than
    `_STALENESS_WINDOW_SECONDS` — orphans from a prior run's hard-killed
    teardown (see this module's own docstring). Safe to call at the start
    of a session, unconditionally, in the sequential case this suite
    normally runs in. **Not unconditionally safe under concurrency**: the
    staleness window narrows the hazard, it does not remove it — a
    concurrent run that is still going past `_STALENESS_WINDOW_SECONDS`
    (this build has measured a run take ~30 minutes against a degraded
    container, well over half this window) remains droppable by a second
    session's sweep. The common case (a healthy prior run left nothing
    behind, and nothing else is concurrently running) is a same-cost
    no-op either way. Never touches a non-`conformance_*` database (the
    real dev database included) by construction."""
    now = time.time()
    databases = await client.list_databases()
    stale = [
        name
        for name in databases
        if name.startswith(_STALE_DATABASE_PREFIX)
        and now - _created_at(name) >= _STALENESS_WINDOW_SECONDS
    ]
    for name in stale:
        await client.drop_database_named(name)
    return stale
