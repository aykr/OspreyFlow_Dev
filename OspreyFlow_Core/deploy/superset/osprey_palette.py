"""A chart palette change reaching boards already drawn (`06_DECISIONS.md` ADR-111 Amendment 4).

Superset remembers the colour each label was first given on a dashboard (`map_label_colors`), and a
guest viewer cannot update it, so a board kept an old palette's colours after the palette changed.
`osprey_setup.py` calls this at every start: a remembered colour that is not in the current palette
is forgotten, and the next drawing deals it again from the palette. A colour a person chose for a
label (`label_colors`) is theirs and is never touched. Imports nothing of Superset, so it is tested
on its own.
"""

from __future__ import annotations

import json
from collections.abc import Sequence


def forget_stale_label_colours(
    json_metadata: str | None, palette: Sequence[str]
) -> str | None:
    """The metadata with stale remembered colours dropped, or None when nothing changes."""
    try:
        metadata = json.loads(json_metadata or "{}")
    except ValueError:
        return None
    remembered = metadata.get("map_label_colors") if isinstance(metadata, dict) else None
    if not isinstance(remembered, dict) or not remembered:
        return None
    current = {colour.lower() for colour in palette}
    kept = {label: colour for label, colour in remembered.items()
            if isinstance(colour, str) and colour.lower() in current}  # fmt: skip
    if kept == remembered:
        return None
    metadata["map_label_colors"] = kept
    return json.dumps(metadata)
