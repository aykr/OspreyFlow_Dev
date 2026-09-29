"""`person_name` — `01_DOMAIN_MODEL.md` §7. Ordering, honorifics and
ALL-CAPS surnames are all about which token is the family name, not about
the characters themselves — diacritics are never stripped or
transliterated here, since doing so would discard information a `person`
normaliser has no business guessing back later.

Splitting given/family is inherently a heuristic for free text with no
declared structure. Two conventions are recognised: `SURNAME, Given` (the
records-management convention `09_INGEST_STUDIO.md` §3 calls out) and
`Given ALL-CAPS-SURNAME` (the CoLP review-queue convention —
`09_INGEST_STUDIO.md` §7's "Owen WILSON" — an ALL-CAPS token, if there is
exactly one, is taken as the family name regardless of its position).
Anything else falls back to last-token-is-family, the ordinary Western
convention. A single-token name is treated as a mononym: family name only,
no given name — the more common real-world case for a bare single token in
this kind of data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import NormalisationError

_HONORIFICS = {
    "mr",
    "mrs",
    "ms",
    "mx",
    "miss",
    "dr",
    "prof",
    "sir",
    "dame",
}


@dataclass(frozen=True)
class PersonNameResult:
    given: str
    family: str


def _strip_honorific(tokens: list[str]) -> list[str]:
    if tokens and tokens[0].rstrip(".").lower() in _HONORIFICS:
        return tokens[1:]
    return tokens


def person_name(raw: str) -> PersonNameResult:
    stripped = raw.strip()
    if not stripped:
        raise NormalisationError("person_name", raw, "empty name")

    if "," in stripped:
        family_part, _, given_part = stripped.partition(",")
        family = family_part.strip()
        given = given_part.strip()
        if not family:
            raise NormalisationError("person_name", raw, "empty family name before ','")
        return PersonNameResult(given=given, family=family)

    tokens = _strip_honorific(re.split(r"\s+", stripped))
    if not tokens:
        raise NormalisationError("person_name", raw, "name is only an honorific")
    if len(tokens) == 1:
        return PersonNameResult(given="", family=tokens[0])

    all_caps = [t for t in tokens if t.isalpha() and t.isupper()]
    if len(all_caps) == 1:
        surname = all_caps[0]
        given = " ".join(t for t in tokens if t != surname)
        return PersonNameResult(given=given, family=surname)

    return PersonNameResult(given=" ".join(tokens[:-1]), family=tokens[-1])
