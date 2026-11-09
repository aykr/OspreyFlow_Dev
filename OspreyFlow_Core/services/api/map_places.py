"""The gazetteer's places: the dataset they are loaded into, and the analyst's place search over
them (`spec/02_GLASS_FRONTEND.md` §3.5's gazetteer search; ADR-147 Amendment 1, P4).

**Where the places are kept.** A gazetteer built in the Conduit (`map_admin.build_basemap`, from
*Admin › Maps*, the set-up console or `ospreyflow map build`) loads its places into a dataset of
its own, `gazetteer-osm-<region>` (the orchestrator's settlement of 9 November 2026). Before P4
they were loaded by the Conduit's own principal into no dataset at all, so no case read them
(ADR-099 decision 5) and a place search would have found nothing anywhere. A case reads the
gazetteer when its Author adds that dataset to it, as any other (ADR-099 Amendment 12: a composite
of the two).

The dataset, and the places and points in it, are held by the unit the build names (ADR-147
Amendment 2, the owner's ruling 8): a setting of *Admin › Maps*' Build (the administrator's own unit
unless another is named) and of both command-line builds (`--unit`), refused in words before
anything is built when no case or dataset here is held by it. The recipe's own `unit-1` is a
default no build uses.

**How they are found.** Within the case's datasets and the reader's clearance, in the store
(`GraphPort.suggest_locations`, rule 3), by `Location.name` alone, never an identifier; of those,
only the gazetteer's own places are offered: in a `gazetteer-*` dataset, with a point, the name
holding the words. A case's own locations (a yard, an address in a statement) are in the case's
dataset and are not offered as places. The answer never carries a gazetteer's identifier for a place
(rule 7; every other node read withholds them too, `ontology.handling.withhold_sources`). No hosted
geocoder is ever called here, whatever the deployment names (`OSPREY_ONLINE_GEOCODER` is the
pipeline's enrich stage's, ADR-136's egress rule applying there); §3.5 says none is.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Protocol

import asyncpg
from services.ingest.geometries import POINT_GEOMETRY_VERSION

from ontology.handling import HandlingScheme, is_gazetteer_held
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.analytics import GeometryKind
from schemas.domain import Node, Principal
from schemas.mapconfig import (
    GAZETTEER_DATASET_PREFIX,
    MapPlace,
    PlaceSearchRequest,
    PlaceSearchResponse,
)

from .datasets import Dataset

#: How many visible `Location`s one search reads, for each casing of the words, before keeping the
#: gazetteer's own: enough that a case's own locations rarely crowd the places out, and when they do
#: `more` says so (counted on names alone, never on an identifier).
SCAN_LIMIT = 200


def gazetteer_dataset_id(region: str) -> str:
    """The dataset a region's gazetteer is loaded into."""
    return f"{GAZETTEER_DATASET_PREFIX}osm-{region}"


#: ADR-147 Amendment 2 (the owner's ruling 8): a unit that holds no case and no dataset here, and is
#: not the building administrator's own, is refused in words before anything is built.
UNKNOWN_UNIT = (
    "No case or dataset in this deployment is held by the unit {unit!r}, so a gazetteer cannot be "
    "built for it. Name a unit that holds one{known}."
)


class UnknownUnit(ValueError):
    """The unit a build names is held by nothing here; its words are `UNKNOWN_UNIT`'s."""


async def units_held(store: object) -> set[str]:
    """Every unit a dataset or a case of this deployment is held by. The Conduit's Postgres store
    is asked directly (`datasets` and `investigations` share its database); the in-memory store
    the tests use answers from its datasets."""
    pool = getattr(store, "pool", None)
    if pool is not None:
        async with pool.acquire() as connection:
            rows = await connection.fetch("SELECT owning_unit FROM datasets")
            try:
                rows += await connection.fetch("SELECT owning_unit FROM investigations")
            except asyncpg.UndefinedTableError:
                pass  # A deployment whose case store has not started yet holds no case.
        return {str(r["owning_unit"]) for r in rows}
    held = getattr(store, "datasets", {})
    return {d.owning_unit for d in held.values()}


