"""The map's place search (`POST /v1/investigations/{id}/map/places`, `02_GLASS_FRONTEND.md` §3.5,
ADR-147 Amendment 1), through the real app with the graph and the analytics store stood in.

What the stand-ins can prove, and only that: the route reads with the principal it is given (the
case's), asks the store for `Location`s by name alone (`suggest_locations`, whose match keeps case,
as the stand-in's does), keeps only the gazetteer's own places (in a `gazetteer-*` dataset, with a
point), takes each to its point, says `more` honestly and never on an identifier, never names a
gazetteer's identifier to the Glass (rule 7), never calls a hosted geocoder whatever the deployment
names, and audits. That the store limits the places to the case's datasets
and the reader's clearance is the store's (rule 3), proven live against ArcadeDB in
`tests/ingest/test_gazetteer_place_search_live.py`: a stand-in would pass whatever it is told.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from services.api.map_places import SCAN_LIMIT

from ports.graph import NodeSuggestions
from schemas.mapconfig import GAZETTEER_SOURCE_IDENTIFIERS
from services.api.app import (
    app,
    get_analytics,
    get_audit,
    get_graph,
    get_investigations,
    get_principal,
)

from schemas.analytics import GeometryKind, GeometryRecord
from schemas.domain import AuditStub, Node, Principal, Provenance, ProvenanceState, SourceRef
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)

from tests.services.api.any_case import AnyCase
from tests.services.api.test_search_route import _FakeAudit

PRINCIPAL = Principal(
    id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"],
    datasets=["case-data", "gazetteer-osm-rutland"],
)  # fmt: skip
HANDLING = {
    "classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1",
    "owning_unit": "unit-1",
}  # fmt: skip
#: A value no response may carry: the gazetteer's own identifier for a place (rule 7).
OSM_ID = "osm-node-31337-PLANTED"


def _location(node_id: str, dataset: str = "gazetteer-osm-rutland", **props: object) -> Node:
    return Node(
        id=node_id,
        type="Location",
        properties=dict(props),
        datasets=[dataset],
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="osm", locator="1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=HANDLING,  # type: ignore[arg-type]
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="fixture"),
    )


def _point(ref: str, lon: float, lat: float) -> GeometryRecord:
    return GeometryRecord(
        geometry_ref=ref, version=1, kind=GeometryKind.POINT, lon=lon, lat=lat,
        handling=HANDLING,  # type: ignore[arg-type]
    )  # fmt: skip


CRANFORD = _location("loc-cranford", name="Cranford", osm_id=OSM_ID, geometry_ref="g-cranford")
CRANBROOK = _location("loc-cranbrook", name="Cranbrook", uprn="100012", geometry_ref="g-cranbrook")
#: A case's own place, which no gazetteer holds: an address in a statement, geocoded, with a postcode
#: as a gazetteer's places have. In the case's dataset, so not a gazetteer's place.
YARD = _location(
    "loc-yard", dataset="case-data", name="Cranford yard 3", postcode="TW5 9QQ",
    geometry_ref="g-yard",
)  # fmt: skip
#: A gazetteer entry with no point (a boundary): there is nowhere to take the map.
NO_POINT = _location("loc-ward", name="Cranford ward", gss_code="E05000001")
#: A gazetteer place whose point the reader may not see.
HIDDEN_POINT = _location("loc-hidden", name="Cranham", osm_id="9", geometry_ref="g-hidden")


class _Graph:
    """`GraphPort.suggest_locations` as the ArcadeDB adapter answers it (`SuggestLocationsBuilder`):
    `Location.name` containing the words, **case kept** (`TextP.containing`), never an identifier,
    at most `limit`. A stand-in that matched ignoring case or on identifiers would accept what the
    real one refuses (rule 15)."""

    def __init__(self, nodes: list[Node]) -> None:
        self.nodes = nodes
        self.calls: list[tuple[str, Principal, int]] = []

    async def suggest_nodes(
        self, prefix: str, principal: Principal, *, limit: int = 10, options: object = None
    ) -> NodeSuggestions:
        """As the real one answers a `Location` scan (`suggestion_scope`): the name **and every
        identifier**, containing, ignoring case. Here so that a search going back to it fails at
        the identifier case's assertion, not on a missing method (rule 15)."""
        q = prefix.casefold()
        hits = [
            n for n in self.nodes
            if any(q in str(v).casefold() for k, v in n.properties.items()
                   if k in ("name", *GAZETTEER_SOURCE_IDENTIFIERS, "postcode", "site_ref"))
        ]  # fmt: skip
        return NodeSuggestions(nodes=hits[:limit], more=len(hits) > limit)

    async def suggest_locations(
        self, name: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        self.calls.append((name, principal, limit))
        return [
            n for n in self.nodes
            if n.type == "Location" and name in str(n.properties.get("name", ""))
        ][:limit]  # fmt: skip


class _Analytics:
    def __init__(self) -> None:
        self.asked: list[tuple[list[str], Principal]] = []
        self.points = {
            "g-cranford": _point("g-cranford", -1.15, 51.43),
            "g-cranbrook": _point("g-cranbrook", 0.53, 51.10),
            "g-yard": _point("g-yard", -1.149, 51.431),
        }

    async def get_geometries(
        self, refs: Sequence[str], principal: Principal, *, version: int | None = None
    ) -> list[GeometryRecord]:
        self.asked.append((list(refs), principal))
        return [self.points[r] for r in refs if r in self.points]


World = tuple[_Graph, _Analytics, _FakeAudit]


@pytest.fixture
def world() -> Iterator[World]:
    graph = _Graph([YARD, CRANFORD, NO_POINT, HIDDEN_POINT, CRANBROOK])
    analytics = _Analytics()
    audit = _FakeAudit()
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_analytics] = lambda: analytics
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = lambda: audit
    yield graph, analytics, audit
    app.dependency_overrides.clear()


