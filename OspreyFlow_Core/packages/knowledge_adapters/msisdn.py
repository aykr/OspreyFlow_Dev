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

#: ADR-103: Ofcom's numbers reserved for drama, as the first seven digits of a ten-digit UK national
#: number (each prefix then a thousand numbers). `phonenumbers` calls some of them unallocated, and
#: they are the only numbers `CLAUDE.md` rule 9's synthetic data may use, so without this no
#: synthetic phone record could be normalised. Listed whole, so the answer does not move with the
#: library's metadata. No real feed holds one, so real intake loses nothing.
_DRAMA_PREFIXES = frozenset(
    {
        "7700900",  # mobile, 07700 900000–900999
        "1134960", "1144960", "1154960", "1164960", "1174960", "1184960",  # Leeds … Reading
        "1214960", "1314960", "1414960", "1514960", "1614960",  # Birmingham … Manchester
        "2079460",  # London, 020 7946 0000–0999
        "1914980",  # Tyneside, 0191 498 0000–0999
        "2896496",  # Northern Ireland, 028 9649 6000–6999
        "2920180",  # Cardiff, 029 2018 0000–0999
        "1632960",  # no area, 01632 960000–960999
        "8081570",  # freephone, 0808 157 0000–0999
        "9098790",  # premium rate, 0909 879 0000–0999
        "3069990",  # UK-wide, 0306 999 0000–0999
    }
)  # fmt: skip


def _is_drama_number(parsed: phonenumbers.PhoneNumber) -> bool:
    national = phonenumbers.national_significant_number(parsed)
    return parsed.country_code == 44 and len(national) == 10 and national[:7] in _DRAMA_PREFIXES
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
    if not phonenumbers.is_valid_number(parsed) and not _is_drama_number(parsed):
        raise NormalisationError("msisdn", raw, "not a valid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
