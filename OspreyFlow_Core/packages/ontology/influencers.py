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
or shipped influencer by id. The composition and the rarity measure resolve the same way
(`resolve_settings`).

**Client parity** (ADR-139 Amendment 2, the client's `add_strength_column`). Strength is a sum, on
the client's scale, of a rarity term and the adds of the influencers that apply, with no count, no
recency and no other kind of change (the client's code has only adds):

```
raw_sum  = rarity term + Σ add
strength = parity_drawn(raw_sum) = 1 / (1 + e^(−(raw_sum − 1) / 0.1))   # drawn on 0–1
```

The drawing curve is centred on 1, an unboosted value no other pair shares, with a scale of 0.1,
so the client's useful range (about 0.5 to 1.5) spreads across the slider; it is strictly
increasing, so the order of the sums is kept. The rarity term of a pair linked through a shared
value `a` is `share_rarity(C(k, 2), Σ_b C(k_b, 2))`; that of a stored (direct) link is the same
with the link as a value of its own, held by its two ends, among the visible links of its type:
`1 − 1/n`. Both are
counted by the graph adapter under access.
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
    SHARED_VALUE,
    ActiveInfluencer,
    AppliedInfluencer,
    CaseInfluencersInput,
    DatasetTrigger,
    InfluencerLayer,
    InfluencerTrigger,
    RarityMeasure,
    StrengthComposition,
    StrengthInfluencer,
    StrengthLegend,
)

from .errors import OntologyError
from .weights import _DEFAULT_PATH, WeightRules

#: A weight of exactly 0 or 1 has no finite pre-logistic score; it is read as this close to it.
_EDGE = 1e-9

#: Client parity's drawing curve (Amendment 2): centred on 1, scale 0.1 (see the module's words).
PARITY_MIDPOINT = 1.0
PARITY_SCALE = 0.1

_MEASURES = ("share", "idf")
_COMPOSITIONS = ("standard", "client_parity")


@dataclass(frozen=True)
class StrengthDefaults:
    """What the weights file ships for ADR-139: its influencers, the types never counted as a
    shared attribute, and (Amendment 2) the rarity measure and the composition."""

    influencers: tuple[StrengthInfluencer, ...]
    rarity_exclude_types: tuple[str, ...]
    rarity_measure: RarityMeasure = "share"
    composition: StrengthComposition = "standard"


@dataclass(frozen=True)
class StrengthSettings:
    """The composition and rarity measure in force in a case, and where the composition came
    from (Amendment 2): a case override, then the installation set, then the weights file."""

    composition: StrengthComposition = "standard"
    composition_layer: InfluencerLayer = "file"
    rarity_measure: RarityMeasure = "share"


def resolve_settings(
    defaults: StrengthDefaults,
    installation_composition: StrengthComposition | None = None,
    installation_measure: RarityMeasure | None = None,
    case_composition: StrengthComposition | None = None,
) -> StrengthSettings:
    """The case's choice, then the installation version's, then the file's. Client parity always
    reads the client's own measure (`share`): its sum is on the client's scale only with it."""
    composition: StrengthComposition = defaults.composition
    layer: InfluencerLayer = "file"
    if installation_composition is not None:
        composition, layer = installation_composition, "installation"
    if case_composition is not None:
        composition, layer = case_composition, "case"
    measure: RarityMeasure = installation_measure or defaults.rarity_measure
    if composition == "client_parity":
        measure = "share"
    return StrengthSettings(
        composition=composition, composition_layer=layer, rarity_measure=measure
    )


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
    if not isinstance(rarity, dict) or set(rarity) - {"exclude_types", "measure"}:
        raise OntologyError("the weights file's `rarity` holds only `exclude_types` and `measure`")
    exclude = rarity.get("exclude_types") or []
    if not isinstance(exclude, list) or not all(isinstance(t, str) for t in exclude):
        raise OntologyError("`rarity.exclude_types` must be a list of entity types")
    measure = rarity.get("measure", "share")
    if measure not in _MEASURES:
        raise OntologyError("`rarity.measure` is `share` (the client's) or `idf`")
    composition = loaded.get("composition", "standard")
    if composition not in _COMPOSITIONS:
        raise OntologyError("the weights file's `composition` is `standard` or `client_parity`")
    return StrengthDefaults(
        influencers=tuple(influencers),
        rarity_exclude_types=tuple(exclude),
        rarity_measure=measure,
        composition=composition,
    )


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
    """The link types that count as direct: those a trigger-less influencer names (a shared value
    is never direct: it is the client's `dup_*`)."""
    named = {
        t
        for a in active
        if a.influencer.trigger is None
        for t in a.influencer.link_types
        if t != SHARED_VALUE
    }
    return sorted(named)


def readable_datasets(
    trigger: DatasetTrigger, readable: Sequence[str] | None
) -> list[str]:
    """The trigger's datasets the reader may read (`None`: every one)."""
    if readable is None:
        return list(trigger.datasets)
    allowed = set(readable)
    return [d for d in trigger.datasets if d in allowed]


def as_the_reader_sees(
    active: Sequence[ActiveInfluencer], readable: Sequence[str] | None
) -> list[ActiveInfluencer]:
    """The influencers in force as a reader may be told of them (Amendment 2, ruling 3): a
    dataset-triggered one names only the datasets they may read, and one naming none of those is
    not shown at all, since it can change nothing they see."""
    seen: list[ActiveInfluencer] = []
    for a in active:
        trigger = a.influencer.trigger
        if isinstance(trigger, DatasetTrigger):
            named = readable_datasets(trigger, readable)
            if not named:
                continue
            if named != trigger.datasets:
                narrowed = a.influencer.model_copy(
                    update={"trigger": trigger.model_copy(update={"datasets": named})}
                )
                a = a.model_copy(update={"influencer": narrowed})
        seen.append(a)
    return seen


def legend_of(
    active: Sequence[ActiveInfluencer],
    switched_off: Sequence[str],
    *,
    case_version: int | None = None,
    case_set_by_name: str | None = None,
    settings: StrengthSettings | None = None,
    readable: Sequence[str] | None = None,
) -> StrengthLegend:
    """The legend box's account of strength (decision 7): exactly the influencers in force, as
    the reader may be told of them, and the composition and rarity measure (Amendment 2)."""
    held = settings or StrengthSettings()
    shown = as_the_reader_sees(active, readable)
    return StrengthLegend(
        influencers=shown,
        direct_link_types=direct_link_types(shown),
        switched_off=list(switched_off),
        rarity_note=RARITY_NOTE,
        composition=held.composition,
        composition_layer=held.composition_layer,
        rarity_measure=held.rarity_measure,
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
    evidencing record, or a readable evidencing dataset, was found for it (`evidence`, by
    influencer id)."""
    if edge_type not in influencer.link_types:
        return False
    return influencer.trigger is None or influencer.id in evidence


def dataset_evidence(
    active: Sequence[ActiveInfluencer],
    edge_type: str,
    dataset: str | None,
    readable: Sequence[str] | None,
) -> dict[str, str]:
    """For a link (or a shared value) evidenced in `dataset`: each dataset-triggered influencer
    naming its type and that dataset, when the reader may read it, mapped to the dataset. A
    dataset the reader may not read evidences nothing (rule 3)."""
    found: dict[str, str] = {}
    if dataset is None:
        return found
    for a in active:
        trigger = a.influencer.trigger
        if (
            isinstance(trigger, DatasetTrigger)
            and edge_type in a.influencer.link_types
            and dataset in readable_datasets(trigger, readable)
        ):
            found[a.influencer.id] = dataset
    return found


def _said(
    applied: Sequence[ActiveInfluencer], evidence: Mapping[str, str]
) -> list[AppliedInfluencer]:
    said: list[AppliedInfluencer] = []
    for a in applied:
        trigger = a.influencer.trigger
        said.append(
            AppliedInfluencer(
                id=a.influencer.id,
                label=a.influencer.label,
                change=a.influencer.change,
                size=a.influencer.size,
                layer=a.layer,
                record_kind=evidence.get(a.influencer.id)
                if isinstance(trigger, InfluencerTrigger)
                else None,
                dataset=evidence.get(a.influencer.id)
                if isinstance(trigger, DatasetTrigger)
                else None,
            )
        )
    return said


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
    return strength, _said(applied, evidence)


# --- client parity (Amendment 2) ----------------------------------------------------------------


def share_rarity(pair_links: int, total_pair_links: int) -> float:
    """The client's `edge_strength_1 = 1 − N / ΣN`, with `N` the visible pair links through one
    value and `ΣN` those through every value of its kind in scope. 0 when nothing is counted."""
    if total_pair_links <= 0 or pair_links <= 0:
        return 0.0
    return 1.0 - pair_links / total_pair_links


def pair_links(holders: int) -> int:
    """`C(k, 2)`: the pair links a value held by `k` visible holders stands for (the client's
    `dup_*` rows through it)."""
    return holders * (holders - 1) // 2


def parity_drawn(raw_sum: float) -> float:
    """A client-parity sum drawn on 0–1, order preserving."""
    exponent = -(raw_sum - PARITY_MIDPOINT) / PARITY_SCALE
    if exponent > 700:
        return 0.0
    return 1.0 / (1.0 + math.exp(exponent))


def parity_strength(
    rarity_term: float,
    edge_type: str,
    active: Sequence[ActiveInfluencer],
    evidence: Mapping[str, str],
) -> tuple[float, float, list[AppliedInfluencer]]:
    """Client parity: the raw sum (the rarity term and every applying influencer's add, the
    client's `edge_strength_1 + abs_add (+ non_dup_add)`), that sum drawn on 0–1, and the adds
    that applied. A multiplier, floor or exclusion has no place in the client's sum and is left
    out (the legend and the Inspector say so)."""
    applied = [
        a
        for a in active
        if a.influencer.change == "add" and applies_to(a.influencer, edge_type, evidence)
    ]
    raw = rarity_term + sum(a.influencer.size for a in applied)
    return raw, parity_drawn(raw), _said(applied, evidence)


__all__ = [
    "PARITY_MIDPOINT",
    "PARITY_SCALE",
    "StrengthDefaults",
    "StrengthSettings",
    "applies_to",
    "as_the_reader_sees",
    "calibrated_boost",
    "connection_strength",
    "dataset_evidence",
    "direct_link_types",
    "legend_of",
    "load_strength_defaults",
    "logistic",
    "pair_links",
    "parity_drawn",
    "parity_strength",
    "pre_logistic",
    "readable_datasets",
    "resolve_influencers",
    "resolve_settings",
    "share_rarity",
]
