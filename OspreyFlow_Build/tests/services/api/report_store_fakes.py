"""A stand-in for the part of the alert store the report's `withheld` flag asks about (SE8b).

`AlertStore.left_out_by_reach` is true when the reader's dataset reach takes an alert out of the
queue. It is false for a reader with no dataset limit, so a test whose reader has none can say so
with this, and a test of the flag with a limit uses a store that drops the alert and says so from
the one filter (`test_report_figures_withheld._ReachStore`).
"""

from __future__ import annotations

from typing import Any


class UnlimitedReachAlerts:
    """An alert store for a reader with no dataset limit: reach removes nothing."""

    async def left_out_by_reach(self, investigation_id: str, reader: Any) -> bool:
        return False
