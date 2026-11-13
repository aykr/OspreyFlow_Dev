"""The index's settings and mapping (ADR-150 decision 3, ADR-149's analysers). Every analyser is
in core OpenSearch (analysis-common), so it needs no plugin on any shape. Every field, keyword
ones included, scores with `similarity: boolean`, so no score depends on documents a reader
cannot see."""

from __future__ import annotations

from typing import Any

_BOOLEAN = {"similarity": "boolean"}
_KEYWORD = {"type": "keyword", **_BOOLEAN}

SETTINGS: dict[str, Any] = {
    "index": {"number_of_shards": 1, "number_of_replicas": 0},
    "analysis": {
        "normalizer": {"folded": {"type": "custom", "filter": ["lowercase", "asciifolding"]}},
        "filter": {
            "edge_2_20": {"type": "edge_ngram", "min_gram": 2, "max_gram": 20},
            "tri": {"type": "ngram", "min_gram": 3, "max_gram": 3},
        },
        "tokenizer": {"whole": {"type": "keyword"}},
        "analyzer": {
            "prefix_index": {
                "type": "custom",
                "tokenizer": "whole",
                "filter": ["lowercase", "asciifolding", "edge_2_20"],
            },
            "prefix_search": {
                "type": "custom",
                "tokenizer": "whole",
                "filter": ["lowercase", "asciifolding"],
            },
            "tri": {
                "type": "custom",
                "tokenizer": "whole",
                "filter": ["lowercase", "asciifolding", "tri"],
            },
            "words": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["lowercase", "asciifolding"],
            },
        },
    },
}

_PREFIX = {
    "type": "text",
    "analyzer": "prefix_index",
    "search_analyzer": "prefix_search",
    **_BOOLEAN,
}

MAPPING: dict[str, Any] = {
    "dynamic": "strict",
    "properties": {
        "kind": _KEYWORD,
        "id": _KEYWORD,
        "node_id": _KEYWORD,
        "type": _KEYWORD,
        "datasets": _KEYWORD,
        "handling_classification": _KEYWORD,
        "handling_code": _KEYWORD,
        "owning_unit": _KEYWORD,
        "originator": _KEYWORD,
        "text_owning_unit": _KEYWORD,
        "identifiers": {**_KEYWORD, "fields": {"prefix": _PREFIX}},
        "names": {
            "type": "keyword",
            "normalizer": "folded",
            **_BOOLEAN,
            "fields": {
                "prefix": _PREFIX,
                "tri": {"type": "text", "analyzer": "tri", **_BOOLEAN},
                "words": {"type": "text", "analyzer": "words", **_BOOLEAN},
            },
        },
        "names_phonetic": _KEYWORD,
        "date": {"type": "date"},
        "text": {
            "type": "text",
            "analyzer": "words",
            "index_options": "offsets",
            **_BOOLEAN,
        },
    },
}


def index_body() -> dict[str, Any]:
    return {"settings": SETTINGS, "mappings": MAPPING}
