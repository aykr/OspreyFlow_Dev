"""`iban` / `card` — `01_DOMAIN_MODEL.md` §7.

`iban`: spacing collapses; the mod-97 checksum (ISO 7064) is validated, not
just the shape, so a mistyped IBAN is rejected rather than stored wrong.

`card`: spacing collapses and the number is Luhn-validated, but the
canonical value is never the full PAN — `last_four` plus a SHA-256 `hash`
of the full number, so two records referencing the same card can be linked
without the platform ever holding the number itself. A source that already
masks the middle digits (`4111********1111`) cannot be Luhn-checked or
hashed meaningfully — for that case `hash` is `None` rather than a hash of
an incomplete number standing in for the real one, and `last_four` is
still extracted, since that much is present verbatim in the source.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .errors import NormalisationError

_MASK_CHARS = frozenset("Xx*•")


def iban(raw: str) -> str:
    cleaned = re.sub(r"\s", "", raw.strip()).upper()
    if not re.fullmatch(r"[A-Z0-9]{15,34}", cleaned):
        raise NormalisationError("iban", raw, "not a plausible IBAN length or character set")
    rearranged = cleaned[4:] + cleaned[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    if int(numeric) % 97 != 1:
        raise NormalisationError("iban", raw, "failed the mod-97 checksum")
    return cleaned


@dataclass(frozen=True)
class CardResult:
    last_four: str
    #: `None` when the source had already masked the number — see the
    #: module docstring. Never a hash of a masked/incomplete value.
    hash: str | None


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        digit = int(ch)
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def card(raw: str) -> CardResult:
    cleaned = re.sub(r"[\s-]", "", raw.strip())
    if len(cleaned) < 4:
        raise NormalisationError("card", raw, "fewer than 4 characters — no last-four to extract")

    tail = cleaned[-4:]
    if not tail.isdigit():
        raise NormalisationError("card", raw, "last four characters are not literal digits")

    if any(ch in _MASK_CHARS for ch in cleaned):
        return CardResult(last_four=tail, hash=None)

    if not cleaned.isdigit() or not (12 <= len(cleaned) <= 19):
        raise NormalisationError("card", raw, "not a plausible card number length")
    if not _luhn_valid(cleaned):
        raise NormalisationError("card", raw, "failed the Luhn checksum")
    return CardResult(last_four=tail, hash=hashlib.sha256(cleaned.encode("ascii")).hexdigest())
