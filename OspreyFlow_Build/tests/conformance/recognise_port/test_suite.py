"""`RecognisePort` conformance suite (`06_DECISIONS.md` ADR-098 decision 2), written before the
adapter (rule 1). Parametrised over `RECOGNISE_PORT_ADAPTERS`; each runs against a live recogniser
sidecar (`services/ner`), as the model suite runs against a live proxy.

What it proves is the contract, not recognition quality: entities come back with the recogniser's
label and an exact *character* span into the text given (a byte span would be wrong after any
non-ASCII character), an empty text has none, the recogniser names itself, and a text past the
limit is refused, never read in part.
"""

from __future__ import annotations

import pytest

from ports.recognise import RecogniserRefusedError
from tests.conformance.registry import RECOGNISE_PORT_ADAPTERS, RecogniseAdapterFactory

pytestmark = pytest.mark.parametrize("factory", RECOGNISE_PORT_ADAPTERS, ids=str)

SENTENCE = "Kenneth Lay met Jeffrey Skilling of Enron in Houston on Monday."


async def test_a_person_an_organisation_and_a_place_are_found_with_their_spans(
    factory: RecogniseAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        result = await adapter.recognise(SENTENCE)
    labels = {e.label for e in result.entities}
    assert {"PERSON", "ORG", "GPE"} <= labels
    for entity in result.entities:
        assert SENTENCE[entity.start : entity.end] == entity.text


async def test_spans_count_characters_not_bytes(factory: RecogniseAdapterFactory) -> None:
    text = "Ça va. Señora Dana Mercer visited Zürich."
    async with factory.context() as adapter:
        result = await adapter.recognise(text)
    assert result.entities
    for entity in result.entities:
        assert text[entity.start : entity.end] == entity.text


async def test_an_empty_text_has_no_entities_and_the_recogniser_names_itself(
    factory: RecogniseAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        result = await adapter.recognise("   ")
    assert result.entities == []
    assert result.recogniser.startswith("stanza:")


async def test_a_text_past_the_limit_is_refused_not_read_in_part(
    factory: RecogniseAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        with pytest.raises(RecogniserRefusedError):
            await adapter.recognise("word " * 50_000)
