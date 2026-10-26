"""Reading a typed identifier — `06_DECISIONS.md` ADR-128 decision 1 (B2), "Reading each
identifier".

One place that turns what an analyst typed or pasted into a kind and a canonical value, so the list
add (`add_by_identifiers.py`) and the single search box (`search.py`) read an identifier the same
way, and each through the Knowledge Adapter its recipe uses (`knowledge_adapters.REGISTRY`), never a
second implementation of the same normalisation.

**Splitting.** A list is split at a line break or a comma, and then, within each piece, at a space.
A piece that reads whole as an identifier is kept whole first, so a number written with spaces
(`+44 7700 900640`, `QQ 12 34 56 A`) is not broken into fragments that match nothing. The cost is
named: a list separated by spaces alone cannot hold numbers written with spaces.

**Kinds, from the shape alone** (nothing here looks at the data, so the reading is the same for an
identifier that exists and one that does not):

- a prison number, `Z####ZZ`: a letter, four digits, two letters;
- a National Insurance number: two letters, six digits, a letter A to D (the PID's own use `QQ`, so
  the real prefix rules are not applied);
- an account reference: text with no space and at least one ASCII letter and one digit, which
  `account_ref` accepts (the letter and the digit are the shape: a bare word is not one, and a bare
  digit string that `msisdn` refuses is not one either);
- anything else `msisdn` accepts is a number;
- anything else is `unknown`, and matches nothing.

A number written with an extension (`01621926368x123`) has a letter and a digit and no space, so it
reads as an account reference; the order above is the ADR's. It matches no account and falls in
"matched nothing".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from knowledge_adapters import NormalisationError, account_ref, msisdn

Kind = Literal["prison_number", "nino", "account", "msisdn", "unknown"]

_PRISON = re.compile(r"[A-Z][0-9]{4}[A-Z]{2}")
_NINO = re.compile(r"[A-Z]{2}[0-9]{6}[A-D]")
_WHITESPACE = re.compile(r"\s+")
_PIECE = re.compile(r"[,\r\n]+")
_QUOTES = "\"'"


@dataclass(frozen=True)
class Reading:
    """One identifier read: its kind and its canonical value (the typed text, tidied, for
    `unknown`)."""

    kind: Kind
    canonical: str

    @property
    def key(self) -> tuple[str, str]:
        """What two spellings of one identifier share: they are one identifier, counted once."""
        return (self.kind, self.canonical.casefold() if self.kind == "unknown" else self.canonical)


def _tidy(text: str) -> str:
    return text.strip().strip(_QUOTES).strip()


def read_identifier(text: str) -> Reading:
    """The kind and canonical value of one typed identifier (see the module docstring)."""
    typed = _tidy(text)
    if not typed:
        return Reading("unknown", "")
    compact = _WHITESPACE.sub("", typed).upper()
    if _PRISON.fullmatch(compact):
        return Reading("prison_number", compact)
    if _NINO.fullmatch(compact):
        return Reading("nino", compact)
    has_letter = any(c.isascii() and c.isalpha() for c in typed)
    has_digit = any(c.isascii() and c.isdigit() for c in typed)
    if has_letter and has_digit and _WHITESPACE.search(typed) is None:
        try:
            return Reading("account", account_ref(typed))
        except NormalisationError:
            pass
    try:
        return Reading("msisdn", msisdn(typed))
    except NormalisationError:
        return Reading("unknown", typed)


def split_identifiers(texts: list[str]) -> list[str]:
    """The identifiers in what was typed or pasted: every string split at a line break or a comma,
    then each piece kept whole when it reads as one identifier and split at its spaces when not.
    Empty pieces are dropped; order is kept; nothing is de-duplicated (the count says what
    repeats)."""
    out: list[str] = []
    for text in texts:
        for raw in _PIECE.split(text):
            piece = _tidy(raw)
            if not piece:
                continue
            if _WHITESPACE.search(piece) is None or read_identifier(piece).kind != "unknown":
                out.append(piece)
                continue
            out.extend(part for part in (_tidy(p) for p in _WHITESPACE.split(piece)) if part)
    return out


def search_alternative(text: str) -> str | None:
    """What the single search box also asks for (ADR-128 decision 1): a phone number or an account
    reference written another way, in its canonical form. `None` when the text is not one, or is
    already canonical, so every other text is searched exactly as before. It depends on the typed
    text alone, never on what the graph holds."""
    reading = read_identifier(text)
    if reading.kind in ("msisdn", "account") and reading.canonical != _tidy(text):
        return reading.canonical
    return None
