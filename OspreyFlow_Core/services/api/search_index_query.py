"""The query side of search on OpenSearch (ADR-149, reserved; v0.5.2 step 3d): request bodies built
and replies read, with no client and no I/O, so every rule here is tested without a store.

The index is the rules lane's (ADR-150): one document per node (`kind: node`) and one per Document's
text (`kind: text`, `node_id` naming its node), each carrying its node's access facts. Its fields
are those ADR-150 decision 3 names; every one uses `similarity: boolean`.

**Two rules hold for every body built here** (`process/lanes/studio/SEARCH_ACCESS_DESIGN.md`, page
A §3):

1. **The access filter is required and sits in the query's own filter**, never in `post_filter`
   (which limits hits but not aggregations) and never in a `should`. So hits, counts and
   suggestions are all limited by it. The filter itself is built elsewhere (stage 8, after the
   owner reads page A); this module only refuses to build a body without one.
2. **No score depends on another document, and nothing expands against the index's word list.**
   Every scoring clause is a fixed score (`constant_score`), and bands are combined with `dis_max`
   at a tie-breaker of 0, so a hit's score is its best band's. No fuzzy, prefix, wildcard, regexp or
   phrase-prefix query is used: their expansion stops at a fixed number of words, and words held
   only in hidden records can use it up and push a visible hit out. Typos, prefixes and sound-alikes
   come from fields the indexer stores instead (trigrams, edge n-grams, Double Metaphone codes).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .identifier_reading import search_alternative
from .search import SUGGEST_MIN_CHARS

#: Rule 2: a longer query is refused, not cut. It also bounds the one variable band (some words of a
#: mention: a point a word), below the band above it.
MAX_QUERY_CHARS = 200

#: Rule 2: results deeper than this are refused, and the error says to narrow the search
#: (`process/lanes/studio/SEARCH_RESPONSE_SHAPE.md`, note 4), never cut.
MAX_DEPTH = 1000

#: The group that lists documents whose text matched, beside the entity types.
MENTIONS = "mentions"

#: The bands, best first (the owner's search scope 3: exact identifier, then close names, then
#: mentions). Fixed scores; `mention_some` alone varies, from 1 to the number of words.
BAND_SCORES: dict[str, int] = {
    "identifier": 3000,
    "name_exact": 2900,
    "name_words": 2500,
    "name_sounds": 2300,
    "name_typo": 2100,
    "mention_phrase": 1500,
    "mention_words": 1200,
}

#: A query of fewer letters than this asks no trigram band: three letters make at most one trigram,
#: which matches every name holding it.
TYPO_MIN_CHARS = 4
#: Of the query's trigrams, the share a name must hold ("Jonathon" and "Jonathan" share 4 of 6).
TYPO_SHARE = "60%"

#: Queries that expand against the index's word list. None is ever built (rule 2 above).
EXPANDING_QUERIES = frozenset(
    {
        "fuzzy",
        "prefix",
        "wildcard",
        "regexp",
        "match_phrase_prefix",
        "match_bool_prefix",
        "query_string",
    }
)

#: Highlight marks: control characters no extracted text holds, so a mark is never confused with the
#: text's own content, and no markup is ever made here or sent to the Glass.
HIGHLIGHT_OPEN = "\x02"
HIGHLIGHT_CLOSE = "\x03"
SNIPPET_CHARS = 160

PhoneticCodes = Callable[[str], Sequence[str]]


def _require_filter(access_filter: dict[str, Any] | None) -> dict[str, Any]:
    if not access_filter:
        raise ValueError("a search body is never built without an access filter")
    return access_filter


def _require_length(text: str) -> str:
    if len(text) > MAX_QUERY_CHARS:
        raise ValueError(
            f"a search is at most {MAX_QUERY_CHARS} characters; this one is {len(text)}"
        )
    return text


def _fixed(name: str, kind: str, condition: dict[str, Any]) -> dict[str, Any]:
    """One band: `condition` on documents of `kind`, scored at the band's fixed score."""
    return {
        "bool": {
            "_name": name,
            "filter": [{"term": {"kind": kind}}],
            "must": [{"constant_score": {"filter": condition, "boost": BAND_SCORES[name]}}],
        }
    }


def _sounds_like(text: str, phonetic_codes: PhoneticCodes) -> dict[str, Any] | None:
    """Every word of the query must share a code with the record's names. A word with no code
    (a number, say) cannot sound like anything, so the band is not asked at all."""
    words = text.split()
    per_word = [list(dict.fromkeys(phonetic_codes(word))) for word in words]
    if not words or any(not codes for codes in per_word):
        return None
    return {"bool": {"must": [{"terms": {"names_phonetic": codes}} for codes in per_word]}}


