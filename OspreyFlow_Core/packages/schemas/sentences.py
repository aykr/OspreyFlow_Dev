"""A rule written as a sentence with blanks (`06_DECISIONS.md` ADR-133 decision 1, stage (b)).

**A sentence, never an expression (rule 8).** Every blank is a closed choice: a type, a property
and a link type the deployment's ontology declares; an operator from a fixed list; a number; a
drawn area; a time window. There is nothing to parse, so a rule cannot fail to parse. Whether each
name is one the ontology declares is checked against it (`services/api/rule_sentences.py`'s
`check_sentence`), since an ontology is not something these models can see.

**It compiles to what exists:** a saved pattern (the subject, its equality conditions and an
optional link, as the query builder draws them; ADR-109 phase D) plus these typed parameters for
what a drawn pattern cannot say. The drawn pattern is the sentence's "advanced" view, and the two
are one rule (`services/api/rule_sentences.py`'s `compile_sentence` and `sentence_of`).

TypeScript is generated from these models (`generate_ts.py`); drift fails the build.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

#: The most conditions one sentence states on its subject.
SENTENCE_CONDITIONS_MAX = 5
#: The most values a "one of" condition lists.
ONE_OF_MAX = 20
#: The most corners a drawn area has.
AREA_POINTS_MAX = 64
#: How far back a preview reads (ADR-133 decision 3: "the last 90 days").
PREVIEW_DAYS = 90
#: The most examples a preview shows (decision 3: "showing up to five").
PREVIEW_EXAMPLES = 5


class AreaPoint(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


class DrawnArea(BaseModel):
    """A drawn area: a closed outline of three to sixty-four corners, in order, the last joined
    back to the first. `name` is what the sentence calls it ("the port area"), never matched on."""

    name: str = Field(default="the drawn area", min_length=1, max_length=80)
    points: list[AreaPoint] = Field(min_length=3, max_length=AREA_POINTS_MAX)


# --- conditions on the subject's declared properties --------------------------------------------


class EqualsCondition(BaseModel):
    op: Literal["equals"] = "equals"
    property: str = Field(min_length=1)
    #: The value as text: a word, a number written out, or `true`/`false` for a yes-or-no property.
    value: str = Field(min_length=1, max_length=200)


class OneOfCondition(BaseModel):
    op: Literal["one_of"] = "one_of"
    property: str = Field(min_length=1)
    values: list[str] = Field(min_length=2, max_length=ONE_OF_MAX)


class AboveCondition(BaseModel):
    op: Literal["above"] = "above"
    property: str = Field(min_length=1)
    value: float


class BelowCondition(BaseModel):
    op: Literal["below"] = "below"
    property: str = Field(min_length=1)
    value: float


class WithinAreaCondition(BaseModel):
    """The subject's own place inside a drawn area: a property that names a geometry (a
    `Location`'s `geometry_ref`)."""

    op: Literal["within_area"] = "within_area"
    property: str = Field(min_length=1)
    area: DrawnArea


class WithinTimeCondition(BaseModel):
    """A date or time property within a window; either end may be open, not both."""

    op: Literal["within_time"] = "within_time"
    property: str = Field(min_length=1)
    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode="after")
    def _a_window(self) -> WithinTimeCondition:
        if self.start is None and self.end is None:
            raise ValueError("a time window needs a start, an end, or both")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("the time window ends before it starts")
        return self


SentenceCondition = Annotated[
    EqualsCondition
    | OneOfCondition
    | AboveCondition
    | BelowCondition
    | WithinAreaCondition
    | WithinTimeCondition,
    Field(discriminator="op"),
]


# --- the optional relationship ------------------------------------------------------------------


class LinkedRelationship(BaseModel):
    """Linked by a declared link type to something (of a declared type, or of any)."""

    kind: Literal["linked"] = "linked"
    link_type: str = Field(min_length=1)
    other_type: str | None = None


class WithinStepsRelationship(BaseModel):
    """Within N steps of something of a declared type, by any links the author may see."""

    kind: Literal["within_steps"] = "within_steps"
    steps: int = Field(ge=1, le=4)
    other_type: str = Field(min_length=1)


class AtLocationRelationship(BaseModel):
    """Linked by a declared link type to a `Location` whose place is inside a drawn area."""

    kind: Literal["at_location"] = "at_location"
    link_type: str = Field(min_length=1)
    area: DrawnArea


class OnHotlistRelationship(BaseModel):
    """The subject's identifier is on one of the author's own active hotlists (ADR-038)."""

    kind: Literal["on_hotlist"] = "on_hotlist"


class OnScreeningListRelationship(BaseModel):
    """The subject's name screens against the deployment's screening lists (ADR-109 phase F's
    `screen`, reused): a person or an organisation only."""

    kind: Literal["on_screening_list"] = "on_screening_list"
    min_score: float = Field(default=0.9, ge=0.5, le=1)


