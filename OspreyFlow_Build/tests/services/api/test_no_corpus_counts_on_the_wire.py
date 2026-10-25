"""No Conduit response carries `weight_components` (ADR-122; rules 3 and 7).

`Edge.weight_components` holds `corpus_source_degree`, `corpus_target_degree`,
`corpus_pair_count` and `corpus_total_occurrences`, counted over the whole store, links above any
one principal's clearance included. A response that carries them lets an unauthorised principal
detect a filtered link through a degree count (rule 3) and sends the Glass an unfiltered count
(rule 7). The rule is enforced where every response is built, so a new route cannot reintroduce it.

The violation each test catches is named in its own docstring. The set of routes is not a list kept
here: it is read from `app.routes`, so a route that returns links and is added later is covered
without anyone remembering to add it, and a response model this file cannot build an instance of
fails the file instead of being skipped.

Limit: the walk sees a route only through its `response_model`. A route that returns a raw mapping
or a `JSONResponse` has none and is not walked, and neither is a WebSocket route, which has no
response model at all; ADR-122 Amendment 1 covers both by excluding the field on the model itself,
which any serialisation of an `Edge` honours. The WebSocket stream is proven separately, by the
delta cases below (the deltas it sends, built from the delta models). A route of the raw-mapping
kind is not proven by this file. Nor does it see a model field typed `Any` or `dict[str, Any]`
that holds an `Edge` at run time.

**ADR-124 (U2a) adds a second gate to this file, over a different rule:** no response and no delta
carries a figure for what its reader may not read (`filtered_count`, `unreadable_count`,
`withheld_count`; rules 3 and 7). It does not look for an `Edge`: it walks the field names of every
route's response model, and of every delta model, so a route with no link in it is covered too.
A route with no field to walk must be named: a JSON mapping in `RAW_MAPPING_ROUTES` (each has a
case of its own), anything else in `NON_JSON_ROUTES` with the reason it carries no figure (no
body, bytes, a stream), or the file fails. `withheld_count` has no exemption: the export manifest
and the export ledger carried it until U9 replaced it with a yes or no (`withheld`).

Pure: imports the app and builds models, opens no connection. Needs `ARCADEDB_HTTP_PORT` and
`POSTGRES_PORT` pointed at unreachable ports only because importing the app reads settings.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import textwrap
import typing
from collections.abc import Callable
from typing import Annotated, Any

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from pydantic import BaseModel, Field, computed_field
from services.api.app import app
from services.api.working_set.models import (
    DeltaAdd,
    DeltaRemove,
    DeltaRemoveSent,
    DeltaReplaceEdge,
    DeltaReplaceEdgeSent,
    DeltaReproject,
    DeltaSnapshot,
    WorkingSetDeltaSent,
)

from schemas.domain import Edge, Subgraph, WeightComponents

from .corpus_counts import (
    FORBIDDEN_KEYS,
    SIZE_KEYS,
    WITHHELD_KEYS,
    build,
    contains_model,
    edge_with_components,
    field_names_reachable,
    keys_at_any_depth,
)


def _routes_returning_links() -> list[APIRoute]:
    return [
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.response_model is not None
        and contains_model(route.response_model, Edge, set())
    ]


def _label(route: APIRoute) -> str:
    return f"{sorted(route.methods or ['?'])[0]} {route.path}"


def test_the_app_has_routes_that_return_links() -> None:
    """Violation caught: the walk over `app.routes` finds nothing (a renamed attribute, a changed
    FastAPI internal), so every per-route case below is parametrised over an empty list and the
    file passes having checked nothing."""
    routes = _routes_returning_links()
    labels = {_label(r) for r in routes}

    assert len(routes) >= 10
    assert "POST /v1/investigations/{investigation_id}/expand" in labels
    assert "POST /v1/investigations/{investigation_id}/links-among" in labels
    assert "POST /v1/investigations/{investigation_id}/paths" in labels
    # No route returns a bare `Subgraph`; the ones that carry one (a seed, a replayed history step,
    # a connections query) are pinned too, so losing one from the walk is a failure.
    assert "POST /v1/investigations/{investigation_id}/seed" in labels
    assert "POST /v1/investigations/{investigation_id}/history/{step_id}" in labels
    assert "POST /v1/investigations/{investigation_id}/connections" in labels


@pytest.mark.parametrize("route", _routes_returning_links(), ids=_label)
def test_a_response_that_returns_links_never_carries_corpus_counts(route: APIRoute) -> None:
    """Violation caught (ADR-122, rule 3 and 7): a response serialised as FastAPI serialises it
    (`response_field.serialize`, json mode) contains `weight_components`, or any of the four
    corpus counts, at any depth, for an Edge that has components. The built instance holds the
    Edge with components wherever the model can hold an Edge."""
    assert route.response_field is not None
    instance = build(route.response_model, edge_with_components())
    assert instance is not None, f"cannot build an instance of {route.response_model}"

    wire = route.response_field.serialize(instance, mode="json")

    assert "e-1" in repr(wire), f"{_label(route)}: the built instance carried no Edge at all"
    assert keys_at_any_depth(wire) & FORBIDDEN_KEYS == set(), _label(route)


def test_the_key_walk_finds_the_counts_where_the_field_is_not_excluded() -> None:
    """Violation caught (rule 15, the gate shown able to fail): the key walk is blind, so every
    per-route case passes for a response that does carry the counts. A stand-in link whose
    `weight_components` is not excluded, serialised the way a route would, must show every
    forbidden key at depth; the real `Edge` must show none, and must still hold the components in
    Python (the weight is computed from them)."""
    edge = edge_with_components()

    class UnguardedEdge(BaseModel):
        weight_components: WeightComponents | None = None

    class Holder(BaseModel):
        edges: list[UnguardedEdge]

    unguarded = Holder(edges=[UnguardedEdge(weight_components=edge.weight_components)])
    assert FORBIDDEN_KEYS <= keys_at_any_depth(unguarded.model_dump(mode="json"))

    assert keys_at_any_depth(edge.model_dump(mode="json")) & FORBIDDEN_KEYS == set()
    assert edge.weight_components is not None
    assert edge.weight_components.corpus_source_degree == 11


STREAM_PATH = "/v1/investigations/{investigation_id}/stream"


def _delta_models() -> list[type[BaseModel]]:
    """The deltas that are *sent* (`WorkingSetDeltaSent`), not the stored ones, which hold the
    record of what was removed (ADR-124 decision 4)."""
    union = typing.get_args(WorkingSetDeltaSent)[0]
    return list(typing.get_args(union))


def test_the_stream_route_exists_and_every_delta_model_is_known_to_this_file() -> None:
    """Violation caught: the WebSocket stream is renamed or removed so the delta cases below
    guard nothing, or a delta model that holds an `Edge` is added to `WorkingSetDelta` without
    this file's per-delta case below covering it (the set that holds links is pinned by name)."""
    streams = [
        r
        for r in app.routes
        if isinstance(r, APIWebSocketRoute)
        and r.path.endswith("/investigations/{investigation_id}/stream")
    ]
    assert len(streams) == 1

    holding = {m for m in _delta_models() if contains_model(m, Edge, set())}
    assert holding == {DeltaAdd, DeltaReplaceEdgeSent, DeltaSnapshot}
    # `DeltaNotice` left the protocol with ADR-124 U2c: its only producers were the withheld
    # notices, so a delta set that still holds one is a delta set that can still send a count.
    assert {m.__name__ for m in _delta_models()} == {
        "DeltaAdd",
        "DeltaRemoveSent",
        "DeltaReplaceEdgeSent",
        "DeltaReproject",
        "DeltaSnapshot",
        "DeltaViewOverCap",
    }


