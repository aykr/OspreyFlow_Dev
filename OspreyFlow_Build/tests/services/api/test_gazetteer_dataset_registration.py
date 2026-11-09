"""The gazetteer's dataset as the command-line builds register it (ADR-147 Amendment 1):
`ospreyflow map build` (`map_admin._build_here`) and `python -m scripts.build_local_basemap` both call
`map_places.register_gazetteer_dataset_from_env` against the Conduit's own database.

The store is stood in by the in-memory one the Conduit's tests use, so this proves what the function
asks of it (the id, the name, the recipe's unit, the person) and that a database it cannot reach is
said in words, as the build's other unreachable store is, never a connection traceback. That the
places themselves are stamped into the dataset is `load_gazetteer`'s, proven live
(`tests/ingest/test_gazetteer_place_search_live.py`).
"""

from __future__ import annotations

import socket

import pytest
from services.api.datasets import InMemoryDatasetStore
from services.api.map_places import (
    DatasetsUnreachable,
    gazetteer_dataset_id,
    gazetteer_unit,
    register_gazetteer_dataset_from_env,
)


class _ClosingStore(InMemoryDatasetStore):
    closed = False

    async def close(self) -> None:
        self.closed = True


async def test_a_command_line_build_registers_the_regions_dataset_for_the_recipes_unit() -> None:
    store = _ClosingStore()

    async def connect(_dsn: str) -> _ClosingStore:
        return store

    held = await register_gazetteer_dataset_from_env("rutland", by="cli:owner", connect=connect)
    assert (held.id, held.owning_unit, held.created_by) == (
        "gazetteer-osm-rutland", gazetteer_unit(), "cli:owner",
    )  # fmt: skip
    assert (
        store.datasets[gazetteer_dataset_id("rutland")].name == "Gazetteer: OpenStreetMap (rutland)"
    )
    assert store.closed
    # A rebuild keeps the first record.
    again = await register_gazetteer_dataset_from_env("rutland", by="cli:other", connect=connect)
    assert again.created_by == "cli:owner"


#: The two ways a build meets no database: nothing listening, and a name that does not resolve. An
#: authentication refusal (`asyncpg.PostgresError`, also caught) is not planted here: importing the
#: driver marks a file live (`tools/test_file_coverage_check.py`), and this one needs no service.
@pytest.mark.parametrize(
    "failure",
    [ConnectionRefusedError(61, "Connect call failed ('127.0.0.1', 5432)"),
     socket.gaierror(8, "nodename nor servname provided, or not known: osprey-postgres")],
)  # fmt: skip
async def test_an_unreachable_database_is_said_in_words(failure: Exception) -> None:
    async def connect(_dsn: str) -> InMemoryDatasetStore:
        raise failure

    with pytest.raises(DatasetsUnreachable) as raised:
        await register_gazetteer_dataset_from_env("rutland", by="cli:owner", connect=connect)
    words = str(raised.value)
    assert "Cannot reach the Conduit's database" in words and "--tiles-only" in words
    # Its name, not its text: the text names an address or a user.
    assert "127.0.0.1" not in words and "osprey-postgres" not in words