SentenceRelationship = Annotated[
    LinkedRelationship
    | WithinStepsRelationship
    | AtLocationRelationship
    | OnHotlistRelationship
    | OnScreeningListRelationship,
    Field(discriminator="kind"),
]

#: The relationships read from the stored graph, so a rule holding one runs after commit.
GRAPH_RELATIONSHIPS = frozenset({"linked", "within_steps", "at_location"})


# --- the optional frequency ---------------------------------------------------------------------


class CountFrequency(BaseModel):
    """N or more events of a declared link type within D days."""

    kind: Literal["count"] = "count"
    link_type: str = Field(min_length=1)
    at_least: int = Field(ge=2, le=1000)
    within_days: int = Field(ge=1, le=366)


class AmountFrequency(BaseModel):
    """A total of a declared amount on a link type's events over X within D days."""

    kind: Literal["amount"] = "amount"
    link_type: str = Field(min_length=1)
    amount_property: str = Field(min_length=1)
    over: float = Field(gt=0)
    within_days: int = Field(ge=1, le=366)


class FirstTimeFrequency(BaseModel):
    """The subject's first event of a declared link type, ever (as the author may see them)."""

    kind: Literal["first_time"] = "first_time"
    link_type: str = Field(min_length=1)


SentenceFrequency = Annotated[
    CountFrequency | AmountFrequency | FirstTimeFrequency,
    Field(discriminator="kind"),
]

# --- the optional strength condition (ADR-139 decision 8) ---------------------------------------


class StrengthReaches(BaseModel):
    """"When the connection strength between the subject and something it is linked to (by a
    declared link type, or any; to a declared type, or anything) reaches X": the link's stored
    weight with the influencers in force, as the rule's author may see it (rule 3)."""

    kind: Literal["connection_strength"] = "connection_strength"
    link_type: str | None = None
    other_type: str | None = None
    reaches: float = Field(gt=0, le=1)


class RarityReaches(BaseModel):
    """"When the shared-attribute rarity between the subject and another of its type reaches X":
    worked out over what the rule's author may see, per dataset or across the case's datasets."""

    kind: Literal["shared_attribute_rarity"] = "shared_attribute_rarity"
    reaches: float = Field(gt=0, le=100)
    scope: Literal["dataset", "case"] = "dataset"


SentenceStrength = Annotated[StrengthReaches | RarityReaches, Field(discriminator="kind")]


SentenceSeverity = Literal["low", "medium", "high"]
#: Who the alert goes to: the case's queue, or labelled for the author's own team within it.
SentenceTeam = Literal["case", "my_team"]
#: As data loads (before or after commit), or on a schedule (ADR-133 decision 1, stage (d)).
SentenceRuns = Literal["pre_commit", "post_commit", "schedule"]
#: How often a scheduled rule runs (decision 1: "daily or weekly").
RuleCadence = Literal["daily", "weekly"]
#: The days a weekly rule may run on, Monday first, as the schedule says them.
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
#: Before commit, what a hit does: loads with its alert, or holds its rows for a reviewer.
SentenceOnHit = Literal["load", "hold"]
#: Just me (alerts for the author alone, as a monitor's), this case (the case team's queue, a
#: typology rule's), or the whole deployment (every case's loads; administrators only).
SentenceScope = Literal["just_me", "this_case", "deployment"]


class RuleSchedule(BaseModel):
    """When a scheduled rule runs (ADR-133 decision 1, stage (d)): every day, or every week on one
    day, at a whole hour, read in Europe/London. A scheduled run judges what was stored over the
    last day or the last week, as the rule's own author."""

    every: RuleCadence = "daily"
    hour: int = Field(default=6, ge=0, le=23)
    #: 1 (Monday) to 7 (Sunday); a weekly rule names one, a daily rule none.
    weekday: int | None = Field(default=None, ge=1, le=7)

    @model_validator(mode="after")
    def _a_day_for_a_week(self) -> RuleSchedule:
        if self.every == "weekly" and self.weekday is None:
            raise ValueError("a weekly schedule names the day of the week it runs on")
        if self.every == "daily" and self.weekday is not None:
            raise ValueError("a daily schedule runs every day, so it names no day of the week")
        return self


