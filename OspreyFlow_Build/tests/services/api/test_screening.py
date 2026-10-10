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


def _exceptions(tmp_path: Path, uses: list[str]) -> Path:
    path = tmp_path / "real_data_exceptions.yaml"
    path.write_text(yaml.safe_dump({"exceptions": [{
        "dataset": "opensanctions", "approved_uses": uses, "added_by": "owner",
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
    config = _exceptions(tmp_path, ["local_development"])
    _, entries = parse_list(REAL, use="local_development", config_path=config)
    assert [e.synthetic for e in entries] == [False]
    with pytest.raises(ListRefused):
        parse_list(REAL, use="owner_run_demonstration", config_path=config)
