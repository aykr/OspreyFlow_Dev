"""Synthetic CDR fixture — `08_ACCEPTANCE_SCENARIOS.md` Scenario B's shape:
the same number rendered four ways, a CLI-suppression prefix, duplicated
rows with differing sequence numbers, mixed timestamp formats including one
local-time row, and one row whose timestamp cannot be recovered at all.

Each duplicate pair's timestamp differs in *representation*, never in
instant — `01_DOMAIN_MODEL.md` §7 rule 2: canonicalise before hashing,
always. A pair that is byte-identical proves nothing about that rule; one
carrier's `2026-01-10T10:00:00Z` and another's `2026-01-10 10:00:00+00:00`
describing the same call is the actual failure mode the rule exists for.

Seeded and deterministic — the random component only
varies call duration, never the structural cases the Phase 2 exit criterion
checks for.
"""

from __future__ import annotations

import random

# Not Ofcom's 07700 900000-999 fictional-drama range — a msisdn normaliser
# correctly rejects those as invalid, which is not the case this fixture
# wants to exercise.
B_PARTY = "07911123456"

#: `01_DOMAIN_MODEL.md` §7's own four renderings of one number.
A_PARTY_RENDERINGS = (
    "01621926368",
    "+44(0)1621926368",
    "441621926368",
    "#31#01621926368",
)

#: One instant per variant, each duplicated below in a different string
#: representation of the *same* instant — all four collapse to a call at
#: 10:00 UTC on their date, in January (GMT, not BST), so the equivalence
#: is exact regardless of timezone handling.
_DUPLICATE_REPRESENTATIONS = (
    # (primary, duplicate) — same instant, 2026-01-10T10:00:00Z.
    ("2026-01-10T10:00:00Z", "2026-01-10 10:00:00+00:00"),
    # Bare local time, no offset at all — recovered via the connector's
    # configured tz (Europe/London, GMT in January).
    ("2026-01-11T10:00:00Z", "2026-01-11 10:00:00"),
    # DD/MM/YYYY — recovered only because the connector declares
    # date_order: dmy; parsed as mdy this would be 1 December.
    ("2026-01-12T10:00:00Z", "12/01/2026 10:00:00"),
    ("2026-01-13T10:00:00Z", "2026-01-13 10:00:00+00:00"),
)


def generate_cdr_rows(seed: int = 42) -> list[dict[str, str]]:
    rng = random.Random(seed)
    rows: list[dict[str, str]] = []
    seq = 1

    for a_variant, (primary_time, duplicate_time) in zip(
        A_PARTY_RENDERINGS, _DUPLICATE_REPRESENTATIONS, strict=True
    ):
        duration = str(rng.randint(10, 300))
        base = {
            "a_party": a_variant,
            "b_party": B_PARTY,
            "duration": duration,
            "direction": "O",
        }
        rows.append({"seq": str(seq), "start_time": primary_time, **base})
        seq += 1

        # The same call, duplicated with a different sequence number and a
        # differently-represented but identical instant —
        # 08_ACCEPTANCE_SCENARIOS.md B2's "duplicated rows with differing
        # sequence numbers", and §7 rule 2's canonicalisation requirement.
        rows.append({"seq": str(seq), "start_time": duplicate_time, **base})
        seq += 1

    # A local-time row with no recoverable offset in the value itself — the
    # recipe's configured default zone recovers it. Dated after the UK's
    # 2026 spring-forward (2026-03-29), so this is only correct if the
    # normaliser applies the summer-time offset (+01:00), not a fixed one.
    rows.append(
        {
            "seq": str(seq),
            "a_party": A_PARTY_RENDERINGS[0],
            "b_party": B_PARTY,
            "start_time": "2026-03-30 11:00:00",
            "duration": str(rng.randint(10, 300)),
            "direction": "I",
        }
    )
    seq += 1

    # Genuinely undeterminable — rejected, never guessed
    # (`01_DOMAIN_MODEL.md` §7, `08_ACCEPTANCE_SCENARIOS.md` B3).
    rows.append(
        {
            "seq": str(seq),
            "a_party": A_PARTY_RENDERINGS[0],
            "b_party": B_PARTY,
            "start_time": "not-a-real-timestamp",
            "duration": str(rng.randint(10, 300)),
            "direction": "O",
        }
    )
    return rows
