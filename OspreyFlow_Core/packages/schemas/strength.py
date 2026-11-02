"""Connection strength (`06_DECISIONS.md` ADR-139; `01_DOMAIN_MODEL.md` §6.1a): link-strength
influencers, direct links and shared-attribute rarity.

**An influencer** changes how strong a link is drawn, at read time, under the viewer's access
(rule 3). It has a trigger (an evidencing record's kind, property and values), the link types it
influences, a change (add a boost before the logistic, multiply the pre-logistic score, set a
floor, or exclude: no stronger than the stored weight), a size and a legend label. **Direct links
are an influencer with no trigger:** it applies to its named link types whatever evidences them.

**Where influencers come from, in resolution order** (decision 3): a case override (its Author's,
audited), then the installation set (maker–checker: proposed by one holder of
`manage_strength_influencers`, approved by a second; every version kept), then the weights file's
developer defaults (`packages/ontology/weights/default.yaml`).

**Stored weights are unchanged** (weights version 3): a link's connection strength is its stored
weight with the influencers that apply to it, worked out when it is read, never stored.

**Rarity** is its own measure beside strength, never folded into it, counted over what the viewer
may see, per dataset or across the case's readable datasets. Two measures (ADR-139 Amendment 2):
**`share`, the client's own and the default**, `1 − L_visible(a) / Σ_b L_visible(b)` for the value
`a` linking a pair, where `L_visible(a) = C(k, 2)` for the `k` visible holders of `a` and the sum
runs over the values of `a`'s kind in scope (a pair takes its highest); and **`idf`**,
`Σ ln(N_visible / df_visible(a))` over the values the pair shares (the first decision's). The Glass
is sent the score and the shared values it may see, never `N`, `df`, `k` or `L` (rule 7).

**Two compositions** (Amendment 2, ruling 2): `standard` (the stored weight with the influencers,
above) and `client_parity` (strength = rarity + the influencers' adds, no count and no recency, the
client's `add_strength_column`), chosen by a version of the installation set or a case override,
and drawn on 0–1 through a logistic of the sum (`ontology/influencers.py`'s `parity_drawn`).

TypeScript is generated from these models (`generate_ts.py`); drift fails the build.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.domain import Node

#: The four kinds of change (decision 1).
InfluencerChange = Literal["add", "multiply", "floor", "exclude"]
#: Where an active influencer came from (decision 3's resolution order, lowest first).
InfluencerLayer = Literal["file", "installation", "case"]
#: Rarity per dataset (the client's own, the default) or across the case's readable datasets.
RarityScope = Literal["dataset", "case"]
#: ADR-139 Amendment 2: the client's share of pair links (the default) or the first decision's IDF.
RarityMeasure = Literal["share", "idf"]
#: ADR-139 Amendment 2: the stored weight with influencers, or the client's rarity plus adds.
StrengthComposition = Literal["standard", "client_parity"]
#: A monitoring condition's figure: on the drawn 0–1 scale, or on the client's raw sum.
StrengthScale = Literal["drawn", "client"]

#: The link-type name an influencer uses for a pair linked through a shared value (the client's
#: `dup_*` rows): in OspreyFlow a shared value is a two-step path, not a stored link type, so this
#: name is reserved and no ontology declares it.
SHARED_VALUE = "SHARED_VALUE"

#: The most values one trigger lists, the most link types one influencer names, the most
#: influencers one layer holds.
TRIGGER_VALUES_MAX = 20
INFLUENCER_LINK_TYPES_MAX = 30
INFLUENCERS_MAX = 50
#: A multiplier's bounds: below 1 it weakens, above 1 it strengthens; never 0 or negative, which
#: would turn the pre-logistic score over and break monotonicity.
MULTIPLY_MIN = 0.1
MULTIPLY_MAX = 5.0
#: An added boost's bounds (pre-logistic units; the shipped boosts are 0.135).
ADD_MAX = 2.0

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class InfluencerTrigger(BaseModel):
    """What triggers an influencer: a record of `entity_type` whose `property` holds one of
    `values`, which the viewer may see, at one end of the link or linked to both of its ends (the
    record "evidences" the link)."""

    kind: Literal["record"] = "record"
    entity_type: str = Field(min_length=1, max_length=80)
    property: str = Field(min_length=1, max_length=80)
    values: list[str] = Field(min_length=1, max_length=TRIGGER_VALUES_MAX)

    @field_validator("values")
    @classmethod
    def _distinct(cls, values: list[str]) -> list[str]:
        if any(not v.strip() for v in values):
            raise ValueError("a trigger value is never empty")
        if len(set(values)) != len(values):
            raise ValueError("each trigger value is named once")
        return values


class DatasetTrigger(BaseModel):
    """ADR-139 Amendment 2, ruling 3: an influencer triggered by a dataset (or the source loaded
    into it), as the client's `abs_add` is by the table it is called on. It applies to every link
    evidenced in one of `datasets`: a stored link that belongs to it, or a pair linked through a
    shared value in it. It applies only where the viewer may read that dataset, so a link seen
    through another dataset is never thickened by one they cannot read (rule 3)."""

    kind: Literal["dataset"] = "dataset"
    datasets: list[str] = Field(min_length=1, max_length=TRIGGER_VALUES_MAX)

    @field_validator("datasets")
    @classmethod
    def _distinct(cls, values: list[str]) -> list[str]:
        if any(not v.strip() for v in values):
            raise ValueError("a dataset is never empty")
        if len(set(values)) != len(values):
            raise ValueError("each dataset is named once")
        return values


class StrengthInfluencer(BaseModel):
    """One influencer (decision 1). `trigger` None is a direct-links influencer. `enabled` False,
    in a higher layer, switches off the influencer of the same `id` below it. `link_types` may
    name `SHARED_VALUE`: a pair linked through a shared value (Amendment 2)."""

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=80)
    trigger: InfluencerTrigger | DatasetTrigger | None = None
    link_types: list[str] = Field(min_length=1, max_length=INFLUENCER_LINK_TYPES_MAX)
    change: InfluencerChange = "add"
    #: add: a boost before the logistic, above 0 and at most `ADD_MAX`; multiply: a factor from
    #: `MULTIPLY_MIN` to `MULTIPLY_MAX`; floor: the least strength, above 0 and at most 1;
    #: exclude: 0 (it has no size).
    size: float = 0.0
    enabled: bool = True
    #: Said beside it wherever a value is still to be agreed ("to be confirmed with the client").
    note: str | None = Field(default=None, max_length=200)

    @field_validator("id")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not _ID.match(value):
            raise ValueError(
                "an influencer's id is lower-case letters, digits, '-' and '_', starting with a "
                "letter or digit"
            )
        return value

    @field_validator("link_types")
    @classmethod
    def _distinct_types(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("each link type is named once")
        return values

    @model_validator(mode="after")
    def _size_fits_change(self) -> StrengthInfluencer:
        size = self.size
        if not math.isfinite(size):
            raise ValueError("an influencer's size is a finite number")
        if self.change == "add" and not 0 < size <= ADD_MAX:
            raise ValueError(f"an added boost is above 0 and at most {ADD_MAX:g}")
        if self.change == "multiply" and not MULTIPLY_MIN <= size <= MULTIPLY_MAX:
            raise ValueError(
                f"a multiplier is from {MULTIPLY_MIN:g} to {MULTIPLY_MAX:g} (1 changes nothing)"
            )
        if self.change == "floor" and not 0 < size <= 1:
            raise ValueError("a floor is a strength above 0 and at most 1")
        if self.change == "exclude" and size != 0:
            raise ValueError("an exclusion has no size; leave it at 0")
        if SHARED_VALUE in self.link_types:
            if isinstance(self.trigger, InfluencerTrigger):
                raise ValueError(
                    "a pair linked through a shared value is evidenced by its dataset, not by a "
                    "record; trigger it by a dataset, or by nothing"
                )
            if self.change != "add":
                raise ValueError("a pair linked through a shared value takes an added boost only")
        return self


def _unique_ids(influencers: list[StrengthInfluencer]) -> list[StrengthInfluencer]:
    ids = [i.id for i in influencers]
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise ValueError(f"each influencer's id is used once; repeated: {', '.join(repeated)}")
    return influencers


class InfluencerSetInput(BaseModel):
    """A proposed installation-wide set: the whole set as it would stand once approved, with the
    composition and rarity measure it chooses (Amendment 2; None keeps the weights file's)."""

    influencers: list[StrengthInfluencer] = Field(max_length=INFLUENCERS_MAX)
    composition: StrengthComposition | None = None
    rarity_measure: RarityMeasure | None = None
    #: Why, in words, for the approver.
    words: str = Field(default="", max_length=500)

    @field_validator("influencers")
    @classmethod
    def _ids(cls, value: list[StrengthInfluencer]) -> list[StrengthInfluencer]:
        return _unique_ids(value)


#: A version's state: waiting for a second person, approved (and in force until a later one is),
#: sent back by a second person or withdrawn by its proposer.
InfluencerSetStatus = Literal["pending", "approved", "sent_back"]


class InfluencerSetVersion(BaseModel):
    """One version of the installation-wide set, kept whole with who proposed and who decided it
    (decision 3). Names are resolved when the read is served, never stored (ADR-106)."""

    version: int = Field(ge=1)
    influencers: list[StrengthInfluencer]
    composition: StrengthComposition | None = None
    rarity_measure: RarityMeasure | None = None
    status: InfluencerSetStatus
    proposed_by: str
    proposed_at: datetime
    words: str = ""
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_words: str | None = None
    #: True for the approved version in force now.
    in_force: bool = False
    proposed_by_name: str | None = None
    decided_by_name: str | None = None


class InfluencerSetHistory(BaseModel):
    """`GET /v1/strength-influencers`: every version, newest first, and the developer defaults
    that apply where no approved version names an influencer (with the file's composition and
    rarity measure)."""

    versions: list[InfluencerSetVersion]
    defaults: list[StrengthInfluencer]
    default_composition: StrengthComposition = "standard"
    default_rarity_measure: RarityMeasure = "share"


class InfluencerDecision(BaseModel):
    """Sending a waiting version back (or its proposer withdrawing it), in words."""

    words: str = Field(min_length=1, max_length=500)


class CaseInfluencersInput(BaseModel):
    """A case's override, set by its Author (decision 3): influencers added for this case, and the
    ids of installation-wide (or shipped) influencers switched off in it."""

    added: list[StrengthInfluencer] = Field(default_factory=list, max_length=INFLUENCERS_MAX)
    switched_off: list[str] = Field(default_factory=list, max_length=INFLUENCERS_MAX)
    #: Amendment 2: the composition this case uses (for a demonstration of client parity, say);
    #: None, the installation's.
    composition: StrengthComposition | None = None
    words: str = Field(default="", max_length=500)

    @field_validator("added")
    @classmethod
    def _ids(cls, value: list[StrengthInfluencer]) -> list[StrengthInfluencer]:
        return _unique_ids(value)


class CaseInfluencers(BaseModel):
    """`GET /v1/investigations/{id}/strength-influencers`: the legend for the case, and its own
    override as its Author last set it (None: it has none)."""

    legend: StrengthLegend
    override: CaseInfluencersInput | None = None
    #: Whether the reader is the case's Author, so the Glass offers the override's editor.
    can_override: bool = False


class InfluencerRefusal(BaseModel):
    """An influencer refused against the deployment's ontology, in words (never a bare 422)."""

    error: Literal["influencer_refused"] = "influencer_refused"
    influencer: str
    reason: str


class ActiveInfluencer(BaseModel):
    """One influencer in force for a case, and where it came from (`layer`); `version` is the
    installation set's or the case override's version, None for the file's."""

    influencer: StrengthInfluencer
    layer: InfluencerLayer
    version: int | None = None


class StrengthLegend(BaseModel):
    """What the legend box says about connection strength (decision 7): the influencers in force,
    each marked by its layer (a case override as such), which link types count as direct, which
    shipped or installation influencers the case has switched off, and the rarity note."""

    influencers: list[ActiveInfluencer]
    direct_link_types: list[str]
    switched_off: list[str] = Field(default_factory=list)
    rarity_note: str
    #: Amendment 2: the composition in force in the case, where it came from, and the rarity
    #: measure.
    composition: StrengthComposition = "standard"
    composition_layer: InfluencerLayer = "file"
    rarity_measure: RarityMeasure = "share"
    #: The case override's version, None when the case has none.
    case_version: int | None = None
    case_set_by_name: str | None = None


class AppliedInfluencer(BaseModel):
    """One influencer that changed one link, and the kind of record that evidenced it (None for a
    direct-links influencer). Only a record the viewer may see is ever named."""

    id: str
    label: str
    change: InfluencerChange
    size: float
    layer: InfluencerLayer
    record_kind: str | None = None
    #: A dataset-triggered influencer: the dataset (readable by the viewer) that evidenced it.
    dataset: str | None = None


class LinkStrength(BaseModel):
    """A link's connection strength as its viewer may see it (decision 5), with what explains it
    (decision 9): the stored weight, the rule and version it was computed under, what is heavy for
    its type, and each influencer that changed it. Never a corpus-wide count (ADR-122)."""

    edge_id: str
    edge_type: str
    base_weight: float
    strength: float
    #: `"<version>/<rule>"` from the stored components, None for a weight from before ADR-120.
    parameter_set: str | None = None
    #: The count that is heavy for the type, or None for a fixed (structural) type.
    heavy: int | None = None
    #: A structural type's fixed strength, or None.
    fixed: float | None = None
    occurrences: int = 0
    last_seen: datetime | None = None
    applied: list[AppliedInfluencer] = Field(default_factory=list)
    #: Amendment 2: the composition `strength` was worked out under. Under `client_parity`,
    #: `rarity_term` is the link's own term (`1 − 1/n` for the `n` visible links of its type in
    #: `dataset`), `raw_sum` that term plus the adds (the client's scale), and `strength` the sum
    #: drawn on 0–1. All three None under `standard`.
    composition: StrengthComposition = "standard"
    rarity_term: float | None = None
    raw_sum: float | None = None
    dataset: str | None = None


class ConnectionStrengthRequest(BaseModel):
    """`POST /v1/investigations/{id}/connection-strength`: the links to explain, or every link of
    the working set the reader may see when none are named."""

    edge_ids: list[str] | None = Field(default=None, max_length=50_000)


class ConnectionStrengths(BaseModel):
    links: list[LinkStrength]
    legend: StrengthLegend


class SharedAttribute(BaseModel):
    """One attribute node a pair shares, as the viewer may see it, with its score: its
    contribution to the pair's rarity (`ln(N_visible / df_visible)`) under `idf`, its own rarity
    (`1 − L/ΣL`) under `share`; a score and never a count."""

    node: Node
    score: float


class PairRarity(BaseModel):
    """Two entities' shared-attribute rarity. `dataset` names the dataset it was worked out in
    (per-dataset scope), None across the case's readable datasets. `score` None: the two are of
    different kinds, or share no dataset in per-dataset scope, so there is no rarity to give."""

    a: str
    b: str
    score: float | None
    dataset: str | None = None
    shared: list[SharedAttribute] = Field(default_factory=list)
    #: Amendment 2, under `client_parity`: the pair's strength through the value linking them,
    #: the rarity plus the adds that apply to a shared value (the client's `dup_*` rows), on the
    #: client's scale and drawn on 0–1, and those adds. None under `standard`.
    parity_raw: float | None = None
    parity_strength: float | None = None
    parity_applied: list[AppliedInfluencer] = Field(default_factory=list)


class RarityRequest(BaseModel):
    """`POST /v1/investigations/{id}/rarity`: per dataset by default; `pairs` are the pairs to
    explain (each two ids of the working set)."""

    scope: RarityScope = "dataset"
    pairs: list[tuple[str, str]] = Field(default_factory=list, max_length=50_000)


class RarityResult(BaseModel):
    """`node_values`: each working-set entity's highest rarity with another working-set entity of
    its kind (absent when it shares nothing that scores); `pairs`: the pairs asked for."""

    scope: RarityScope
    node_values: dict[str, float]
    pairs: list[PairRarity]
    measure: RarityMeasure = "share"
    composition: StrengthComposition = "standard"


#: The rarity note the legend carries (decision 7), in the user guide's words.
RARITY_NOTE = (
    "Shared-attribute rarity is worked out over what you may see: two analysts with different "
    "access can see different rarity for the same pair."
)


ALL_MODELS = (
    InfluencerTrigger,
    DatasetTrigger,
    StrengthInfluencer,
    InfluencerSetInput,
    InfluencerSetVersion,
    InfluencerSetHistory,
    InfluencerDecision,
    CaseInfluencersInput,
    CaseInfluencers,
    InfluencerRefusal,
    ActiveInfluencer,
    StrengthLegend,
    AppliedInfluencer,
    LinkStrength,
    ConnectionStrengthRequest,
    ConnectionStrengths,
    SharedAttribute,
    PairRarity,
    RarityRequest,
    RarityResult,
)

CaseInfluencers.model_rebuild()
