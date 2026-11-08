"""Phase 6's exit (ADR-140 Amendment 10): the keyboard case that builds chapter 4's *Intelligence
reports* map from scratch asserts its saved map equals `keyboard/fixtures/pid_intel_reports_map.json`,
since the workspace reads no YAML. This holds that copy to the committed recipe, so the keyboard case
is proving the real map and not a copy that has drifted from it."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
RECIPE = CORE / "packages/demo_fixtures/pid_intel_reports_recipe.yaml"
COPY = CORE / "apps/workspace/keyboard/fixtures/pid_intel_reports_map.json"
PARTS = ("row_template", "unmapped_fields", "deduplicate")


def _differences(recipe: dict, copy: dict) -> list[str]:
    return [part for part in PARTS if recipe.get(part) != copy.get(part)]


def test_the_keyboard_copy_is_the_committed_map() -> None:
    recipe = yaml.safe_load(RECIPE.read_text())
    copy = json.loads(COPY.read_text())
    assert len(recipe["row_template"]["entities"]) == 11
    assert len(recipe["row_template"]["edges"]) == 10
    assert _differences(recipe, copy) == []


def test_a_copy_differing_by_one_condition_is_caught() -> None:
    """Rule 15: the comparison is shown red on the shape it really reads, one link's condition."""
    recipe = yaml.safe_load(RECIPE.read_text())
    copy = json.loads(COPY.read_text())
    copy["row_template"]["edges"][3].pop("when")
    assert _differences(recipe, copy) == ["row_template"]
