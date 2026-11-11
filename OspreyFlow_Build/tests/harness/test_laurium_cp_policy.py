"""`make cp-policy-check`'s rules on all three cloud-platform shapes with Laurium rendered (P12 part 2's
brief, exit 2; the lane-reviewer's item 10): platform's development and production fixtures name
`deep_read`, so each fixture is checked here with Laurium chosen, and Laurium's Deployment is
asserted present, so a pass is not a pass for want of Laurium.

Needs Docker (Helm's pinned image, `tools.helm_chart`): run on the test server, never on the Mac.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from tools.cp_policy_check import FIXTURES, check, render


@pytest.mark.parametrize("name", ["development", "production", "production-bedrock"])
def test_the_platforms_rules_hold_with_laurium_rendered(name: str, tmp_path: Path) -> None:
    raw: dict[str, Any] = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text("utf-8"))
    raw["models"] = {**raw.get("models", {}), "extraction_engine": "laurium"}
    config = tmp_path / "osprey.yaml"
    config.write_text(yaml.safe_dump(raw, sort_keys=False), "utf-8")
    target = render(config)
    rendered = yaml.safe_load(target.values)
    assert "laurium" in {w["name"] for w in rendered["workloads"]}, "Laurium was not rendered"
    count, violations = check(target)
    assert count > 0
    assert [str(v) for v in violations] == []
