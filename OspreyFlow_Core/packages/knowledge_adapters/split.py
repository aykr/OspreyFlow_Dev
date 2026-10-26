"""`split` — ADR-127 Amendment 15. A cell holding several values joined by a delimiter becomes a
list of text, for a property the ontology declares `string[]` (`Person.aliases`, which Brief 1's
prisoner file writes as names joined by `|`).

Unlike the other adapters it normalises no identifier: its output is a list, and a list is accepted
for a `string[]` property and for nothing else. Each part is trimmed; an empty part is dropped; the
source's order is kept; a part given twice is kept once, at its first place, since a list of names
says nothing by saying one twice (case is part of a name, so `Cal` and `cal` are two). An empty or
blank cell is an empty list. The delimiter is `|`; a recipe may name another with
`split(delimiter=;)`. A recipe's transform arguments are split on commas, so a comma cannot be the
delimiter here.
"""

from __future__ import annotations

from .errors import NormalisationError


def split(raw: str, *, delimiter: str = "|") -> list[str]:
    if delimiter == "":
        raise NormalisationError("split", raw, "the delimiter is empty")
    parts: list[str] = []
    for piece in raw.split(delimiter):
        part = piece.strip()
        if part and part not in parts:
            parts.append(part)
    return parts
