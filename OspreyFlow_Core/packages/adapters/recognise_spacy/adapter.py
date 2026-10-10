"""`RecognisePort` on spaCy (MIT), in process — `06_DECISIONS.md` ADR-108 phase D, ruling Q3.

Unlike the Stanza sidecar this runs in the calling process: the pipeline (`en_core_web_sm` by
default, pinned into the venv, no network at call time) loads once per adapter and is reused.
spaCy's own tag set already matches the conformance suite's canonical core (PERSON, ORG, GPE), so
no label is renamed. A text past the limit is refused whole, never read in part (rule 2).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ports.recognise import RecognisedEntity, RecogniseResult, RecogniserRefusedError

#: The same ceiling the ner sidecar holds: past it the text is refused, never cut (rule 2).
MAX_CHARS = 100_000


@dataclass
class RecogniseSpacyAdapter:
    pipeline_name: str = "en_core_web_sm"
    _nlp: Any = field(default=None, repr=False)

    def _load(self) -> Any:
        if self._nlp is None:
            import spacy

            self._nlp = spacy.load(self.pipeline_name)
        return self._nlp

    async def recognise(self, text: str) -> RecogniseResult:
        if len(text) > MAX_CHARS:
            raise RecogniserRefusedError(
                f"the text is {len(text):,} characters; this recogniser reads at most {MAX_CHARS:,}"
            )
        nlp = self._load()
        # spaCy is synchronous CPU work; a thread keeps the Conduit's event loop free.
        doc = await asyncio.to_thread(nlp, text)
        version = nlp.meta.get("version", "?")
        return RecogniseResult(
            recogniser=f"spacy:{self.pipeline_name}-{version}",
            entities=[
                RecognisedEntity(
                    label=ent.label_, text=ent.text, start=ent.start_char, end=ent.end_char
                )
                for ent in doc.ents
            ],
        )

    async def aclose(self) -> None:
        """Nothing held open; here so every recogniser closes the same way."""
