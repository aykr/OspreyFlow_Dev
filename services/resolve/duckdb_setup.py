"""DuckDB connection setup for Splink (`spec/06_DECISIONS.md` ADR-021) — registers the `soundex`
scalar UDF DuckDB itself lacks. Confirmed directly, not assumed: `SELECT soundex('MERCER')`
against a bare DuckDB connection raises `Catalog Error: Scalar Function with name soundex does not
exist!`. `phonetics` (MIT) is already a transitive dependency of `splink==3.9.9` itself, so this
adds no new dependency.

**`_soundex` sanitises its input — fixed, not merely disclosed.** `phonetics.soundex`
indexes a 27-character digit table with
`ord(c) - ord('a')` for every character after the first, with no bounds check: any character
outside `a`-`z` — a hyphen, an apostrophe, a space, a digit, an accented letter — makes that
either negative or too large and raises `IndexError: string index out of range`, not a graceful
skip. `Person.family_name` is exactly where this was reachable (`packages/ontology/default.yaml`'s
one `resolution:` block blocks on `soundex(family_name)`), and a hyphenated or apostrophised
surname is ordinary UK data, not an edge case — confirmed directly: `smith-jones`, `o-brien`,
`o'brien`, `van der berg` and `müller` all crashed the unmodified function, not only a hyphen.
"""

from __future__ import annotations

import re
import unicodedata

import duckdb
import duckdb.func
import phonetics

#: What survives sanitisation before `phonetics.soundex` ever sees it — everything else in the
#: alphabet the digit table actually indexes.
_NON_ALPHA = re.compile(r"[^a-z]")


def _soundex(value: str | None) -> str | None:
    """Accents are folded to their base letter (`unicodedata` NFKD decomposition, dropping the
    combining marks), not merely discarded along with everything else — `müller` blocks as
    `muller` would, not as `mller`, which a same-surname pair spelled with and without the umlaut
    would otherwise fail to share. Anything left that still isn't `a`-`z` (a hyphen, an apostrophe,
    a space, a digit) is stripped outright: `phonetics.soundex` has no notion of any of them, and
    `spec/01_DOMAIN_MODEL.md` already treats `soundex(family_name)` as an approximate blocking key,
    not an identity comparison — Splink's own comparison step, not this key, is what re-checks a
    pair blocked together. `None` if nothing letter-shaped survives (an empty value, or one that
    is entirely punctuation/digits) — the same "no blocking key" result `not value` already
    returns for an empty/`None` input, not a new failure mode this fix introduces."""
    if not value:
        return None
    folded = unicodedata.normalize("NFKD", value.lower())
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    letters = _NON_ALPHA.sub("", ascii_only)
    if not letters:
        return None
    return str(phonetics.soundex(letters))


def new_connection() -> duckdb.DuckDBPyConnection:
    """A fresh, private in-memory connection per resolution run — mirrors
    `adapters/analytics_duckdb/testing.py`'s own per-test-connection pattern. Never shared across
    calls: Splink mutates the connection it's given (temp tables, registered UDFs), so reuse
    across concurrent resolution runs would race.

    **`null_handling="special"` — the non-Latin-family-name crash's own fix, repaired at the point
    of input the same way the hyphen/apostrophe crash was.** `_soundex` above already returns
    `None` for a name that sanitises to nothing letter-shaped — an entirely non-Latin-script family
    name (Chinese, Cyrillic, Arabic, Devanagari, etc.) folds to nothing the same way an
    all-punctuation value does, and `_soundex`'s own docstring already names this as "the same
    'no blocking key' result... already returns," not a new failure mode. **Without this
    parameter, that already-correct return value crashed anyway** — DuckDB's own default UDF
    contract (`FunctionNullHandling.DEFAULT`) forbids a registered function from ever returning
    `NULL` for a non-`NULL` input, so `resolve_entity_type` raised `SplinkException` (wrapping
    DuckDB's own `Invalid Input Error: ... The UDF is not expected to return NULL values`) the
    moment even one person in the population being resolved had a family name that sanitised to
    nothing — taking down the whole population's resolution pass, not only that one person's own
    match candidacy. `null_handling="special"` tells DuckDB a `NULL` return is a legitimate value
    this function produces on purpose, letting the already-intended "no blocking key" behaviour
    actually reach the blocking SQL instead of crashing before it gets there: a person with no
    letter-shaped soundex key simply never blocks with anyone via this rule (standard SQL — `NULL`
    never equals `NULL`), the same outcome an empty `family_name` already produces today, without
    taking the rest of the population down with them."""
    con = duckdb.connect(":memory:")
    con.create_function(
        "soundex",
        _soundex,
        ["VARCHAR"],
        "VARCHAR",
        null_handling=duckdb.func.FunctionNullHandling.SPECIAL,
    )
    return con