@pytest.mark.parametrize("delta_model", _delta_models(), ids=lambda m: m.__name__)
def test_a_delta_the_stream_sends_never_carries_corpus_counts(
    delta_model: type[BaseModel],
) -> None:
    """Violation caught (ADR-122, rule 3 and 7): a delta sent on the working-set WebSocket
    (`delta.model_dump_json()`, `app.py` stream, resync and live push; `notify.publish_delta` and
    the delta store dump it the same way) contains `weight_components` or a corpus count at any
    depth, for an Edge that has components. Every model in `WorkingSetDelta` is built holding that
    Edge where it can hold one and dumped as the stream dumps it."""
    instance = build(delta_model, edge_with_components())
    assert instance is not None
    sent = json.loads(instance.model_dump_json())

    if contains_model(delta_model, Edge, set()):
        assert "e-1" in repr(sent), f"{delta_model.__name__}: no Edge in the built delta"
    assert keys_at_any_depth(sent) & FORBIDDEN_KEYS == set(), delta_model.__name__


# --- ADR-124 (U2a): no response and no delta carries a figure for what the reader may not read ---


def _wire_annotation(route: APIRoute) -> Any:
    """What a route puts on the wire: its `response_model`, or, where it declares none, what its
    handler is annotated to return (`reports/feed` returns `ReportFigures | Response`)."""
    if route.response_model is not None:
        return route.response_model
    return inspect.signature(route.endpoint, eval_str=True).return_annotation


