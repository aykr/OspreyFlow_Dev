"""Access control, injected into the traversal — never applied after
retrieval (`CLAUDE.md` rule 3, `docs/00_ARCHITECTURE.md` §5).

Two axes gate a read (`01_DOMAIN_MODEL.md` §2.2 — the field-by-field
table). `action_code` and `sanitisation_code` never gate a read at all: the
first constrains what may be *done*, the second is the export gate's own
reason for existing.

**Axis 1 — `classification`.** A dominance rule over the scheme's own
ordering: a record is visible iff its `handling.classification` is no more
restrictive than the principal's clearance.

**Axis 2 — `handling_code`, checked only when its scheme entry is
`dissemination: restricted`.** A `permitted`/`conditional` code never gates
a read. A `restricted` code does, and only within its permitted set: the
principal must both carry that code in `receivable_handling_codes` *and*
belong to the record's `owning_unit` or `originator`. A classification-only
filter passes every existence-leak test written against classification
alone and still discloses a recipient-restricted record to the wrong unit
— which is why both axes are compiled into one predicate below and embedded
directly in the traversal, never as a second, separate check.
"""

from __future__ import annotations

from ontology.handling import HandlingScheme
from schemas.domain import Principal

from .gremlin_literals import groovy_string_list_literal, groovy_string_literal


class AccessFilter:
    def __init__(self, scheme: HandlingScheme) -> None:
        self._scheme = scheme
        self._rank = {classification: i for i, classification in enumerate(scheme.classification)}
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
            # An unrecognised clearance is treated as the most restrictive
            # possible principal: default-deny, not default-allow
            # (01_DOMAIN_MODEL.md §2.2 — stated, not assumed).
            return []
        return [c for c, rank in self._rank.items() if rank <= principal_rank]

    def _receivable_restricted_codes(self, principal: Principal) -> list[str]:
        return [c for c in principal.receivable_handling_codes if c in self._restricted_codes]

    def gremlin_has_step(self, principal: Principal) -> str:
        """Both axes, compiled into one fragment to chain directly onto
        whatever vertex/edge step it follows. A record's `handling_code` is
        visible either because it isn't a restricted code at all, or
        because this principal both may receive that specific restricted
        code and belongs to the record's owning or originating unit."""
        classification_step = (
            f'has("handling_classification",'
            f"within({groovy_string_list_literal(self.allowed_classifications(principal))}))"
        )

        unit = groovy_string_literal(principal.org_unit)
        non_restricted = groovy_string_list_literal(self._non_restricted_codes)
        receivable_restricted = groovy_string_list_literal(
            self._receivable_restricted_codes(principal)
        )
        handling_code_step = (
            "filter(or("
            f'has("handling_code",within({non_restricted})),'
            "and("
            f'has("handling_code",within({receivable_restricted})),'
            f'or(has("owning_unit",{unit}),has("originator",{unit}))'
            ")"
            "))"
        )
        return f"{classification_step}.{handling_code_step}"
