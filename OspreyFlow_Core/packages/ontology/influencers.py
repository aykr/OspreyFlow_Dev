"""Link-strength influencers (`06_DECISIONS.md` ADR-139; `01_DOMAIN_MODEL.md` §6.1a): the shipped
defaults, the resolution order, and the arithmetic. Pure: no store, no clock.

**The arithmetic** (decisions 1 and 5). A link's stored weight `w` (weights version 3, unchanged)
is a logistic of a pre-logistic score; that score is recovered exactly by the logistic's inverse,
`raw = midpoint + scale · ln(w / (1 − w))` (the file's one deployment-wide `midpoint` and `scale`,
the same in every version). Then, of the influencers that apply to the link:

```
raw'     = (raw + Σ add) · Π multiply
strength = normalise(raw')                     # the same logistic
strength = max(strength, every floor)          # "the link is at least this strong"
strength = min(strength, w)   if any exclude   # "drawn no stronger than the base"
```

With nothing applying, `strength == w` exactly. Every step is non-decreasing in `w`, and `w` is
non-decreasing in the link's occurrences (§6.1's invariant), so **adding occurrences never lowers a
strength**, whichever influencers apply (`test_influencers.py`'s grid). An exclusion is last, so it
caps whatever a floor raised: "no stronger than the base" is absolute.

**When one applies** (decision 2). A direct-links influencer (no trigger) applies to every link of
its named types. A triggered one applies to a link of its named types only when the graph adapter
has found, as the viewer, a record of the trigger's kind whose property holds one of its values, at
one end of the link or linked to both ends; the adapter passes the kinds it found (`evidence`), and
a record the viewer may not see is never found (rule 3), so it changes nothing.

**The resolution order** (decision 3): a case override, then the installation set, then the weights
file. Influencers are matched by `id`: a later layer's influencer replaces an earlier one of the
same id, and one with `enabled: false` switches it off. A case may also switch off any installation
or shipped influencer by id.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from schemas.strength import (
    RARITY_NOTE,
    ActiveInfluencer,
    AppliedInfluencer,
    CaseInfluencersInput,
    StrengthInfluencer,
    StrengthLegend,
)

from .errors import OntologyError
from .weights import _DEFAULT_PATH, WeightRules

#: A weight of exactly 0 or 1 has no finite pre-logistic score; it is read as this close to it.
_EDGE = 1e-9


@dataclass(frozen=True)
class StrengthDefaults:
    """What the weights file ships for ADR-139: its influencers, and the types never counted as a
    shared attribute."""

    influencers: tuple[StrengthInfluencer, ...]
    rarity_exclude_types: tuple[str, ...]


def load_strength_defaults(path: Path | None = None) -> StrengthDefaults:
    """The weights file's `influencers` and `rarity` blocks. Refuses a malformed influencer by its
    position and id, in words (`OntologyError`)."""
    source = Path(path) if path is not None else _DEFAULT_PATH
    loaded: Any = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    raw_influencers = loaded.get("influencers") or []
    if not isinstance(raw_influencers, list):
        raise OntologyError("the weights file's `influencers` must be a list")
    influencers: list[StrengthInfluencer] = []
    for position, raw in enumerate(raw_influencers, start=1):
        try:
            influencers.append(StrengthInfluencer.model_validate(raw))
        except ValidationError as error:
            named = raw.get("id") if isinstance(raw, dict) else None
            raise OntologyError(
                f"influencer {position} ({named!r}) in the weights file is refused: "
                f"{error.errors()[0]['msg']}"
            ) from error
    ids = [i.id for i in influencers]
    if len(set(ids)) != len(ids):
        raise OntologyError("the weights file names an influencer id twice")
    rarity = loaded.get("rarity") or {}
    if not isinstance(rarity, dict) or set(rarity) - {"exclude_types"}:
        raise OntologyError("the weights file's `rarity` holds only `exclude_types`")
    exclude = rarity.get("exclude_types") or []
    if not isinstance(exclude, list) or not all(isinstance(t, str) for t in exclude):
        raise OntologyError("`rarity.exclude_types` must be a list of entity types")
    return StrengthDefaults(influencers=tuple(influencers), rarity_exclude_types=tuple(exclude))


def calibrated_boost(rules: WeightRules) -> float:
    """The size a shipped boost is calibrated to (decision 1): how far doubling an ordinary link's
    count moves its pre-logistic score, an ordinary link being one at the default rule's heavy
    count."""
    heavy = rules.default.heavy or 10
    return rules.alpha * (math.log1p(2 * heavy) - math.log1p(heavy)) / math.log1p(heavy)


# --- the resolution order -----------------------------------------------------------------------


def resolve_influencers(
    shipped: Sequence[StrengthInfluencer],
    installation: Sequence[StrengthInfluencer] | None = None,
    case: CaseInfluencersInput | None = None,
    *,
    installation_version: int | None = None,
    case_version: int | None = None,
) -> tuple[list[ActiveInfluencer], list[str]]:
    """The influencers in force, each with its layer, and the ids the case switched off.

    Order is kept: the file's, then those the installation adds, then those the case adds; a
    replacement takes the place of what it replaces."""
    active: dict[str, ActiveInfluencer] = {}
    for influencer in shipped:
        active[influencer.id] = ActiveInfluencer(influencer=influencer, layer="file")
    for influencer in installation or ():
        active[influencer.id] = ActiveInfluencer(
            influencer=influencer, layer="installation", version=installation_version
        )
    switched_off: list[str] = []
    if case is not None:
        for influencer in case.added:
            active[influencer.id] = ActiveInfluencer(
                influencer=influencer, layer="case", version=case_version
            )
        for key in case.switched_off:
            held = active.get(key)
            if held is not None and held.layer != "case":
                del active[key]
                switched_off.append(key)
    in_force = [a for a in active.values() if a.influencer.enabled]
    return in_force, sorted(switched_off)


def direct_link_types(active: Sequence[ActiveInfluencer]) -> list[str]:
    """The link types that count as direct: those a trigger-less influencer names."""
    named = {t for a in active if a.influencer.trigger is None for t in a.influencer.link_types}
    return sorted(named)


def legend_of(
    active: Sequence[ActiveInfluencer],
    switched_off: Sequence[str],
    *,
    case_version: int | None = None,
    case_set_by_name: str | None = None,
) -> StrengthLegend:
    """The legend box's account of strength (decision 7): exactly the influencers in force."""
    return StrengthLegend(
        influencers=list(active),
        direct_link_types=direct_link_types(active),
        switched_off=list(switched_off),
        rarity_note=RARITY_NOTE,
        case_version=case_version,
        case_set_by_name=case_set_by_name,
    )