def _api_routes() -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute)]


def test_the_withheld_figure_walk_sees_every_route() -> None:
    """Violation caught: the walk over `app.routes` finds few or none (a renamed attribute, a
    changed FastAPI internal), so the per-route case below is parametrised over a short list and
    the file passes having checked little."""
    labels = {_label(r) for r in _api_routes()}

    assert len(labels) >= 200
    for pinned in (
        "POST /v1/investigations/{investigation_id}/expand",
        "POST /v1/investigations/{investigation_id}/expand/preview",
        "POST /v1/investigations/{investigation_id}/seed",
        "POST /v1/investigations/{investigation_id}/history/{step_id}",
        "POST /v1/investigations/{investigation_id}/alerts/{alert_id}/jump",
        "PUT /v1/investigations/{investigation_id}/resolution/threshold",
        "GET /healthz",
    ):
        assert pinned in labels, pinned


@pytest.mark.parametrize("route", _api_routes(), ids=_label)
def test_no_route_can_put_a_withheld_figure_on_the_wire(route: APIRoute) -> None:
    """Violation caught (ADR-124 decision 1, rules 3 and 7): a route whose response, at any depth,
    can carry `filtered_count` or `unreadable_count`: a figure that points at what the reader may
    not read, which a field held at 0 would still claim was complete. Every route is walked,
    whether or not its response holds an `Edge`."""
    assert _withheld_figures_on(route) == set(), _label(route)


@pytest.mark.parametrize("route", _api_routes(), ids=_label)
def test_no_route_can_put_a_step_size_on_the_wire(route: APIRoute) -> None:
    """Violation caught (ADR-124 decision 8, rules 3 and 7): a response, at any depth, that can
    carry `node_count` or `edge_count`. The history listing carried both, counted over a snapshot
    of the stored material, unfiltered. No route returns either name today (checked by running
    this walk over the app), so the set is global rather than kept per route."""
    assert field_names_reachable(_wire_annotation(route)) & SIZE_KEYS == set(), _label(route)


class _Sized(BaseModel):
    id: str
    node_count: int
    edge_count: int


def test_a_step_size_on_a_response_is_found_by_the_gate() -> None:
    """Violation caught (rule 15, the gate shown able to fail): the history listing's old shape,
    a list of steps each with its two sizes, walked by the predicate the per-route case uses."""
    assert field_names_reachable(list[_Sized]) & SIZE_KEYS == SIZE_KEYS


def _withheld_figures_on(route: APIRoute) -> set[str]:
    """The withheld figures `route` can carry. There is no exemption: the export manifest and the
    export ledger carried `withheld_count` until ADR-124 U9 replaced it with a yes or no."""
    return field_names_reachable(_wire_annotation(route)) & WITHHELD_KEYS


class _Figure(BaseModel):
    withheld_count: int = 0


class _Page(BaseModel):
    figures: list[_Figure]


