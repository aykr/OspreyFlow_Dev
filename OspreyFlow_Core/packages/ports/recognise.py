"""`RecognisePort` — the fast named-entity recogniser (`06_DECISIONS.md` ADR-098 decision 2).

A local recogniser (Stanza, in the `ner` sidecar) that finds people, organisations and places in a
text in a fraction of a second, where the language model (`ModelPort.extract`) takes minutes. It
answers spans, not entities: a label of the recogniser's own and an exact character span into the
text given. Mapping a label to an ontology type, and keeping every finding a suggestion until a
person accepts it (rule 5), is the Conduit's.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class RecognisedEntity(BaseModel):
    #: The recogniser's own label: PERSON, ORG, GPE, LOC, FAC, DATE, MONEY, ...
    label: str
    text: str
    #: Character offsets into the text given (not bytes): `text == given[start:end]`.
    start: int
    end: int


class RecogniseResult(BaseModel):
    #: Which recogniser and version found these, e.g. "stanza:1.10.1"; recorded on each finding.
    recogniser: str
    entities: list[RecognisedEntity]


class RecogniserRefusedError(Exception):
    """The recogniser refused the text (past its limit): nothing is read in part (rule 2)."""


class RecogniserUnavailableError(Exception):
    """The recogniser could not be reached or did not answer."""


class RecognisePort(Protocol):
    async def recognise(self, text: str) -> RecogniseResult: ...
