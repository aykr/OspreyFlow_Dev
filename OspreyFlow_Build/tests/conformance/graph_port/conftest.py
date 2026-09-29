"""Session-scoped hygiene for the `GraphPort` conformance suite.

Runs `sweep_stale_conformance_databases` once before any test in this
directory, so a prior run's hard-killed teardown (`packages/adapters/
graph_arcadedb/testing.py`'s own docstring has the full incident) does not
compound silently across sessions until the ArcadeDB volume fills again.
Not a fix for the underlying gap — `testing.py`'s `finally` block still
cannot survive a hard kill — only the self-healing recovery for it.

**Not `autouse` (round 05, 26 September 2026).** It was, directory-wide,
which meant `test_guard.py`'s own two tests — the ones `make conformance-
guard` / `ci.yml`'s `conformance-guard` job select with `-k test_guard`,
specifically because they are the one conformance check every other job in
this tree can assume needs no live store — inherited a real ArcadeDB
connection attempt they never asked for and do not need, since neither
touches `GraphPort` at all. Confirmed directly: with this fixture
`autouse`, `make conformance-guard` errored both `test_guard.py` cases with
`httpx.ConnectError` on a machine with no ArcadeDB running — the same
machine every other port's `test_guard.py` passed on cleanly, without
infrastructure, in the same run. `test_suite.py` now requests this fixture
explicitly (`pytestmark`), which is the one module that actually needs the
sweep; the guard test's own invariant — a cheap, infra-free sanity check,
uniform across all four ports — is restored rather than worked around at
the Makefile/CI-job level.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.testing import sweep_stale_conformance_databases

#: Deliberately outside the `conformance_` prefix `sweep_stale_conformance_
#: databases` deletes by name — a database actually created under a name
#: starting with that prefix would otherwise be eligible to delete itself.
_SWEEP_CLIENT_DATABASE = "sweep-control"


@pytest.fixture(scope="session")
async def _sweep_stale_conformance_databases() -> AsyncIterator[None]:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(_SWEEP_CLIENT_DATABASE))
    try:
        swept = await sweep_stale_conformance_databases(client)
        if swept:
            print(f"\nconformance conftest: swept {len(swept)} stale database(s): {swept}")
    finally:
        await client.aclose()
    yield
