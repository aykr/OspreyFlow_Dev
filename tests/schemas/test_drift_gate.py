"""Proves the schemas-check drift gate is sensitive to real change — Phase 0
exit criterion 3 (`docs/07_BUILD_PLAN.md`): a Pydantic model change not
reflected in the generated TypeScript fails the build.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from schemas_check import diff_against_committed  # noqa: E402

from schemas._phase0_placeholders import ALL_MODELS  # noqa: E402


def test_committed_generated_types_match_current_models() -> None:
    assert diff_against_committed(ALL_MODELS) == []


def test_drift_gate_detects_a_changed_model() -> None:
    mutated = list(ALL_MODELS)
    index = next(i for i, m in enumerate(mutated) if m.__name__ == "NodeWrite")
    changed_node_write = type(
        "NodeWrite",
        (BaseModel,),
        {"__annotations__": {"a_field_absent_from_committed_output": str}},
    )
    mutated[index] = changed_node_write

    differing = diff_against_committed(mutated)

    assert "NodeWrite.ts" in differing
