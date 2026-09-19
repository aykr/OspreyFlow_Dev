"""Session-scoped hygiene for the `GraphPort` conformance suite.

Runs `sweep_stale_conformance_databases` once before any test in this
directory, so a prior run's hard-killed teardown (`packages/adapters/
graph_arcadedb/testing.py`'s own docstring has the full incident) does not
compound silently across sessions until the ArcadeDB volume fills again.
Not a fix for the underlying gap — `testing.py`'s `finally` block still
cannot survive a hard kill — only the self-healing recovery for it.
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


@pytest.fixture(scope="session", autouse=True)
async def _sweep_stale_conformance_databases() -> AsyncIterator[None]:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(_SWEEP_CLIENT_DATABASE))
    try:
        swept = await sweep_stale_conformance_databases(client)
        if swept:
            print(f"\nconformance conftest: swept {len(swept)} stale database(s): {swept}")
    finally:
        await client.aclose()
    yield