def test_a_withheld_count_on_any_route_is_found_by_the_gate() -> None:
    """Violation caught (rule 15, the gate shown able to fail): a route that carries
    `withheld_count`, or either other figure, wherever it is, the export manifest's and the
    ledger's own paths included. A throwaway app with such routes, walked by the same predicate the
    per-route case uses."""
    from fastapi import FastAPI

    planted = FastAPI()

    @planted.get("/v1/investigations/{investigation_id}/something-new", response_model=_Page)
    async def something_new() -> _Page:  # pragma: no cover - never called
        return _Page(figures=[])

    @planted.get("/v1/exports", response_model=_Page)
    async def the_ledger() -> _Page:  # pragma: no cover
        return _Page(figures=[])

    @planted.post("/v1/investigations/{investigation_id}/export", response_model=_Figure)
    async def the_export() -> _Figure:  # pragma: no cover
        return _Figure()

    found = {_label(r): _withheld_figures_on(r) for r in planted.routes if isinstance(r, APIRoute)}

    assert found["GET /v1/investigations/{investigation_id}/something-new"] == {"withheld_count"}
    assert found["GET /v1/exports"] == {"withheld_count"}
    assert found["POST /v1/investigations/{investigation_id}/export"] == {"withheld_count"}


PACK_EXPORT_ROUTE = "POST /v1/investigations/{investigation_id}/packs/{pack_id}/export"


def _is_a_yes_or_no(annotation: Any) -> bool:
    """`bool` or `bool | None`, and nothing else: `withheld` is an allowed name for a flag, so the
    gate pins its type where an export carries it."""
    options = {a for a in typing.get_args(annotation) if a is not type(None)} or {annotation}
    return options == {bool}


def test_the_pack_export_sends_withheld_as_a_yes_or_no_never_a_number() -> None:
    """Violation caught (ADR-124 decision 9, ruled for packs): the pack export's `withheld` typed
    as an integer, a count of the pack's items the exporter may not view. The name is allowed (it
    is the flag), so the type is what is pinned: on the route's response model, and on the wire
    for an instance that says true."""
    route = _route_named(PACK_EXPORT_ROUTE)
    model = _wire_annotation(route)
    assert _is_a_yes_or_no(model.model_fields["withheld"].annotation)
    instance = build(model, edge_with_components())
    assert instance is not None
    wire = route.response_field.serialize(instance, mode="json")  # type: ignore[union-attr]
    assert wire["withheld"] is False  # built fields are the type's zero: a bool, not 0


class _CountedExport(BaseModel):
    withheld: int | None = None


class _FlagExport(BaseModel):
    withheld: bool | None = None


def test_the_yes_or_no_pin_rejects_an_integer_withheld() -> None:
    """Violation caught (rule 15, the pin shown able to fail): the pack export's old shape."""
    assert not _is_a_yes_or_no(_CountedExport.model_fields["withheld"].annotation)
    assert _is_a_yes_or_no(_FlagExport.model_fields["withheld"].annotation)
    assert _is_a_yes_or_no(bool)
    assert not _is_a_yes_or_no(int)


class _Inner(BaseModel):
    filtered_count: int = 0


class _Deep(BaseModel):
    by_kind: dict[str, list[_Inner | None]]


class _Aliased(BaseModel):
    n: int = Field(default=0, alias="unreadable_count")


class _Computed(BaseModel):
    @computed_field  # type: ignore[prop-decorator]
    @property
    def filtered_count(self) -> int:
        return 0


@dataclasses.dataclass
class _Plain:
    inner: _Inner


class _Clean(BaseModel):
    edges: list[Edge]
    total: int


def test_the_withheld_figure_walk_finds_a_field_wherever_a_model_can_hold_it() -> None:
    """Violation caught (rule 15, the gate shown able to fail): the field-name walk is blind to a
    nesting, so every per-route case passes for a response that does carry the figure. Each shape a
    response uses is built here with the field inside it, and the walk must find it; the same walk
    over a model without it must find none."""
    for shape in (
        _Inner,
        _Deep,
        list[_Deep],
        _Deep | None,
        Annotated[_Deep, "doc"],
        dict[str, _Deep],
        _Plain,
        _Computed,
    ):
        assert "filtered_count" in field_names_reachable(shape), shape
    assert "unreadable_count" in field_names_reachable(_Aliased)
    assert field_names_reachable(_Clean) & WITHHELD_KEYS == set()


