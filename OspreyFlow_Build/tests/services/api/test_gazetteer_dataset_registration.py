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
from datetime import UTC, datetime

import pytest
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.map_places import (
    DatasetsUnreachable,
    UnknownUnit,
    check_unit,
    check_unit_from_env,
    gazetteer_dataset_id,
    register_gazetteer_dataset_from_env,
)


class _ClosingStore(InMemoryDatasetStore):
    closed = False

    async def close(self) -> None:
        self.closed = True


async def test_a_command_line_build_registers_the_regions_dataset_for_the_builds_unit() -> None:
    """ADR-147 Amendment 2 (the owner's ruling 8): the unit is the build's, never the recipe's."""
    store = _ClosingStore()

    async def connect(_dsn: str) -> _ClosingStore:
        return store

    held = await register_gazetteer_dataset_from_env(
        "rutland", by="cli:owner", unit="unit-7", connect=connect
    )
    assert (held.id, held.owning_unit, held.created_by) == (
        "gazetteer-osm-rutland", "unit-7", "cli:owner",
    )  # fmt: skip
    assert (
        store.datasets[gazetteer_dataset_id("rutland")].name == "Gazetteer: OpenStreetMap (rutland)"
    )
    assert store.closed
    # A rebuild keeps the first record.
    again = await register_gazetteer_dataset_from_env(
        "rutland", by="cli:other", unit="unit-8", connect=connect
    )
    assert (again.created_by, again.owning_unit) == ("cli:owner", "unit-7")


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
        await register_gazetteer_dataset_from_env(
            "rutland", by="cli:owner", unit="unit-1", connect=connect
        )
    words = str(raised.value)
    assert "Cannot reach the Conduit's database" in words and "run the build again" in words
    # Its name, not its text: the text names an address or a user.
    assert "127.0.0.1" not in words and "osprey-postgres" not in words


def _held_by(*units: str) -> InMemoryDatasetStore:
    store = _ClosingStore()
    for unit in units:
        store.datasets[f"d-{unit}"] = Dataset(
            id=f"d-{unit}", name=unit, owning_unit=unit, created_at=datetime.now(UTC),
            created_by="someone",
        )  # fmt: skip
    return store


def test_a_unit_that_holds_nothing_here_is_refused_in_words_naming_those_that_do() -> None:
    """ADR-147 Amendment 2 (the owner's ruling 8): refused in words when no such unit exists."""
    with pytest.raises(UnknownUnit) as raised:
        check_unit("unit-9", {"unit-1", "unit-7"})
    assert str(raised.value) == (
        "No case or dataset in this deployment is held by the unit 'unit-9', so a gazetteer "
        "cannot be built for it. Name a unit that holds one."
    )
    check_unit("unit-7", {"unit-1", "unit-7"})
    # The building administrator's own unit is always one (a deployment with nothing loaded yet).
    check_unit("unit-3", set(), own="unit-3")


def test_a_rebuild_for_another_unit_than_the_first_build_s_is_refused_in_words() -> None:
    """The region's dataset keeps its first unit, so another would leave it holding the places of
    two units."""
    with pytest.raises(UnknownUnit) as raised:
        check_unit("unit-7", {"unit-1", "unit-7"}, built_for="unit-1")
    assert str(raised.value).startswith("This region's gazetteer is held by the unit 'unit-1'")
    check_unit("unit-1", {"unit-1", "unit-7"}, built_for="unit-1")


async def test_the_command_line_check_asks_the_conduit_s_database_and_closes_it() -> None:
    store = _held_by("unit-7")

    async def connect(_dsn: str) -> InMemoryDatasetStore:
        return store

    await check_unit_from_env("unit-7", region="rutland", connect=connect)
    assert store.closed
    with pytest.raises(UnknownUnit):
        await check_unit_from_env("unit-1", region="rutland", connect=connect)
    # Built before for unit-7: a rebuild for another unit is refused, though it holds a dataset.
    store.datasets["gazetteer-osm-rutland"] = store.datasets["d-unit-7"].model_copy(
        update={"id": "gazetteer-osm-rutland"}
    )
    store.datasets["d-unit-8"] = store.datasets["d-unit-7"].model_copy(
        update={"id": "d-unit-8", "owning_unit": "unit-8"}
    )
    with pytest.raises(UnknownUnit):
        await check_unit_from_env("unit-8", region="rutland", connect=connect)


async def test_the_command_line_check_says_an_unreachable_database_in_words() -> None:
    async def connect(_dsn: str) -> InMemoryDatasetStore:
        raise ConnectionRefusedError(61, "Connect call failed ('127.0.0.1', 5432)")

    with pytest.raises(DatasetsUnreachable) as raised:
        await check_unit_from_env("unit-7", region="rutland", connect=connect)
    assert "nothing was built" in str(raised.value) and "127.0.0.1" not in str(raised.value)


async def test_a_unit_holding_only_a_gazetteer_holds_nothing() -> None:
    """The orchestrator's review of P5, item 12: an earlier gazetteer's own dataset is not a unit's
    data, so it does not make the unit one a build may name."""
    from services.api.map_places import units_held

    store = _held_by("unit-1")
    store.datasets["gazetteer-osm-rutland"] = store.datasets["d-unit-1"].model_copy(
        update={"id": "gazetteer-osm-rutland", "owning_unit": "unit-9"}
    )
    assert await units_held(store) == {"unit-1"}
    with pytest.raises(UnknownUnit):
        check_unit("unit-9", await units_held(store))
