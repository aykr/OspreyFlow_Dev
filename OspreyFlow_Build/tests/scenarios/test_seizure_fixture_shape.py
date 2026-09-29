"""Proves the seizure-record fixture (`tests/scenarios/fixtures/
seizure_record.py`) actually carries the shape `08_ACCEPTANCE_SCENARIOS.md`
B15 assumes — two distinct SIMs and one handset, all adapter-valid — before
anything tries to load it into a graph. The same discipline
`test_hmp_fixture_shape.py` established for Scenario A: a fixture's own
claimed shape is a fact to prove, not a docstring to trust.

No graph adapter needed — this only exercises the real `imei`/`imsi`
Knowledge Adapters directly, the same normalisers a recipe's `transform:`
step would call at load time.
"""

from __future__ import annotations

from demo_fixtures.seizure_record import (
    HANDSET_IMEI_NORMALISED,
    SEIZURE_DATE,
    SIM_A_IMSI_NORMALISED,
    SIM_B_IMSI_NORMALISED,
    SIM_B_MSISDN_NORMALISED,
    generate_seizure_record,
)
from knowledge_adapters.imei import imei
from knowledge_adapters.imsi import imsi
from knowledge_adapters.msisdn import msisdn


def test_handset_imei_normalises_to_the_expected_value() -> None:
    record = generate_seizure_record()
    assert imei(record["handset_imei_raw"]) == HANDSET_IMEI_NORMALISED


def test_both_sims_normalise_and_are_distinct() -> None:
    record = generate_seizure_record()
    sim_a, sim_b = record["sims"]

    normalised_a = imsi(sim_a["imsi_raw"])
    normalised_b = imsi(sim_b["imsi_raw"])

    assert normalised_a == SIM_A_IMSI_NORMALISED
    assert normalised_b == SIM_B_IMSI_NORMALISED
    assert normalised_a != normalised_b


def test_sim_a_carries_no_attributed_msisdn() -> None:
    """Deliberate, not an omission — see the fixture's own docstring."""
    record = generate_seizure_record()
    sim_a, _ = record["sims"]
    assert sim_a["msisdn_raw"] is None


def test_sim_b_msisdn_normalises_and_is_distinct_from_either_imsi() -> None:
    record = generate_seizure_record()
    _, sim_b = record["sims"]

    normalised = msisdn(sim_b["msisdn_raw"])

    assert normalised == SIM_B_MSISDN_NORMALISED
    assert normalised not in (SIM_A_IMSI_NORMALISED, SIM_B_IMSI_NORMALISED)


def test_the_swap_leaves_no_gap_and_no_overlap() -> None:
    """B15's traversal only needs both `PAIRED_WITH` edges to exist; this
    guards the fixture's own honesty about the interval shape it claims —
    SIM A's window ends exactly where SIM B's begins, and SIM B's stays
    open (`paired_to is None`) through the seizure date, so B17's brush
    lands inside a genuinely still-open interval rather than a stale one."""
    record = generate_seizure_record()
    sim_a, sim_b = record["sims"]

    assert sim_a["paired_from"] < sim_a["paired_to"] == sim_b["paired_from"]
    assert sim_b["paired_to"] is None
    assert sim_b["paired_from"] < record["seizure_date"] == SEIZURE_DATE


def test_generation_is_deterministic_across_calls() -> None:
    first = generate_seizure_record()
    second = generate_seizure_record()
    assert first == second
