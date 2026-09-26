"""`scripts/real_data_exceptions.py` — its own docstring has the full mechanism and why the check
is a runtime one, not a CI gate."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from scripts.real_data_exceptions import (
    RealDataException,
    add_exception,
    is_permitted,
    load_exceptions,
    remove_exception,
)

#: `06_DECISIONS.md` ADR-049 Stage 2 §6, ruling 3 — every construction below names one, since the
#: field is required.
_DECISION_RECORD = "ADR-035 §C3"


def test_no_config_file_means_no_exceptions() -> None:
    """The default, fail-closed state: nothing is admitted until the owner adds it."""
    assert load_exceptions(config_path=Path("/nonexistent/real_data_exceptions.yaml")) == []


def test_a_dataset_not_in_the_config_is_not_permitted(tmp_path: Path) -> None:
    """Proves the gate is not vacuous — `CLAUDE.md` rule 12: name the test that would fail."""
    config = tmp_path / "real_data_exceptions.yaml"
    assert is_permitted("Some Corpus", "local_development", config_path=config) is False


def test_a_dataset_added_for_one_use_is_not_permitted_for_another(tmp_path: Path) -> None:
    config = tmp_path / "real_data_exceptions.yaml"
    add_exception(
        RealDataException(
            dataset="Test Corpus",
            approved_uses=("local_development",),
            added_by="tester",
            added_date=date(2026, 9, 23),
            device="test-host",
            justification="testing the mechanism",
            decision_record=_DECISION_RECORD,
        ),
        config_path=config,
    )
    assert is_permitted("Test Corpus", "local_development", config_path=config) is True
    assert is_permitted("Test Corpus", "owner_run_demonstration", config_path=config) is False


def test_matching_is_case_insensitive_on_the_dataset_name(tmp_path: Path) -> None:
    config = tmp_path / "real_data_exceptions.yaml"
    add_exception(
        RealDataException(
            dataset="Test Corpus",
            approved_uses=("scale_testing",),
            added_by="tester",
            added_date=date(2026, 9, 23),
            device="test-host",
            justification="testing the mechanism",
            decision_record=_DECISION_RECORD,
        ),
        config_path=config,
    )
    assert is_permitted("test corpus", "scale_testing", config_path=config) is True


def test_removing_an_exception_makes_it_no_longer_permitted(tmp_path: Path) -> None:
    config = tmp_path / "real_data_exceptions.yaml"
    add_exception(
        RealDataException(
            dataset="Test Corpus",
            approved_uses=("local_development",),
            added_by="tester",
            added_date=date(2026, 9, 23),
            device="test-host",
            justification="testing the mechanism",
            decision_record=_DECISION_RECORD,
        ),
        config_path=config,
    )
    assert remove_exception("Test Corpus", config_path=config) is True
    assert is_permitted("Test Corpus", "local_development", config_path=config) is False


def test_removing_a_dataset_not_present_returns_false(tmp_path: Path) -> None:
    config = tmp_path / "real_data_exceptions.yaml"
    assert remove_exception("Not There", config_path=config) is False


def test_adding_a_duplicate_dataset_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "real_data_exceptions.yaml"
    entry = RealDataException(
        dataset="Test Corpus",
        approved_uses=("local_development",),
        added_by="tester",
        added_date=date(2026, 9, 23),
        device="test-host",
        justification="testing the mechanism",
        decision_record=_DECISION_RECORD,
    )
    add_exception(entry, config_path=config)
    with pytest.raises(ValueError, match="already"):
        add_exception(entry, config_path=config)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dataset": ""},
        {"approved_uses": ()},
        {"approved_uses": ("not_a_real_use",)},
        {"added_by": ""},
        {"device": ""},
        {"justification": ""},
    ],
)
def test_an_incomplete_entry_is_rejected(kwargs: dict[str, object]) -> None:
    base = {
        "dataset": "Test Corpus",
        "approved_uses": ("local_development",),
        "added_by": "tester",
        "added_date": date(2026, 9, 23),
        "device": "test-host",
        "justification": "testing the mechanism",
        "decision_record": _DECISION_RECORD,
    }
    base.update(kwargs)
    with pytest.raises(ValueError):
        RealDataException(**base)  # type: ignore[arg-type]


def _entry_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "dataset": "Test Corpus",
        "approved_uses": ("local_development",),
        "added_by": "tester",
        "added_date": date(2026, 9, 23),
        "device": "test-host",
        "justification": "testing the mechanism",
        "decision_record": _DECISION_RECORD,
    }
    base.update(overrides)
    return base


def test_an_absent_decision_record_is_rejected() -> None:
    """`06_DECISIONS.md` ADR-049 Stage 2 §6, ruling 3's own "seventh required field" — the absent
    case, shown to fail closed the same way every other required field already does."""
    with pytest.raises(ValueError, match="decision_record must not be empty"):
        RealDataException(**_entry_kwargs(decision_record=""))


@pytest.mark.parametrize(
    "malformed",
    [
        "not an adr reference at all",
        "ADR-35",  # two digits, not three
        "ADR-0355",  # four digits, not three
        "035",  # no ADR- prefix
        "ADR035",  # no hyphen
        "ADR-035 C3",  # missing the § before the section
    ],
)
def test_a_malformed_decision_record_is_rejected(malformed: str) -> None:
    """The format-only check, ruling 3's own literal shape ('ADR-' + three digits, optional
    ' §<section>') — each case here is a plausible near-miss a real operator might type, not an
    arbitrary string, the same "planted violation takes the real shape" discipline `CLAUDE.md`
    rule 15 asks for."""
    with pytest.raises(ValueError, match="decision_record"):
        RealDataException(**_entry_kwargs(decision_record=malformed))


@pytest.mark.parametrize("wellformed", ["ADR-035", "ADR-035 §C3", "ADR-001 §A"])
def test_a_well_formed_decision_record_is_accepted(wellformed: str) -> None:
    entry = RealDataException(**_entry_kwargs(decision_record=wellformed))
    assert entry.decision_record == wellformed


def test_an_entry_with_an_absent_decision_record_fails_closed_in_is_permitted(
    tmp_path: Path,
) -> None:
    """The end-to-end case ruling 3 itself names: an entry already on disk (however it got there)
    with no `decision_record` at all must not silently permit — `load_exceptions` (which
    `is_permitted` calls) raises the identical `ValueError` reconstructing it would, rather than
    returning a principal-shaped `True`."""
    config = tmp_path / "real_data_exceptions.yaml"
    config.write_text(
        """
