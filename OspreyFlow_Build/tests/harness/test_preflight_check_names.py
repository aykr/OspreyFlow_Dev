"""The set-up console lists the preflight checks before their results arrive, in `harness.preflight.
ALL_CHECKS`'s own order (`apps/harness/src/screens/PreflightScreen.tsx`, `CHECK_NAMES`: "kept identical").
Nothing held the two together, so a check added to `ALL_CHECKS` (gate-b's `access-key`, ADR-114
Amendment 41) was missing from the console's list, and from `test_webapp_preflight.py`'s, which runs on
the server alone and so went red first on GitHub (run 43385169520). This needs no Docker."""

from __future__ import annotations

import re

from harness.preflight import ALL_CHECKS
from tools.layout import CORE

SCREEN = CORE / "apps" / "harness" / "src" / "screens" / "PreflightScreen.tsx"


def test_the_set_up_console_lists_every_check_in_all_checks_order() -> None:
    text = SCREEN.read_text(encoding="utf-8")
    listed = re.search(r"const CHECK_NAMES = \[(.*?)\] as const;", text, re.S)
    assert listed, "no CHECK_NAMES in PreflightScreen.tsx"
    assert re.findall(r'"([a-z-]+)"', listed.group(1)) == [check.NAME for check in ALL_CHECKS]
