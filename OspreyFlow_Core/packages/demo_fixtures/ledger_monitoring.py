"""Operation Ledger's monitoring week (`06_DECISIONS.md` ADR-108 Amendment 5;
`process/ALERTING_MONITORING_PLAN.md`, use cases A1 to A4; rule 9: synthetic, in-repo, never real).

The bank's next weekly transaction export arrives after the seed's, for the week of Monday 5 to
Sunday 11 October 2026 (the seed's own export ends with the week of 28 September). It is in the
seed's own columns (`ledger.transaction_rows`), so the committed `ledger_transactions_recipe.yaml`
loads it unchanged, and it is drawn from `random.Random` seeded by a fixed digest, so it is the same
on every run; like `ledger.py` it is pure (standard library, no clock, no environment) until
`write_batches` writes it.

- **A1, rapid movement and a circle.** Crescent Imports pays £18,000 into Sofia Ruiz's Monzo account
  on Monday morning; £17,400 of it leaves for Tomas Zelinsky's Starling account six hours later (the
  account is a pass-through); on Thursday Zelinsky pays £16,900 back to Crescent (value back where
  it started, in three movements). Zelinsky's payment comes more than 48 hours after his account was
  paid, so it is not a pass-through of its own.
- **A2, a cash deposit into a hotlisted account.** On Friday £9,700 is paid in, in cash, from
  Zelinsky's account into Jamal Carter's Lloyds account, which the analyst hotlisted after the SAR.
  A cash deposit is written as the seed writes its own (`CASH_IN`, the depositor's account paying
  the account credited).
- **Background.** Ordinary trading between the three trading counterparties (Kesterton Freight
  buys pallets from Midland Pallets and fuel cards from Arden Fuel Cards; Midland Pallets buys fuel
  cards), always in that direction, so no payment ever comes back round, and each onward payment is
  well under what arrived, so no account passes money through. None of it touches Hale Logistics,
  whose own September trading would close a circle with any new payment to or from it.

**What the week must raise** is `EXPECTED_ALERTS`, in order, once the analyst has hotlisted
Carter's account and deployed `RAPID_MOVEMENT` and `CIRCULAR_FLOW` from the templates; the golden
tests (`tests/scenarios/test_ledger_monitoring_storyline.py`) load the file through the committed
recipe and assert exactly these. A3's list versions are the synthetic UK Sanctions List files in
`screening_lists/` (`UK_LIST_V1`, `UK_LIST_V2`).
"""

from __future__ import annotations

import csv
import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .ledger import CRESCENT_ACC, HALE_BIZ, MULE_ACCOUNTS, TRADING_ACCOUNTS

#: The week the export covers: the Monday after the seed's last trading week, to its Sunday.
WEEK_START = date(2026, 10, 5)
WEEK_END = date(2026, 10, 11)

#: The file, written under the dataset folder's `incoming/` until the presenter releases it.
WEEK_2 = "ledger_transactions_week2.csv"
INCOMING = "incoming"
#: The committed recipe that loads it: the seed's own transactions template, columns unchanged.
RECIPE = "ledger_transactions_recipe.yaml"
HEADER = ("payer_iban", "payee_iban", "amount", "at", "transaction_type")

#: A3: the synthetic UK Sanctions List (FCDO format; ADR-133 Amendment 6), version 1 as the seed
#: places it and version 2 as the presenter releases it over it.
UK_LIST_NAME = "UK Sanctions List (synthetic)"
UK_LIST_SOURCE = "uk_sanctions_list"
UK_LIST_V1 = "synthetic_uk_sanctions_list_v1.xml"
UK_LIST_V2 = "synthetic_uk_sanctions_list_v2.xml"
#: Where the list is read from, relative to the dataset's folder (`uploaded/ledger/`).
UK_LIST_FILE = "lists/uk_sanctions_list.xml"
#: The designation version 2 adds: an Operation Ledger customer (Sofia Ruiz, born 14 June 2001).
UK_LIST_ADDED = "SYNUK0007"

RUIZ_ACC = MULE_ACCOUNTS["Ruiz"]
ZELINSKY_ACC = MULE_ACCOUNTS["Zelinsky"]
CARTER_ACC = MULE_ACCOUNTS["Carter"]
#: A2: the account the analyst hotlists, as they would copy it from the Inspector.
HOTLISTED_ACCOUNT = CARTER_ACC

#: The storyline's rows: (payer, payee, amount, when, type).
STORY: tuple[tuple[str, str, str, datetime, str], ...] = (
    (CRESCENT_ACC, RUIZ_ACC, "18000", datetime(2026, 10, 5, 10, 5, tzinfo=UTC), "TRANSFER"),
    (RUIZ_ACC, ZELINSKY_ACC, "17400", datetime(2026, 10, 5, 16, 20, tzinfo=UTC), "TRANSFER"),
    (ZELINSKY_ACC, CRESCENT_ACC, "16900", datetime(2026, 10, 8, 11, 30, tzinfo=UTC), "TRANSFER"),
    (ZELINSKY_ACC, CARTER_ACC, "9700", datetime(2026, 10, 9, 11, 40, tzinfo=UTC), "CASH_IN"),
)
#: How many background payments the week carries beside the storyline's.
BACKGROUND = 9