@pytest.mark.parametrize("delta_model", _delta_models(), ids=lambda m: m.__name__)
def test_no_delta_model_can_carry_a_withheld_figure(delta_model: type[BaseModel]) -> None:
    """Violation caught (ADR-124 decision 1): a delta sent on the working-set WebSocket whose
    shape holds `filtered_count` or `unreadable_count`. Every model in `WorkingSetDelta` is walked,
    whether or not it holds an `Edge`."""
    assert field_names_reachable(delta_model) & WITHHELD_KEYS == set(), delta_model.__name__


@pytest.mark.parametrize("delta_model", _delta_models(), ids=lambda m: m.__name__)
def test_no_sent_delta_can_carry_the_record_of_what_was_removed(
    delta_model: type[BaseModel],
) -> None:
    """Violation caught (ADR-124 decision 4, rule 3): a sent delta whose shape holds `removed`, the
    record of the handling, datasets and ends of what a removal or a replacement removed. It is
    for the stored form alone; a sent form that could hold it could send it. The behavioural half
    (a projection that passes the record through) is `test_delta_projection.py`."""
    assert "removed" not in field_names_reachable(delta_model), delta_model.__name__


@pytest.mark.parametrize("route", _api_routes(), ids=_label)
def test_no_route_can_put_the_removal_record_on_the_wire(route: APIRoute) -> None:
    """Violation caught (ADR-124 decision 4, rule 3): a route whose response, at any depth, can hold
    `removed`: the record of what a removal or a replacement removed, which belongs to the stored
    form that is published and never to anything a route returns. A route that returns a stored
    delta by annotating it as one is the way it would get out."""
    assert "removed" not in field_names_reachable(_wire_annotation(route)), _label(route)


#: The routes that return a delta the stored way (a replacement), and what each is given.
ROUTES_RETURNING_A_REPLACEMENT = [
    "DELETE /v1/investigations/{investigation_id}/nodes/{node_id}/picture",
    "POST /v1/investigations/{investigation_id}/links/{edge_id}/change",
    "PUT /v1/investigations/{investigation_id}/nodes/{node_id}/picture",
]


def test_the_pinned_replacement_routes_are_the_routes_that_can_return_one() -> None:
    """Violation caught (rule 15): a route added that returns a replacement or a removal, and is
    not in the hand-kept list above, so the serialisation case below never sees it. The set is
    derived from the app's own routes (a response model that holds either sent form) and must
    equal the list."""
    derived = {
        _label(r)
        for r in _api_routes()
        if contains_model(_wire_annotation(r), DeltaReplaceEdgeSent, set())
        or contains_model(_wire_annotation(r), DeltaRemoveSent, set())
    }

    assert derived == set(ROUTES_RETURNING_A_REPLACEMENT)


def _route_named(label: str) -> APIRoute:
    (route,) = [r for r in _api_routes() if _label(r) == label]
    return route


@pytest.mark.parametrize("label", ROUTES_RETURNING_A_REPLACEMENT)
async def test_a_stored_replacement_serialised_as_the_route_would_carries_no_record(
    label: str,
) -> None:
    """Violation caught (rule 3): a route that returns the stored object, record and all. The
    stored replacement is put through the route's own `response_field` as FastAPI puts a returned
    value through it (`serialize_response`), at every place the response can hold one, and the key
    `removed` is nowhere in what comes out."""
    from fastapi.routing import serialize_response
    from services.api.working_set.models import RemovedElement

    from .working_set.test_visible_link import edge

    stored = DeltaReplaceEdge(
        seq=1,
        old_edge_id="old",
        edge=edge("new", "a", "b"),
        removed=RemovedElement(handling=edge("old", "a", "b").handling, source="a", target="b"),
    )
    route = _route_named(label)
    instance = build(route.response_model, edge_with_components())
    assert instance is not None, f"cannot build an instance of {route.response_model}"

    def with_the_stored_replacement(value: Any) -> Any:
        """The built instance as plain data, each replacement in it swapped for the stored one."""
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        if isinstance(value, dict):
            if value.get("op") == "replace_edge":
                return stored.model_dump(mode="json")
            return {k: with_the_stored_replacement(v) for k, v in value.items()}
        if isinstance(value, list):
            items = [with_the_stored_replacement(v) for v in value]
            if items and all(isinstance(i, dict) and "op" in i for i in items):
                # A list of deltas holds the stored replacement alone (an unvalidated built node
                # in the others would not survive the route's own validation).
                return [stored.model_dump(mode="json")]
            return items
        return value

    returned = with_the_stored_replacement(instance)
    assert "removed" in keys_at_any_depth(returned), f"{label}: the stored form was not planted"

    wire = await serialize_response(
        field=route.response_field, response_content=returned, is_coroutine=True
    )

    assert "old" in repr(wire), f"{label}: the replacement is not in what the route sends"
    assert "removed" not in keys_at_any_depth(wire), label