exceptions:
  - dataset: "Test Corpus"
    approved_uses: [local_development]
    added_by: tester
    added_date: "2026-09-23"
    device: test-host
    justification: testing the mechanism
""",
        encoding="utf-8",
    )
    with pytest.raises(KeyError, match="decision_record"):
        is_permitted("Test Corpus", "local_development", config_path=config)


def test_an_entry_with_a_malformed_decision_record_fails_closed_in_is_permitted(
    tmp_path: Path,
) -> None:
    config = tmp_path / "real_data_exceptions.yaml"
    config.write_text(
        """
exceptions:
  - dataset: "Test Corpus"
    approved_uses: [local_development]
    added_by: tester
    added_date: "2026-09-23"
    device: test-host
    justification: testing the mechanism
    decision_record: "not-a-real-reference"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="decision_record"):
        is_permitted("Test Corpus", "local_development", config_path=config)


def test_the_real_local_config_is_not_committed() -> None:
    """The mechanism's own guarantee: a clone of this repository never contains the config file
    itself, only the schema example. If this test fails, something committed the real file."""
    real_config = Path(__file__).resolve().parents[1] / "config" / "real_data_exceptions.yaml"
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(real_config)],
        capture_output=True,
        cwd=real_config.parent.parent,
    )
    assert tracked.returncode != 0, (
        "config/real_data_exceptions.yaml must never be committed -- found it tracked by git"
    )
