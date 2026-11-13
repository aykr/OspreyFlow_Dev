"""The index's settings and mapping (ADR-150 decision 3, ADR-149's analysers). Every analyser is
in core OpenSearch (analysis-common), so it needs no plugin on any shape. Every field, keyword
ones included, scores with `similarity: boolean`, so no score depends on documents a reader
cannot see."""

from __future__ import annotations

import hashlib
import json
from typing import Any

_BOOLEAN = {"similarity": "boolean"}

#: The longest prefix the type-ahead matches (edge n-grams up to it, at index time). The query side
#: refuses a longer one in words (ADR-149; rule 2), importing this same constant.
PREFIX_MAX_CHARS = 50
#: The longest name or identifier indexed as a keyword, in characters: at four bytes a character
#: at most, under Lucene's 32,766-byte term, which refuses the whole document otherwise. A longer
#: value is kept in the document's source but not indexed as a keyword (its sub-fields still are).
#: Never on an access field (datasets, handling, units): a value there left unindexed would let a
#: query's filter pass it unseen, so an over-long one is refused and set aside (it fails closed).
KEYWORD_MAX_CHARS = 8191
_KEYWORD = {"type": "keyword", **_BOOLEAN}
_LONG_KEYWORD = {"type": "keyword", "ignore_above": KEYWORD_MAX_CHARS, **_BOOLEAN}

SETTINGS: dict[str, Any] = {
    # An edge n-gram filter's min and max may differ by at most `index.max_ngram_diff`.
    "index": {"number_of_shards": 1, "number_of_replicas": 0, "max_ngram_diff": PREFIX_MAX_CHARS},
    "analysis": {
        "normalizer": {"folded": {"type": "custom", "filter": ["lowercase", "asciifolding"]}},
        "filter": {
            "edge_prefix": {"type": "edge_ngram", "min_gram": 2, "max_gram": PREFIX_MAX_CHARS},
        },
        "tokenizer": {
            "whole": {"type": "keyword"},
            # Trigrams from a tokenizer, each at its own position, so `minimum_should_match`
            # counts them; an `ngram` filter puts them at one position, read as synonyms.
            "tri": {"type": "ngram", "min_gram": 3, "max_gram": 3, "token_chars": []},
        },
        "analyzer": {
            "prefix_index": {
                "type": "custom",
                "tokenizer": "whole",
                "filter": ["lowercase", "asciifolding", "edge_prefix"],
            },
            "prefix_search": {
                "type": "custom",
                "tokenizer": "whole",
                "filter": ["lowercase", "asciifolding"],
            },
            "tri": {
                "type": "custom",
                "tokenizer": "tri",
                "filter": ["lowercase", "asciifolding"],
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
        "identifiers": {**_LONG_KEYWORD, "fields": {"prefix": _PREFIX}},
        "names": {
            "type": "keyword",
            "normalizer": "folded",
            "ignore_above": KEYWORD_MAX_CHARS,
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


#: The settings and mapping this code builds documents for, as one digest. Written into each index's
#: `_meta` when it is made, and checked before every write (`indexer.check_mapping`): an index made
#: by other code (before an upgrade that changed either, or by an older replica in a rolling one)
#: would refuse or misread this code's documents, so the indexer stops and says a rebuild is needed
#: rather than setting every document aside.
MAPPING_FINGERPRINT = hashlib.sha256(
    json.dumps({"settings": SETTINGS, "mappings": MAPPING}, sort_keys=True).encode()
).hexdigest()


def index_body() -> dict[str, Any]:
    return {
        "settings": SETTINGS,
        "mappings": {**MAPPING, "_meta": {"mapping_fingerprint": MAPPING_FINGERPRINT}},
    }
