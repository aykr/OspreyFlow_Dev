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
(`GraphPort.suggest_nodes`, rule 3), only the gazetteer's own places: a `Location` carrying one of
the external gazetteers' identifiers and a `geometry_ref`. A case's own locations (a yard, an
address in a statement) carry neither and are not offered as places. No hosted geocoder is ever
called here, whatever the deployment names (`OSPREY_ONLINE_GEOCODER` is the pipeline's enrich
stage's, ADR-136's egress rule applying there); §3.5 says none is.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import yaml

from ports.analytics import AnalyticsPort
from ports.graph import GraphPort, SuggestOptions
from schemas.analytics import GeometryKind
from schemas.domain import Node, Principal
from schemas.mapconfig import MapPlace, PlaceSearchRequest, PlaceSearchResponse

from .datasets import Dataset

#: The external gazetteers' identifiers on `Location` (`packages/ontology/default.yaml`, v7 and v9).
#: `site_ref` is not one: it names a deployment's own place (a yard, a wing), not a gazetteer's.
GAZETTEER_IDENTIFIERS: tuple[str, ...] = (
    "osm_id",
    "uprn",
    "os_place_id",
    "postcode",
    "gss_code",
    "gnis_feature_id",
    "tiger_geoid",
    "nad_address_id",
)

#: How many visible `Location`s one search reads before keeping the gazetteer's own: enough that a
#: case's own locations rarely crowd the places out, and when they do `more` says so.
SCAN_LIMIT = 200

_RECIPE = Path(__file__).resolve().parents[2] / "recipes" / "osm_gazetteer.yaml"


def gazetteer_dataset_id(region: str) -> str:
    """The dataset a region's gazetteer is loaded into."""
    return f"gazetteer-osm-{region}"


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


def is_gazetteer_place(node: Node) -> bool:
    if node.type != "Location":
        return False
    props = node.properties
    if not isinstance(props.get("name"), str) or not props.get("geometry_ref"):
        return False
    return any(props.get(identifier) not in (None, "") for identifier in GAZETTEER_IDENTIFIERS)


async def search_places(
    graph: GraphPort,
    analytics: AnalyticsPort,
    body: PlaceSearchRequest,
    principal: Principal,
) -> PlaceSearchResponse:
    """The gazetteer's places matching `body.query`, read with `principal` (the case's), each with
    its point. A place whose point the reader may not see, or that has none (a boundary), is not
    offered: there is nowhere to take the map."""
    found = await graph.suggest_nodes(
        body.query.strip(),
        principal,
        limit=SCAN_LIMIT,
        options=SuggestOptions(mode="contains", ignore_case=True, types=("Location",)),
    )
    candidates = [node for node in found.nodes if is_gazetteer_place(node)]
    refs = list(dict.fromkeys(str(node.properties["geometry_ref"]) for node in candidates))
    points = {
        record.geometry_ref: record
        for record in (await analytics.get_geometries(refs, principal) if refs else [])
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
            not place.name.casefold().startswith(body.query.casefold().strip()),
            place.name.casefold(),
        )
    )
    return PlaceSearchResponse(
        places=places[: body.limit], more=len(places) > body.limit or found.more
    )
