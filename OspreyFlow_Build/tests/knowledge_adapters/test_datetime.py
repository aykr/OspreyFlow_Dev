"""Golden test — `datetime` (`01_DOMAIN_MODEL.md` §7).

`08_ACCEPTANCE_SCENARIOS.md` B3: "the local-time file is converted with its
original offset recorded; a file with no recoverable offset is rejected
with a named error, not guessed." §7 extends the same rejection shape to
an ambiguous date order.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from knowledge_adapters.datetime_adapter import datetime_adapter
from knowledge_adapters.errors import NormalisationError


def test_iso_with_z_suffix_converts_to_utc_with_zero_offset() -> None:
    result = datetime_adapter("2014-03-11T19:42:01Z")
    assert result.utc == datetime(2014, 3, 11, 19, 42, 1, tzinfo=UTC)
    assert result.original_offset == "+00:00"


def test_iso_with_explicit_offset_converts_and_records_that_offset() -> None:
    result = datetime_adapter("2014-03-11 19:42:01+01:00")
    assert result.utc == datetime(2014, 3, 11, 18, 42, 1, tzinfo=UTC)
    assert result.original_offset == "+01:00"


def test_iso_needs_no_date_order_even_when_none_is_configured() -> None:
    # Year-month-day is unambiguous by construction — no date_order needed.
    result = datetime_adapter("2014-03-11T19:42:01Z", date_order=None)
    assert result.utc == datetime(2014, 3, 11, 19, 42, 1, tzinfo=UTC)


def test_naive_local_time_with_a_configured_zone_records_the_zones_own_offset() -> None:
    # 11 March 2014 is before the UK's spring clock change — GMT, +00:00.
    result = datetime_adapter("2014-03-11 19:42:01", tz="Europe/London")
    assert result.utc == datetime(2014, 3, 11, 19, 42, 1, tzinfo=UTC)
    assert result.original_offset == "+00:00"


def test_naive_local_time_across_the_dst_boundary_records_the_summer_offset() -> None:
    # 11 July 2014 is during British Summer Time — +01:00, not +00:00.
    result = datetime_adapter("2014-07-11 19:42:01", tz="Europe/London")
    assert result.utc == datetime(2014, 7, 11, 18, 42, 1, tzinfo=UTC)
    assert result.original_offset == "+01:00"


def test_dmy_date_order_is_applied_as_configured() -> None:
    result = datetime_adapter("11/03/2014 19:42:01", tz="Europe/London", date_order="dmy")
    assert result.utc == datetime(2014, 3, 11, 19, 42, 1, tzinfo=UTC)


def test_mdy_date_order_is_applied_as_configured() -> None:
    result = datetime_adapter("03/11/2014 19:42:01", tz="Europe/London", date_order="mdy")
    assert result.utc == datetime(2014, 3, 11, 19, 42, 1, tzinfo=UTC)


def test_ambiguous_date_order_with_no_declaration_is_rejected_not_guessed() -> None:
    """There is no default — §7's own example: `03/04/2026` is April in
    the UK and March in the US, and guessing between them is exactly what
    this adapter must never do."""
    with pytest.raises(NormalisationError, match="ambiguous date order"):
        datetime_adapter("03/04/2026 10:00:00", tz="Europe/London")


def test_naive_local_time_with_no_configured_zone_is_rejected_not_guessed() -> None:
    with pytest.raises(NormalisationError):
        datetime_adapter("2014-03-11 19:42:01")


def test_unrecognisable_format_is_rejected() -> None:
    with pytest.raises(NormalisationError):
        datetime_adapter("not a date at all", tz="Europe/London", date_order="dmy")
