"""`scripts.make_home_cases` (ADR-145 Amendment 4 decision 2; L3.1b step 4), in memory.

What a mistake here would do, and the case that catches it:

- a dataset left with no home case: `test_every_dataset_but_a_layer_gets_one`;
- a service account, or an account the directory cannot vouch for, made a home case's Author
  (ADR-112 Amendment 5): `test_a_person_who_made_the_dataset_is_its_author_and_no_one_else_is`, red
  with every `created_by` taken as a person
  (`test_the_author_check_fails_with_every_maker_taken_as_a_person`);
- with no directory to ask, a guess made: `test_with_no_directory_every_home_case_needs_an_owner`;
- a second home case on a second run: `test_a_dataset_with_a_home_case_is_kept`;
- a dry run that plans other writes than the real run makes:
  `test_the_dry_run_plans_what_the_real_run_makes`.
"""

from __future__ import annotations

from typing import Any

from scripts.make_home_cases import DatasetRow, DryRun, Report, make_homes

DATASETS = [
    DatasetRow("ds-prison", "Prison records", "unit-1", "source", "d.engineer"),
    DatasetRow("ds-bank", "Bank records", "unit-1", "source", "service-account-loader"),
    DatasetRow("ds-gone", "Old records", "unit-1", "source", "left-the-unit"),
    DatasetRow("comp-both", "Bank + Prison", "unit-1", "composite", "d.engineer"),
    DatasetRow("layer-1", "A case's layer", "unit-1", "analyst_layer", "d.engineer"),
]
PERSONS = {"d.engineer"}


class _Made:
    """Records each home case made and who was made its Author."""

    def __init__(self) -> None:
        self.made: dict[str, str | None] = {}

    async def make(self, dataset: DatasetRow, author: str | None) -> None:
        self.made[dataset.id] = author


async def _run(persons: Any = PERSONS, with_a_home: Any = ()) -> tuple[_Made, Report]:
    made = _Made()
    report = await make_homes(DATASETS, set(with_a_home), persons, through=made, say=lambda _: None)
    return made, report


async def test_every_dataset_but_a_layer_gets_one() -> None:
    made, _ = await _run()
    assert set(made.made) == {"ds-prison", "ds-bank", "ds-gone", "comp-both"}


async def test_a_person_who_made_the_dataset_is_its_author_and_no_one_else_is() -> None:
    made, report = await _run()
    assert made.made == {
        "ds-prison": "d.engineer", "comp-both": "d.engineer", "ds-bank": None, "ds-gone": None,
    }  # fmt: skip
    assert report.needs_an_owner == ["Bank records (ds-bank)", "Old records (ds-gone)"]


async def test_the_author_check_fails_with_every_maker_taken_as_a_person() -> None:
    """Rule 15, red: a directory answering everyone a person makes the service account an
    Author."""
    made, _ = await _run(persons={d.created_by for d in DATASETS})
    assert made.made["ds-bank"] == "service-account-loader"


async def test_with_no_directory_every_home_case_needs_an_owner() -> None:
    made, report = await _run(persons=None)
    assert set(made.made.values()) == {None}
    assert len(report.needs_an_owner) == 4


async def test_a_dataset_with_a_home_case_is_kept() -> None:
    made, report = await _run(with_a_home=["ds-prison", "ds-bank", "ds-gone", "comp-both"])
    assert made.made == {} and len(report.kept) == 4


async def test_the_dry_run_plans_what_the_real_run_makes() -> None:
    """Four writes per dataset either way: the case, what it reads, its grants, the link."""
    report = Report()
    lines: list[str] = []
    await make_homes(
        DATASETS, set(), PERSONS, through=DryRun(report.writes), report=report, say=lines.append
    )
    assert len(report.writes) == 4 * 4
    assert any(
        "Prison records (ds-prison): home case made, its Author d.engineer" in x for x in lines
    )
    assert any("2 home cases need an owner" in x for x in lines)