def _search(query: str = "cran", **extra: object) -> httpx.Response:
    return TestClient(app).post(
        "/v1/investigations/inv-1/map/places", json={"query": query, **extra}
    )


def test_only_the_gazetteers_places_with_a_point_are_offered(world: World) -> None:
    graph, analytics, audit = world
    response = _search()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "places": [
            {"id": "loc-cranbrook", "name": "Cranbrook", "lon": 0.53, "lat": 51.10},
            {"id": "loc-cranford", "name": "Cranford", "lon": -1.15, "lat": 51.43},
        ],
        "more": False,
    }
    # Read with the case's principal, by name, the words as typed and capitalised (the store's
    # match keeps case).
    assert [(words, principal) for words, principal, _limit in graph.calls] == [
        ("cran", PRINCIPAL), ("Cran", PRINCIPAL),
    ]  # fmt: skip
    # The yard's point is never asked after: it is not a gazetteer's place.
    assert all("g-yard" not in refs and p == PRINCIPAL for refs, p in analytics.asked)
    assert audit.records[-1]["action"] == "map_place_search"
    assert audit.records[-1]["investigation_id"] == "inv-1"
    assert audit.records[-1]["result_cardinality"] == 2


def test_a_gazetteers_own_identifier_never_reaches_the_glass(world: World) -> None:
    """Rule 7: a source-system identifier (`osm_id`, `uprn`) is the gazetteer's, never the
    Glass's."""
    response = _search()
    assert OSM_ID not in response.text and "100012" not in response.text
    for place in response.json()["places"]:
        assert set(place) == {"id", "name", "lon", "lat"}


def test_more_is_said_when_more_places_matched_than_are_shown(world: World) -> None:
    """Rule 2: a short list is never passed off as every match."""
    assert _search(limit=1).json() == {
        "places": [{"id": "loc-cranbrook", "name": "Cranbrook", "lon": 0.53, "lat": 51.10}],
        "more": True,
    }
    graph, _analytics, _audit = world
    # The store's scan filled by a case's own places named alike: more matched than were read.
    graph.nodes = [
        _location(f"own-{i}", dataset="case-data", name=f"Cranwell {i}", geometry_ref="g-x")
        for i in range(SCAN_LIMIT + 1)
    ]
    assert _search().json() == {"places": [], "more": True}


def test_a_query_too_short_or_too_long_is_refused_and_asks_nothing(world: World) -> None:
    graph, analytics, audit = world
    client = TestClient(app)
    for bad in ({"query": "c"}, {"query": "x" * 101}, {"query": "cran", "limit": 0},
                {"query": "cran", "limit": 26}):  # fmt: skip
        assert client.post("/v1/investigations/inv-1/map/places", json=bad).status_code == 422
    assert graph.calls == [] and analytics.asked == [] and audit.records == []


def test_the_route_needs_a_principal(world: World) -> None:
    """Rule 4 at the route: no principal, no answer, and the store is asked nothing."""
    graph, _analytics, _audit = world
    app.dependency_overrides.pop(get_principal)
    assert _search().status_code in (401, 403)
    assert graph.calls == []