def check_unit(unit: str, held: set[str], *, own: str | None = None) -> None:
    """Refuses `unit` in words unless it holds a case or a dataset here, or is `own` (the building
    administrator's)."""
    if unit == own or unit in held:
        return
    named = sorted(held | ({own} if own else set()))
    known = f": {', '.join(named)}" if named else ""
    raise UnknownUnit(UNKNOWN_UNIT.format(unit=unit, known=known))


class _Registers(Protocol):
    async def register(self, dataset: Dataset) -> Dataset: ...


async def register_gazetteer_dataset(
    store: _Registers, region: str, *, by: str, unit: str
) -> Dataset:
    """The region's gazetteer dataset, held by `unit` (the build's setting), made if the store does
    not hold it (a rebuild keeps it, and its unit)."""
    return await store.register(
        Dataset(
            id=gazetteer_dataset_id(region),
            name=f"Gazetteer: OpenStreetMap ({region})",
            owning_unit=unit,
            created_at=datetime.now(UTC),
            created_by=by,
        )
    )


#: What a command-line build says when the Conduit's database cannot be reached to register the
#: gazetteer's dataset, in place of a connection traceback.
UNREACHABLE_DATASETS = (
    "Cannot reach the Conduit's database to register the gazetteer's dataset ({error}). The place "
    "names are loaded into it already; run the build again once the deployment is up to register "
    "it, so a case's Author can add it."
)

#: What a command-line build says about the places' points (ADR-147 Amendment 1).
NO_POINTS_HERE = (
    "The places' points were not written: the analytics store is the Conduit's, which a second "
    "process cannot open while it runs. Until a build from Admin › Maps writes them, these places "
    "are found by name but not offered by the map's place search."
)


class DatasetsUnreachable(RuntimeError):
    """The dataset store could not be reached; its words are `UNREACHABLE_DATASETS`'s."""


async def check_unit_from_env(
    unit: str, *, connect: Callable[[str], Awaitable[Any]] | None = None
) -> None:
    """The command-line builds' unit check (`check_unit`), against the Conduit's own database,
    before anything is built. An unreachable database is said in words."""
    from .config import PostgresConfig
    from .datasets import PostgresDatasetStore

    opener = connect or PostgresDatasetStore.connect
    try:
        store = await opener(PostgresConfig.from_env().dsn)
    except (OSError, asyncpg.PostgresError) as exc:
        words = UNREACHABLE_FOR_UNIT.format(unit=unit, error=type(exc).__name__)
        raise DatasetsUnreachable(words) from None
    try:
        check_unit(unit, await units_held(store))
    finally:
        await store.close()


#: The unit check's own words when the database cannot be reached: nothing is built yet.
UNREACHABLE_FOR_UNIT = (
    "Cannot reach the Conduit's database to check the unit {unit!r} ({error}), so nothing was "
    "built. Start the deployment and run the build again."
)


async def register_gazetteer_dataset_from_env(
    region: str, *, by: str, unit: str, connect: Callable[[str], Awaitable[Any]] | None = None
) -> Dataset:
    """The command-line builds' registration, against the Conduit's own database
    (`PostgresConfig.from_env`). An unreachable database is said in words, never a traceback."""
    from .config import PostgresConfig
    from .datasets import PostgresDatasetStore

    opener = connect or PostgresDatasetStore.connect
    try:
        store = await opener(PostgresConfig.from_env().dsn)
    except (OSError, asyncpg.PostgresError) as exc:
        raise DatasetsUnreachable(UNREACHABLE_DATASETS.format(error=type(exc).__name__)) from None
    try:
        return await register_gazetteer_dataset(store, region, by=by, unit=unit)
    finally:
        await store.close()


