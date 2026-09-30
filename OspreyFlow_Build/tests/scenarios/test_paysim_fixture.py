"""ADR-055 §7, tests named before the code (`CLAUDE.md` rule 12): the PaySim reader, the fraud
neighbourhood, the `step` mapping and the labels. The fixture is the first eight rows of the real
file (which hold two fraud transfers) plus three planted rows: one non-fraud row into a fraud
account (it must be in the graph), one row that touches no fraud account, and one whose origin is
only a *second hop* from fraud (it must be left out)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from demo_fixtures.paysim import (
    COLUMNS,
    PaysimFileError,
    fraud_neighbourhood,
    read_paysim,
    step_timestamp,
    to_event,
)
from schemas.domain import Handling

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "paysim_sample.csv"
_HANDLING = Handling(classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u")


def test_the_reader_gives_every_row_of_the_file_in_order() -> None:
    rows = list(read_paysim(SAMPLE))

    assert len(rows) == 11
    assert [r.index for r in rows] == list(range(11))
    assert rows[0].type == "PAYMENT" and rows[0].amount == 9839.64
    assert rows[0].origin == "C1231006815" and rows[0].destination == "M1979787155"


@pytest.mark.parametrize("missing", COLUMNS)
def test_a_file_with_a_missing_or_renamed_column_is_refused(tmp_path: Path, missing: str) -> None:
    text = SAMPLE.read_text(encoding="utf-8").replace(missing, missing + "_renamed", 1)
    broken = tmp_path / "broken.csv"
    broken.write_text(text, encoding="utf-8")

    with pytest.raises(PaysimFileError, match=missing):
        list(read_paysim(broken))


def test_the_fraud_neighbourhood_is_the_fraud_accounts_and_every_row_touching_them() -> None:
    rows = list(read_paysim(SAMPLE))

    accounts, touching = fraud_neighbourhood(rows)

    assert accounts == {"C1305486145", "C553264065", "C840083671", "C38997010"}
    # The two fraud rows and the non-fraud CASH_IN into a fraud account. Not the row whose origin
    # is one hop further out (C900000003 -> C900000004), and not the unrelated payment.
    assert sorted(r.index for r in touching) == [2, 3, 9]
    assert all(
        r.origin in accounts or r.destination in accounts for r in touching
    )


def test_step_maps_to_the_declared_hour_at_both_ends() -> None:
    assert step_timestamp(1) == datetime(2017, 1, 1, 1, tzinfo=UTC)
    assert step_timestamp(743) == datetime(2017, 1, 31, 23, tzinfo=UTC)


def test_every_event_carries_its_fraud_labels_unchanged() -> None:
    rows = list(read_paysim(SAMPLE))

    events = [to_event(r, investigation_scope="case-x", handling=_HANDLING) for r in rows]

    assert [e.properties["is_fraud"] for e in events] == [r.is_fraud for r in rows]
    assert [e.properties["is_flagged_fraud"] for e in events] == [r.is_flagged for r in rows]
    assert sum(e.properties["is_fraud"] for e in events) == 2
    fraud_event = events[2]
    assert fraud_event.edge_type == "TRANSACTED"
    assert fraud_event.properties["amount"] == 181.0
    assert fraud_event.properties["transaction_type"] == "TRANSFER"
    assert fraud_event.occurred_at == step_timestamp(1)
    assert fraud_event.investigation_scope == "case-x"


def test_events_have_unique_ids_and_the_same_account_keeps_the_same_node_id() -> None:
    rows = list(read_paysim(SAMPLE))
    events = [to_event(r, investigation_scope="case-x", handling=_HANDLING) for r in rows]

    assert len({e.event_id for e in events}) == len(events)
    # C553264065 is the destination of rows 2 and 9 and its id must agree across them.
    assert events[2].target_id == events[9].target_id
    assert events[2].target_id != events[3].target_id


# --- the graph side --------------------------------------------------------------------------


def test_the_graph_takes_the_neighbourhood_as_account_endpoints_with_amounts_on_edges() -> None:
    from demo_fixtures.paysim import build_graph_writes

    _accounts, touching = fraud_neighbourhood(list(read_paysim(SAMPLE)))

    nodes, edges = build_graph_writes(touching, created_by="seed", handling=_HANDLING)

    # Four fraud accounts, plus the origin of the CASH_IN that touches one of them. Nothing else:
    # not the second-hop account, not the unrelated payment's accounts.
    assert len(nodes) == 5 and len({n.id for n in nodes}) == 5
    assert {n.properties["value_raw"] for n in nodes} == {
        "C1305486145", "C553264065", "C840083671", "C38997010", "C900000003",
    }
    assert all(n.type == "Endpoint" and n.properties["endpoint_kind"] == "account" for n in nodes)
    assert len(edges) == 3 and all(e.type == "TRANSACTED" for e in edges)
    by_amount = sorted((e.properties["amount"], e.properties["transaction_type"]) for e in edges)
    assert by_amount == [(75.5, "CASH_IN"), (181.0, "CASH_OUT"), (181.0, "TRANSFER")]
    # No fraud label on the edge: that lives on the analytics event.
    assert all("is_fraud" not in e.properties for e in edges)
    assert all(e.interval is not None and e.interval.valid_from.tzinfo for e in edges)


def test_graph_node_ids_are_the_ids_the_events_use() -> None:
    """If these disagreed, selecting an account in the Glass would find no events for it."""
    from demo_fixtures.paysim import build_graph_writes

    rows = list(read_paysim(SAMPLE))
    _accounts, touching = fraud_neighbourhood(rows)
    nodes, edges = build_graph_writes(touching, created_by="seed", handling=_HANDLING)
    events = {r.index: to_event(r, investigation_scope="c", handling=_HANDLING) for r in rows}

    node_ids = {n.id for n in nodes}
    for row in touching:
        assert events[row.index].source_id in node_ids
        assert events[row.index].target_id in node_ids
    assert {e.id for e in edges} == {events[r.index].edge_id for r in touching}


def test_the_graph_sample_takes_only_the_first_n_fraud_rows_in_file_order() -> None:
    """The full neighbourhood is 74,000 accounts and takes hours to write to a real ArcadeDB. A
    sample is the first N fraud rows and everything touching their accounts: deterministic (file
    order), so the same sample is written every time. Catches a limit that is ignored, or that picks
    by something other than file order."""
    from demo_fixtures.paysim import fraud_accounts

    rows = list(read_paysim(SAMPLE))
    fraud_rows = [r for r in rows if r.is_fraud]
    assert len(fraud_rows) >= 2
    first = fraud_rows[0]

    assert fraud_accounts(rows, limit=1) == {first.origin, first.destination}
    assert fraud_accounts(rows, limit=None) == fraud_accounts(rows)
    assert fraud_accounts(rows, limit=len(fraud_rows)) == fraud_accounts(rows)
    assert fraud_accounts(rows, limit=1) < fraud_accounts(rows)
