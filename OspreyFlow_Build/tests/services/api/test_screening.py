"""Name screening and the screening-list loader (`spec/06_DECISIONS.md` ADR-109 phase F).

What a mistake would do, and the case that catches it:

- a name matched only in one word order would miss "PETROVA, Elena" for "Elena Petrov"
  (`test_screening_matches_across_word_order_and_punctuation`), and one matched too loosely would
  bury a reviewer in false hits (`test_screening_refuses_a_different_name`);
- a date of birth that disagrees, ignored, would screen the wrong person in
  (`test_a_disagreeing_date_of_birth_rules_a_match_out`);
- a real list loaded without the owner's exceptions entry would put real people's data on a
  device and in a case unadmitted (rule 9) — refused, and admitted only with the entry for that use
  (`test_a_real_list_is_refused_without_the_owners_exception`,
  `test_a_real_list_loads_with_the_owners_exception_for_that_use`);
- the committed list not being synthetic would be rule 9 broken in the repository itself
  (`test_the_committed_list_is_synthetic`).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from scripts.load_screening_list import ListRefused, parse_list
from services.api.screening import ScreeningEntry, normalised, screen

LIST = [
    ScreeningEntry(id="1", list_name="L", listing="sanction", entity_type="Person",
                   name="PETROVA, Elena", date_of_birth=date(1979, 4, 2)),
    ScreeningEntry(id="2", list_name="L", listing="pep", entity_type="Person", name="Harriet Quennell"),
]  # fmt: skip

COMMITTED = Path(__file__).resolve().parents[4] / "OspreyFlow_Core/packages/demo_fixtures/screening_list_synthetic.yaml"


def test_screening_matches_across_word_order_and_punctuation() -> None:
    assert normalised("PETROVA, Elena") == normalised("elena petrova")
    (hit,) = screen("Elena Petrov", None, LIST, min_score=0.9)
    assert hit.entry.id == "1" and hit.score >= 0.9


def test_screening_refuses_a_different_name() -> None:
    assert screen("Elena Markovic", None, LIST, min_score=0.9) == []


def test_a_disagreeing_date_of_birth_rules_a_match_out() -> None:
    assert screen("Elena Petrova", date(1985, 1, 1), LIST, min_score=0.9) == []
    assert len(screen("Elena Petrova", date(1979, 4, 2), LIST, min_score=0.9)) == 1


def test_the_committed_list_is_synthetic() -> None:
    raw = yaml.safe_load(COMMITTED.read_text(encoding="utf-8"))
    assert raw["synthetic"] is True
    name, entries = parse_list(raw, use="local_development")
    assert entries and all(e.synthetic for e in entries) and name.startswith("Synthetic")


def _exceptions(tmp_path: Path, uses: list[str], dataset: str = "opensanctions") -> Path:
    path = tmp_path / "real_data_exceptions.yaml"
    path.write_text(yaml.safe_dump({"exceptions": [{
        "dataset": dataset, "approved_uses": uses, "added_by": "owner",
        "added_date": "2026-10-10", "device": "owner-mac", "justification": "local demo",
        "decision_record": "ADR-035 §C3",
    }]}))  # fmt: skip
    return path


REAL = {"list_name": "OpenSanctions consolidated", "dataset": "opensanctions",
        "entries": [{"id": "x", "listing": "sanction", "entity_type": "Person", "name": "Someone"}]}  # fmt: skip


def test_a_real_list_is_refused_without_the_owners_exception(tmp_path: Path) -> None:
    with pytest.raises(ListRefused, match="rule 9"):
        parse_list(REAL, use="local_development", config_path=tmp_path / "absent.yaml")
    with pytest.raises(ListRefused, match="must name its `dataset`"):
        parse_list({**REAL, "dataset": ""}, use="local_development", config_path=tmp_path / "absent.yaml")


def test_a_real_list_loads_with_the_owners_exception_for_that_use(tmp_path: Path) -> None:
    config = _exceptions(tmp_path, ["local_development"], dataset="ofac_sdn")
    real = {**REAL, "list_name": "OFAC SDN", "dataset": "ofac_sdn"}
    _, entries = parse_list(real, use="local_development", config_path=config)
    assert [e.synthetic for e in entries] == [False]
    with pytest.raises(ListRefused):
        parse_list(real, use="owner_run_demonstration", config_path=config)


def test_a_real_list_whose_licence_is_not_confirmed_is_refused_even_with_the_exception(
    tmp_path: Path,
) -> None:
    """The owner's answer of 1 November 2026: UN and OpenSanctions are synthetic-only until their
    licences are confirmed, through this loader as through a subscription's refresh."""
    config = _exceptions(tmp_path, ["local_development"])
    with pytest.raises(ListRefused, match="licence is not confirmed"):
        parse_list(REAL, use="local_development", config_path=config)
    config = _exceptions(tmp_path, ["local_development"], dataset="un_consolidated")
    with pytest.raises(ListRefused, match="non-commercial use only"):
        parse_list({**REAL, "dataset": "un_consolidated"}, use="local_development", config_path=config)


