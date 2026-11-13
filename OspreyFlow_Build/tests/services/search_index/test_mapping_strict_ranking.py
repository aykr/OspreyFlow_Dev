"""The owner's ruling of 13 November for the index side (ADR-150 decision 3, ADR-149): strict
ranking. No score depends on how rare a word is (every searchable field, sub-fields included, scores
with `similarity: boolean`, never BM25's default); a name is matched by trigrams, edge n-grams and
the Conduit's own Double Metaphone key, a keyword computed before indexing, with no phonetic or
fuzzy analysis inside OpenSearch."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from services.search_index.mapping import MAPPING, PREFIX_MAX_CHARS, SETTINGS

#: Field types OpenSearch scores (a `date` is matched by range, never scored by term frequency).
SCORED = {"text", "keyword"}


def _fields(properties: dict[str, Any], prefix: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    for name, spec in properties.items():
        path = f"{prefix}{name}"
        yield path, spec
        yield from _fields(spec.get("fields", {}), f"{path}.")


def test_every_scored_field_is_boolean_so_no_word_rarity_ranks() -> None:
    scored = [(p, s) for p, s in _fields(MAPPING["properties"]) if s.get("type") in SCORED]
    assert len(scored) > 10
    assert [p for p, s in scored if s.get("similarity") != "boolean"] == []
    assert MAPPING["dynamic"] == "strict"  # no field arrives with the default similarity


def test_names_match_by_trigrams_edge_ngrams_and_the_conduits_phonetic_key() -> None:
    names = MAPPING["properties"]["names"]["fields"]
    analyzers = SETTINGS["analysis"]["analyzer"]
    filters = SETTINGS["analysis"]["filter"]
    assert filters[analyzers[names["tri"]["analyzer"]]["filter"][-1]] == {
        "type": "ngram", "min_gram": 3, "max_gram": 3,
    }  # fmt: skip
    edge = filters[analyzers[names["prefix"]["analyzer"]]["filter"][-1]]
    assert edge == {"type": "edge_ngram", "min_gram": 2, "max_gram": PREFIX_MAX_CHARS}
    assert MAPPING["properties"]["names_phonetic"]["type"] == "keyword"


def test_no_phonetic_or_fuzzy_analysis_inside_opensearch() -> None:
    kinds = {f["type"] for f in SETTINGS["analysis"]["filter"].values()}
    assert kinds <= {"ngram", "edge_ngram"}, kinds
    text = repr(SETTINGS) + repr(MAPPING)
    for word in ("phonetic\"", "'phonetic'", "fuzzy", "double_metaphone", "synonym", "stemmer"):
        assert word not in text, word
