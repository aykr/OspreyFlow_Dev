"""The gazetteer's places: the dataset they are loaded into, and the analyst's place search over
them (`spec/02_GLASS_FRONTEND.md` §3.5's gazetteer search; ADR-147 Amendment 1, P4).

**Where the places are kept.** A gazetteer built in the Conduit (`map_admin.build_basemap`, from
*Admin › Maps*, the set-up console or `ospreyflow map build`) loads its places into a dataset of
its own, `gazetteer-osm-<region>` (the orchestrator's settlement of 9 November 2026). Before P4
they were loaded by the Conduit's own principal into no dataset at all, so no case read them
(ADR-099 decision 5) and a place search would have found nothing anywhere. A case reads the
gazetteer when its Author adds that dataset to it, as any other (ADR-099 Amendment 12: a composite
of the two).

The dataset is held by the unit the gazetteer recipe gives its places
(`recipes/osm_gazetteer.yaml`'s `defaults.handling.owning_unit`), whoever runs the build: the
places are that unit's by their own handling, so the dataset is too, and a build from the console
and one from the command line give the same answer.

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
from pathlib import Path
from typing import Any, Protocol

import asyncpg
import yaml
from services.ingest.geometries import POINT_GEOMETRY_VERSION

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

_RECIPE = Path(__file__).resolve().parents[2] / "recipes" / "osm_gazetteer.yaml"


def gazetteer_dataset_id(region: str) -> str:
    """The dataset a region's gazetteer is loaded into."""
    return f"{GAZETTEER_DATASET_PREFIX}osm-{region}"


def gazetteer_unit(recipe: Path = _RECIPE) -> str:
    """The unit the gazetteer recipe gives its places, which holds their dataset."""
    loaded = yaml.safe_load(recipe.read_text(encoding="utf-8"))
    return str(loaded["defaults"]["handling"]["owning_unit"])


class _Registers(Protocol):
    async def register(self, dataset: Dataset) -> Dataset: ...


async def register_gazetteer_dataset(store: _Registers, region: str, *, by: str) -> Dataset:
    """The region's gazetteer dataset, made if the store does not hold it (a rebuild keeps it)."""
    return await store.register(
        Dataset(
            id=gazetteer_dataset_id(region),
            name=f"Gazetteer: OpenStreetMap ({region})",
            owning_unit=gazetteer_unit(),
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


async def register_gazetteer_dataset_from_env(
    region: str, *, by: str, connect: Callable[[str], Awaitable[Any]] | None = None
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
        return await register_gazetteer_dataset(store, region, by=by)
    finally:
        await store.close()


def is_gazetteer_place(node: Node, query: str) -> bool:
    """A gazetteer's place (in a gazetteer dataset: what the gazetteer holds, not a case's own
    location with a postcode) with a point, whose **name** holds `query`. The store is asked by name
    alone already (`suggest_locations`); the name is checked again here, ignoring case, since the
    store's match keeps case and is asked in several casings."""
    if node.type != "Location" or not node.properties.get("geometry_ref"):
        return False
    if not any(d.startswith(GAZETTEER_DATASET_PREFIX) for d in node.datasets):
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
    # asked as typed, capitalised and in lower case, and the answers joined.
    found: dict[str, Node] = {}
    more = False
    for words in dict.fromkeys((query, query[:1].upper() + query[1:], query.lower())):
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