# --- ADR-146 Amendment 7: a list's marking ------------------------------------------------------

_MARKED = {"list_name": "Marked", "synthetic": True,
           "entries": [{"id": "m-1", "listing": "sanction", "entity_type": "Person", "name": "Elena PETROVA"}]}  # fmt: skip


def test_a_lists_marking_is_carried_by_each_entry_and_an_unmarked_list_is_official_p() -> None:
    _, entries = parse_list({**_MARKED, "marking": {"classification": "SECRET", "handling_code": "P"}},
                            use="local_development")  # fmt: skip
    assert [(e.classification, e.handling_code) for e in entries] == [("SECRET", "P")]
    _, unmarked = parse_list(_MARKED, use="local_development")
    assert [(e.classification, e.handling_code) for e in unmarked] == [(None, None)]


@pytest.mark.parametrize(
    ("marking", "said"),
    [
        ({"classification": "RESTRICTED-ISH", "handling_code": "P"}, "is not a classification"),
        ({"classification": "SECRET", "handling_code": "Z9"}, "is not a handling code"),
        ({"classification": "SECRET"}, "names exactly"),
        ({"classification": "SECRET", "handling_code": "P", "caveat": "x"}, "names exactly"),
        ("SECRET", "names exactly"),
        # The lane review's item 11: a code restricted to one unit, which a list's matches,
        # written in the deployer's unit, cannot name.
        ({"classification": "OFFICIAL", "handling_code": "R"}, "restricts a list to one unit"),
    ],
)
def test_a_marking_the_scheme_does_not_define_is_refused_in_words(marking: object, said: str) -> None:
    with pytest.raises(ListRefused, match=said):
        parse_list({**_MARKED, "marking": marking}, use="local_development")


def test_a_change_of_marking_is_a_change_of_the_entry() -> None:
    """A refresh that re-marks a list re-screens its entries (`diff_entries`, by fingerprint)."""
    plain = LIST[0]
    marked = ScreeningEntry(**{**plain.__dict__, "classification": "SECRET", "handling_code": "P"})
    assert plain.fingerprint() != marked.fingerprint()


def test_a_rule_screens_only_against_the_lists_its_deployer_is_cleared_for() -> None:
    from services.api.kyc_rules import lists_cleared_for

    from ontology.handling import load_uk_le_scheme
    from schemas.domain import Principal

    marked = ScreeningEntry(**{**LIST[0].__dict__, "id": "s", "classification": "SECRET", "handling_code": "P"})
    entries = [LIST[0], marked]
    official = Principal(id="o", clearance="OFFICIAL", org_unit="u")
    secret = Principal(id="s", clearance="SECRET", org_unit="u")
    scheme = load_uk_le_scheme()
    assert [e.id for e in lists_cleared_for(entries, official, scheme)] == ["1"]
    assert [e.id for e in lists_cleared_for(entries, secret, scheme)] == ["1", "s"]


def test_a_marking_above_the_deployments_highest_is_refused_in_words() -> None:
    """The lane review's item 11: a deployment whose ceiling is OFFICIAL (ADR-148) never holds a
    SECRET list's matches."""
    from services.ingest.ceiling import DeploymentCeiling

    from ontology.handling import load_uk_le_scheme

    ceiling = DeploymentCeiling.of("OFFICIAL", load_uk_le_scheme())
    with pytest.raises(ListRefused, match="above this deployment's highest marking"):
        parse_list({**_MARKED, "marking": {"classification": "SECRET", "handling_code": "P"}},
                   use="local_development", ceiling=ceiling)  # fmt: skip
    _, entries = parse_list({**_MARKED, "marking": {"classification": "OFFICIAL", "handling_code": "P"}},
                            use="local_development", ceiling=ceiling)  # fmt: skip
    assert entries[0].classification == "OFFICIAL"
