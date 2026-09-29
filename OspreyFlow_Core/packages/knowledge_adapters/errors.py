"""The one error shape every Knowledge Adapter raises — `01_DOMAIN_MODEL.md`
§7: reject rather than guess, consistently. A datetime with no recoverable
offset and a value that fails its check digit fail the same way — a named
rejection, never a silent coercion — so the ingest pipeline can group
rejections by cause and report a count (`09_INGEST_STUDIO.md` §5, Stage 4)
without each adapter inventing its own exception shape.
"""

from __future__ import annotations


class NormalisationError(Exception):
    """Raised by a Knowledge Adapter when it cannot produce a canonical
    value. `adapter` and `reason` are what the ingest report groups
    rejections by; `raw` is retained for the sample the report shows
    alongside the count — never for the rejected row to be silently
    coerced from it."""

    def __init__(self, adapter: str, raw: str, reason: str) -> None:
        self.adapter = adapter
        self.raw = raw
        self.reason = reason
        super().__init__(f"{adapter}: cannot normalise {raw!r} — {reason}")
