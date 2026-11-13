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


#: Everything the analysis may be built of: an allow-list, so a built-in stemmer, a language
#: analyser, a phonetic tokenizer or a synonym filter named anywhere is refused, not missed.
TOKENIZERS = {"whole", "standard"}
FILTERS = {"lowercase", "asciifolding", "edge_prefix", "tri"}
CUSTOM_FILTER_TYPES = {"ngram", "edge_ngram"}
CUSTOM_TOKENIZER_TYPES = {"keyword"}
NORMALIZER_FILTERS = {"lowercase", "asciifolding"}


def test_no_phonetic_fuzzy_synonym_or_stemming_analysis_inside_opensearch() -> None:
    analysis = SETTINGS["analysis"]
    assert set(analysis) <= {"analyzer", "filter", "tokenizer", "normalizer"}
    assert {f["type"] for f in analysis["filter"].values()} <= CUSTOM_FILTER_TYPES
    assert {t["type"] for t in analysis["tokenizer"].values()} <= CUSTOM_TOKENIZER_TYPES
    for name, analyzer in analysis["analyzer"].items():
        assert analyzer["type"] == "custom", name
        assert analyzer["tokenizer"] in TOKENIZERS, name
        assert set(analyzer["filter"]) <= FILTERS, name
    for normalizer in analysis["normalizer"].values():
        assert set(normalizer["filter"]) <= NORMALIZER_FILTERS
    # Every field names one of these analysers, or none (a keyword); never a built-in one.
    for path, spec in _fields(MAPPING["properties"]):
        for key in ("analyzer", "search_analyzer"):
            if key in spec:
                assert spec[key] in analysis["analyzer"], (path, spec[key])
        if "normalizer" in spec:
            assert spec["normalizer"] in analysis["normalizer"], path