def is_gazetteer_place(node: Node, query: str) -> bool:
    """A gazetteer's place (a case's own copy of one, `provenance.gazetteer`, ADR-147 Amendment 2;
    or one in a gazetteer dataset: what the gazetteer holds, not a case's own location with a
    postcode) with a point, whose **name** holds `query`. The store is asked by name
    alone already (`suggest_locations`); the name is checked again here, ignoring case, since the
    store's match keeps case and is asked in several casings."""
    if node.type != "Location" or not node.properties.get("geometry_ref"):
        return False
    if not is_gazetteer_held(node):
        return False
    name = node.properties.get("name")
    return isinstance(name, str) and query.casefold() in name.casefold()


async def search_places(
    graph: GraphPort,
    analytics: AnalyticsPort,
    body: PlaceSearchRequest,
    principal: Principal,
) -> PlaceSearchResponse:
    """The gazetteer's places matching `body.query`, read with `principal` (the case's), each with
    its point. A place whose point the reader may not see, or that has none (a boundary), is not
    offered: there is nowhere to take the map."""
    query = body.query.strip()
    # Names alone, at the store (`GraphPort.suggest_locations`: `Location.name`, containing, the
    # access step in the traversal, rule 3): never an identifier, so neither the places nor
    # `more` can answer on an `osm_id` or a `uprn` (rule 7). Its match keeps case, so the words are
    # asked as typed, capitalised, in title case ("St Albans") and in lower case, and the answers
    # joined.
    found: dict[str, Node] = {}
    more = False
    for words in dict.fromkeys(
        (query, query[:1].upper() + query[1:], query.title(), query.lower())
    ):
        nodes = await graph.suggest_locations(words, principal, limit=SCAN_LIMIT + 1)
        more = more or len(nodes) > SCAN_LIMIT
        for node in nodes[:SCAN_LIMIT]:
            found.setdefault(node.id, node)
    candidates = [node for node in found.values() if is_gazetteer_place(node, query)]
    refs = list(dict.fromkeys(str(node.properties["geometry_ref"]) for node in candidates))
    points = {
        record.geometry_ref: record
        for record in (
            await analytics.get_geometries(refs, principal, version=POINT_GEOMETRY_VERSION)
            if refs
            else []
        )
        if record.kind is GeometryKind.POINT and record.lon is not None and record.lat is not None
    }
    places: list[MapPlace] = []
    for node in candidates:
        point = points.get(str(node.properties["geometry_ref"]))
        if point is None or point.lon is None or point.lat is None:
            continue
        places.append(
            MapPlace(id=node.id, name=str(node.properties["name"]), lon=point.lon, lat=point.lat)
        )
    places.sort(
        key=lambda place: (
            not place.name.casefold().startswith(query.casefold()),
            place.name.casefold(),
        )
    )
    return PlaceSearchResponse(places=places[: body.limit], more=len(places) > body.limit or more)


#: ADR-147 Amendment 2: a command-line build that could not refresh the cases' copies says so.
UNREFRESHED_COPIES = (
    "The places are committed, but the cases that added this gazetteer were not given them again: "
    "the Conduit's database could not be reached ({error}). Run the build again once the "
    "deployment is up."
)


async def refresh_case_copies_from_env(
    graph: GraphPort, scheme: HandlingScheme, gazetteer: str
) -> int:
    """The command-line builds' refresh of every case's copies of `gazetteer` (ADR-147 Amendment
    2: a re-build refreshes them), once its places are committed. Returns how many cases. The
    working sets are the Conduit's: a copy reverted here (its place gone) leaves an open case's
    canvas when the case is next opened. An unreachable database is said in words."""
    from .case_gazetteers import refresh_cases_from_env

    try:
        return await refresh_cases_from_env(graph, scheme, gazetteer)
    except (OSError, asyncpg.PostgresError) as exc:
        raise DatasetsUnreachable(UNREFRESHED_COPIES.format(error=type(exc).__name__)) from None
