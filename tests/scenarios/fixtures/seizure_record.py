"""Synthetic seizure-record fixture — `08_ACCEPTANCE_SCENARIOS.md` Scenario
B's own fixture line: "one later seizure record with two SIMs and a handset
identifier" (B13, B15). Two SIMs, each identified by its own IMSI, both
paired with the one handset, identified by its IMEI — the SIM-swap shape
`06_DECISIONS.md` ADR-023's `PAIRED_WITH` edge exists to make one traversal.

Raw, not pre-normalised — the same discipline as `cdr.py`'s phone-number
renderings, which are left for a recipe's `transform:` step to canonicalise
rather than normalised by the fixture itself. Here that step is this
fixture's own shape test (`test_seizure_fixture_shape.py`), which proves the
raw values are genuinely well-formed by running them through the real
`imei`/`imsi`/`msisdn` Knowledge Adapters, since no seizure-record connector
or recipe exists yet to do it end to end (a disclosed gap:
only the CSV connector is built; a device-extraction format is not).

**The MSISDN leg.** SIM B — the one active at seizure — also carries the
MSISDN a device extraction typically reads straight off the SIM alongside
its IMSI. This is the number B5/B7 land an analyst on; reaching the handset
from it is `Endpoint(msisdn) --SAME_AS--> Endpoint(imsi) --PAIRED_WITH-->
Device`, ADR-023's corrected two-hop answer to its own second question, not
a direct pairing. SIM A stays IMSI-only, deliberately — not every recovered
SIM has a confidently-attributed number, and this fixture should not imply
one always exists. The `SAME_AS` itself is written `{"score": 1.0}`,
`provenance.state = ASSERTED`, the same shape
`WorkingSetService.manual_link` already uses for a directly-known (not
Splink-scored) link — a device extraction reading both fields off one SIM
is a direct observation, not a probabilistic match.

Seeded and deterministic (`CLAUDE.md` rule 9) — the random component varies
only the pairing dates, never the identifiers themselves.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

#: A real-format, Luhn-valid IMEI (TAC 490154, serial 203237, check digit 8)
#: — the same value `tests/knowledge_adapters/test_imei.py` already golden-
#: tests, reused rather than invented so this fixture cannot drift from the
#: normaliser's own accepted shape.
HANDSET_IMEI_RAW = "49-015420/3237518"
HANDSET_IMEI_NORMALISED = "49015420323751"

#: Two distinct SIMs, rendered with the MCC-MNC separator style
#: `imsi()`'s own golden test already strips.
SIM_A_IMSI_RAW = "234-15-0123456781"
SIM_B_IMSI_RAW = "234-15-0123456782"
SIM_A_IMSI_NORMALISED = "234150123456781"
SIM_B_IMSI_NORMALISED = "234150123456782"

#: SIM B's own number — one digit off `cdr.py`'s `B_PARTY` (07911123456) so
#: the two fixtures are never mistaken for describing the same real-world
#: Endpoint, and a genuinely valid UK mobile range (unlike Ofcom's
#: 07700 900000-999 fictional-drama block `cdr.py`'s own comment already
#: avoids) — checked directly against the real `msisdn()` normaliser, not
#: assumed plausible.
SIM_B_MSISDN_RAW = "07911123457"
SIM_B_MSISDN_NORMALISED = "+447911123457"

#: The swap: SIM A is pulled the day SIM B is inserted, both in the one
#: handset, both dated before the seizure below (B13's "ingest the later
#: seizure record", B17's "brush to the seizure date").
_SWAP_DATE = datetime(2026, 1, 21, tzinfo=UTC)
SEIZURE_DATE = datetime(2026, 2, 3, tzinfo=UTC)


def generate_seizure_record(seed: int = 7) -> dict[str, object]:
    """One seizure record: a handset and the two SIMs recovered with it,
    each with the window it was paired to the handset, plus the MSISDN a
    device extraction read straight off the currently-active SIM. The
    random component only jitters the pairing start date by a few hours —
    never the identifiers or their ordering, which the shape test and the
    `PAIRED_WITH`/`SAME_AS` conformance cases both depend on being exact."""
    rng = random.Random(seed)
    jitter = timedelta(hours=rng.randint(0, 23))

    return {
        "handset_imei_raw": HANDSET_IMEI_RAW,
        "sims": [
            {
                "imsi_raw": SIM_A_IMSI_RAW,
                "msisdn_raw": None,
                "paired_from": (_SWAP_DATE - timedelta(days=20)) + jitter,
                "paired_to": _SWAP_DATE,
            },
            {
                "imsi_raw": SIM_B_IMSI_RAW,
                "msisdn_raw": SIM_B_MSISDN_RAW,
                "paired_from": _SWAP_DATE,
                "paired_to": None,  # still in the handset at the point of seizure
            },
        ],
        "seizure_date": SEIZURE_DATE,
    }
