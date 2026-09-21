"""`services/resolve/duckdb_setup.py`'s `_soundex` — `07_BUILD_PLAN.md`'s Stage 6b carry-over 2,
closed here rather than re-scoped. `phonetics.soundex` indexes its digit table with
`ord(c) - ord('a')` and no bounds check, so anything outside `a`-`z` after the first character
raised `IndexError` before this fix — not only a hyphen, checked directly below for an apostrophe,
a space, a digit and an accented letter too, since a narrower fix that only handled hyphens would
have left `O'Brien` (as ordinary a UK surname as `Smith-Jones`) still crashing.
"""

from __future__ import annotations

from services.resolve.duckdb_setup import _soundex


def test_a_hyphenated_family_name_does_not_raise() -> None:
    """The exact reproduction Stage 6b's own carry-over 2 named: `Smith-Jones` is ordinary data,
    not an edge case, and the unmodified function raised `IndexError` on it."""
    assert _soundex("smith-jones") is not None
    assert _soundex("o-brien") is not None
    assert _soundex("d-artagnan") is not None
    assert _soundex("jean-luc") is not None


def test_an_apostrophised_family_name_does_not_raise() -> None:
    """`O'Brien`/`O'Neill` are at least as ordinary a UK surname shape as a hyphenated one — a fix
    scoped to hyphens alone would have left this crashing."""
    assert _soundex("o'brien") is not None
    assert _soundex("o'neill") is not None


def test_a_family_name_with_an_internal_space_does_not_raise() -> None:
    assert _soundex("van der berg") is not None


def test_a_family_name_with_digits_does_not_raise() -> None:
    """Implausible as an authored name but not implausible as bad OCR/ingest data reaching this
    function unchanged — the sanitiser must not assume its input was already validated upstream."""
    assert _soundex("smith2") is not None


def test_an_accented_family_name_does_not_raise_and_folds_to_its_base_letters() -> None:
    """Accents are folded (`unicodedata` NFKD), not merely stripped along with everything else —
    an umlauted and a plain-ASCII spelling of the same surname must still share a blocking key,
    or a same-surname pair one of them was transcribed without diacritics for would silently stop
    blocking together."""
    assert _soundex("müller") == _soundex("muller")
    assert _soundex("josé") == _soundex("jose")


def test_a_value_that_is_entirely_punctuation_or_digits_returns_none_not_an_error() -> None:
    """The same 'no blocking key' result `_soundex(None)`/`_soundex('')` already return for an
    empty input — not a new failure mode this fix introduces."""
    assert _soundex("123") is None
    assert _soundex("---") is None
    assert _soundex("") is None
    assert _soundex(None) is None


def test_hyphenated_and_plain_variants_of_the_same_surname_still_share_a_blocking_key() -> None:
    """Sanitisation must not just avoid crashing — it must still produce the blocking key a
    plain-ASCII variant of the same name would, or a hyphenated surname would silently stop
    matching its own unhyphenated spelling."""
    assert _soundex("smithjones") == _soundex("smith-jones")
