"""The drift gate `07_BUILD_PLAN.md`'s Phase 8 documentation-refresh entry names:
`scripts/demo_guide_check.py`'s own docstring has the full reasoning for why `DEMO_REGISTRY` is a
stand-in for ADR-035's own still-unbuilt fail-closed registry, not the real thing.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from demo_guide_check import DEMO_GUIDE_PATH, DEMO_REGISTRY, find_undocumented  # noqa: E402


def test_every_registered_demo_is_documented_with_its_distribution_class() -> None:
    guide_text = DEMO_GUIDE_PATH.read_text(encoding="utf-8")
    missing = find_undocumented(guide_text)
    assert missing == [], (
        f"{DEMO_GUIDE_PATH.name} is missing a name or distribution-class marker for: {missing} "
        "— a demo was added or reclassified without the guide being updated to match."
    )


def test_the_check_fails_for_a_registered_demo_the_guide_does_not_document() -> None:
    """Proves the gate is not vacuous — `CLAUDE.md` rule 12: name the test that would fail."""
    guide_text = DEMO_GUIDE_PATH.read_text(encoding="utf-8")
    registry_plus_one = (*DEMO_REGISTRY, ("Totally Fictional Demo XYZ", "shipped"))

    missing = find_undocumented(guide_text, registry_plus_one)

    assert missing == ["Totally Fictional Demo XYZ"]


def test_the_check_fails_for_a_registered_demo_documented_with_no_distribution_class() -> None:
    guide_text = "This guide mentions Totally Fictional Demo XYZ but never says which class it is."
    registry = (("Totally Fictional Demo XYZ", "shipped"),)

    missing = find_undocumented(guide_text, registry)

    assert missing == ["Totally Fictional Demo XYZ"]
