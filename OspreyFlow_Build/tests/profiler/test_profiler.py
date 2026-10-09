"""`services/ingest/profiler.py` — `09_INGEST_STUDIO.md` §3's "type inference, null and cardinality
statistics, and pattern recognition against the Knowledge Adapters" —
including shape-masking, §3's redaction rule.

Pure and headless, no live service needed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.ingest.profiler import profile_source

from ontology.handling import HandlingScheme, load_uk_le_scheme
from schemas.domain import Handling, Principal
from schemas.profile import AnomalyKind, InferredType, SourceProfile

_SCHEME: HandlingScheme = load_uk_le_scheme()
_SOURCE_HANDLING = Handling(
    classification="OFFICIAL-SENSITIVE",
    handling_code="P",
    originator="unit-1",
    owning_unit="unit-1",
)
_CLEARED = Principal(id="analyst-1", clearance="OFFICIAL-SENSITIVE", org_unit="unit-1")
#: Below the source's OFFICIAL-SENSITIVE marking — insufficiently cleared.
_UNCLEARED = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1")


def _rows(*dicts: dict[str, str]) -> list[dict[str, str]]:
    return list(dicts)


def _profile(
    rows: list[Mapping[Any, Any]] | list[dict[str, str]],
    *,
    principal: Principal = _CLEARED,
    source_handling: Handling = _SOURCE_HANDLING,
    sample_size: int | None = None,
) -> SourceProfile:
    kwargs: dict[str, Any] = {}
    if sample_size is not None:
        kwargs["sample_size"] = sample_size
    return profile_source(
        rows, source_handling=source_handling, principal=principal, scheme=_SCHEME, **kwargs
    )


def test_integer_column_is_inferred_with_full_confidence() -> None:
    rows = _rows(*({"duration": str(n)} for n in (10, 42, 300, 7)))
    profile = _profile(rows)
    (col,) = profile.columns
    assert col.inferred_type is InferredType.INTEGER
    assert col.type_confidence == 1.0


def test_a_value_with_a_leading_zero_is_never_inferred_numeric() -> None:
    """`01621926368` is an identifier, not the integer `1621926368` with a
    digit silently discarded — this platform never guesses which a bare
    column is (`services/ingest/profiler.py` module docstring)."""
    rows = _rows({"a_party": "01621926368"}, {"a_party": "07911123456"})
    profile = _profile(rows)
    (col,) = profile.columns
    assert col.inferred_type is InferredType.STRING


def test_float_column_is_inferred_correctly() -> None:
    rows = _rows({"x": "1.5"}, {"x": "2.75"}, {"x": "0.5"})
    profile = _profile(rows)
    (col,) = profile.columns
    assert col.inferred_type is InferredType.FLOAT
    assert col.type_confidence == 1.0


def test_boolean_column_is_inferred_correctly() -> None:
    rows = _rows({"flag": "true"}, {"flag": "False"}, {"flag": "TRUE"})
    profile = _profile(rows)
    (col,) = profile.columns
    assert col.inferred_type is InferredType.BOOLEAN


def test_iso_datetime_column_is_inferred_correctly() -> None:
    rows = _rows(
        {"start_time": "2026-01-10T10:00:00Z"},
        {"start_time": "2026-01-11T10:00:00+00:00"},
    )
    profile = _profile(rows)
    (col,) = profile.columns
    assert col.inferred_type is InferredType.DATETIME
    assert col.type_confidence == 1.0


def test_mixed_column_reports_the_majority_type_and_a_partial_confidence() -> None:
    rows = _rows({"v": "1"}, {"v": "2"}, {"v": "not a number"})
    profile = _profile(rows)
    (col,) = profile.columns
    assert col.inferred_type is InferredType.INTEGER
    assert col.type_confidence == 2 / 3


def test_null_and_distinct_counts_are_correct() -> None:
    rows = _rows({"v": "a"}, {"v": ""}, {"v": "a"}, {"v": "b"})
    profile = _profile(rows)
    (col,) = profile.columns
    assert col.null_count == 1
    assert col.distinct_count == 2
    assert col.sample_size == 4


def test_sample_values_are_first_five_distinct_in_order() -> None:
    rows = _rows(*({"v": letter} for letter in ["a", "b", "a", "c", "d", "e", "f"]))
    profile = _profile(rows)
    (col,) = profile.columns
    assert col.sample_values == ["a", "b", "c", "d", "e"]


def test_msisdn_column_is_pattern_recognised() -> None:
    rows = _rows(
        {"a_party": "01621926368"},
        {"a_party": "+447911123456"},
        {"a_party": "441621926368"},
    )
    profile = _profile(rows)
    (col,) = profile.columns
    assert {m.adapter for m in col.pattern_matches} >= {"msisdn"}
    match = next(m for m in col.pattern_matches if m.adapter == "msisdn")
    assert match.match_rate == 1.0


def test_email_column_is_pattern_recognised() -> None:
    rows = _rows({"contact": "Person@Example.com"}, {"contact": "other@test.org"})
    profile = _profile(rows)
    (col,) = profile.columns
    assert any(m.adapter == "email" for m in col.pattern_matches)


def test_person_name_and_address_are_never_reported_as_pattern_matches() -> None:
    """Both adapters reject only an empty string, so any non-empty text
    column would "match" them almost regardless of content — a signal
    with no discriminating power, deliberately excluded
    (`services/ingest/profiler.py` module docstring)."""
    rows = _rows({"note": "SMITH, John"}, {"note": "just some free text"})
    profile = _profile(rows)
    (col,) = profile.columns
    assert {m.adapter for m in col.pattern_matches}.isdisjoint({"person_name", "address"})


#: 23 IMEIs whose 15th digit passes the Luhn check, plus two whose check digit is
#: wrong — the 92% match rate seen live on 9 October 2026, where `imsi 100%` was
#: ranked above `imei 92%` because any 15 digits pass the IMSI adapter.
_IMEI_COLUMN = [
    "355260181590838", "350166131860913", "353909960308240", "356281948219932",
    "355181909378654", "357975432319483", "357574911862525", "357601895559791",
    "357114710497460", "355075291703422", "353667127684263", "358465632122332",
    "350792440268595", "359528907866666", "351760313721593", "350109281590138",
    "359624595711775", "357741215472802", "353852808414855", "352538885393366",
    "353387500474394", "355755131373532", "357990751163727",
    "356516761222021", "359729975288202",  # the two with a failing check digit
]  # fmt: skip

#: 15-digit strings that fail both Luhn forms (IMEI's position-15 check and the
#: card adapter's whole-string check) — only the shape-only IMSI adapter matches.
_IMSI_COLUMN = [
    "234018263304348", "234395486205798", "234718033401878", "234878384837261",
    "234675136134125", "234242731672326", "234865635515058", "234770658948113",
    "234114402426462", "234889751402614", "234014193141705", "234864920831240",
    "234234483478245", "234040008838737", "234167868433532", "234650201462016",
    "234849340722470", "234455853043520", "234561748338014", "234829657249208",
    "234682889093100", "234251678008374", "234333776174093", "234192544992070",
    "234741374847771",
]  # fmt: skip


def test_a_checksum_backed_match_outranks_a_shape_only_match() -> None:
    """An IMEI column: `imsi` matches 100% of it (any 15 digits do), `imei`
    92% — but the IMEI match is backed by a Luhn check and the IMSI match by
    nothing beyond length, so `imei` must rank first. Found live, 9 October
    2026 (`07_BUILD_PLAN.md`'s row at 58e9cdf)."""
    rows = _rows(*({"handset": v} for v in _IMEI_COLUMN))
    profile = _profile(rows)
    (col,) = profile.columns
    adapters = [m.adapter for m in col.pattern_matches]
    assert "imei" in adapters and "imsi" in adapters
    assert adapters[0] == "imei"
    assert adapters.index("imei") < adapters.index("imsi")
    imei_match = next(m for m in col.pattern_matches if m.adapter == "imei")
    assert imei_match.match_rate == 0.92  # the displayed rate is never adjusted


def test_an_imsi_column_still_reports_imsi_first() -> None:
    rows = _rows(*({"subscriber": v} for v in _IMSI_COLUMN))
    profile = _profile(rows)
    (col,) = profile.columns
    adapters = [m.adapter for m in col.pattern_matches]
    assert adapters[0] == "imsi"


def test_a_column_below_the_match_threshold_is_not_reported() -> None:
    rows = _rows(
        {"mixed": "01621926368"},
        {"mixed": "not a phone number"},
        {"mixed": "also not one"},
    )
    profile = _profile(rows)
    (col,) = profile.columns
    assert col.pattern_matches == []


def test_ragged_rows_are_counted_as_an_anomaly() -> None:
    """`csv.DictReader` represents a short row with a `None` value."""
    rows = _rows({"a": "1", "b": "2"}, {"a": "3", "b": None})
    profile = _profile(rows)
    anomaly = next(a for a in profile.anomalies if a.kind is AnomalyKind.RAGGED_ROW)
    assert anomaly.count == 1
    assert anomaly.column is None


def test_verbatim_duplicate_rows_are_counted_as_an_anomaly() -> None:
    rows = _rows({"a": "1", "b": "2"}, {"a": "1", "b": "2"}, {"a": "1", "b": "3"})
    profile = _profile(rows)
    anomaly = next(a for a in profile.anomalies if a.kind is AnomalyKind.DUPLICATE_ROW)
    assert anomaly.count == 1


def test_mixed_datetime_formats_in_one_column_is_an_anomaly() -> None:
    rows = _rows(
        {"start_time": "2026-01-10T10:00:00Z"},
        {"start_time": "2026-01-11T10:00:00Z"},
        {"start_time": "2026-01-12"},  # date-only — a different shape
    )
    profile = _profile(rows)
    anomaly = next(a for a in profile.anomalies if a.kind is AnomalyKind.MIXED_DATETIME_FORMATS)
    assert anomaly.column == "start_time"
    assert anomaly.count == 1


def test_undetermined_timezone_in_a_datetime_column_is_an_anomaly() -> None:
    rows = _rows(
        {"start_time": "2026-01-10 10:00:00"},  # naive, no offset
        {"start_time": "2026-01-11 11:00:00"},
    )
    profile = _profile(rows)
    anomaly = next(a for a in profile.anomalies if a.kind is AnomalyKind.UNDETERMINED_TIMEZONE)
    assert anomaly.column == "start_time"
    assert anomaly.count == 2


def test_a_clean_iso_offset_column_has_no_datetime_anomalies() -> None:
    rows = _rows(
        {"start_time": "2026-01-10T10:00:00Z"},
        {"start_time": "2026-01-11T11:00:00+00:00"},
    )
    profile = _profile(rows)
    kinds = {a.kind for a in profile.anomalies}
    assert AnomalyKind.MIXED_DATETIME_FORMATS not in kinds
    assert AnomalyKind.UNDETERMINED_TIMEZONE not in kinds


def test_sample_is_whole_source_is_true_when_every_row_was_read() -> None:
    rows = _rows({"a": "1"}, {"a": "2"})
    profile = _profile(rows, sample_size=10)
    assert profile.sample_is_whole_source is True
    assert profile.rows_sampled == 2


def test_sample_is_whole_source_is_false_when_the_cap_is_hit() -> None:
    rows = _rows(*({"a": str(i)} for i in range(5)))
    profile = _profile(rows, sample_size=3)
    assert profile.sample_is_whole_source is False
    assert profile.rows_sampled == 3


def test_an_empty_source_produces_no_columns_and_no_crash() -> None:
    profile = _profile([])
    assert profile.columns == []
    assert profile.rows_sampled == 0
    assert profile.sample_is_whole_source is True


# --- Shape-masking (09_INGEST_STUDIO.md §3) -------------------------------


def test_a_principal_cleared_for_the_sources_marking_sees_values_in_full() -> None:
    rows = _rows({"a_party": "01621926368"}, {"a_party": "07911123456"})
    profile = _profile(rows, principal=_CLEARED)
    assert profile.values_masked is False
    (col,) = profile.columns
    assert col.sample_values == ["01621926368", "07911123456"]


def test_an_uncleared_principal_sees_shape_masked_values_not_the_originals() -> None:
    rows = _rows({"a_party": "01621926368"})
    profile = _profile(rows, principal=_UNCLEARED)
    assert profile.values_masked is True
    (col,) = profile.columns
    assert col.sample_values != ["01621926368"]
    # Structure preserved (same length, still digits-shaped), content
    # replaced — not simply hidden.
    assert len(col.sample_values[0]) == len("01621926368")


def test_shape_masking_never_produces_an_empty_value() -> None:
    """"Never blank the values: a profiler that shows nothing cannot be
    checked" (`09_INGEST_STUDIO.md` §3) — masking a value must never
    reduce it to nothing, only obscure its content."""
    rows = _rows({"a_party": "01621926368"})
    profile = _profile(rows, principal=_UNCLEARED)
    (col,) = profile.columns
    assert col.sample_values[0] != ""
    assert len(col.sample_values[0]) > 0


def test_shape_masking_preserves_separators_literally() -> None:
    rows = _rows({"phone": "+44 7700 900123"})
    profile = _profile(rows, principal=_UNCLEARED)
    (col,) = profile.columns
    masked = col.sample_values[0]
    assert masked.count(" ") == 2
    assert masked.startswith("+")


def test_shape_masking_also_applies_to_anomaly_samples() -> None:
    rows = _rows({"start_time": "2026-01-10 10:00:00"})
    profile = _profile(rows, principal=_UNCLEARED)
    anomaly = next(a for a in profile.anomalies if a.kind is AnomalyKind.UNDETERMINED_TIMEZONE)
    assert anomaly.sample == "####-##-## ##:##:##"


def test_shape_masking_golden_cases() -> None:
    """Exact golden values for `09_INGEST_STUDIO.md` §3's class-based
    masking rule: a letter becomes `A`, a digit becomes `#`, everything
    else is shown literally, length is always preserved (below the cap
    — see `test_shape_masking_caps_long_values`)."""
    cases = {
        "+44 7700 900461": "+## #### ######",
        # An unseparated MSISDN — the case the rule exists to catch: no
        # space or hyphen to key a "first group" rule off of.
        "07700900461": "###########",
        # A person name: no digits, no separators, still fully masked.
        "WILSON": "AAAAAA",
        # Non-ASCII letters must mask too — this is Unicode-aware, not
        # ASCII-only (`09_INGEST_STUDIO.md` §3).
        "أحمد": "AAAA",
        # A mixed letter-digit reference: the whole point of class-based
        # masking is that this does NOT collapse to a uniform symbol —
        # the letter/digit pattern stays visible in the mask itself.
        "A2435AB": "A####AA",
        # An email address: `.` and `@` are separators, not content.
        "john.smith@example.com": "AAAA.AAAAA@AAAAAAA.AAA",
    }
    for value, expected in cases.items():
        rows = _rows({"v": value})
        profile = _profile(rows, principal=_UNCLEARED)
        (col,) = profile.columns
        assert col.sample_values[0] == expected, f"{value!r} -> {col.sample_values[0]!r}"


def test_shape_masking_caps_long_values_and_appends_the_true_length() -> None:
    """`09_INGEST_STUDIO.md` §3: an uncapped positional mask over a long
    value discloses its exact length almost as plainly as showing it.
    Unit-level against `_shape_mask` directly — a `STRING` column with a
    value this long and no pattern match is classified free text by
    `profile_source` (see `test_free_text_column_gets_a_summary_not_a_positional_mask`),
    so the capped-but-still-positional case is exercised here instead."""
    from services.ingest.profiler import _shape_mask

    value = "A" * 40
    assert _shape_mask(value) == "A" * 32 + "…(40)"


def test_free_text_column_gets_a_summary_not_a_positional_mask() -> None:
    """A `STRING` column with no pattern match and a value over the cap
    is free text — masking it positionally would disclose word lengths
    and punctuation in order, which for short prose is close to reading
    it, so it gets a character-class-and-length summary instead
    (`09_INGEST_STUDIO.md` §3)."""
    long_value = "Officer noted the vehicle left the scene heading north."
    assert len(long_value) > 32
    rows = _rows({"notes": long_value})
    profile = _profile(rows, principal=_UNCLEARED)
    (col,) = profile.columns
    assert len(col.sample_values) == 1
    summary = col.sample_values[0]
    assert summary != long_value
    assert "…" not in summary  # not a positional mask at all
    assert "free text" in summary
    assert str(len(long_value)) in summary


def test_masking_is_one_decision_for_the_whole_source_not_per_column() -> None:
    """`09_INGEST_STUDIO.md` §3: "the only marking available is the one
    set on the source at Connect" — a single source-level marking, so
    masking is the same answer for every column."""
    rows = _rows({"a": "01621926368", "b": "some free text value"})
    profile = _profile(rows, principal=_UNCLEARED)
    assert profile.values_masked is True
    a_col = next(c for c in profile.columns if c.name == "a")
    b_col = next(c for c in profile.columns if c.name == "b")
    assert a_col.sample_values[0] != "01621926368"
    assert b_col.sample_values[0] != "some free text value"
