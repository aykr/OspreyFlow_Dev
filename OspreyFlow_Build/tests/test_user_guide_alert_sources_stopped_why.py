"""The user guide's §7.5 sentence on *What raises alerts* and a stopped hotlist or watch (v0.6.0
#14), held to the code: the panel shows `stopped_why` under *Stopped* for a stopped row, the
inventory fills it for hotlists and watched patterns only, and a rule's row carries none (the
orchestrator's ruling, 15 November 2026). Red first: the guide's plant in
`process/lanes/rules/v060-i14-stopped-why/plants.py`."""

from __future__ import annotations

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_the_guide_says_what_raises_alerts_shows_why_and_a_rule_says_nothing_more() -> None:
    guide = _fold((CORE / "docs/user-guide.md").read_text(encoding="utf-8"))
    assert (
        "**What raises alerts** says the same words under *Stopped* beside each of your stopped "
        "hotlists and watched patterns." in guide
    )
    assert (
        "A rule there that is *Stopped* says nothing more, as a rule's retirement records "
        "no reason."
        in guide
    )


def test_the_code_does_what_the_guide_says() -> None:
    panel = _fold(
        (CORE / "apps/workspace/src/alerts/AlertSourcesPanel.tsx").read_text(encoding="utf-8")
    )
    assert 'key === "state" && s.state === "stopped" && s.stopped_why' in panel
    inventory = _fold((CORE / "services/api/alert_sources.py").read_text(encoding="utf-8"))
    assert 'stopped_why=hotlist.stopped_why if hotlist.status != "active" else None' in inventory
    assert 'stopped_why=monitor.stopped_why if monitor.status != "active" else None' in inventory
    rule_row = inventory[
        inventory.index("for rule in rules:") : inventory.index("for hotlist in hotlists:")
    ]
    assert "stopped_why" not in rule_row
