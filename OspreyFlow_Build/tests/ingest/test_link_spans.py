"""ADR-127 decision 11: a link can be a span.

A recipe's link binds `temporal.at` (its start) and, optionally, `temporal.valid_to` (its end) from
two columns. An empty end cell means the span is still open, stored as the model stores open: an
`Interval` whose `valid_to` is `None`. A link bound to one instant keeps `valid_from = valid_to`.
Both cells go through the same canonicalisation as every other time (the connector's date order, the
zone), and a link's analytics event is at its start, span or instant, closed or open. What a mistake
would do, and the case that catches it:

- a custody row with an empty end read as an instant, or rejected as missing
  (`test_a_custody_row_with_an_empty_end_loads_an_open_span_with_its_event_at_the_start`);
- a closed span losing its end, or an event at its end
  (`test_a_closed_span_loads_both_ends_and_its_event_is_at_the_start`);
- a reversed span loaded, or rejected with the values in the reason, which is shown to the loader
  (`test_a_reversed_span_is_rejected_naming_the_columns_and_never_the_values`);
- the instant link changing (`test_an_instant_link_is_unchanged`);
- the end read with another date order than the start
  (`test_the_end_is_read_with_the_connectors_date_order_and_the_zone`);
- the dry run drawing a different interval from the load (`test_verify_draws_the_span_the_load_writes`);
- a span's edge asked for with no end in the staged Parquet (the load reads its rows back from it:
  every case here runs through `load_with_rules`, which stages and reads back).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.api.studio_publish import load_with_rules
from services.ingest.engine import dry_run_recipe

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.ingest import LoadReport, Recipe
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_load_record_created_and_merged import _recipe as _base_recipe

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")


def _recipe(*, span: bool = True, date_order: str | None = None) -> Recipe:
    document = _base_recipe().model_dump(by_alias=True)
    temporal: dict[str, Any] = {"at": {"field": "paid_at", "transform": "datetime(tz=UTC)"}}
    if span:
        temporal["valid_to"] = {"field": "ended_at", "transform": "datetime(tz=UTC)"}
    document["row_template"]["edges"][0]["temporal"] = temporal
    if date_order:
        document["connector"] = {**document["connector"], "date_order": date_order}
    return Recipe.model_validate(document)


def _row(paid_at: str, ended_at: str, payer: str = "SYN-1", payee: str = "SYN-2") -> dict[str, str]:
    return {"payer": payer, "payee": payee, "paid_at": paid_at, "ended_at": ended_at, "memo": ""}


async def _load(
    rows: list[dict[str, str]], recipe: Recipe | None = None, graph: MergingGraph | None = None
) -> tuple[LoadReport, list[Any], MergingGraph]:
    graph = graph or MergingGraph(ONTOLOGY)
    report, events, _held = await load_with_rules(
        recipe or _recipe(),
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id="load-1",
        investigation_scope="case-1",
        source="custody.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
    )
    return report, events, graph


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


async def test_a_custody_row_with_an_empty_end_loads_an_open_span_with_its_event_at_the_start() -> None:
    report, events, graph = await _load([_row("2026-03-01T09:00:00+00:00", "")])
    assert report.rejections == [], report.rejections
    (edge,) = graph.committed_edges
    assert edge.interval is not None
    assert edge.interval.valid_from == _at("2026-03-01T09:00:00+00:00")
    assert edge.interval.valid_to is None, "an open span has no end, not the start repeated"
    (event,) = events
    assert event.occurred_at == _at("2026-03-01T09:00:00+00:00")


async def test_a_blank_end_cell_of_spaces_is_open_too() -> None:
    report, _events, graph = await _load([_row("2026-03-01T09:00:00+00:00", "   ")])
    assert report.rejections == []
    assert graph.committed_edges[0].interval.valid_to is None  # type: ignore[union-attr]


async def test_a_closed_span_loads_both_ends_and_its_event_is_at_the_start() -> None:
    report, events, graph = await _load(
        [_row("2026-03-01T09:00:00+00:00", "2026-03-09T17:30:00+00:00")]
    )
    assert report.rejections == []
    (edge,) = graph.committed_edges
    assert edge.interval is not None
    assert edge.interval.valid_from == _at("2026-03-01T09:00:00+00:00")
    assert edge.interval.valid_to == _at("2026-03-09T17:30:00+00:00")
    (event,) = events
    assert event.occurred_at == _at("2026-03-01T09:00:00+00:00")


async def test_a_span_that_starts_and_ends_together_is_an_instant_with_an_end() -> None:
    _report, _events, graph = await _load(
        [_row("2026-03-01T09:00:00+00:00", "2026-03-01T09:00:00+00:00")]
    )
    interval = graph.committed_edges[0].interval
    assert interval is not None and interval.valid_to == interval.valid_from


async def test_a_reversed_span_is_rejected_naming_the_columns_and_never_the_values() -> None:
    report, events, graph = await _load(
        [
            _row("2026-03-09T09:00:00+00:00", "2026-03-01T09:00:00+00:00", "SYN-1", "SYN-2"),
            _row("2026-03-01T09:00:00+00:00", "", "SYN-3", "SYN-4"),
        ]
    )
    (rejection,) = report.rejections
    assert rejection.row_index == 0
    assert "paid_at" in rejection.reason and "ended_at" in rejection.reason
    # The reason, which a loader is shown for every row, names columns and carries no value (the
    # sample is the loader's own row, as for every rejection).
    assert "2026-03" not in rejection.reason and "SYN-1" not in rejection.reason, rejection.reason
    # The good row still loads, and the reversed row wrote no link and no event.
    assert len(graph.committed_edges) == 1 and len(events) == 1


async def test_an_instant_link_is_unchanged() -> None:
    report, events, graph = await _load(
        [_row("2026-03-01T09:00:00+00:00", "")], recipe=_recipe(span=False)
    )
    assert report.rejections == []
    (edge,) = graph.committed_edges
    assert edge.interval is not None
    assert edge.interval.valid_from == edge.interval.valid_to == _at("2026-03-01T09:00:00+00:00")
    assert events[0].occurred_at == _at("2026-03-01T09:00:00+00:00")


async def test_the_end_is_read_with_the_connectors_date_order_and_the_zone() -> None:
    day_first = await _load([_row("02/03/2026 10:00", "04/03/2026 10:00")], _recipe(date_order="dmy"))
    month_first = await _load([_row("02/03/2026 10:00", "04/03/2026 10:00")], _recipe(date_order="mdy"))
    dmy = day_first[2].committed_edges[0].interval
    mdy = month_first[2].committed_edges[0].interval
    assert dmy is not None and mdy is not None
    assert (dmy.valid_from.month, dmy.valid_from.day) == (3, 2)
    assert (dmy.valid_to.month, dmy.valid_to.day) == (3, 4)  # type: ignore[union-attr]
    assert (mdy.valid_from.month, mdy.valid_from.day) == (2, 3)
    assert (mdy.valid_to.month, mdy.valid_to.day) == (4, 3)  # type: ignore[union-attr]
    # An offset on the end is brought to UTC as the start's is.
    zoned = await _load([_row("2026-03-01T09:00:00+00:00", "2026-03-02T09:00:00+02:00")])
    end = zoned[2].committed_edges[0].interval.valid_to  # type: ignore[union-attr]
    assert end == _at("2026-03-02T07:00:00+00:00")


async def test_an_end_that_does_not_read_as_a_time_is_rejected_naming_the_column() -> None:
    report, _events, graph = await _load([_row("2026-03-01T09:00:00+00:00", "not a time")])
    (rejection,) = report.rejections
    assert "ended_at" in rejection.reason
    assert graph.committed_edges == []


async def test_verify_draws_the_span_the_load_writes() -> None:
    rows = [
        _row("2026-03-01T09:00:00+00:00", ""),
        _row("2026-03-01T09:00:00+00:00", "2026-03-09T09:00:00+00:00", "SYN-3", "SYN-4"),
    ]
    result = await dry_run_recipe(
        _recipe(), rows, graph=MergingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ontology=ONTOLOGY, principal=LOADER, source="custody.csv", scheme=SCHEME,
    )  # fmt: skip
    intervals = sorted(
        ((e.interval.valid_from, e.interval.valid_to) for e in result.edges if e.interval),
        key=lambda pair: pair[1] is not None,
    )
    assert intervals == [
        (_at("2026-03-01T09:00:00+00:00"), None),
        (_at("2026-03-01T09:00:00+00:00"), _at("2026-03-09T09:00:00+00:00")),
    ]


async def test_verify_merges_two_rows_of_one_pair_into_the_union_as_the_load_does() -> None:
    """Two custody rows of one pair (one closed, one open) are one link in one audience: the real
    load merges them (earliest start, open if either is open), and Verify must show that same
    interval, not the first row's."""
    rows = [
        _row("2026-03-05T09:00:00+00:00", "2026-03-09T09:00:00+00:00"),
        _row("2026-03-01T09:00:00+00:00", ""),
    ]
    result = await dry_run_recipe(
        _recipe(), rows, graph=MergingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ontology=ONTOLOGY, principal=LOADER, source="custody.csv", scheme=SCHEME,
    )  # fmt: skip
    (edge,) = [e for e in result.edges if e.interval]
    assert edge.occurrences == 2
    assert edge.interval is not None
    assert edge.interval.valid_from == _at("2026-03-01T09:00:00+00:00")
    assert edge.interval.valid_to is None, "an open row makes the pair open, as the load does"
    # And the closed pair stays closed, from the earliest start to the latest end.
    closed = await dry_run_recipe(
        _recipe(),
        [
            _row("2026-03-05T09:00:00+00:00", "2026-03-09T09:00:00+00:00"),
            _row("2026-03-01T09:00:00+00:00", "2026-03-02T09:00:00+00:00"),
        ],
        graph=MergingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ontology=ONTOLOGY, principal=LOADER, source="custody.csv", scheme=SCHEME,
    )  # fmt: skip
    (merged,) = [e for e in closed.edges if e.interval]
    assert merged.interval is not None
    assert merged.interval.valid_from == _at("2026-03-01T09:00:00+00:00")
    assert merged.interval.valid_to == _at("2026-03-09T09:00:00+00:00")