def test_no_hosted_geocoder_is_called_even_when_the_deployment_names_one(world: World) -> None:
    """§3.5: "no hosted geocoder is ever called". The deployment's online geocoder (the pipeline's
    enrich stage's, `OSPREY_ONLINE_GEOCODER`) is set here and must be asked nothing, even for a
    name the gazetteer does not hold."""
    asked: list[str] = []

    async def online(name: str) -> tuple[float, float] | None:
        asked.append(name)
        return (0.0, 0.0)

    previous = getattr(app.state, "online_geocode", None)
    app.state.online_geocode = online
    try:
        graph, _analytics, _audit = world
        graph.nodes = []
        response = _search("Nowhere-on-the-gazetteer")
        assert response.json() == {"places": [], "more": False}
        assert _search().status_code == 200
    finally:
        app.state.online_geocode = previous
    assert asked == []


class _OneCase:
    """Holds `held` for the principal on `inv-1` alone, and applies it as the real store does
    (`InvestigationStore.get_authorized`): no level, or another case, is not found."""

    def __init__(self, held: AccessLevel | None) -> None:
        self.held = held

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        if investigation_id != "inv-1" or self.held is None:
            raise InvestigationNotFoundError(investigation_id)
        if self.held.rank < need.rank:
            raise InsufficientAccessError(f"{need.value} needed")
        return Investigation(
            id="inv-1", name="A case", created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="alice", owning_unit="unit-1",
        )  # fmt: skip


@pytest.mark.parametrize(
    ("held", "case", "answered"),
    [
        (None, "inv-1", False),  # no level on the case
        (AccessLevel.VIEWER, "inv-2", False),  # another case's id
        (AccessLevel.VIEWER, "inv-1", True),
    ],
)
def test_the_case_level_is_checked_before_the_store_is_asked(
    world: World, held: AccessLevel | None, case: str, answered: bool
) -> None:
    """Rule 4 at the route, through the real level dependency (`_authorized_at`): a reader with
    no level on the case, or naming another case, is answered as the case not existing, and the
    store is asked nothing."""
    graph, analytics, audit = world
    app.dependency_overrides[get_investigations] = lambda: _OneCase(held)
    response = TestClient(app).post(f"/v1/investigations/{case}/map/places", json={"query": "cran"})
    if answered:
        assert response.status_code == 200 and response.json()["places"]
        assert graph.calls
    else:
        assert response.status_code == 404, response.text
        assert graph.calls == [] and analytics.asked == []
        assert all(r["action"] != "map_place_search" for r in audit.records)


def test_a_match_on_a_gazetteers_identifier_alone_offers_nothing(world: World) -> None:
    """Rule 7: the place search once asked the store's general suggestion scan, which matches a
    `Location` on its identifiers too, so a search for part of a `uprn` reached Cranbrook by it,
    and a run of such searches could rebuild the identifier. It now asks by name alone
    (`suggest_locations`), so such a fragment offers nothing."""
    for query in ("100012", "00012", OSM_ID[:8]):
        response = _search(query)
        assert response.json() == {"places": [], "more": False}, query


def test_a_spaces_only_query_is_refused_not_a_scan(world: World) -> None:
    graph, _analytics, _audit = world
    for spaces in ("   ", " a "):
        assert _search(spaces).status_code == 422
    assert graph.calls == []


def test_an_identifier_fragment_finds_no_place_and_says_no_more(world: World) -> None:
    """Rule 7 (the independent review): the store is asked by name alone, so a fragment of an
    `osm_id` or a `uprn` matches nothing there, and `more` cannot answer on it either. A run of such
    searches tells the reader nothing about a place's identifier."""
    graph, _analytics, _audit = world
    # Many places carrying the fragment in their identifiers, enough to fill a scan.
    graph.nodes = [
        _location(f"p-{i}", name=f"Hamlet {i}", osm_id=f"31337{i:04d}", uprn=f"1000{i:06d}",
                  geometry_ref="g-cranford")
        for i in range(SCAN_LIMIT + 5)
    ]  # fmt: skip
    for fragment in ("31337", "1000", "osm-node"):
        assert _search(fragment).json() == {"places": [], "more": False}, fragment


def test_a_case_s_copy_of_a_gazetteer_place_is_offered(world: World) -> None:
    """ADR-147 Amendment 2 (the owner's ruling 6): a case that added a gazetteer reads its places as
    copies in its own dataset, known by their provenance; a case's own location stays the case's."""
    graph, analytics, _audit = world
    copy = _location("loc-copy", dataset="case-data", name="Cranwell", osm_id=OSM_ID,
                     geometry_ref="g-copy")  # fmt: skip
    copy.provenance.gazetteer = "gazetteer-osm-rutland"
    graph.nodes = [YARD, copy]
    analytics.points["g-copy"] = _point("g-copy", -0.5, 53.0)
    body = _search().json()
    assert body["places"] == [{"id": "loc-copy", "name": "Cranwell", "lon": -0.5, "lat": 53.0}]
    assert OSM_ID not in str(body)