def test_the_record_walk_finds_the_field_on_the_stored_forms() -> None:
    """Violation caught (rule 15, the gate shown able to fail): the walk is blind to `removed`, so
    the case above passes whatever a sent delta holds. It must find the field on the two stored
    forms, which do hold it, and the stored forms must be the only ones that do."""
    assert "removed" in field_names_reachable(DeltaRemove)
    assert "removed" in field_names_reachable(DeltaReplaceEdge)
    assert not {m for m in _delta_models() if "removed" in field_names_reachable(m)}


async def test_projecting_each_stored_delta_form_never_sends_the_record() -> None:
    """Violation caught (ADR-124 decision 4, rule 3), by the projection and not only by the shape of
    the sent models: a `project_delta` that passes the stored form through (`DeltaRemove` and
    `DeltaReplaceEdge` hold the record of what they removed). Each stored form is projected for an
    OFFICIAL and a SECRET reader, as the live forward builds it, and the key `removed` is nowhere
    in what is sent. Unlike the shape case above this one is red against a leaking projection."""
    from services.api.working_set.models import RemovedElement, RemovedRecord
    from services.api.working_set.service import WorkingSetService

    from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
    from .working_set.test_visible_link import OFFICIAL_READER, SCHEME, SECRET_READER, edge, node

    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [node("a"), node("b"), node("s", "SECRET")])
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)
    old = edge("old", "a", "b")
    stored_forms = [
        DeltaRemove(
            seq=1,
            node_ids=["a", "s"],
            edge_ids=["old"],
            removed=RemovedRecord(
                nodes={
                    "a": RemovedElement(handling=node("a").handling),
                    "s": RemovedElement(handling=node("s", "SECRET").handling),
                },
                edges={
                    "old": RemovedElement(handling=old.handling, source="a", target="b"),
                },
            ),
        ),
        DeltaReplaceEdge(
            seq=2,
            old_edge_id="old",
            edge=edge("new", "a", "b"),
            removed=RemovedElement(handling=old.handling, source="a", target="b"),
        ),
    ]

    for reader in (OFFICIAL_READER, SECRET_READER):
        for stored in stored_forms:
            sent = await service.project_live("inv-1", stored, reader)
            assert "removed" not in keys_at_any_depth(sent.model_dump(mode="json"))
            assert type(sent) not in {DeltaRemove, DeltaReplaceEdge}


def test_a_reproject_delta_carries_no_figure_of_the_actors_view() -> None:
    """Violation caught (ADR-124 decision 1): `merged`, `split` and `affected` ride a delta every
    reader receives, counted from the actor's own view. They are the acting analyst's own
    response (`ResolutionOutcome`), not the delta's."""
    assert {"merged", "split", "affected"} & set(DeltaReproject.model_fields) == set()


#: Routes that answer with a bare mapping, which has no model to walk. Each is read by hand: the
#: three below return a figure of their own (`seq`, `removed`, a liveness word), none a withheld
#: one; `test_a_raw_mapping_route_names_no_withheld_figure` is the case for each, and the list
#: below is what lets a new one in only by being named here.
RAW_MAPPING_ROUTES = {
    "DELETE /v1/investigations/{investigation_id}/nodes",
    "DELETE /v1/investigations/{investigation_id}/nodes/{node_id}/suppression-mark",
    "GET /healthz",
}


