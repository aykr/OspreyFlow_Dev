"""Alert trends in SQL (`06_DECISIONS.md` ADR-134 decision 3): the one `WHERE` clause both analytics
adapters run over the alert facts, compiled before anything is aggregated — never a filter on a
result (`00_ARCHITECTURE.md` §2.2, rule 3).

An alert is counted for a reader only when all of these hold, each in the query:

- **its audience**, as the one queue reads it (`services/api/alerts.py` `queue_scope`): a
  typology alert is its case's; a hotlist or monitor alert is its owner's, and its owner's team's
  when shared;
- **the reader's datasets** (ADR-099, `reach_clause`): an alert of another dataset is not in the
  case's world, one naming none stays in reach;
- **its handlings are known**, so an alert kept before they were is counted for no one;
- **every handling it rests on** is one the reader may view — `AccessFilter`'s predicate, the same
  one events are read through, over the alert's handling rows. The check is written as "not among
  the alerts with a handling the reader may not view", a subquery that needs no correlation, so
  DuckDB and ClickHouse read the same text; `COALESCE(..., FALSE)` keeps a `NULL` from reading as
  "may view".

Both engines read `?` parameters, so the predicate is shared; only the period expression differs.
"""

from __future__ import annotations

from schemas.analytics import AlertTrendRequest
from schemas.domain import Principal

from .access_filter import AccessFilter, SqlPredicate

#: The fields a trend may split by or filter on, each one column of `alert_facts`.
ALERT_TREND_COLUMNS = {
    "rule": "rule",
    "typology": "typology",
    "severity": "severity",
    "outcome": "outcome",
}

FACT_COLUMNS = (
    "alert_id, investigation_scope, kind, rule, typology, severity, outcome, raised_at, owner_id, "
    "audience, team, dataset_id, known"
)
HANDLING_COLUMNS = "alert_id, handling_classification, handling_code, owning_unit, originator"


def alert_predicate(
    req: AlertTrendRequest, principal: Principal, access: AccessFilter
) -> SqlPredicate:
    """The reader's alerts in the request's window and filters: one `WHERE` over `alert_facts`."""
    clauses = ["raised_at >= ?"]
    params: list[object] = [req.window.valid_from]
    if req.window.valid_to is not None:
        clauses.append("raised_at <= ?")
        params.append(req.window.valid_to)
    clauses.append(
        "((audience = 'case' AND investigation_scope = ?) "
        "OR (audience <> 'case' AND owner_id = ?) "
        "OR (audience = 'team' AND team = ?))"
    )
    params += [req.investigation_scope, principal.id, principal.org_unit]
    if principal.datasets is not None:
        if principal.datasets:
            marks = ",".join("?" for _ in principal.datasets)
            clauses.append(f"(dataset_id IS NULL OR dataset_id IN ({marks}))")
            params += list(principal.datasets)
        else:
            clauses.append("dataset_id IS NULL")
    clauses.append("known = 1")
    viewable = access.predicate(principal)
    clauses.append(
        "alert_id NOT IN (SELECT alert_id FROM alert_fact_handlings "
        f"WHERE NOT COALESCE(({viewable.where}), FALSE))"
    )
    params += viewable.params
    for field, values in sorted(req.filters.items()):
        if not values:
            continue
        marks = ",".join("?" for _ in values)
        clauses.append(f"{ALERT_TREND_COLUMNS[field]} IN ({marks})")
        params += list(values)
    return SqlPredicate(" AND ".join(clauses), params)


def series_expression(req: AlertTrendRequest) -> str:
    return "NULL" if req.group_by is None else ALERT_TREND_COLUMNS[req.group_by]


__all__ = [
    "ALERT_TREND_COLUMNS",
    "FACT_COLUMNS",
    "HANDLING_COLUMNS",
    "alert_predicate",
    "series_expression",
]
