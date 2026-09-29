"""Source profiler shapes — `09_INGEST_STUDIO.md` §3: "Source profiler: type inference,
null and cardinality
statistics, and pattern recognition against the Knowledge Adapters."

Headless in Phase 2: `services/ingest/profiler.py` produces a
`SourceProfile` from raw source rows. `09_INGEST_STUDIO.md` §3 defines
what "redacted" means, now that it is a real, implemented decision rather
than an undefined word: shape-masking, not hiding. Connect (stage 1) sets
the source's handling marking before Profile (stage 2) ever runs, so the
marking is available at profiling time — a principal cleared for it sees
sample values in full; anyone else sees each value's structure with its
content masked by character class (a letter as `A`, a digit as `#`,
`+44 7700 900461` as `+## #### ######`), capped in length, and replaced
with a character-class-and-length summary instead for a free-text
column. Values are never simply hidden: a profiler that shows nothing
cannot be checked, and an unchecked mapping is how a source silently
fragments the graph. The studio (Phase 5a) is the display surface over
this shape, not a second implementation of profiling or of the masking
decision.

TypeScript types are generated from these (`generate_ts.py`); a drift
between the two fails the build (`tools/schemas_check.py`).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class InferredType(StrEnum):
    """`date` and `datetime` are not split here — a profiler is advisory,
    not a normaliser, and a bare `2026-01-10` is just a datetime at
    midnight for this purpose. The real distinction (and the real
    rejection of an undated/ambiguous value) belongs to the `datetime`
    Knowledge Adapter at mapping time, not to the profiler's guess."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"


class PatternMatch(BaseModel):
    """One Knowledge Adapter tried against a column's non-null sample
    values. `match_rate` is the fraction that parsed without the adapter
    raising `NormalisationError`. Only adapters with a genuine reject
    condition are tried — `services/ingest/profiler.py`'s module
    docstring records which, and why `person_name`/`address` are excluded
    (both reject only an empty string, so they would "match" almost any
    text column and the signal would be worthless)."""

    adapter: str
    match_rate: float = Field(ge=0.0, le=1.0)


class ColumnProfile(BaseModel):
    name: str
    sample_size: int = Field(ge=0)
    null_count: int = Field(ge=0)
    distinct_count: int = Field(ge=0)
    inferred_type: InferredType
    #: The winning type's share of non-null sampled values — 0.0 when the
    #: column has no non-null values in the sample at all.
    type_confidence: float = Field(ge=0.0, le=1.0)
    #: Up to five distinct non-null values, in first-seen order —
    #: shape-masked when `SourceProfile.values_masked` is `True`, in full
    #: otherwise. One decision for the whole source (see there), not a
    #: per-column one.
    sample_values: list[str] = Field(default_factory=list)
    pattern_matches: list[PatternMatch] = Field(default_factory=list)


class AnomalyKind(StrEnum):
    """`09_INGEST_STUDIO.md` §3: "The profile also flags what will hurt
    later." `ENCODING_NOT_UTF8` is deliberately absent — detecting it
    needs the raw bytes a connector decoded, not the already-decoded rows
    this profiler receives; it belongs to the connector layer, not here
    (`services/ingest/profiler.py`'s module docstring records this as a
    stated gap, not a silent omission)."""

    RAGGED_ROW = "ragged_row"
    DUPLICATE_ROW = "duplicate_row"
    MIXED_DATETIME_FORMATS = "mixed_datetime_formats"
    UNDETERMINED_TIMEZONE = "undetermined_timezone"


class ProfileAnomaly(BaseModel):
    kind: AnomalyKind
    #: `None` for a whole-row anomaly (`RAGGED_ROW`, `DUPLICATE_ROW`);
    #: set for a per-column one.
    column: str | None = None
    count: int = Field(ge=0)
    sample: str


class SourceProfile(BaseModel):
    rows_sampled: int = Field(ge=0)
    #: `09_INGEST_STUDIO.md` §3: "reads a sample — 10,000 rows or the
    #: whole file, whichever is smaller." `False` means the sample cap
    #: was hit and the source has more rows than were profiled — never
    #: left implicit.
    sample_is_whole_source: bool
    #: Whether every sample value in `columns` and `anomalies` was
    #: shape-masked rather than shown in full — one decision for the
    #: whole source, from the single marking set on it at Connect, not a
    #: per-column one (`09_INGEST_STUDIO.md` §3).
    values_masked: bool
    columns: list[ColumnProfile]
    anomalies: list[ProfileAnomaly] = Field(default_factory=list)


ALL_MODELS: tuple[type[BaseModel], ...] = (
    PatternMatch,
    ColumnProfile,
    ProfileAnomaly,
    SourceProfile,
)
