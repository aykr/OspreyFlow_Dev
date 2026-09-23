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
    }
    base.update(kwargs)
    with pytest.raises(ValueError):
        RealDataException(**base)  # type: ignore[arg-type]


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