#: A1's rules, as the analyst deploys them from the typology templates (ADR-133 decision 2), each
#: running after each load commits (the default; the data engineer's pipeline applies every case
#: rule unless it chooses otherwise, ADR-133 Amendment 4). Rapid movement keeps the template's
#: defaults; the circle is tuned to a week ("value back where it started within 7 days"), so it
#: judges this week against the week before it and not against September's structuring, which the
#: case already holds as an alert of its own. Plain data; `schemas.domain` validates it.
RAPID_MOVEMENT_NAME = "Money straight through an account"
RAPID_MOVEMENT: Mapping[str, Any] = {
    "typology": "rapid_movement",
    "within_hours": 48,
    "keep_fraction": 0.8,
}
CIRCULAR_FLOW_NAME = "Money back where it started within a week"
CIRCULAR_FLOW: Mapping[str, Any] = {"typology": "circular_flow", "max_hops": 4, "window_days": 7}
#: A3's rule, as the onboarding chapter deployed it: screening against the lists (the template's
#: defaults), after commit.
SCREENING_NAME = "Screen customers against the lists"
SCREENING: Mapping[str, Any] = {"typology": "kyc_screening"}


@dataclass(frozen=True)
class ExpectedAlert:
    """One alert the week raises: its kind (a typology, or `hotlist`) and the account it names
    (the pass-through account, the circle's start, the hotlisted account) or, for a screening
    match, the customer's family name."""

    kind: str
    names: str


#: The week's alerts, in the order they are raised: the load's rules after it commits (rapid
#: movement, then the circle, in the order they were deployed), then the hotlist over what the load
#: touched; then, when the presenter releases the list's version 2 and refreshes it, the screening
#: match. Nothing else.
EXPECTED_ALERTS: tuple[ExpectedAlert, ...] = (
    ExpectedAlert("rapid_movement", RUIZ_ACC),
    ExpectedAlert("circular_flow", CRESCENT_ACC),
    ExpectedAlert("hotlist", CARTER_ACC),
    ExpectedAlert("kyc_screening", "Ruiz"),
)

#: A4: the alert the analyst closes, and how (one of the five closing reasons; ADR-133 Amendment 5).
CLOSED_KIND = "rapid_movement"
CLOSING_REASON = "referred"
CLOSING_WORDS = (
    "To the MLRO: a further SAR on the Monzo account, citing the circle through Crescent."
)


def _rng() -> random.Random:
    digest = hashlib.sha256(b"operation-ledger|monitoring|week-2").digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _cell(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(payer: str, payee: str, amount: str, at: datetime, kind: str) -> dict[str, str]:
    return {
        "payer_iban": payer,
        "payee_iban": payee,
        "amount": amount,
        "at": _cell(at),
        "transaction_type": kind,
    }


def background_rows() -> list[dict[str, str]]:
    """Trading between the three counterparties, always buyer to supplier: Kesterton Freight (the
    first) pays the other two, Midland Pallets pays Arden Fuel Cards, so no payment comes back
    round. A supplier's own onward payment is under £450 against at least £1,200 it was paid, so
    no account passes money through; and no three of one buyer's payments to one supplier sum past
    £10,000, so nothing looks structured."""
    kesterton, midland, arden = TRADING_ACCOUNTS
    rng = _rng()
    rows: list[tuple[datetime, dict[str, str]]] = []
    pairs = [(kesterton, midland), (kesterton, arden), (midland, arden)]
    for n in range(BACKGROUND):
        payer, payee = pairs[n % len(pairs)]
        day = WEEK_START + timedelta(days=rng.randrange(5))
        at = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(
            minutes=rng.randrange(9 * 60, 17 * 60)
        )
        # Kesterton's purchases are a few thousand, never three in a week summing past £10,000
        # (so structuring, if it is live, finds nothing); Midland's own are hundreds (rapid
        # movement needs 80% of an incoming amount to leave again).
        amount = (
            rng.randrange(1_200, 3_250, 50) if payer == kesterton else rng.randrange(150, 450, 10)
        )
        rows.append((at, _row(payer, payee, str(amount), at, "PAYMENT")))
    rows.sort(key=lambda r: (r[0], r[1]["payer_iban"]))
    return [r for _, r in rows]


def week_rows() -> list[dict[str, str]]:
    """The week's export, in time order: the storyline's four rows and the background."""
    story = [_row(*s) for s in STORY]
    rows = [*story, *background_rows()]
    rows.sort(key=lambda r: (r["at"], r["payer_iban"]))
    return rows


def touching(account: str, rows: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    """The rows whose payer or payee is the account."""
    return [r for r in (rows if rows is not None else week_rows())
            if account in (r["payer_iban"], r["payee_iban"])]  # fmt: skip


#: Accounts the background never touches (the storyline's and Hale Logistics').
UNTOUCHED_BY_BACKGROUND = frozenset({HALE_BIZ, CRESCENT_ACC, RUIZ_ACC, ZELINSKY_ACC, CARTER_ACC})


@dataclass(frozen=True)
class WrittenBatch:
    name: str  # relative to the output folder, with `/` separators
    rows: int
    bytes: int
    sha256: str


def output_name() -> str:
    return f"{INCOMING}/{WEEK_2}"


def write_batches(out_dir: Path) -> list[WrittenBatch]:
    """Writes the week's export under `out_dir/incoming/` and answers it. A second call rewrites it
    byte for byte."""
    rows = week_rows()
    path = out_dir / output_name()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADER)
        for row in rows:
            writer.writerow([row[c] for c in HEADER])
    data = path.read_bytes()
    return [WrittenBatch(output_name(), len(rows), len(data), hashlib.sha256(data).hexdigest())]


__all__ = [
    "CIRCULAR_FLOW",
    "EXPECTED_ALERTS",
    "HOTLISTED_ACCOUNT",
    "RAPID_MOVEMENT",
    "SCREENING",
    "STORY",
    "UK_LIST_V1",
    "UK_LIST_V2",
    "WEEK_2",
    "ExpectedAlert",
    "WrittenBatch",
    "background_rows",
    "week_rows",
    "write_batches",
]
