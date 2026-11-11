"""`process/lanes/groups.tsv` gives every `progress.tsv` row exactly one feature group and one deployment group
(the owner, 11 November 2026), the two views `lanes_heartbeat.sh` shows by default.

Rule 15: each way the check can fail is planted in a copy of the real files, in the shape they have (a row cut,
a row repeated with other groups, a step renamed, a value misspelt), and the check is asserted to name it.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

LANES = Path(__file__).resolve().parents[1] / "process" / "lanes"
PROGRESS = LANES / "progress.tsv"
GROUPS = LANES / "groups.tsv"


def _rows(text: str) -> list[list[str]]:
    return [line.split("\t") for line in text.splitlines() if line.strip() and not line.startswith("#")]


def _allowed(groups_text: str, heading: str) -> set[str]:
    for line in groups_text.splitlines():
        if line.startswith(f"# {heading}: "):
            return {value.strip() for value in line.split(": ", 1)[1].split(" | ")}
    return set()


def problems(progress_text: str, groups_text: str) -> list[str]:
    """Every way the two files disagree, one line each; an empty list when every row has its two groups."""
    found: list[str] = []
    features, deployments = _allowed(groups_text, "Feature"), _allowed(groups_text, "Deployment")
    if not features or not deployments:
        found.append("groups.tsv's header does not list the allowed Feature and Deployment values")
    steps = [(row[0], row[1]) for row in _rows(progress_text) if len(row) >= 4]
    grouped: Counter[tuple[str, str]] = Counter()
    for row in _rows(groups_text):
        if len(row) != 4:
            found.append(f"groups.tsv row {' / '.join(row)} has {len(row)} columns, not 4")
            continue
        lane, step, feature, deployment = row
        grouped[(lane, step)] += 1
        if feature not in features:
            found.append(f"{lane} {step}: feature '{feature}' is not an allowed value")
        if deployment not in deployments:
            found.append(f"{lane} {step}: deployment '{deployment}' is not an allowed value")
    for key in steps:
        if grouped[key] == 0:
            found.append(f"{key[0]} {key[1]} has no group in groups.tsv")
        elif grouped[key] > 1:
            found.append(f"{key[0]} {key[1]} has {grouped[key]} rows in groups.tsv, not one")
    for key in grouped:
        if key not in set(steps):
            found.append(f"groups.tsv names {key[0]} {key[1]}, which progress.tsv lacks")
    return found


def _real() -> tuple[str, str]:
    return PROGRESS.read_text(encoding="utf-8"), GROUPS.read_text(encoding="utf-8")


def test_every_step_has_exactly_one_feature_and_one_deployment() -> None:
    assert problems(*_real()) == []


def test_a_step_with_no_group_is_named() -> None:
    progress, groups = _real()
    cut = "case-b\tP12\tLaurium\tClient install\n"
    assert cut in groups
    assert problems(progress, groups.replace(cut, "")) == ["case-b P12 has no group in groups.tsv"]


def test_a_step_grouped_twice_is_named() -> None:
    progress, groups = _real()
    again = "case-b\tP12\tModels and maps\tClient install\n"
    assert problems(progress, groups + again) == ["case-b P12 has 2 rows in groups.tsv, not one"]


def test_a_step_with_a_second_feature_column_is_named() -> None:
    progress, groups = _real()
    row = "case-b\tP12\tLaurium\tClient install\n"
    found = problems(progress, groups.replace(row, "case-b\tP12\tLaurium\tModels and maps\tClient install\n"))
    assert "groups.tsv row case-b / P12 / Laurium / Models and maps / Client install has 5 columns, not 4" in found
    assert "case-b P12 has no group in groups.tsv" in found


def test_a_step_progress_lacks_is_named() -> None:
    progress, groups = _real()
    assert problems(progress, groups + "case-b\tP13\tLaurium\tClient install\n") == [
        "groups.tsv names case-b P13, which progress.tsv lacks"
    ]


def test_the_same_step_code_in_another_lane_is_a_different_row() -> None:
    """`carries` is a step of platform-b and of studio: a lane-blind check would let one row stand for both."""
    progress, groups = _real()
    cut = "studio\tcarries\tIngest Studio\tSmall\n"
    assert cut in groups
    assert problems(progress, groups.replace(cut, "")) == ["studio carries has no group in groups.tsv"]


def test_a_value_outside_the_lists_is_named() -> None:
    progress, groups = _real()
    row = "case-b\tP12\tLaurium\tClient install\n"
    assert problems(progress, groups.replace(row, "case-b\tP12\tLaurium\tClient Install\n")) == [
        "case-b P12: deployment 'Client Install' is not an allowed value"
    ]
    assert problems(progress, groups.replace(row, "case-b\tP12\tLaurium engine\tClient install\n")) == [
        "case-b P12: feature 'Laurium engine' is not an allowed value"
    ]
