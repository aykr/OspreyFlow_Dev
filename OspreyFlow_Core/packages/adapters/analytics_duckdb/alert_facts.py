"""Alert trends in SQL (`06_DECISIONS.md` ADR-134 decision 3): the one `WHERE` clause both analytics
adapters run over the alert facts, compiled before anything is aggregated — never a filter on a
result (`00_ARCHITECTURE.md` §2.2, rule 3).

An alert is counted for a reader only when all of these hold, each in the query:

- **its audience**, as the one queue reads it (`services/api/alerts.py` `queue_scope`): a
  typology alert is its case's; a hotlist or monitor alert is its owner's, and its owner's team's
  when shared; a rule's alert routed to a named team (`routed`, ADR-146 decision 8) its case's
  team members' alone (the home case's Authors read it in the queue, not in trends);
- **the reader's datasets** (ADR-099, `reach_clause`): an alert of another dataset is not in the
  case's world, one naming none stays in reach;
- **its handlings are known**, so an alert kept before they were is counted for no one;
- **every handling it rests on** is one the reader may view — `AccessFilter`'s predicate, the same
  one events are read through, over the alert's handling rows. The check is written as "not among
  the alerts with a handling the reader may not view", a subquery that needs no correlation, so
  DuckDB and ClickHouse read the same text; `COALESCE(..., FALSE)` keeps a `NULL` from reading as
  "may view";
- **no citation outside its row's set is one the reader may view whole** (ADR-146 Amendment 7, the
  orchestrator's review, item 6): an alert with citations is kept as one row per set of them
  (`fact_id`), each citation outside the set a group (`grp` > 0) of handling rows, and a row is not
  counted for a reader who may view every handling of one of its groups. So exactly one row of
  such an alert is counted for a reader (the set they may read), or none.

Both engines read `?` parameters, so the predicate is shared; only the period expression differs.
"""

from __future__ import annotations

from collections.abc import Sequence

from schemas.analytics import AlertFact, AlertTrendRequest
from schemas.domain import Principal
from schemas.rights import teams_of

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
    "audience, team, dataset_id, known, fact_id"
)
HANDLING_COLUMNS = (
    "alert_id, handling_classification, handling_code, owning_unit, originator, fact_id, grp"
)


def alert_predicate(
    req: AlertTrendRequest, principal: Principal, access: AccessFilter
) -> SqlPredicate:
    """The reader's alerts in the request's window and filters: one `WHERE` over `alert_facts`."""
    clauses = ["raised_at >= ?"]
    params: list[object] = [req.window.valid_from]
    if req.window.valid_to is not None:
        clauses.append("raised_at <= ?")
        params.append(req.window.valid_to)
    # ADR-146 decision 8: a rule's alert routed to a named team is its case's, for the team's
    # members alone (`team` holds the team's role id; the reader's teams are the custom roles their
    # token carries now), never its deployer's as an owner.
    teams = teams_of(principal.roles)
    routed = (
        f"OR (audience = 'routed' AND investigation_scope = ? "
        f"AND team IN ({','.join('?' for _ in teams)}))"
        if teams
        else ""
    )
    clauses.append(
        "((audience = 'case' AND investigation_scope = ?) "
        "OR (audience IN ('team', 'owner') AND owner_id = ?) "
        f"OR (audience = 'team' AND team = ?) {routed})"
    )
    params += [req.investigation_scope, principal.id, principal.org_unit]
    if teams:
        params += [req.investigation_scope, *teams]
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
        "fact_id NOT IN (SELECT fact_id FROM alert_fact_handlings "
        f"WHERE grp = 0 AND NOT COALESCE(({viewable.where}), FALSE))"
    )
    params += viewable.params
    clauses.append(
        "fact_id NOT IN (SELECT fact_id FROM alert_fact_handlings WHERE grp > 0 "
        "GROUP BY fact_id, grp "
        f"HAVING MIN(CASE WHEN COALESCE(({viewable.where}), FALSE) THEN 1 ELSE 0 END) = 1)"
    )
    params += viewable.params
    for field, values in sorted(req.filters.items()):
        if not values:
            continue
        marks = ",".join("?" for _ in values)
        clauses.append(f"{ALERT_TREND_COLUMNS[field]} IN ({marks})")
        params += list(values)
    return SqlPredicate(" AND ".join(clauses), params)


#: The handling rows of the counted rows a trend's marking is read from: their own, never a hidden
#: citation's (`grp` > 0), whose marking would name a list the reader may not see.
def counted_handlings(where: str) -> str:
    return f"fact_id IN (SELECT fact_id FROM alert_facts WHERE {where}) AND grp = 0"


def fact_rows(facts: Sequence[AlertFact]) -> tuple[list[list[object]], list[list[object]]]:
    """Each fact's `alert_facts` row (`FACT_COLUMNS`, in order) and its handling rows
    (`HANDLING_COLUMNS`): its own handlings in group 0, each of `hidden_from` in a group of its
    own."""
    facts_out: list[list[object]] = []
    handlings_out: list[list[object]] = []
    for f in facts:
        fact_id = f.fact_id or f.alert_id
        facts_out.append([f.alert_id, f.investigation_scope, f.kind, f.rule, f.typology, f.severity,
                          f.outcome, f.raised_at, f.owner_id, f.audience, f.team, f.dataset_id,
                          0 if f.handlings is None else 1, fact_id])  # fmt: skip
        for grp, group in enumerate([f.handlings or [], *f.hidden_from]):
            handlings_out += [[f.alert_id, h.classification, h.handling_code, h.owning_unit,
                               h.originator, fact_id, grp] for h in group]  # fmt: skip
    return facts_out, handlings_out


def series_expression(req: AlertTrendRequest) -> str:
    return "NULL" if req.group_by is None else ALERT_TREND_COLUMNS[req.group_by]


__all__ = [
    "ALERT_TREND_COLUMNS",
    "FACT_COLUMNS",
    "HANDLING_COLUMNS",
    "alert_predicate",
    "counted_handlings",
    "fact_rows",
    "series_expression",
]
