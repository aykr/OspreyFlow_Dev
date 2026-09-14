"""`imsi` — `01_DOMAIN_MODEL.md` §7. With or without an MCC-MNC separator,
the canonical form is the bare 15-digit string."""

from __future__ import annotations

import re

from .errors import NormalisationError

_SEPARATORS = re.compile(r"[\s-]")


def imsi(raw: str) -> str:
    digits = _SEPARATORS.sub("", raw.strip())
    if not digits.isdigit():
        raise NormalisationError("imsi", raw, "contains non-digit characters")
    if len(digits) != 15:
        raise NormalisationError("imsi", raw, f"expected 15 digits, got {len(digits)}")
    return digits