#: Routes whose response has no field to walk and is not a JSON mapping, each with why it carries
#: no figure. A route that returns a body of another kind has to be named here.
NON_JSON_ROUTES: dict[str, str] = {
    "PUT /v1/investigations/{investigation_id}/tab": "204, no body",
    "DELETE /v1/investigations/{investigation_id}": "204, no body",
    "PUT /v1/investigations/{investigation_id}/access": "204, no body",
    "PUT /v1/investigations/{investigation_id}/access/grants/{account_id}": "204, no body",
    "DELETE /v1/investigations/{investigation_id}/access/grants/{account_id}": "204, no body",
    "DELETE /v1/investigations/{investigation_id}/links/{edge_id}/notes/{note_id}": "204, no body",
    "DELETE /v1/admin/dashboards/{client_id}": "204, no body",
    "DELETE /v1/investigations/{investigation_id}/trends/{trend_id}": "204, no body",
    "DELETE /v1/investigations/{investigation_id}/packs/{pack_id}/items/{item_id}": "204, no body",
    "GET /v1/investigations/{investigation_id}/documents/{document_id}/file": "a file's bytes",
    "GET /v1/investigations/{investigation_id}/nodes/{node_id}/picture": "an image's bytes",
    "GET /v1/map/tiles/{provider_id}/{z}/{x}/{y}": "a map tile's bytes",
    "GET /v1/map/local-source/{provider_id}": "a map source file's bytes",
    "GET /v1/investigations/{investigation_id}/sites/{site_id}/image": "an image's bytes",
    "POST /v1/admin/geospatial/build-basemap": "a stream of build progress text",
}


def test_every_route_with_no_field_to_walk_is_named_and_given_a_reason() -> None:
    """Violation caught: a route is added that answers with something the walk cannot see into (a
    bare mapping, bytes, a stream, nothing) and is not named, so a withheld figure could go out in
    it unseen. A route that is neither given a response model (which the walk then covers) nor
    named here with its reason fails; so does a name here that no longer matches a route."""
    no_fields = {_label(r) for r in _api_routes() if not field_names_reachable(_wire_annotation(r))}

    assert no_fields == RAW_MAPPING_ROUTES | set(NON_JSON_ROUTES)
    assert not RAW_MAPPING_ROUTES & set(NON_JSON_ROUTES)
    assert all(reason.strip() for reason in NON_JSON_ROUTES.values())


def _withheld_names_in_source(handler: Callable[..., Any]) -> set[str]:
    """The withheld keys a handler's own source writes: a string constant, or a keyword argument
    (`dict(filtered_count=...)`). The handler itself, not what it calls: a figure built in a helper
    and returned by name is outside this scan, which is why the lists above are read by hand."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(handler)))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found |= {node.value} & WITHHELD_KEYS
        if isinstance(node, ast.keyword) and node.arg in WITHHELD_KEYS:
            found.add(node.arg)
    return found


@pytest.mark.parametrize(
    "route",
    [r for r in _api_routes() if _label(r) in RAW_MAPPING_ROUTES],
    ids=_label,
)
def test_a_raw_mapping_route_names_no_withheld_figure(route: APIRoute) -> None:
    """Violation caught (ADR-124 decision 1): a handler that returns a bare mapping writes
    `filtered_count` or `unreadable_count` into it."""
    assert _withheld_names_in_source(route.endpoint) == set(), _label(route)


def test_the_source_scan_finds_a_withheld_key_in_a_handler_that_writes_one() -> None:
    """Violation caught (rule 15, the scan shown able to fail): a scan that reads the source and
    finds nothing in any handler. Two handlers that put the figure in a mapping, as the keys of a
    literal and as a keyword, and one that does not."""

    async def literal() -> dict[str, int]:
        return {"filtered_count": 1}

    async def keyword() -> dict[str, int]:
        return dict(unreadable_count=2)

    async def clean() -> dict[str, int]:
        return {"seq": 3}

    assert _withheld_names_in_source(literal) == {"filtered_count"}
    assert _withheld_names_in_source(keyword) == {"unreadable_count"}
    assert _withheld_names_in_source(clean) == set()
