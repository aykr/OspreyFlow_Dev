"""The provenance entries a link's successor must not carry (ADR-124 decision 11).

A link changed through `LinkChangeService`, or a picture removed through `EntityPictureService`,
is written as a successor of the old link. Until U10 its provenance named the old link's id
(`manual:change:<old id>`, `manual:remove-picture:<old id>`). Provenance is part of the body every
reader of the successor is sent, so it named a link the reader may not be able to read (rule 3).
The lineage lives in the link-change store, where link history filters it per reader.

A successor's own change is recorded under the bare marker (`manual:change`,
`manual:remove-picture`), which names nothing. It keeps the old link's document sources, which are
the evidence for the link; whether a source naming a document is itself a referent is ADR-125's.
"""

from __future__ import annotations

from collections.abc import Sequence

from schemas.domain import SourceRef

CHANGE_MARKER = "manual:change"
PICTURE_MARKER = "manual:remove-picture"

#: The two prefixes that carried an old link's id. `scripts/strip_change_provenance.py` strips
#: each, from the Vault and from every working set's stored copies.
ID_BEARING_PREFIXES = (f"{CHANGE_MARKER}:", f"{PICTURE_MARKER}:")


def carries_a_link_id(document_id: str) -> bool:
    return document_id.startswith(ID_BEARING_PREFIXES)


def without_link_ids(sources: Sequence[SourceRef]) -> list[SourceRef]:
    """`sources` with every entry that names an earlier link removed: nothing an earlier revision
    wrote about its predecessor is carried into a new successor."""
    return [s for s in sources if not carries_a_link_id(s.document_id)]
