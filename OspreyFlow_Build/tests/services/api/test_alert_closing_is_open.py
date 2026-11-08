"""A proposed close is still open (`06_DECISIONS.md` ADR-146 decision 6, gap map
G9): a high-severity alert proposed for closing waits for a second person (ADR-133 decision 7) and
counts as open on Home, the banner's Monitoring count and in trends. Home and the banner are the
Glass's (`homeData.test.ts`, `App.chrome.test.tsx`); trends read each alert's fact, whose outcome
is written here.

Red with `closing` left out: an `_outcome` that read anything not open or claimed as decided gave a
proposed close its proposed disposition, so a trend counted it closed (shown by hand, L2.8).
"""

from __future__ import annotations

import pytest
from services.api.alerts import _outcome


@pytest.mark.parametrize("proposed", [None, "false_positive", "true_positive", "referred"])
def test_a_proposed_close_is_open_in_trends(proposed: str | None) -> None:
    assert _outcome("closing", proposed) == "open"


def test_the_other_statuses_keep_their_outcome() -> None:
    assert _outcome("open", None) == "open"
    assert _outcome("claimed", None) == "claimed"
    assert _outcome("closed", "false_positive") == "false_positive"
    assert _outcome("closed", None) == "closed"
