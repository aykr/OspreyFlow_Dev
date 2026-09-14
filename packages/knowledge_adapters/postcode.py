"""`postcode` — `01_DOMAIN_MODEL.md` §7. A whole column that is already a
UK postcode (as opposed to `address`, which finds one embedded in free
text) gets its own adapter with its own reject condition: spacing and case
vary, but a value with no recognisable outward/inward structure is
rejected rather than passed through unchanged.

Royal Mail's published format: an outward code (one or two letters, one or
two digits, an optional trailing letter) and an inward code (one digit,
two letters).
"""

from __future__ import annotations

import re

from .errors import NormalisationError

#: Shared with `address.py`, which extracts a postcode from free text
#: rather than validating a whole column — same shape, same reject
#: condition, one definition.
UK_POSTCODE_RE = re.compile(r"\b([A-Za-z]{1,2}\d[A-Za-z\d]?)\s*(\d[A-Za-z]{2})\b")


def postcode(raw: str) -> str:
    stripped = raw.strip()
    match = UK_POSTCODE_RE.fullmatch(stripped)
    if match is None:
        raise NormalisationError("postcode", raw, "not a recognisable UK postcode")
    outward, inward = match.groups()
    return f"{outward.upper()} {inward.upper()}"
