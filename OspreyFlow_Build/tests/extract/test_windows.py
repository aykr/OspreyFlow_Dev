"""ADR-095 decision 2: a text longer than one extraction window is read in overlapping windows, and
nothing past a window is dropped unread (rule 2). What a mistake would do, and the case that
catches it:

- a long email sent whole to a model that cuts it inside
  (`test_a_long_text_is_read_in_more_than_one_call`);
- a finding in a later window dropped, or located in the window instead of the whole text
  (`test_a_finding_in_a_later_window_is_kept_where_it_stands_in_the_whole_text`);
- a name that straddles a window boundary lost
  (`test_a_name_across_a_boundary_is_found_in_the_overlap`);
- the overlap counting one mention twice (`test_a_mention_in_the_overlap_is_kept_once`).

The model stand-in sees only what it is sent, as the real one does, and reports a person for each
of the names it is told to look for that appear in that text.
"""

from __future__ import annotations

import asyncio
from typing import Any

from services.api.review import run_extraction
from services.extract.profile import ExtractionProfile

from ontology.loader import load_default_ontology
from schemas.domain import Handling, Principal
from schemas.model import ExtractionRequest, ExtractionResult

ONTOLOGY = load_default_ontology()
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


class Reader:
    def __init__(self, names: list[str]) -> None:
        self.names = names
        self.seen: list[str] = []

    async def extract(self, request: ExtractionRequest) -> ExtractionResult:
        self.seen.append(request.text)
        people = [{"family_name": n, "confidence": 0.9} for n in self.names if n in request.text]
        return ExtractionResult(
            document_id=request.document_id, model="stand-in", data={"Person": people}
        )


class Store:
    def __init__(self) -> None:
        self.text: str | None = None

    async def store_document_text(self, document_id: str, text: str, principal: Principal) -> None:
        self.text = text

    async def store(self, candidates: list[Any], principal: Principal) -> list[Any]:
        return candidates


def _run(text: str, names: list[str], **kw: Any) -> tuple[list[Any], Reader, Store]:
    reader, store = Reader(names), Store()
    found = asyncio.run(
        run_extraction(
            reader,  # type: ignore[arg-type]
            ONTOLOGY,
            store,  # type: ignore[arg-type]
            document_id="doc-1",
            text=text,
            profile=ExtractionProfile(["Person"]),
            handling=Handling(
                classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"
            ),
            principal=ANALYST,
            extraction_model="stand-in",
            **kw,
        )
    )
    return found, reader, store


def _span(candidate: Any) -> tuple[int, int]:
    start, end = candidate.locator.removeprefix("char span ").split("-")
    return int(start), int(end)


def test_a_short_text_is_read_in_one_call() -> None:
    found, reader, store = _run("Dan Lee wrote.", ["Lee"], window_chars=100, overlap_chars=10)
    assert len(reader.seen) == 1 and len(found) == 1 and store.text == "Dan Lee wrote."


def test_a_long_text_is_read_in_more_than_one_call() -> None:
    text = "a " * 150
    _, reader, store = _run(text, [], window_chars=100, overlap_chars=10)
    assert len(reader.seen) == 4
    assert all(len(window) <= 100 for window in reader.seen)
    assert store.text == text  # the whole text is kept for the reader


def test_a_finding_in_a_later_window_is_kept_where_it_stands_in_the_whole_text() -> None:
    text = "x" * 250 + " Holloway met them."
    (found,), _, _ = _run(text, ["Holloway"], window_chars=100, overlap_chars=10)
    start, end = _span(found)
    assert text[start:end] == "Holloway"


def test_a_name_across_a_boundary_is_found_in_the_overlap() -> None:
    text = "y" * 95 + "Pendry" + "y" * 50
    found, _, _ = _run(text, ["Pendry"], window_chars=100, overlap_chars=20)
    assert [text[slice(*_span(f))] for f in found] == ["Pendry"]


def test_a_mention_in_the_overlap_is_kept_once() -> None:
    text = "z" * 85 + " Lee " + "z" * 100
    found, reader, _ = _run(text, ["Lee"], window_chars=100, overlap_chars=20)
    assert sum("Lee" in w for w in reader.seen) == 2
    assert len(found) == 1
