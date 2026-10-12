"""A palette change reaches boards already drawn (`06_DECISIONS.md` ADR-111 Amendment 4).

Superset remembers the colour each label was first given on a dashboard (`map_label_colors` in its
metadata), and a guest viewer cannot update it — so after the chart palette changed, the Compliance
board went on drawing the old colours (found live, 12 October 2026). Superset's start forgets every
remembered colour that is not in the current palette, so the next drawing deals them again; a
colour a person chose for a label (`label_colors`) is theirs and is kept.

What a mistake would do, and the case that catches it:
- an old palette's colour kept — `test_colours_outside_the_palette_are_forgotten`;
- a person's own choice lost, or a current colour reshuffled —
  `test_a_chosen_colour_and_a_current_one_are_kept`;
- a board written although nothing changed — `test_nothing_to_forget_changes_nothing`.
"""

from __future__ import annotations

import importlib.util
import json

from tools.layout import CORE

_spec = importlib.util.spec_from_file_location(
    "osprey_palette", CORE / "deploy" / "superset" / "osprey_palette.py"
)
assert _spec and _spec.loader
osprey_palette = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(osprey_palette)

PALETTE = ["#2290c8", "#ac4a06", "#369974"]


def test_colours_outside_the_palette_are_forgotten() -> None:
    metadata = json.dumps({"map_label_colors": {"high": "#3682b2", "low": "#83330d"}, "x": 1})
    changed = osprey_palette.forget_stale_label_colours(metadata, PALETTE)
    assert changed is not None
    assert json.loads(changed) == {"map_label_colors": {}, "x": 1}


def test_a_chosen_colour_and_a_current_one_are_kept() -> None:
    metadata = json.dumps({
        "label_colors": {"high": "#123456"},
        "map_label_colors": {"high": "#3682B2", "medium": "#369974"},
    })  # fmt: skip
    changed = json.loads(osprey_palette.forget_stale_label_colours(metadata, PALETTE) or "{}")
    assert changed["label_colors"] == {"high": "#123456"}
    assert changed["map_label_colors"] == {"medium": "#369974"}


def test_nothing_to_forget_changes_nothing() -> None:
    assert osprey_palette.forget_stale_label_colours(
        json.dumps({"map_label_colors": {"medium": "#369974"}}), PALETTE
    ) is None
    assert osprey_palette.forget_stale_label_colours("", PALETTE) is None
    assert osprey_palette.forget_stale_label_colours("{}", PALETTE) is None