def build_search_body(
    text: str,
    *,
    access_filter: dict[str, Any],
    phonetic_codes: PhoneticCodes,
    types: Sequence[str],
    page_size: int,
    page: int = 1,
    group: str | None = None,
    case_datasets: Sequence[str] = (),
    datasets: Sequence[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """A search's body (`process/lanes/studio/SEARCH_RESPONSE_SHAPE.md`).

    - `types` is every entity type the ontology has, and `case_datasets` every dataset of the
      case, so the counts are asked for all of them.
    - `datasets` and the dates narrow the search and join the access filter, never replace it.
    - `group` (a type, or `MENTIONS`) narrows the list alone. It is a `post_filter`, so every
      group's count stays whole. The access filter is never a `post_filter`."""
    access = _require_filter(access_filter)
    if page < 1 or page_size < 1:
        raise ValueError("a page and its size start at 1")
    if page * page_size > MAX_DEPTH:
        raise ValueError(
            f"results are listed {MAX_DEPTH} deep at most; narrow the search to see further"
        )
    text = _require_length(text).strip()

    identifiers = [text]
    canonical = search_alternative(text)
    if canonical is not None and canonical != text:
        identifiers.append(canonical)

    bands = [
        _fixed("identifier", "node", {"terms": {"identifiers": identifiers}}),
        _fixed("name_exact", "node", {"match": {"names": {"query": text}}}),
        _fixed(
            "name_words", "node", {"match": {"names.words": {"query": text, "operator": "and"}}}
        ),
    ]
    sounds = _sounds_like(text, phonetic_codes)
    if sounds is not None:
        bands.append(_fixed("name_sounds", "node", sounds))
    if sum(ch.isalnum() for ch in text) >= TYPO_MIN_CHARS:
        bands.append(
            _fixed(
                "name_typo",
                "node",
                {"match": {"names.tri": {"query": text, "minimum_should_match": TYPO_SHARE}}},
            )
        )
    bands += [
        _fixed("mention_phrase", "text", {"match_phrase": {"text": {"query": text}}}),
        _fixed("mention_words", "text", {"match": {"text": {"query": text, "operator": "and"}}}),
        # Some words: a point for each word matched (`similarity: boolean`), so at most the
        # number of words, which MAX_QUERY_CHARS keeps under `mention_words`.
        {
            "bool": {
                "_name": "mention_some",
                "filter": [{"term": {"kind": "text"}}],
                "must": [{"match": {"text": {"query": text}}}],
            }
        },
    ]

    filters: list[dict[str, Any]] = [access]
    if datasets:
        filters.append({"terms": {"datasets": list(datasets)}})
    if date_from or date_to:
        span = {k: v for k, v in (("gte", date_from), ("lte", date_to)) if v}
        filters.append({"range": {"date": span}})

    body: dict[str, Any] = {
        "query": {
            "bool": {"filter": filters, "must": [{"dis_max": {"queries": bands, "tie_breaker": 0}}]}
        },
        "sort": [
            {"_score": {"order": "desc"}},
            {"date": {"order": "desc", "missing": "_last"}},
            {"node_id": {"order": "asc"}},
        ],
        "track_scores": True,
        "collapse": {"field": "node_id"},
        "from": (page - 1) * page_size,
        "size": page_size + 1,
        "_source": ["node_id", "kind"],
        "highlight": {
            "pre_tags": [HIGHLIGHT_OPEN],
            "post_tags": [HIGHLIGHT_CLOSE],
            "encoder": "default",
            "fields": {
                "text": {
                    "type": "unified",
                    "fragment_size": SNIPPET_CHARS,
                    "number_of_fragments": 1,
                },
                "names.words": {"type": "unified", "number_of_fragments": 0},
            },
        },
        "aggs": {
            # Node documents by type, and text documents (mentions) apart, so a Document found by
            # its title and in its text is counted once in each, never twice in one.
            "by_type": {
                "filter": {"term": {"kind": "node"}},
                "aggs": {
                    "types": {
                        "terms": {
                            "field": "type",
                            "size": len(types) + 1,
                            "shard_size": 10 * (len(types) + 1),
                        }
                    }
                },
            },
            "mentions": {"filter": {"term": {"kind": "text"}}},
            "datasets": {
                "terms": {
                    "field": "datasets",
                    "size": len(case_datasets) + 1,
                    "shard_size": 10 * (len(case_datasets) + 1),
                }
            },
            "earliest": {"min": {"field": "date"}},
            "latest": {"max": {"field": "date"}},
        },
    }
    if group == MENTIONS:
        body["post_filter"] = {"term": {"kind": "text"}}
    elif group is not None:
        body["post_filter"] = {
            "bool": {"filter": [{"term": {"kind": "node"}}, {"term": {"type": group}}]}
        }
    return body


def build_suggest_body(prefix: str, *, access_filter: dict[str, Any], limit: int) -> dict[str, Any]:
    """Suggestions as the analyst types (ADR-059 Amendment 1, reserved): the stored prefixes of
    node documents' identifiers and names, never a prefix query (rule 2 above)."""
    access = _require_filter(access_filter)
    prefix = _require_length(prefix).strip()
    if len(prefix) < SUGGEST_MIN_CHARS:
        raise ValueError(f"a suggestion needs at least {SUGGEST_MIN_CHARS} characters")

    def fixed(field_name: str, score: int) -> dict[str, Any]:
        return {
            "constant_score": {
                "filter": {"match": {field_name: {"query": prefix, "operator": "and"}}},
                "boost": score,
            }
        }

    return {
        "query": {
            "bool": {
                "filter": [access, {"term": {"kind": "node"}}],
                "must": [
                    {
                        "dis_max": {
                            "queries": [
                                fixed("identifiers", BAND_SCORES["identifier"]),
                                fixed("names", BAND_SCORES["name_exact"]),
                                fixed("identifiers.prefix", BAND_SCORES["name_words"]),
                                fixed("names.prefix", BAND_SCORES["name_sounds"]),
                            ],
                            "tie_breaker": 0,
                        }
                    }
                ],
            }
        },
        "sort": [{"_score": {"order": "desc"}}, {"node_id": {"order": "asc"}}],
        "track_scores": True,
        "size": limit + 1,
        "_source": ["node_id"],
    }


@dataclass(frozen=True)
class SnippetPart:
    text: str
    match: bool


@dataclass(frozen=True)
class IndexHit:
    node_id: str
    band: str
    snippet: list[SnippetPart] = field(default_factory=list)


@dataclass(frozen=True)
class IndexSearchResult:
    hits: list[IndexHit]
    more: bool
    counts: dict[str, int]
    mentions: int
    #: False when OpenSearch says a count may be short (rule 2: the Glass says so).
    counts_exact: bool
    dataset_counts: dict[str, int]
    #: The earliest and latest `date` among the matches, as OpenSearch writes them; `None` if
    #: none is dated.
    earliest: str | None
    latest: str | None


_BAND_BY_SCORE = {score: band for band, score in BAND_SCORES.items()}


def _band(score: float) -> str:
    """The band a score names. A score no band gives is refused: it means a clause was scored by
    something other than its fixed score, which rule 2 of this module rules out."""
    if score == int(score) and int(score) in _BAND_BY_SCORE:
        return _BAND_BY_SCORE[int(score)]
    if score == int(score) and 1 <= score < BAND_SCORES["mention_words"]:
        return "mention_some"
    raise ValueError(f"a hit scored {score}, which no band gives")


def _snippet(fragment: str) -> list[SnippetPart]:
    """A highlighted fragment as plain parts, matched or not. The text is never parsed as markup."""
    parts: list[SnippetPart] = []
    rest = fragment
    while rest:
        start = rest.find(HIGHLIGHT_OPEN)
        if start == -1:
            parts.append(SnippetPart(rest, False))
            break
        end = rest.find(HIGHLIGHT_CLOSE, start)
        if end == -1:  # an unclosed mark: the rest is plain text, the mark dropped
            parts.append(SnippetPart(rest.replace(HIGHLIGHT_OPEN, ""), False))
            break
        if start:
            parts.append(SnippetPart(rest[:start], False))
        parts.append(SnippetPart(rest[start + 1 : end], True))
        rest = rest[end + 1 :]
    return parts


def _exact(terms: dict[str, Any]) -> bool:
    error: int = terms.get("doc_count_error_upper_bound", 0)
    other: int = terms.get("sum_other_doc_count", 0)
    return error == 0 and other == 0


def read_search_response(reply: dict[str, Any], *, page_size: int) -> IndexSearchResult:
    raw = reply["hits"]["hits"]
    hits = []
    for hit in raw[:page_size]:
        highlight = hit.get("highlight", {})
        fragments = highlight.get("text") or highlight.get("names.words") or []
        hits.append(
            IndexHit(
                node_id=hit["_source"]["node_id"],
                band=_band(hit["_score"]),
                snippet=_snippet(fragments[0]) if fragments else [],
            )
        )
    aggs = reply["aggregations"]
    by_type = aggs["by_type"]["types"]
    datasets = aggs["datasets"]
    return IndexSearchResult(
        hits=hits,
        more=len(raw) > page_size,
        counts={b["key"]: b["doc_count"] for b in by_type["buckets"]},
        mentions=aggs["mentions"]["doc_count"],
        counts_exact=_exact(by_type) and _exact(datasets),
        dataset_counts={b["key"]: b["doc_count"] for b in datasets["buckets"]},
        earliest=aggs["earliest"].get("value_as_string")
        if aggs["earliest"].get("value") is not None
        else None,
        latest=aggs["latest"].get("value_as_string")
        if aggs["latest"].get("value") is not None
        else None,
    )


def read_suggest_response(reply: dict[str, Any], *, limit: int) -> tuple[list[str], bool]:
    raw = reply["hits"]["hits"]
    return [hit["_source"]["node_id"] for hit in raw[:limit]], len(raw) > limit
