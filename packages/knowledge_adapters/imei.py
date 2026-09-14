"""`imei` — `01_DOMAIN_MODEL.md` §7. 14/15/16-digit forms with `/` separators
collapse to the 14-digit TAC+serial, with the Luhn check digit (position 15)
and the software-version digit (position 16, IMEISV) both dropped — the
check digit's job is validation, not identity, and IMEISV varies with a
handset's firmware rather than the handset itself.
"""

from __future__ import annotations

import re

from .errors import NormalisationError

_SEPARATORS = re.compile(r"[/\s-]")


def _luhn_check_digit(body14: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(body14)):
        digit = int(ch)
        if i % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - total % 10) % 10)


def imei(raw: str) -> str:
    digits = _SEPARATORS.sub("", raw.strip())
    if not digits.isdigit():
        raise NormalisationError("imei", raw, "contains non-digit characters")
    if len(digits) not in (14, 15, 16):
        raise NormalisationError("imei", raw, f"expected 14, 15 or 16 digits, got {len(digits)}")

    body = digits[:14]
    # A 15-digit form is TAC(8)+serial(6)+check(1) — the one length that
    # carries a Luhn check digit at all. 16-digit IMEISV is
    # TAC(8)+serial(6)+SV(2): two arbitrary software-version digits, not a
    # check digit, so there is nothing to validate there.
    if len(digits) == 15:
        check_digit = digits[14]
        if _luhn_check_digit(body) != check_digit:
            raise NormalisationError("imei", raw, "check digit failed Luhn validation")
    return body
