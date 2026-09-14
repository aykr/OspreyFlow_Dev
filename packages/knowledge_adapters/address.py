"""`address` — `01_DOMAIN_MODEL.md` §7. Free text structures into lines and
a detected postcode; the gazetteer identifier (UPRN in the UK, a GNIS
feature id, TIGER GEOID or county parcel id in the US) is deliberately left
unattached here. Attaching one needs a live reference partition to match
against (`03_CONDUIT_MIDDLEWARE.md` §5's geospatial connectors), which
Phase 2 does not build — the field exists on `AddressResult` now so the
gazetteer match, when it lands, is a value assigned to an existing field,
not a schema change.

Unlike the other adapters, there is no reject case here beyond "empty
input": free text that fails to yield a postcode is still a structured
address, just one without that one field, which is different in kind from
a phone number that fails to parse at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import NormalisationError
from .postcode import UK_POSTCODE_RE


@dataclass(frozen=True)
class AddressResult:
    lines: list[str]
    postcode: str | None
    gazetteer_id: str | None = None


def address(raw: str) -> AddressResult:
    stripped = raw.strip()
    if not stripped:
        raise NormalisationError("address", raw, "empty address")

    match = UK_POSTCODE_RE.search(stripped)
    postcode = f"{match.group(1).upper()} {match.group(2).upper()}" if match else None
    lines = [line.strip() for line in re.split(r"[,\n]", stripped) if line.strip()]
    return AddressResult(lines=lines, postcode=postcode, gazetteer_id=None)
