"""Handling scheme loader and evaluator — `spec/01_DOMAIN_MODEL.md` §2.2.

The enforcement logic reads the booleans a scheme declares (`dissemination`,
`direct_action`, `consult_originator`), never the code letters, so swapping
`uk-le.yaml` for `us-criminal-intelligence.yaml` — or enabling both — is a
configuration change with nothing above this module to touch.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError

from schemas.domain import Handling, Principal

from .errors import HandlingSchemeError

_SCHEME_DIR = Path(__file__).resolve().parent / "handling"

Dissemination = Literal["permitted", "conditional", "restricted"]


class HandlingCode(BaseModel):
    label: str
    dissemination: Dissemination


class ActionCode(BaseModel):
    label: str
    direct_action: bool
    originator_permission: bool = False


class SanitisationCode(BaseModel):
    label: str
    consult_originator: bool


class HandlingScheme(BaseModel):
    name: str
    classification: list[str]
    handling_codes: dict[str, HandlingCode]
    action_codes: dict[str, ActionCode]
    sanitisation_codes: dict[str, SanitisationCode]

    def clears(self, principal_clearance: str, classification: str) -> bool:
        """The classification dominance rule (`01_DOMAIN_MODEL.md` §2.2),
        for a single check rather than `AccessFilter`'s per-query
        `within(...)` list — the source profiler's shape-masking decision
        (`09_INGEST_STUDIO.md` §3) is the caller, since it has no
        traversal to inject a predicate into.

        An unrecognised *principal* clearance clears nothing — the same
        default-deny `AccessFilter.allowed_classifications` applies,
        since a malformed or stale clearance is a security posture
        question, not a configuration bug. An unrecognised
        *classification* is different in kind: it means the marking being
        checked is not in this scheme at all, the same scheme mismatch
        `evaluate_handling` treats as a hard error rather than silently
        denying or allowing."""
        if classification not in self.classification:
            raise HandlingSchemeError(
                f"classification {classification!r} is not defined in scheme {self.name!r}"
            )
        try:
            principal_rank = self.classification.index(principal_clearance)
        except ValueError:
            return False
        return self.classification.index(classification) <= principal_rank


class HandlingDecision(BaseModel):
    """What the export gate and every dissemination decision branch on —
    never the raw code letters."""

    dissemination: Dissemination
    direct_action_permitted: bool
    originator_permission_required: bool
    consult_originator: bool


def load_handling_scheme(path: str | Path) -> HandlingScheme:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise HandlingSchemeError(f"{path}: handling scheme must be a YAML mapping")
    try:
        return HandlingScheme.model_validate({"name": path.stem, **raw})
    except ValidationError as exc:
        raise HandlingSchemeError(f"{path}: {exc}") from exc


def load_uk_le_scheme() -> HandlingScheme:
    return load_handling_scheme(_SCHEME_DIR / "uk-le.yaml")


def load_us_criminal_intelligence_scheme() -> HandlingScheme:
    return load_handling_scheme(_SCHEME_DIR / "us-criminal-intelligence.yaml")


_DISSEMINATION_RANK: dict[str, int] = {"permitted": 0, "conditional": 1, "restricted": 2}


def _known(
    codes: Mapping[str, object], code: str | None, kind: str, scheme: HandlingScheme
) -> None:
    if code is not None and code not in codes:
        raise HandlingSchemeError(f"{kind} {code!r} is not defined in scheme {scheme.name!r}")


def is_restricted(code: str, scheme: HandlingScheme) -> bool:
    """Whether `code` is a restricted handling code in `scheme`: the one place that decides it, for
    the access step (`graph_arcadedb/access_filter.py`) and for what a link merges into
    (`audience_of`). A code the scheme does not define is not restricted."""
    defined = scheme.handling_codes.get(code)
    return defined is not None and defined.dissemination == "restricted"


def audience_of(
    handling: Handling, datasets: Iterable[str], scheme: HandlingScheme
) -> tuple[str, str, tuple[str, ...], str | None, str | None]:
    """The key two link writes share exactly when the same principals see both (ADR-102
    Amendment 3): every part the access step reads. The classification, the handling code, the set
    of datasets (ADR-099) and, only where the code is restricted, the originator and the owning
    unit, which decide visibility only then (`access_filter.py`). The action and sanitisation codes
    decide no visibility and are not in it. A write merges into an existing link only with an equal
    key."""
    return audience_parts(
        handling.classification,
        handling.handling_code,
        datasets,
        handling.originator,
        handling.owning_unit,
        scheme,
    )


def audience_parts(
    classification: str,
    handling_code: str,
    datasets: Iterable[str],
    originator: str,
    owning_unit: str,
    scheme: HandlingScheme,
) -> tuple[str, str, tuple[str, ...], str | None, str | None]:
    """`audience_of` from the parts themselves, for a stored link read back as flat properties."""
    restricted = is_restricted(handling_code, scheme)
    return (
        classification,
        handling_code,
        tuple(sorted(set(datasets))),
        originator if restricted else None,
        owning_unit if restricted else None,
    )


def merge_handling(existing: Handling, incoming: Handling, scheme: HandlingScheme) -> Handling:
    """The handling of an element written again (ADR-102): never lower than either write's. The
    higher classification; the handling code with the narrower dissemination; the action code that
    forbids direct action (then the one needing the originator's permission) over one that permits
    it, and any over none; the sanitisation code that consults the originator over one that does
    not, and any over none; the earlier review date; a legal basis once given. The owning unit and
    originator stay the existing element's: the restricted-code check rests on them, and a later
    write does not move the element to another unit. Lowering handling is an analyst's explicit
    change, never a merge.

    The same order whichever write came first, except the units, which are the first's. A code
    the scheme does not define is refused rather than ranked by guesswork."""
    for h in (existing, incoming):
        if h.classification not in scheme.classification:
            raise HandlingSchemeError(
                f"classification {h.classification!r} is not defined in scheme {scheme.name!r}"
            )
        _known(scheme.handling_codes, h.handling_code, "handling code", scheme)
        _known(scheme.action_codes, h.action_code, "action code", scheme)
        _known(scheme.sanitisation_codes, h.sanitisation_code, "sanitisation code", scheme)

    classification = max(
        (existing.classification, incoming.classification), key=scheme.classification.index
    )
    handling_code = max(
        (existing.handling_code, incoming.handling_code),
        key=lambda c: _DISSEMINATION_RANK[scheme.handling_codes[c].dissemination],
    )

    def action_rank(code: str | None) -> tuple[int, int]:
        if code is None:
            return (0, 0)
        a = scheme.action_codes[code]
        return (2 if not a.direct_action else 1, 1 if a.originator_permission else 0)

    def sanitisation_rank(code: str | None) -> int:
        if code is None:
            return 0
        return 2 if scheme.sanitisation_codes[code].consult_originator else 1

    reviews = [d for d in (existing.review_date, incoming.review_date) if d is not None]
    return existing.model_copy(
        update={
            "classification": classification,
            "handling_code": handling_code,
            "action_code": max((existing.action_code, incoming.action_code), key=action_rank),
            "sanitisation_code": max(
                (existing.sanitisation_code, incoming.sanitisation_code), key=sanitisation_rank
            ),
            "review_date": min(reviews) if reviews else None,
            "legal_basis": existing.legal_basis or incoming.legal_basis,
        }
    )


def evaluate_handling(handling: Handling, scheme: HandlingScheme) -> HandlingDecision:
    """Evaluate one node/edge's `Handling` block against the active scheme."""
    if handling.classification not in scheme.classification:
        raise HandlingSchemeError(
            f"classification {handling.classification!r} is not defined in scheme {scheme.name!r}"
        )
    handling_code = scheme.handling_codes.get(handling.handling_code)
    if handling_code is None:
        raise HandlingSchemeError(
            f"handling code {handling.handling_code!r} is not defined in scheme {scheme.name!r}"
        )

    direct_action_permitted = False
    originator_permission_required = False
    if handling.action_code is not None:
        action_code = scheme.action_codes.get(handling.action_code)
        if action_code is None:
            raise HandlingSchemeError(
                f"action code {handling.action_code!r} is not defined in scheme {scheme.name!r}"
            )
        direct_action_permitted = action_code.direct_action
        originator_permission_required = action_code.originator_permission

    consult_originator = False
    if handling.sanitisation_code is not None:
        sanitisation_code = scheme.sanitisation_codes.get(handling.sanitisation_code)
        if sanitisation_code is None:
            raise HandlingSchemeError(
                f"sanitisation code {handling.sanitisation_code!r} is not defined in "
                f"scheme {scheme.name!r}"
            )
        consult_originator = sanitisation_code.consult_originator

    return HandlingDecision(
        dissemination=handling_code.dissemination,
        direct_action_permitted=direct_action_permitted,
        originator_permission_required=originator_permission_required,
        consult_originator=consult_originator,
    )


def principal_may_view(handling: Handling, principal: Principal, scheme: HandlingScheme) -> bool:
    """The same two axes `AccessFilter.gremlin_has_step` compiles into a
    traversal predicate (`01_DOMAIN_MODEL.md` §2.2), evaluated directly
    for one `Handling` block instead of injected into a query — for a
    caller with no traversal to inject a predicate into, such as the
    source profiler's shape-masking decision (`09_INGEST_STUDIO.md` §3).
    `action_code`/`sanitisation_code` never gate a read, only classification
    and a restricted `handling_code` do."""
    if not scheme.clears(principal.clearance, handling.classification):
        return False
    code = scheme.handling_codes.get(handling.handling_code)
    if code is None:
        raise HandlingSchemeError(
            f"handling code {handling.handling_code!r} is not defined in scheme {scheme.name!r}"
        )
    if code.dissemination != "restricted":
        return True
    return handling.handling_code in principal.receivable_handling_codes and principal.org_unit in (
        handling.owning_unit,
        handling.originator,
    )


def in_case_datasets(datasets: Sequence[str], principal: Principal) -> bool:
    """ADR-099's third axis for one element: it belongs to one of the case's datasets, or the
    principal is the Conduit's own unlimited background work (`datasets is None`). The same rule
    `AccessFilter.gremlin_dataset_step` compiles into a traversal."""
    if principal.datasets is None:
        return True
    return not set(datasets).isdisjoint(principal.datasets)


def principal_may_read(
    handling: Handling, datasets: Sequence[str], principal: Principal, scheme: HandlingScheme
) -> bool:
    """All three axes for one stored element, for a caller holding its body already (the working
    set's projection, export): its handling and its datasets."""
    return in_case_datasets(datasets, principal) and principal_may_view(handling, principal, scheme)
