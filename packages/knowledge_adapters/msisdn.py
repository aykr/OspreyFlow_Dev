"""`msisdn` — `01_DOMAIN_MODEL.md` §7. National, international,
CLI-suppression prefixes and extensions all collapse to the same E.164
value — this is what `08_ACCEPTANCE_SCENARIOS.md` B1 means by "all four
renderings of the shared number resolve to one `Endpoint`".

CLI suppression (`#31#` in the UK) is stripped from the value this function
returns — it must not change which `Endpoint` the number resolves to, or
the same caller with and without suppression would fragment into two
entities, exactly the failure `01_DOMAIN_MODEL.md` §7 warns about. The
suppression prefix is still a fact about the caller's behaviour, but it is
preserved by the caller retaining `value_raw` unmodified, not by this
function baking it into the canonical value.
"""

from __future__ import annotations

import re

import phonenumbers

from .errors import NormalisationError

_CLI_SUPPRESSION_PREFIXES = ("#31#",)
_TRUNK_PARENTHESIS = re.compile(r"\(0\)")


def msisdn(raw: str, *, default_region: str = "GB") -> str:
    cleaned = raw.strip()
    for prefix in _CLI_SUPPRESSION_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    cleaned = _TRUNK_PARENTHESIS.sub("", cleaned)

    try:
        parsed = phonenumbers.parse(cleaned, default_region)
    except phonenumbers.NumberParseException as exc:
        raise NormalisationError("msisdn", raw, str(exc)) from exc
    if not phonenumbers.is_valid_number(parsed):
        raise NormalisationError("msisdn", raw, "not a valid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
