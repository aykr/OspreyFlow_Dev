"""`AnalyticsPort` — `spec/00_ARCHITECTURE.md` §2.2, `spec/01_DOMAIN_MODEL.md` §9.

Columnar aggregation over event-shaped data: temporal histograms, geospatial
binning, baseline statistics, cross-filter counts. This is SQL, not
traversal. There is no `raw_sql` escape hatch, deliberately — an arbitrary
SQL string cannot be access-filtered, the same reason the Conduit never
accepts free-form Gremlin (ADR-003). Every method takes a `Principal`; the
adapter injects the filter into the `WHERE` clause before the query runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from schemas.analytics import (
    ActivityRequest,
    ActivityResult,
    AlertFact,
    AlertTrendRequest,
    BaselineRequest,
    BaselineResult,
    CrossFilterRequest,
    EventListRequest,
    EventListResult,
    EventRecord,
    FirstSeenRequest,
    FirstSeenResult,
    FrequencyRequest,
    FrequencyResult,
    GeoBin,
    GeoBinRequest,
    GeocodedEvent,
    GeocodeRequest,
    GeometryRecord,
    Histogram,
    HistogramRequest,
    Sighting,
    SightingRequest,
    TrendRequest,
    TrendResult,
)
from schemas.domain import Principal


class TrendLimitExceeded(Exception):
    """A trend past its bound (ADR-113 decision 2, rule 2): refused, never cut. `would_be` counts
    only what the reader could see, so the refusal discloses nothing."""

    def __init__(self, cap_kind: str, cap: int, would_be: int) -> None:
        super().__init__(f"the trend would have {would_be} {cap_kind}; the bound is {cap}")
        self.cap_kind, self.cap, self.would_be = cap_kind, cap, would_be


#: What a field name may be, said whenever one is refused: the rule, never what was sent (spec 08's
#: A7). Every adapter refuses in these words, so the routes answer each the same way.
FIELD_NAME_RULE = (
    "A field to filter, group, sum or write by is named with letters, digits and underscores "
    "only; one in this request was not, so nothing was read or written."
)


class AnalyticsFieldRefused(ValueError):
    """A field name a request carries (a `value_filters` key, a dimension's or a histogram's
    `field`, a trend's `group_by` or `measure_field`, a geocode's `property`, an `amount_property`)
    that is not a plain identifier: refused before any SQL is built, since a field name is
    interpolated where values are parameterised. The words are `FIELD_NAME_RULE` and do not carry
    the name sent, which may be hostile. A `ValueError`, as the adapters' guard always raised."""

    def __init__(self) -> None:
        super().__init__(FIELD_NAME_RULE)


#: Past this, a total of declared amounts is refused (ADR-133 Amendment 10): a decimal of 38 digits,
#: 9 after the point, holds less than 10^29, and a total is checked short of it.
AMOUNT_TOTAL_LIMIT = 10**28


class AmountTotalOutOfRange(Exception):
    """A frequency's or an activity's total of a declared amount at or past `AMOUNT_TOTAL_LIMIT`
    (ADR-133 Amendment 10, rule 2): refused whole on every adapter, never wrapped or cut."""

    def __init__(self) -> None:
        super().__init__(
            "a total of the declared amount reaches 10^28, past what is counted exactly; nothing "
            "is answered"
        )


def refuse_an_amount_total_out_of_range(*totals: float | None) -> None:
    """Raises `AmountTotalOutOfRange` if any total reaches the limit (in either direction)."""
    if any(t is not None and abs(t) >= AMOUNT_TOTAL_LIMIT for t in totals):
        raise AmountTotalOutOfRange


