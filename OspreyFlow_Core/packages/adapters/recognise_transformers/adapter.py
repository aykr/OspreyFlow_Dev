"""`RecognisePort` on a Hugging Face token-classification model (Apache-2.0 transformers) —
`06_DECISIONS.md` ADR-108 phase D, ruling Q3.

In process, like the spaCy adapter. The default model (`dslim/bert-base-NER`) tags PER, ORG, LOC
and MISC; the first three are normalised to the suite's canonical core — PER → PERSON and
LOC → GPE (BERT-NER's LOC covers the geopolitical names the suite means; the approximation is
this adapter's, said here, never silent) — and anything else keeps the model's own tag. Weights
load from the local Hugging Face cache; they are fetched once (an authorised download) and the
deployment serves them from disk thereafter.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ports.recognise import RecognisedEntity, RecogniseResult, RecogniserRefusedError

MAX_CHARS = 100_000

_CANONICAL = {"PER": "PERSON", "ORG": "ORG", "LOC": "GPE"}

#: The Hugging Face commit each model this adapter names is fetched at (PL11, 21 November 2026:
#: the fetch was unpinned and followed the Hub's `main`). `dslim/bert-base-NER` at this commit is
#: MIT on its model card (`spec/LICENCE_REGISTER.yaml` holds the row and where it was read). A
#: model with no entry here is loaded as before, at the Hub's `main`; only the default is pinned.
PINNED_REVISIONS: dict[str, str] = {
    "dslim/bert-base-NER": "d1a3e8f13f8c3566299d95fcfc9a8d2382a9affc",
}


@dataclass
class RecogniseTransformersAdapter:
    model_name: str = "dslim/bert-base-NER"
    #: Overrides `PINNED_REVISIONS` for this model; `None` takes its pin, or `main` with no pin.
    revision: str | None = None
    _pipeline: Any = field(default=None, repr=False)

    def _load(self) -> Any:
        if self._pipeline is None:
            from transformers import pipeline

            self._pipeline = pipeline(
                "token-classification",
                model=self.model_name,
                revision=self.revision or PINNED_REVISIONS.get(self.model_name),
                aggregation_strategy="simple",
            )
        return self._pipeline

    async def recognise(self, text: str) -> RecogniseResult:
        if len(text) > MAX_CHARS:
            raise RecogniserRefusedError(
                f"the text is {len(text):,} characters; this recogniser reads at most {MAX_CHARS:,}"
            )
        if not text.strip():
            return RecogniseResult(recogniser=f"transformers:{self.model_name}", entities=[])
        ner = self._load()
        found = await asyncio.to_thread(ner, text)
        entities: list[RecognisedEntity] = []
        for hit in found:
            start, end = int(hit["start"]), int(hit["end"])
            entities.append(
                RecognisedEntity(
                    label=_CANONICAL.get(hit["entity_group"], hit["entity_group"]),
                    # The exact characters at the span, never the tokeniser's reassembled word —
                    # the suite's own `text == given[start:end]` is the contract.
                    text=text[start:end],
                    start=start,
                    end=end,
                )
            )
        return RecogniseResult(recogniser=f"transformers:{self.model_name}", entities=entities)

    async def aclose(self) -> None:
        """Nothing held open; here so every recogniser closes the same way."""
