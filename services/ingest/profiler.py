"""The source profiler — `09_INGEST_STUDIO.md` §3, `07_BUILD_PLAN.md`
Phase 2: "Source profiler: type inference, null and cardinality
statistics, and pattern recognition against the Knowledge Adapters."

Headless: `profile_source` takes the same `Iterable[Mapping[str, str]]`
row shape every connector yields (`connectors/csv_connector.py`) and
returns a `SourceProfile` (`schemas/profile.py`). No studio here — that is
Phase 5a's job over this shape — but shape-masking (§3) is a real,
implemented decision, not a display concern deferred alongside it: Connect
(stage 1) sets the source's handling marking before Profile (stage 2)
ever runs, so `source_handling` is always available by the time
`profile_source` is called, and masking sample values is exactly as much
this function's job as computing them is.

**Pattern recognition is scoped to adapters with a genuine reject
condition, tried against a single column's values only.** `msisdn`,
`imei`, `imsi`, `email`, `iban`, `card`, `postcode` and `grid_ref`'s
bare-string form all reject a value that does not fit their shape (a
checksum, a valid parse, a recognised British National Grid letter pair),
so a high match rate is a real signal. `person_name` and `address` reject
only an empty string — nearly any non-empty text "matches" both — so
including them would make every text column report two meaningless 100%
matches; they are deliberately not tried here. `coordinate_lon`/
`coordinate_lat`/`geometry_ref` need a *pair* of columns and a declared
`source_crs`, and `grid_ref`'s three-column split form needs three,
none of which a single column's values can supply — cross-column pattern
detection is out of scope for this phase's profiler. ISO-datetime
recognition is handled separately below (`_iso_shape`), not through the
`datetime` Knowledge Adapter directly, because the adapter's own bare
call rejects a naive (offset-less) value outright — exactly the case this
profiler needs to see *and flag* (`AnomalyKind.UNDETERMINED_TIMEZONE`),
not have hidden behind a low match rate with no explanation.

**Shape-masking (`09_INGEST_STUDIO.md` §3).** `_shape_mask` is
class-based: every alphanumeric character becomes `#`; separators
(spaces, hyphens, the `+` in a phone number) are always shown literally,
since they carry the shape, not the content. No prefix is revealed —
`09_INGEST_STUDIO.md` §3 asks for "enough to confirm the profiler's
pattern match and to spot a malformed column, disclosing nothing", and
the pattern-match confirmation and malformed-column signal both come
from the preserved *shape* (length, separator positions), not from any
visible content. Deliberately independent of whether the value has any
separators at all — a rule keyed on "the first group before a space"
would leave an unseparated identifier like an MSISDN written with no
spacing (`01621926368`) entirely unmasked, which is exactly the value
most in need of masking.

**`ENCODING_NOT_UTF8` is not detected here.** It needs the raw bytes a
connector decoded, not the already-decoded string rows this function
receives — that check belongs at the connector layer. Not silently
covered; simply out of scope for a function whose input is already text.

**Ragged rows and `DUPLICATE_ROW`.** `csv.DictReader` (the CSV connector)
represents a short row with `None` values and a long row's extra fields
under a `None` key — both signal raggedness and are counted together.
`DUPLICATE_ROW` here means the whole row is verbatim-identical to an
earlier one; this is a purely mechanical check run before any recipe
exists, distinct from the recipe's own content-hash dedup
(`01_DOMAIN_MODEL.md` §7 rule 3), which canonicalises declared key fields
through their Knowledge Adapters first and only exists once a mapping
does.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from knowledge_adapters import REGISTRY
from knowledge_adapters.errors import NormalisationError
from ontology.handling import HandlingScheme, principal_may_view
from schemas.domain import Handling, Principal
from schemas.profile import (
    AnomalyKind,
    ColumnProfile,
    InferredType,
    PatternMatch,
    ProfileAnomaly,
    SourceProfile,
)

#: `09_INGEST_STUDIO.md` §3: "reads a sample — 10,000 rows or the whole
#: file, whichever is smaller."
DEFAULT_SAMPLE_SIZE = 10_000

#: A pattern match below this rate is noise, not a proposal — the studio
#: (Phase 5a) "proposes the whole thing" for a recognised shape and this
#: is the bar for what counts as recognised.
PATTERN_MATCH_THRESHOLD = 0.6

#: Only adapters with a genuine reject condition — see the module
#: docstring for why `person_name`/`address` are excluded and why
#: `datetime` is handled separately, not through `REGISTRY["datetime"]`.
_PATTERN_ADAPTER_NAMES = (
    "msisdn",
    "imei",
    "imsi",
    "email",
    "iban",
    "card",
    "postcode",
    "grid_ref",
)

_INTEGER_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?\d+\.\d+(?:[eE][+-]?\d+)?$|^[+-]?\d+[eE][+-]?\d+$")
_BOOLEAN_VALUES = frozenset({"true", "false"})

_ISO_OFFSET_RE = re.compile(r"(?:[+-]\d{2}:?\d{2}|Z)$")
_ISO_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _digits_have_spurious_leading_zero(digits: str) -> bool:
    """`01621926368` is an identifier (an MSISDN, here), not the integer
    `1621926368` with information silently discarded — leading zeros are
    only ever spurious padding on an actual quantity, never meaningful on
    an identifier, and this platform does not guess which a bare column
    is. Treated as `STRING` rather than `INTEGER`/`FLOAT` for that
    reason."""
    return len(digits) > 1 and digits[0] == "0"


def _is_integer(value: str) -> bool:
    if not _INTEGER_RE.fullmatch(value):
        return False
    return not _digits_have_spurious_leading_zero(value.lstrip("+-"))


def _is_float(value: str) -> bool:
    if not _FLOAT_RE.fullmatch(value):
        return False
    integer_part = re.split(r"[.eE]", value.lstrip("+-"), maxsplit=1)[0]
    return not _digits_have_spurious_leading_zero(integer_part)


def _is_boolean(value: str) -> bool:
    return value.strip().lower() in _BOOLEAN_VALUES


def _iso_shape(value: str) -> str | None:
    """`None` when `value` is not ISO-8601-shaped at all; otherwise a
    label for which shape, used both for type inference and for
    `MIXED_DATETIME_FORMATS`/`UNDETERMINED_TIMEZONE`."""
    stripped = value.strip()
    try:
        datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        return None
    if _ISO_DATE_ONLY_RE.fullmatch(stripped):
        return "date_only"
    if _ISO_OFFSET_RE.search(stripped):
        return "with_offset"
    return "naive"


def _shape_mask(value: str) -> str:
    """Masks every alphanumeric character of `value` as `#`; separators
    (spaces, hyphens, the `+` in a phone number) are always shown
    literally, since they carry the shape, not the content. Deliberately
    independent of whether `value` has any separators at all — a rule
    keyed on "the first group" would leave an unseparated identifier like
    an MSISDN written with no spacing (`01621926368`) entirely unmasked,
    which is exactly the value most in need of masking."""
    return "".join("#" if ch.isalnum() else ch for ch in value)


def _classify_value(value: str) -> InferredType:
    if _is_boolean(value):
        return InferredType.BOOLEAN
    if _is_integer(value):
        return InferredType.INTEGER
    if _is_float(value):
        return InferredType.FLOAT
    if _iso_shape(value) is not None:
        return InferredType.DATETIME
    return InferredType.STRING


def _pattern_matches(values: list[str]) -> list[PatternMatch]:
    matches: list[PatternMatch] = []
    for name in _PATTERN_ADAPTER_NAMES:
        adapter = REGISTRY[name]
        hits = 0
        for value in values:
            try:
                adapter(value)
            except NormalisationError:
                continue
            hits += 1
        rate = hits / len(values) if values else 0.0
        if rate >= PATTERN_MATCH_THRESHOLD:
            matches.append(PatternMatch(adapter=name, match_rate=rate))

    iso_hits = sum(1 for v in values if _iso_shape(v) is not None)
    iso_rate = iso_hits / len(values) if values else 0.0
    if iso_rate >= PATTERN_MATCH_THRESHOLD:
        matches.append(PatternMatch(adapter="datetime", match_rate=iso_rate))

    matches.sort(key=lambda m: m.match_rate, reverse=True)
    return matches


def _datetime_anomalies(column: str, values: list[str]) -> list[ProfileAnomaly]:
    shapes = [s for v in values if (s := _iso_shape(v)) is not None]
    if not shapes:
        return []

    anomalies: list[ProfileAnomaly] = []
    distinct_shapes = set(shapes)
    if len(distinct_shapes) > 1:
        counts = Counter(shapes)
        minority_shape, minority_count = counts.most_common()[-1]
        sample = next(v for v, s in zip(values, shapes, strict=False) if s == minority_shape)
        anomalies.append(
            ProfileAnomaly(
                kind=AnomalyKind.MIXED_DATETIME_FORMATS,
                column=column,
                count=minority_count,
                sample=sample,
            )
        )

    undetermined = [v for v, s in zip(values, shapes, strict=False) if s in ("naive", "date_only")]
    if undetermined:
        anomalies.append(
            ProfileAnomaly(
                kind=AnomalyKind.UNDETERMINED_TIMEZONE,
                column=column,
                count=len(undetermined),
                sample=undetermined[0],
            )
        )
    return anomalies


def _profile_column(name: str, raw_values: list[Any]) -> tuple[ColumnProfile, list[ProfileAnomaly]]:
    non_null = [v for v in raw_values if v not in (None, "")]
    null_count = len(raw_values) - len(non_null)
    distinct_count = len(set(non_null))

    type_counts = Counter(_classify_value(v) for v in non_null)
    if type_counts:
        inferred_type, matched = type_counts.most_common(1)[0]
        confidence = matched / len(non_null)
    else:
        inferred_type, confidence = InferredType.STRING, 0.0

    sample_values = list(dict.fromkeys(non_null))[:5]

    column = ColumnProfile(
        name=name,
        sample_size=len(raw_values),
        null_count=null_count,
        distinct_count=distinct_count,
        inferred_type=inferred_type,
        type_confidence=confidence,
        sample_values=sample_values,
        pattern_matches=_pattern_matches(non_null),
    )
    anomalies = (
        _datetime_anomalies(name, non_null) if inferred_type is InferredType.DATETIME else []
    )
    return column, anomalies


def _row_level_anomalies(rows: list[Mapping[Any, Any]]) -> list[ProfileAnomaly]:
    ragged_count = 0
    ragged_sample: str | None = None
    seen: set[tuple[tuple[Any, Any], ...]] = set()
    duplicate_count = 0
    duplicate_sample: str | None = None

    for row in rows:
        # `csv.DictReader`'s ragged-row markers: `None` as a value (a short
        # row) or as a key (a long row's overflow, per `restkey`).
        if None in row or any(v is None for v in row.values()):
            ragged_count += 1
            if ragged_sample is None:
                ragged_sample = repr(row)
            continue  # a ragged row can't be hashed meaningfully as a duplicate key

        key = tuple(sorted(row.items()))
        if key in seen:
            duplicate_count += 1
            if duplicate_sample is None:
                duplicate_sample = repr(row)
        else:
            seen.add(key)

    anomalies: list[ProfileAnomaly] = []
    if ragged_count:
        assert ragged_sample is not None
        anomalies.append(
            ProfileAnomaly(
                kind=AnomalyKind.RAGGED_ROW, column=None, count=ragged_count, sample=ragged_sample
            )
        )
    if duplicate_count:
        assert duplicate_sample is not None
        anomalies.append(
            ProfileAnomaly(
                kind=AnomalyKind.DUPLICATE_ROW,
                column=None,
                count=duplicate_count,
                sample=duplicate_sample,
            )
        )
    return anomalies


_SENTINEL = object()


def _mask_profile(profile: SourceProfile) -> SourceProfile:
    masked_columns = [
        column.model_copy(update={"sample_values": [_shape_mask(v) for v in column.sample_values]})
        for column in profile.columns
    ]
    masked_anomalies = [
        anomaly.model_copy(update={"sample": _shape_mask(anomaly.sample)})
        for anomaly in profile.anomalies
    ]
    return profile.model_copy(
        update={"values_masked": True, "columns": masked_columns, "anomalies": masked_anomalies}
    )


def profile_source(
    rows: Iterable[Mapping[Any, Any]],
    *,
    source_handling: Handling,
    principal: Principal,
    scheme: HandlingScheme,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> SourceProfile:
    iterator = iter(rows)
    sampled = list(itertools.islice(iterator, sample_size))
    sample_is_whole_source = next(iterator, _SENTINEL) is _SENTINEL

    columns = [k for k in sampled[0] if k is not None] if sampled else []
    column_profiles: list[ColumnProfile] = []
    anomalies: list[ProfileAnomaly] = []
    for name in columns:
        profile, column_anomalies = _profile_column(name, [row.get(name) for row in sampled])
        column_profiles.append(profile)
        anomalies.extend(column_anomalies)
    anomalies.extend(_row_level_anomalies(sampled))

    result = SourceProfile(
        rows_sampled=len(sampled),
        sample_is_whole_source=sample_is_whole_source,
        values_masked=False,
        columns=column_profiles,
        anomalies=anomalies,
    )
    if not principal_may_view(source_handling, principal, scheme):
        result = _mask_profile(result)
    return result
