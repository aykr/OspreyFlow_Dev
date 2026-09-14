"""Access control compiled into a SQL predicate — injected into the `WHERE`
clause before aggregation, never applied to a result after the fact
(`00_ARCHITECTURE.md` §2.2, `CLAUDE.md` rule 3).

Mirrors `adapters/graph_arcadedb/access_filter.py`'s two axes exactly: both
adapters enforce the same `Handling` model against the same
`HandlingScheme` (`01_DOMAIN_MODEL.md` §2.2), so the same principal must see
the same records whichever store answers the query.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ontology.handling import HandlingScheme
from schemas.domain import Principal


@dataclass(frozen=True)
class SqlPredicate:
    where: str
    params: list[object] = field(default_factory=list)


def _in_clause(column: str, values: list[str]) -> tuple[str, list[object]]:
    if not values:
        # An empty allowed/receivable set must exclude every row, not match
        # every row — the same default-deny an unrecognised clearance gets
        # in the graph adapter.
        return "FALSE", []
    placeholders = ",".join("?" for _ in values)
    return f"{column} IN ({placeholders})", list(values)


class AccessFilter:
    def __init__(self, scheme: HandlingScheme) -> None:
        self._scheme = scheme
        self._rank = {c: i for i, c in enumerate(scheme.classification)}
        self._restricted_codes = {
            code
            for code, defn in scheme.handling_codes.items()
            if defn.dissemination == "restricted"
        }
        self._non_restricted_codes = [
            code for code in scheme.handling_codes if code not in self._restricted_codes
        ]

    def allowed_classifications(self, principal: Principal) -> list[str]:
        principal_rank = self._rank.get(principal.clearance)
        if principal_rank is None:
            return []
        return [c for c, rank in self._rank.items() if rank <= principal_rank]

    def _receivable_restricted_codes(self, principal: Principal) -> list[str]:
        return [c for c in principal.receivable_handling_codes if c in self._restricted_codes]

    def predicate(self, principal: Principal) -> SqlPredicate:
        classification_sql, classification_params = _in_clause(
            "handling_classification", self.allowed_classifications(principal)
        )
        non_restricted_sql, non_restricted_params = _in_clause(
            "handling_code", self._non_restricted_codes
        )
        receivable_sql, receivable_params = _in_clause(
            "handling_code", self._receivable_restricted_codes(principal)
        )
        where = (
            f"({classification_sql})"
            f" AND (({non_restricted_sql}) OR (({receivable_sql}) AND"
            " (owning_unit = ? OR originator = ?)))"
        )
        params = [
            *classification_params,
            *non_restricted_params,
            *receivable_params,
            principal.org_unit,
            principal.org_unit,
        ]
        return SqlPredicate(where, params)
