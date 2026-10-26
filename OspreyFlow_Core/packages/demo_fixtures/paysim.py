"""The PaySim mobile-money dataset, read for a demo (ADR-055, ruled by the owner on
29 September 2026).

PaySim is *synthetic* ("Synthetic Financial Datasets For Fraud Detection", Lopez-Rojas, Elmir and
Axelsson, "PaySim: A financial mobile money simulator for fraud detection", EMSS 2016). Nothing in
it is a real person. It is still classified `internal` and never committed: the file lives under
`OspreyFlow_Data/`.

**What goes where.** The analytics store takes every row as an event, so counts, time windows and
amounts cover the full set. The graph takes only the *fraud neighbourhood*: every account that is
the origin or destination of a fraud row, and every transaction touching one. Loading all of the
roughly 8.5 million accounts as nodes would give a forest of one-edge stars.

This module is pure: it reads, selects and builds records. Writing them to ArcadeDB and DuckDB is
`scripts/seed_paysim.py`.
"""

from __future__ import annotations

import csv
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from schemas.analytics import EventRecord
from schemas.domain import (
    EdgeWrite,
    Handling,
    Interval,
    NodeWrite,
    Provenance,
    ProvenanceState,
    SourceRef,
)

COLUMNS: tuple[str, ...] = (
    "step",
    "type",
    "amount",
    "nameOrig",
    "oldbalanceOrg",
    "newbalanceOrig",
    "nameDest",
    "oldbalanceDest",
    "newbalanceDest",
    "isFraud",
    "isFlaggedFraud",
)

#: The data is simulated and has no real date. One `step` is one hour after this instant.
STEP_ORIGIN = datetime(2017, 1, 1, tzinfo=UTC)

#: Fixed namespace so an account or a transaction gets the same identifier on every load.
_NAMESPACE = uuid.UUID("6f0a5c1e-6b0e-4e2a-9d0a-50a15a1e0055")


class PaysimFileError(ValueError):
    """The file is not the PaySim log this loader reads."""


@dataclass(frozen=True)
class PaysimRow:
    index: int
    step: int
    type: str
    amount: float
    origin: str
    destination: str
    is_fraud: int
    is_flagged: int


def read_paysim(path: Path) -> Iterator[PaysimRow]:
    """Yield every row in file order. A missing or renamed column is refused before any row is
    read: a loader that guessed would load the wrong numbers under the right names."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        for column in COLUMNS:
            if column not in header:
                raise PaysimFileError(
                    f"{path.name} has no column {column!r}; this is not the PaySim log "
                    f"(expected {', '.join(COLUMNS)})."
                )
        for index, raw in enumerate(reader):
            yield PaysimRow(
                index=index,
                step=int(raw["step"]),
                type=raw["type"],
                amount=float(raw["amount"]),
                origin=raw["nameOrig"],
                destination=raw["nameDest"],
                is_fraud=int(raw["isFraud"]),
                is_flagged=int(raw["isFlaggedFraud"]),
            )


def step_timestamp(step: int) -> datetime:
    return STEP_ORIGIN + timedelta(hours=step)


def fraud_neighbourhood(rows: Iterable[PaysimRow]) -> tuple[set[str], list[PaysimRow]]:
    """The fraud accounts, and every row that touches one of them (as origin or destination).

    Two passes over `rows` are needed, so pass a list, or call once per pass with a re-read of the
    file (`scripts/seed_paysim.py` does the latter for the 6.4 million-row file)."""
    materialised = rows if isinstance(rows, list) else list(rows)
    accounts = fraud_accounts(materialised)
    return accounts, [r for r in materialised if r.origin in accounts or r.destination in accounts]


def fraud_accounts(rows: Iterable[PaysimRow], *, limit: int | None = None) -> set[str]:
    """The origin and destination of each fraud row. With `limit`, only those of the first `limit`
    fraud rows *in file order*: the graph sample (writing all ~74,000 accounts to a real ArcadeDB
    takes hours), deterministic so the same sample is written every time."""
    accounts: set[str] = set()
    taken = 0
    for row in rows:
        if row.is_fraud:
            if limit is not None and taken >= limit:
                break
            accounts.add(row.origin)
            accounts.add(row.destination)
            taken += 1
    return accounts


def account_node_id(account: str) -> str:
    """The same account has the same identifier in an event whether or not it is in the graph."""
    return f"paysim-acct-{uuid.uuid5(_NAMESPACE, account).hex}"


def to_event(row: PaysimRow, *, investigation_scope: str, handling: Handling) -> EventRecord:
    """One event per row. The fraud labels ride on the event, not on any graph edge, so "what the
    simulator says was fraud" stays apart from "what looks fraudulent"."""
    key = f"{row.index}:{row.origin}:{row.destination}:{row.step}"
    tx_id = uuid.uuid5(_NAMESPACE, key).hex
    return EventRecord(
        event_id=f"paysim-ev-{tx_id}",
        edge_id=f"paysim-tx-{tx_id}",
        edge_type="TRANSACTED",
        source_id=account_node_id(row.origin),
        target_id=account_node_id(row.destination),
        occurred_at=step_timestamp(row.step),
        properties={
            "amount": row.amount,
            "transaction_type": row.type,
            "is_fraud": row.is_fraud,
            "is_flagged_fraud": row.is_flagged,
            "step": row.step,
        },
        investigation_scope=investigation_scope,
        handling=handling,
    )


def _provenance(row_index: int) -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[
            SourceRef(
                document_id="paysim-dataset", locator=f"row {row_index}", excerpt_hash="paysim"
            )
        ],
        first_seen=datetime.now(UTC),
    )


def build_graph_writes(
    rows: Iterable[PaysimRow], *, created_by: str, handling: Handling
) -> tuple[list[NodeWrite], list[EdgeWrite]]:
    """The graph side of the neighbourhood: an `Endpoint` (kind `account`) for each account that
    appears in `rows`, and a `TRANSACTED` edge per row carrying the amount and the type.

    Identifiers are the same ones `to_event` uses, so an account selected in the Glass finds its
    events, and an edge matches its event. The fraud labels are deliberately not here."""
    nodes: dict[str, NodeWrite] = {}
    edges: list[EdgeWrite] = []
    now = datetime.now(UTC)
    for row in rows:
        for account in (row.origin, row.destination):
            node_id = account_node_id(account)
            if node_id not in nodes:
                nodes[node_id] = NodeWrite(
                    id=node_id,
                    type="Endpoint",
                    properties={
                        "value_raw": account,
                        "value_normalised": account,
                        "endpoint_kind": "account",
                    },
                    provenance=_provenance(row.index),
                    handling=handling,
                    created_by=created_by,
                    created_at=now,
                )
        event = to_event(row, investigation_scope="", handling=handling)
        edges.append(
            EdgeWrite(
                id=event.edge_id,
                type="TRANSACTED",
                source=account_node_id(row.origin),
                target=account_node_id(row.destination),
                properties={"amount": row.amount, "transaction_type": row.type},
                interval=Interval(
                    valid_from=step_timestamp(row.step), valid_to=step_timestamp(row.step)
                ),
                provenance=_provenance(row.index),
                handling=handling,
                created_by=created_by,
                created_at=now,
            )
        )
    return list(nodes.values()), edges