# --- the arithmetic -----------------------------------------------------------------------------


def pre_logistic(weight: float, rules: WeightRules) -> float:
    """The score a stored weight is the logistic of: the logistic's inverse."""
    w = min(max(weight, _EDGE), 1 - _EDGE)
    return rules.midpoint + rules.scale * math.log(w / (1 - w))


def logistic(raw: float, rules: WeightRules) -> float:
    exponent = -(raw - rules.midpoint) / rules.scale
    if exponent > 700:  # beyond a double's range: the logistic is 0 to every digit kept
        return 0.0
    return 1.0 / (1.0 + math.exp(exponent))


def applies_to(influencer: StrengthInfluencer, edge_type: str, evidence: Mapping[str, str]) -> bool:
    """A direct-links influencer applies to its link types; a triggered one only where a visible
    evidencing record was found for it (`evidence`, by influencer id)."""
    if edge_type not in influencer.link_types:
        return False
    return influencer.trigger is None or influencer.id in evidence


def connection_strength(
    weight: float,
    edge_type: str,
    active: Sequence[ActiveInfluencer],
    evidence: Mapping[str, str],
    rules: WeightRules,
) -> tuple[float, list[AppliedInfluencer]]:
    """A link's connection strength from its stored `weight`, and the influencers that changed it.

    `evidence` maps a triggered influencer's id to the kind of the visible record that evidenced
    this link; the graph adapter builds it under the viewer's access predicate."""
    applied = [a for a in active if applies_to(a.influencer, edge_type, evidence)]
    if not applied:
        return weight, []
    raw = pre_logistic(weight, rules)
    added = sum(a.influencer.size for a in applied if a.influencer.change == "add")
    factor = math.prod(a.influencer.size for a in applied if a.influencer.change == "multiply")
    strength = logistic((raw + added) * factor, rules)
    if not any(a.influencer.change in ("add", "multiply") for a in applied):
        strength = weight
    floors = [a.influencer.size for a in applied if a.influencer.change == "floor"]
    if floors:
        strength = max(strength, *floors)
    if any(a.influencer.change == "exclude" for a in applied):
        strength = min(strength, weight)
    said = [
        AppliedInfluencer(
            id=a.influencer.id,
            label=a.influencer.label,
            change=a.influencer.change,
            size=a.influencer.size,
            layer=a.layer,
            record_kind=(
                None if a.influencer.trigger is None else evidence.get(a.influencer.id)
            ),
        )
        for a in applied
    ]
    return strength, said


__all__ = [
    "StrengthDefaults",
    "applies_to",
    "calibrated_boost",
    "connection_strength",
    "direct_link_types",
    "legend_of",
    "load_strength_defaults",
    "logistic",
    "pre_logistic",
    "resolve_influencers",
]