class AnalyticsPort(Protocol):
    async def histogram(self, req: HistogramRequest, principal: Principal) -> Histogram: ...
    async def geo_bins(self, req: GeoBinRequest, principal: Principal) -> list[GeoBin]: ...

    async def list_sightings(self, req: SightingRequest, principal: Principal) -> list[Sighting]:
        """Phase 8 Stage 4f's own addition, found missing while building B18's snail trail —
        a disclosed gap. Ordered by `occurred_at` ascending; a row with
        no `lat`/`lon` is excluded, the same `lat IS NOT NULL AND lon IS NOT NULL` filter
        `geo_bins` already applies."""
        ...

    async def geocode_events(
        self, req: GeocodeRequest, principal: Principal
    ) -> list[GeocodedEvent]:
        """**A1's "incidents geocode into cells" — owner rulings R9 (c) and R10, round 13cf.**
        The one containment method: which of `req.cells`' polygons covers each admitted event's
        point, recorded on the event as `properties[req.property]` and returned.
        `GeocodeRequest`'s docstring has the full contract: covering rather than strict, ties to
        the smallest ref, stale values cleared, and access applied to events and polygons alike.
        Ordered by `event_id`."""
        ...

    async def cross_filter(
        self, req: CrossFilterRequest, principal: Principal
    ) -> dict[str, Histogram]: ...

    async def baseline(self, req: BaselineRequest, principal: Principal) -> BaselineResult: ...

    async def list_events(self, req: EventListRequest, principal: Principal) -> EventListResult:
        """A page of the events the filter describes, newest first, with the total (ADR-089).
        Access control is in the query: a hidden event is neither listed nor counted."""
        ...

    async def trend(self, req: TrendRequest, principal: Principal) -> TrendResult:
        """Events per week or month, optionally split into series by a field, as a count or the
        sum of a numeric property (ADR-113). Access control is in the query: a hidden event moves no
        point, no total, no series and no classification. Past `max_periods` or `max_series` it
        raises `TrendLimitExceeded` — never a partial trend."""
        ...

    async def alert_trend(self, req: AlertTrendRequest, principal: Principal) -> TrendResult:
        """Alerts raised per week or month, optionally split by rule, typology, severity or outcome
        (ADR-134 decision 3), over the alert facts `load_alert_facts` keeps. Access control is in
        the query: an alert is counted only when the reader is in its audience (its case for a
        typology alert; its owner, or its owner's team when shared, for the others), it is within
        the reader's datasets, and the reader may view every handling it rests on — so an alert on
        something they may not see moves no point, no total, no series and no classification. An
        alert whose handlings are not known is counted for no one. Past `max_periods` or
        `max_series` it raises `TrendLimitExceeded`, counted from what the reader sees."""
        ...

    async def first_seen(self, req: FirstSeenRequest, principal: Principal) -> FirstSeenResult:
        """The earliest event in `req.filter` per node (either end) and per link (ADR-087). Access
        control is in the query: an event the principal may not see cannot pull a first appearance
        forward, so the answer equals the one over a corpus without that event."""
        ...

    async def event_frequency(
        self, req: FrequencyRequest, principal: Principal
    ) -> FrequencyResult:
        """A rule's frequency and amount conditions (ADR-133 decision 1, stage (b)): for each of
        `req.filter.node_ids`, at either end of an event, the most events — and the largest total of
        `req.amount_property` — in any span of `req.span_days` days (ends included) ending at one
        of its events within the filter, and its earliest event up to the window's end. An event
        to itself counts once. Access control is in the query (rule 3): an event the principal may
        not see adds nothing to a count or a total and is never a first, so the answer equals the
        one over a store without it, and a node reached only through hidden events is absent."""
        ...

    async def account_activity(
        self, req: ActivityRequest, principal: Principal
    ) -> ActivityResult:
        """An account against its own past (ADR-133 decision 2, stage (c)): for each of
        `req.filter.node_ids`, at either end of an event, its events and the total of
        `req.amount_property` within `req.filter.window` (ends included) and in the
        `req.baseline_days` days before the window's start, its first event in the window and its
        last before it. An event to itself counts once. Access control is in the query (rule 3): an
        event the principal may not see is not counted, totalled, first or last, so the answer
        equals the one over a store without it, and a node reached only through hidden events is
        absent."""
        ...

    # --- writes --------------------------------------------------------------
    #
    # Not principal-scoped writes: an ingest/gazetteer load is a backend
    # operation attributed by the caller's own audit trail (the connector or
    # recipe run), the same shape as `GraphPort.revert_elements` — never a
    # principal-scoped read. Reads take a `Principal` and are filtered by
    # `handling` exactly like every `EventFilter`-based method above.
    #
    # `load_events` mirrors `load_geometries` exactly, and exists for the
    # same reason: before this, nothing implementing `AnalyticsPort` had a
    # real write path for `EventRecord`s at all — every event that ever
    # reached a conformance test went through `analytics_duckdb/testing.py`'s
    # own bypass SQL, never the adapter or the port. `run_recipe`
    # (`services/ingest/engine.py`) already returns the `EventRecord`s a
    # load produced; this is what a caller now has to actually persist them
    # through, the same way `load_geometries` is.

    async def load_events(self, records: Sequence[EventRecord]) -> None: ...

    async def retract_load(self, load_id: str) -> int:
        """Removes every event a load wrote (ADR-127 decision 6) and returns how many. Removes
        nothing else: another load's events, and events with no `load_id`, stay. Idempotent: a
        second call, or one for a load that wrote none, removes nothing, returns 0 and raises
        nothing. Like `load_events` it is a backend write, not principal-scoped, and counts every
        event of the load whatever its marking; afterwards no read, for any principal, returns or
        counts a retracted event."""
        ...

    async def withdraw_events_by_id(self, event_ids: Sequence[str], load_id: str) -> int:
        """Sets aside exactly these events, by `event_id`, marked with `load_id`, and returns how
        many (ADR-110 Amendments 8 point 1 and 15: a full snapshot's refresh withdrawing a dropped
        row's own events, which the row's record names). Never by link: another event on the same
        link, of any load or case, stays. Afterwards no read, for any principal, returns or counts
        one of them. An id no event holds is not counted; an event already set aside stays with the
        load that set it aside. Idempotent; no ids set aside nothing. A backend write, not
        principal-scoped, like `retract_load`. `retract_load` of the load that wrote an event
        removes it wherever it is, set aside included."""
        ...

    async def restore_withdrawn_events(self, load_id: str) -> int:
        """Puts back exactly the events `load_id` set aside, as they were, and returns how many
        (the revert of the refresh). Idempotent: a second call, or one for a load that set none
        aside, puts back nothing and returns 0."""
        ...

    async def events_of_load_among(self, load_id: str, event_ids: Sequence[str]) -> set[str]:
        """Which of `event_ids` are events `load_id` wrote, **whatever the marking and whatever the
        caller may read**: no principal, no access step. For the revert alone (ADR-127 Amendment 8),
        to close the alerts that cite an event it is about to retract, asking about the ids the
        alerts name and never listing a load's events. A route must never call it
        (`tests/test_unfiltered_node_lookup_confined.py`). An id no event holds, and an event of
        another load or of none, are absent from the answer; no ids give the empty set."""
        ...

    async def load_alert_facts(self, facts: Sequence[AlertFact]) -> None:
        """Keeps these alerts for alert trends, each replacing whatever was kept for the same
        `alert_id` (its fact and its handlings), so an alert written twice is counted once. A
        backend write like `load_events`, not principal-scoped."""
        ...

    async def load_geometries(self, records: Sequence[GeometryRecord]) -> None: ...

    async def retract_geometries(self, geometry_refs: Sequence[str], *, version: int) -> int:
        """Removes the rows of these refs at this partition version (ADR-127 decision 6: a revert
        takes back the points its load inserted, which its record lists) and returns how many.
        Removes nothing else: another ref, and the same ref at another version, stay. Idempotent:
        a ref already gone, or never written, removes nothing and raises nothing; no refs remove
        nothing. A backend write, not principal-scoped, like `load_geometries`: it counts and
        removes a row whatever its marking; afterwards no read, for any principal, returns it."""
        ...

    async def get_geometry(
        self, geometry_ref: str, principal: Principal, *, version: int | None = None
    ) -> GeometryRecord | None: ...

    async def get_geometries(
        self, geometry_refs: Sequence[str], principal: Principal, *, version: int | None = None
    ) -> list[GeometryRecord]: ...

    async def list_boundaries(
        self, principal: Principal, *, version: int | None = None
    ) -> list[GeometryRecord]:
        """The "select an existing boundary" read path,
        a disclosed gap: every stored
        `GeometryKind.POLYGON` row at the resolved partition version — the
        server-backed counterpart to the transient, browser-only drawn-
        boundary filter (`apps/workspace/src/map/BoundaryFilterTool.tsx`).
        Access-filtered exactly like `get_geometry`/`get_geometries`: a
        boundary the given `principal` cannot view must not appear, count,
        or otherwise be detectable."""
        ...
