"""The scale cohort's paste list (ADR-127 Amendment 40, "The paste list").

`pid_plan.scale_bulk_list(plan)` lists the scale plan's 3,000 prisoners' numbers, and
`python -m scripts.write_pid_files --profile scale` writes them as `scale_cohort_list.txt`, for the
add-many route (under its 5,000 cap). The figures are asserted from the plan, not from the list,
so a list that drifts from the plan goes red. The demo profile's output is unchanged: it still
writes `pid_cohort_list.txt` and no scale file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from demo_fixtures import pid_files, pid_plan


@pytest.fixture(scope="module")
def demo() -> Any:
    return pid_plan.build_plan("demo")


@pytest.fixture(scope="module")
def scale() -> Any:
    return pid_plan.build_plan("scale")


def _prisoner_numbers(plan: Any) -> set[str]:
    return {
        str(e.properties["prison_number"])
        for e in plan.entities
        if e.entity_type == "Person" and "prison_number" in e.properties
    }


def test_the_scale_list_is_3000_distinct_numbers_each_a_prisoner_of_the_scale_plan(
    scale: Any,
) -> None:
    listed = pid_plan.scale_bulk_list(scale)
    assert len(listed) == 3_000 == len(set(listed))
    assert set(listed) == _prisoner_numbers(scale)
    assert len(_prisoner_numbers(scale)) == 3_000


def test_the_scale_list_is_in_a_stable_order(scale: Any) -> None:
    listed = pid_plan.scale_bulk_list(scale)
    assert list(listed) == sorted(listed)
    assert pid_plan.scale_bulk_list(pid_plan.build_plan("scale")) == listed


def test_the_scale_list_is_refused_for_the_demo_plan(demo: Any) -> None:
    """The demo's own list is `bulk_list`, landing F2's prisoners; this one is the scale plan's."""
    with pytest.raises(ValueError, match="scale"):
        pid_plan.scale_bulk_list(demo)


def test_the_scale_files_include_the_list_one_number_a_line(scale: Any, tmp_path: Path) -> None:
    report = pid_files.write_files(scale, tmp_path)
    path = tmp_path / "scale_cohort_list.txt"
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n") and "\r" not in text
    assert text.splitlines() == list(pid_plan.scale_bulk_list(scale))
    assert [entry.name for entry in report.lists] == ["scale_cohort_list.txt"]
    assert report.lists[0].rows == 3_000
    assert not (tmp_path / pid_files.COHORT_LIST).exists()
    assert '"scale_cohort_list.txt"' in report.manifest


def test_the_demo_files_still_write_only_their_own_list(demo: Any, tmp_path: Path) -> None:
    report = pid_files.write_files(demo, tmp_path)
    assert [entry.name for entry in report.lists] == [pid_files.COHORT_LIST]
    assert (tmp_path / pid_files.COHORT_LIST).is_file()
    assert not (tmp_path / "scale_cohort_list.txt").exists()
