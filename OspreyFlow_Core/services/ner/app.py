"""The fast named-entity recogniser (`06_DECISIONS.md` ADR-098 decision 2): Stanza's English
recogniser behind one call, in a container of its own beside the transcription one.

`POST /v1/recognise` with `{"text": ...}` answers the entities Stanza finds, each with its label
(Stanza's own: PERSON, ORG, GPE, LOC, FAC, DATE, ...) and its exact character span in the text it
was given. It knows nothing of the ontology, cases or handling: the Conduit maps labels to entity
types and keeps every finding a suggestion until a person accepts it (rule 5). The model is read
from the image, downloaded when it was built, so the deployment needs no network to recognise.
"""

from __future__ import annotations

import os
from functools import lru_cache

import stanza
from fastapi import FastAPI
from pydantic import BaseModel, Field

MODEL_DIR = os.environ.get("STANZA_RESOURCES_DIR", "/models")
#: A text longer than this is refused rather than read in part (rule 2's spirit: no silent cut).
MAX_CHARS = 200_000

app = FastAPI(title="OspreyFlow recogniser")


class RecogniseRequest(BaseModel):
    text: str = Field(max_length=MAX_CHARS)


class RecognisedEntity(BaseModel):
    label: str
    text: str
    start: int
    end: int


class RecogniseResult(BaseModel):
    recogniser: str
    entities: list[RecognisedEntity]


@lru_cache(maxsize=1)
def _pipeline() -> stanza.Pipeline:
    return stanza.Pipeline(
        "en",
        dir=MODEL_DIR,
        processors="tokenize,ner",
        download_method=None,  # never at run time: the image holds the model
        use_gpu=False,
        logging_level="WARN",
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    _pipeline()
    return {"status": "ok", "recogniser": f"stanza:{stanza.__version__}"}


@app.post("/v1/recognise")
def recognise(request: RecogniseRequest) -> RecogniseResult:
    entities: list[RecognisedEntity] = []
    if request.text.strip():
        doc = _pipeline()(request.text)
        entities = [
            RecognisedEntity(label=e.type, text=e.text, start=e.start_char, end=e.end_char)
            for e in doc.ents
        ]
    return RecogniseResult(recogniser=f"stanza:{stanza.__version__}", entities=entities)
