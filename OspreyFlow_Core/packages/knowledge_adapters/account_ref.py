"""`account_ref` — `01_DOMAIN_MODEL.md` §7; ADR-127 decision 4.

A bank or private-cash account reference: trimmed, internal whitespace removed, upper-cased. An
empty value, and any character outside letters, digits, `-` and `/`, is refused. Nothing else is
checked — no check digits and no country logic: a reference's own scheme is the source's, and a
value that `iban` can validate belongs to `iban`.

The character set is judged before upper-casing, and on ASCII only: `ß` upper-cases to `SS`, and a
full-width digit is not a digit here, so checking afterwards would let both through. A refusal names
the rule and never the value, so a rejection report carries no account reference in its reasons.
"""

from __future__ import annotations

import re

from .errors import NormalisationError

_WHITESPACE = re.compile(r"\s")
_ALLOWED = re.compile(r"[A-Za-z0-9/-]+")


def account_ref(raw: str) -> str:
    compact = _WHITESPACE.sub("", raw.strip())
    if not compact:
        raise NormalisationError("account_ref", raw, "empty: an account reference needs a value")
    if _ALLOWED.fullmatch(compact) is None:
        raise NormalisationError(
            "account_ref",
            raw,
            "a character outside ASCII letters, digits, '-' and '/', "
            "the only ones a reference may hold",
        )
    return compact.upper()
