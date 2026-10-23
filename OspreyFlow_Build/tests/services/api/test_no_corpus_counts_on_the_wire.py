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

Pure: imports the app and builds models, opens no connection. Needs `ARCADEDB_HTTP_PORT` and
`POSTGRES_PORT` pointed at unreachable ports only because importing the app reads settings.
"""

from __future__ import annotations

import json
import typing

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from pydantic import BaseModel
from services.api.app import app
from services.api.working_set.models import (
    DeltaAdd,
    DeltaNotice,
    DeltaRemove,
    DeltaReplaceEdge,
    DeltaReproject,
    DeltaSnapshot,
    DeltaUpdate,
    WorkingSetDelta,
)

from schemas.domain import Edge, WeightComponents

from .corpus_counts import (
    FORBIDDEN_KEYS,
    build,
    contains_model,
    edge_with_components,
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
    union = typing.get_args(WorkingSetDelta)[0]
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
    assert holding == {DeltaAdd, DeltaReplaceEdge, DeltaSnapshot}
    assert set(_delta_models()) == {
        DeltaAdd,
        DeltaUpdate,
        DeltaRemove,
        DeltaReplaceEdge,
        DeltaReproject,
        DeltaNotice,
        DeltaSnapshot,
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
