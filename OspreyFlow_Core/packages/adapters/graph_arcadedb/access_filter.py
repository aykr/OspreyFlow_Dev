"""Access control, injected into the traversal — never applied after
retrieval (`spec/00_ARCHITECTURE.md` §5).

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

**Axis 3 — `datasets` (ADR-099).** A case reads only elements of its own datasets. It rides in the
same fragment, so every read limits the node, the link and the link's far end alike. The step is
`filter(values("datasets").unfold().is(within(...)))`, not `has("datasets", within(...))`: the
property is a list, and on ArcadeDB 25.5.1 `has` compares the whole list with each value and
matches nothing. `None` (the Conduit's own background work) adds no step; an empty list sees
nothing.
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

    @staticmethod
    def gremlin_dataset_step(datasets: list[str] | None) -> str | None:
        """ADR-099's axis on its own, for `gremlin_structural_step` to carry."""
        if datasets is None:
            return None
        named = groovy_string_list_literal(sorted(set(datasets)))
        return f'filter(values("datasets").unfold().is(within({named})))'

    def gremlin_structural_step(
        self, *, include_superseded: bool = False, datasets: list[str] | None = None
    ) -> str:
        """The two exclusions `gremlin_has_step` bundles in that are not
        principal-dependent at all — reverted and (unless lifted)
        superseded (`01_DOMAIN_MODEL.md` §2.4) — factored out so a caller
        that must *not* also compile the two access axes
        (`ExpandBuilder.render_candidate_count_gremlin`, the unfiltered
        half of `Subgraph.filtered_count`'s comparison, §8.2) can still
        exclude the same not-really-there-any-more elements without
        reproducing the clearance/handling-code compilation below.

        `datasets` (ADR-099) is carried here, not with the two handling axes, because the candidate
        count must apply it too: what lies outside a case's datasets is not hidden from the case,
        it is not in its world, and counting it would say there is more."""
        steps = ['has("reverted",false)']
        if not include_superseded:
            steps.append('hasNot("superseded_by")')
        dataset_step = self.gremlin_dataset_step(datasets)
        if dataset_step is not None:
            steps.append(dataset_step)
        return ".".join(steps)

    def gremlin_has_step(self, principal: Principal, *, include_superseded: bool = False) -> str:
        """Both handling axes, plus two more that are not
        principal-dependent at all: a reverted element (`services/ingest`'s
        `revert_load`, `01_DOMAIN_MODEL.md` §2.4) is invisible to every
        read regardless of clearance, and a superseded node — the old
        revision a correction has replaced (`supersede_node`, same §2.4) —
        is invisible by default too, since "excluded from reads by
        default" only means something if ordinary reads actually exclude
        it. Riding in the same fragment is what makes every existing call
        site enforce both for free, with no change to `builders.py`.
        `include_superseded` is the one caller-controlled exception —
        `get_node`'s explicit-revision lookup — and it *only* lifts the
        supersession check: classification and `handling_code` still apply
        underneath it, so asking for history never surfaces a record the
        caller could not otherwise see. A record's `handling_code` is
        visible either because it isn't a restricted code at all, or
        because this principal both may receive that specific restricted
        code and belongs to the record's owning or originating unit."""
        structural_step = self.gremlin_structural_step(
            include_superseded=include_superseded, datasets=principal.datasets
        )
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
        steps = [structural_step, classification_step]
        steps.append(handling_code_step)
        return ".".join(steps)
