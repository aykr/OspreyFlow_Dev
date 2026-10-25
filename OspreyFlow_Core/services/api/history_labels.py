"""The labels of a case's history steps (ADR-124 decision 8): fixed text, one per write site.

A label holds no number and no name. It is shown to anyone who can see the case and it is stored
beside an unfiltered snapshot, so a label that said how many nodes a step added, or which case or
alert it came from, would be a figure for the case's contents that the reader may not be entitled
to (rules 3 and 7). Each site in `app.py` names one of these and computes nothing.

`CHANGED` is not the label of a site. It is what `history.py`'s rewrite of stored labels gives a
label that matches no pattern.
"""

from __future__ import annotations

BRANCHED = "Branched"
SEEDED = "Seeded"
EXPANDED = "Expanded"
LINKS_AMONG = "Showed links among the view"
REMOVED = "Removed"
STARTER_QUESTION = "Ran a starter question"
SHARED_CONTACTS = "Showed two who share contacts"
OPENED_FROM_ALERT = "Opened from an alert"
OWNERSHIP = "Showed an ownership structure"
ALERT_CANVAS = "Opened an alert"

CHANGED = "Changed"

#: The labels a write site may use.
FIXED_LABELS = frozenset(
    {
        BRANCHED,
        SEEDED,
        EXPANDED,
        LINKS_AMONG,
        REMOVED,
        STARTER_QUESTION,
        SHARED_CONTACTS,
        OPENED_FROM_ALERT,
        OWNERSHIP,
        ALERT_CANVAS,
    }
)