class RuleSentence(BaseModel):
    """The whole sentence: "When a <subject> [whose …] [linked by …] [N or more times in D days],
    raise a <severity> alert for <team>, <runs>; for <scope>." The checks here are the ones that
    need no ontology; `check_sentence` does the rest."""

    subject: str = Field(min_length=1)
    conditions: list[SentenceCondition] = Field(
        default_factory=list, max_length=SENTENCE_CONDITIONS_MAX
    )
    relationship: SentenceRelationship | None = None
    frequency: SentenceFrequency | None = None
    #: ADR-139 decision 8: "… and the connection strength (or shared-attribute rarity) between …
    #: reaches X".
    strength: SentenceStrength | None = None
    severity: SentenceSeverity = "medium"
    team: SentenceTeam = "case"
    runs: SentenceRuns = "post_commit"
    on_hit: SentenceOnHit = "load"
    scope: SentenceScope = "this_case"
    #: Stage (d): when a rule that runs on a schedule runs; none for one that runs as data loads.
    schedule: RuleSchedule | None = None

    @model_validator(mode="after")
    def _blanks_agree(self) -> RuleSentence:
        if self.runs == "schedule" and self.schedule is None:
            raise ValueError(
                "a rule that runs on a schedule needs one: every day or every week, at an hour"
            )
        if self.runs != "schedule" and self.schedule is not None:
            raise ValueError("only a rule that runs on a schedule takes a schedule")
        if self.runs == "schedule" and self.scope == "deployment":
            raise ValueError(
                "a rule for the whole deployment is judged within each case as its data loads; a "
                "schedule runs within one case, so a scheduled rule is for this case or for you"
            )
        if self.on_hit == "hold" and self.runs != "pre_commit":
            raise ValueError("only a rule that runs before commit can hold its rows")
        if (
            self.runs == "pre_commit"
            and self.relationship is not None
            and self.relationship.kind in GRAPH_RELATIONSHIPS
        ):
            raise ValueError(
                "a link is read from the stored graph, so a rule that names one runs after commit"
            )
        if self.strength is not None and self.runs == "pre_commit":
            raise ValueError(
                "strength and rarity are read from the stored graph, so a rule that names one "
                "runs after commit or on a schedule"
            )
        if self.scope == "just_me":
            if self.team != "case":
                raise ValueError("a rule just for you raises its alerts for you alone")
            if self.runs == "pre_commit":
                raise ValueError(
                    "a rule just for you runs after each load commits or on a schedule; "
                    "it cannot judge or hold a case's rows"
                )
        properties = [c.property for c in self.conditions]
        if len(properties) != len(set(properties)):
            raise ValueError("each property takes one condition in a sentence")
        return self


class SentenceRuleParams(BaseModel):
    """ADR-133 decision 1: the typology a sentence deploys as. `pattern_id` is its drawn pattern
    (the subject, its equality conditions and a link: what the query builder draws), saved as the
    author's and read afresh as them at each evaluation (ADR-036's discipline, as ADR-109 phase D's
    `pattern` rule); `sentence` is the whole rule as written, and the source of what a pattern
    cannot say. A run that would judge more than `max_matches` subjects is refused in words, never
    judged in part (rule 2)."""

    typology: Literal["sentence"] = "sentence"
    pattern_id: str = Field(min_length=1)
    sentence: RuleSentence
    max_matches: int = Field(default=200, ge=1, le=1000)


class SentenceRuleInput(BaseModel):
    """What an author deploys from the sentence builder: a name and the sentence. The Conduit
    checks it against the ontology, saves its drawn pattern as the author's and deploys the rule."""

    name: str = Field(min_length=1, max_length=120)
    sentence: RuleSentence
    budget_ms: int = Field(default=5000, ge=100, le=60000)
    max_matches: int = Field(default=200, ge=1, le=1000)


class SentenceRefusal(BaseModel):
    """A sentence refused at validation, by the blank it is about, in words (never a bare 400)."""

    error: Literal["sentence_refused"] = "sentence_refused"
    blank: str
    reason: str
    detail: str


class PreviewExample(BaseModel):
    """One alert the rule would have raised: the subject as the author reads it, and the finding."""

    node_id: str
    name: str
    entity_type: str
    words: str


class RulePreview(BaseModel):
    """ADR-133 decision 3: what the rule would have raised over the last `days` days, run as its
    author over stored data, raising and writing nothing. `would_raise` and `examples` are counted
    only over what the author may see (rules 3 and 7). Over the working-set limit the preview is
    refused with `limit_exceeded` instead, never counted in part (rule 2)."""

    days: int = PREVIEW_DAYS
    would_raise: int = Field(ge=0)
    examples: list[PreviewExample] = Field(default_factory=list, max_length=PREVIEW_EXAMPLES)
    #: The rule's sentence in words, as previewed.
    words: str


class RulePreviewRequest(BaseModel):
    sentence: RuleSentence


ALL_MODELS = (
    AreaPoint,
    DrawnArea,
    EqualsCondition,
    OneOfCondition,
    AboveCondition,
    BelowCondition,
    WithinAreaCondition,
    WithinTimeCondition,
    LinkedRelationship,
    WithinStepsRelationship,
    AtLocationRelationship,
    OnHotlistRelationship,
    OnScreeningListRelationship,
    CountFrequency,
    AmountFrequency,
    FirstTimeFrequency,
    StrengthReaches,
    RarityReaches,
    RuleSchedule,
    RuleSentence,
    SentenceRuleParams,
    SentenceRuleInput,
    SentenceRefusal,
    PreviewExample,
    RulePreview,
    RulePreviewRequest,
)
