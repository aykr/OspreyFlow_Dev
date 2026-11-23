"""A stand-in for the part of the alert store the report's `withheld` flag asks about (SE8b).

`AlertStore.left_out_on_borrowed_layer` is true when the reader's rights leave a borrowed layer out
of their read set and an alert of theirs is on it. It is false for a reader with no dataset limit or
a case that borrows no layer, so a test whose reader has none can say so with this; a test of the
flag itself runs the real store (`test_report_figures_withheld._PostgresRefusingPool`).
"""

from __future__ import annotations

from typing import Any


class UnlimitedReachAlerts:
    """An alert store for a reader whose rights leave out no borrowed layer."""

    async def left_out_on_borrowed_layer(
        self, investigation_id: str, reader: Any, borrowed: str | None
    ) -> bool:
        return False
