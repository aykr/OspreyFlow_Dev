"""ADR-053 point 2 and Amendment 1: the Enron seed refuses unless *all three* conditions hold
(an exceptions entry for this dataset and use, the corpus provisioned, a checkout), and nothing
else selects it. Each test names the refusal it proves; the planted-fault runs are in the build log.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from scripts import real_data_exceptions as rde
from scripts.seed_enron import (
    DATASET,
    FOLDER,
    USE,
    NotProvisionedError,
    _parse_args,
    authorise,
    permitted_here,
)


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    (tmp_path / FOLDER / "smith-a" / "sent").mkdir(parents=True)
    return tmp_path


def _args(corpus: Path, *extra: str) -> object:
    return _parse_args(["--case-name", "Enron", "--data-dir", str(corpus), *extra])


def test_it_refuses_with_no_exceptions_entry(corpus: Path) -> None:
    with pytest.raises(NotProvisionedError, match="exceptions"):
        authorise(_args(corpus), in_checkout=True, permitted=lambda: False)  # type: ignore[arg-type]


def test_it_refuses_when_the_corpus_is_not_provisioned(tmp_path: Path) -> None:
    with pytest.raises(NotProvisionedError, match="not provisioned"):
        authorise(_args(tmp_path), in_checkout=True, permitted=lambda: True)  # type: ignore[arg-type]


def test_it_refuses_from_a_bundle_with_everything_else_in_place(corpus: Path) -> None:
    with pytest.raises(NotProvisionedError, match="checkout"):
        authorise(_args(corpus), in_checkout=False, permitted=lambda: True)  # type: ignore[arg-type]


def test_with_all_three_it_returns_the_corpus_folder(corpus: Path) -> None:
    assert authorise(_args(corpus), in_checkout=True, permitted=lambda: True) == corpus / FOLDER  # type: ignore[arg-type]


def _entry(dataset: str, uses: tuple[str, ...]) -> rde.RealDataException:
    return rde.RealDataException(
        dataset=dataset,
        approved_uses=uses,
        added_by="owner",
        added_date=date(2026, 9, 30),
        device="this-machine",
        justification="owner-run demonstration on the owner's own machine",
        decision_record="ADR-053",
    )


def test_an_entry_for_another_dataset_or_another_use_does_not_permit_it(tmp_path: Path) -> None:
    """Catches a check that matches any entry, or ignores which use was approved."""
    config = tmp_path / "exceptions.yaml"
    rde.add_exception(_entry("some-other-corpus", (USE,)), config_path=config)
    assert permitted_here(config_path=config) is False
    rde.add_exception(_entry(DATASET, ("local_development",)), config_path=config)
    assert permitted_here(config_path=config) is False
    rde.add_exception(_entry("enron-extra", (USE,)), config_path=config)
    assert permitted_here(config_path=config) is False


def test_an_entry_for_this_dataset_and_use_permits_it(tmp_path: Path) -> None:
    config = tmp_path / "exceptions.yaml"
    rde.add_exception(_entry(DATASET, (USE,)), config_path=config)
    assert permitted_here(config_path=config) is True


def test_a_missing_exceptions_file_is_a_refusal_not_a_crash(tmp_path: Path) -> None:
    assert permitted_here(config_path=tmp_path / "none.yaml") is False


def test_a_container_run_takes_the_hosts_attestations() -> None:
    """The container has no `.git` and no exceptions file, so the host checks both and says so."""
    args = _parse_args(
        ["--case-name", "x", "--attested-checkout", "--attested-permission", "--grant", "a=author"]
    )
    assert args.attested_checkout and args.attested_permission
    plain = _parse_args(["--case-name", "x"])
    assert not plain.attested_checkout and not plain.attested_permission


def test_a_case_name_is_required() -> None:
    with pytest.raises(SystemExit):
        _parse_args([])


def test_the_enron_seed_can_resume_and_refuses_a_second_events_load() -> None:
    """The same protections as PaySim's: an interrupted graph write can be resumed, and events are
    never loaded twice (ADR-055 Amendment 3)."""
    assert _parse_args(["--case-name", "x", "--resume"]).resume is True
    assert _parse_args(["--case-name", "x"]).resume is False
    from scripts import seed_enron, seed_support

    assert seed_enron.write_graph is seed_support.write_graph
    assert seed_enron.events_already_loaded is seed_support.events_already_loaded
