"""The link a write made, under the id the store gave it (ADR-102 Amendment 3, rules 3 and 7).

`GraphPort.upsert_edges` returns one id per write, in order, and it is not always the id sent: a
write merges into a link of its own audience and returns that link's id, and a write whose id a link
of another audience holds is a link of its own under a new id. A caller that puts a link on the
canvas, in a delta or in the change stream must name the link the store holds, so it builds them
from what was returned. One that kept the id it sent would name another audience's link there,
and the notes opened on it would be that audience's."""

from __future__ import annotations

from collections.abc import Sequence

from schemas.domain import EdgeId, EdgeWrite


def as_stored(writes: Sequence[EdgeWrite], stored_ids: Sequence[EdgeId]) -> list[EdgeWrite]:
    """`writes`, each under the id `upsert_edges` returned for it. The two are the same length by
    the port's contract; a store that returned fewer or more is a defect and raises."""
    return [w.model_copy(update={"id": i}) for w, i in zip(writes, stored_ids, strict=True)]
