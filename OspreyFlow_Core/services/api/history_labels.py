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
#: ADR-128 decision 3: an edit to the case brief (its priority, a requirement's text or status, a
#: requirement added or removed). One text for all of them: it says that the brief changed, never
#: what it said. An attach or a detach is not a step (`case_brief.py`: a step is shown to every
#: reader, and one for an attachment the reader may not read would be a trace of it).
BRIEF_EDITED = "Edited the brief"

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
        BRIEF_EDITED,
    }
)

#: Steps that hold no canvas snapshot, so restoring one would replace the canvas with nothing. The
#: listing marks them `restorable: false` and the restore route refuses them.
NOT_RESTORABLE = frozenset({BRIEF_EDITED})
