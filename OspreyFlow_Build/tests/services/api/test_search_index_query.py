"""The query side of search on OpenSearch (ADR-149, reserved; v0.5.2 step 3d), as pure request
bodies:
`services/api/search_index_query.py`. What a mistake would do, and the case that catches it:

- a body built with no access filter, or the filter put where it does not limit the counts
  (`post_filter` limits hits but not aggregations; a `should` limits nothing)
  (`test_a_body_cannot_be_built_without_an_access_filter`,
  `test_the_access_filter_limits_hits_and_counts_alike`);
- a clause that expands against the index's word list (fuzzy, prefix, wildcard, regexp, phrase
  prefix), which page A rules out because hidden records can use up the expansion
  (`test_no_clause_expands_against_the_word_list`, shown able to fail by
  `test_the_expansion_check_finds_a_planted_fuzzy_clause`);
- a score that depends on another document, or bands that overlap, so a close name outranks an exact
  identifier (`test_the_bands_never_overlap`, `test_every_dis_max_takes_the_best_band_alone`);
- a long query cut silently (rule 2) (`test_a_query_over_the_limit_is_refused_not_cut`);
- the canonical form of a number not asked (ADR-128)
  (`test_the_identifier_band_asks_the_canonical_form_too`);
- a snippet carrying markup from the document into the Glass
  (`test_a_snippet_is_text_and_marks_never_markup`);
- counts shown as exact when OpenSearch says they may not be (rule 2)
  (`test_counts_that_opensearch_says_may_be_short_are_not_shown_as_exact`).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from services.api import search_index_query as q

ACCESS = {"bool": {"filter": [{"terms": {"handling_classification": ["OFFICIAL"]}}]}}
INDEX_TYPES = ["Person", "Organisation", "Document", "Endpoint"]


def _codes(word: str) -> list[str]:
    """A stand-in for the index's own phonetic function, which production wires in."""
    table = {"mohammed": ["MHMT"], "smyth": ["SM0", "XMT"], "jon": ["JN"]}
    return table.get(word.lower(), [])


def _body(text: str = "Mohammed Smyth", **kw: Any) -> dict[str, Any]:
    return q.build_search_body(
        text, access_filter=ACCESS, phonetic_codes=_codes, types=INDEX_TYPES, limit=20, **kw
    )


def _walk(node: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _expanding_clauses(body: dict[str, Any]) -> list[str]:
    return [
        key
        for key, value in _walk(body)
        if key in q.EXPANDING_QUERIES or (key == "fuzziness" and value not in (0, "0"))
    ]


# --- access: the filter is required and limits hits and counts alike ------------------------------


def test_a_body_cannot_be_built_without_an_access_filter() -> None:
    missing: dict[str, Any] | None
    for missing in (None, {}):
        with pytest.raises(ValueError, match="access filter"):
            q.build_search_body(
                "Smyth",
                access_filter=missing,  # type: ignore[arg-type]
                phonetic_codes=_codes,
                types=INDEX_TYPES,
                limit=20,
            )
        with pytest.raises(ValueError, match="access filter"):
            q.build_suggest_body("Sm", access_filter=missing, limit=10)  # type: ignore[arg-type]


def test_the_access_filter_limits_hits_and_counts_alike() -> None:
    for body in (_body(), q.build_suggest_body("Sm", access_filter=ACCESS, limit=10)):
        assert "post_filter" not in body
        assert body["query"]["bool"]["filter"][0] == ACCESS
        # The counts are aggregations of the same query, never of a second, unfiltered one.
        for key, _ in _walk(body.get("aggs", {})):
            assert key not in ("global", "post_filter")


def test_narrowing_filters_join_the_access_filter_never_replace_it() -> None:
    body = _body(
        datasets=["ds-1"], entity_types=["Person"], date_from="2026-01-01", date_to="2026-02-01"
    )
    filters = body["query"]["bool"]["filter"]
    assert filters[0] == ACCESS
    assert {"terms": {"datasets": ["ds-1"]}} in filters
    assert {"terms": {"type": ["Person"]}} in filters
    assert {"range": {"date": {"gte": "2026-01-01", "lte": "2026-02-01"}}} in filters


# --- no expansion, no corpus statistics -----------------------------------------------------------


def test_no_clause_expands_against_the_word_list() -> None:
    for text in ("Mohammed Smyth", "07700 900123", "Jon", "the harbour street warehouse"):
        assert _expanding_clauses(_body(text)) == []
    assert _expanding_clauses(q.build_suggest_body("Smy", access_filter=ACCESS, limit=10)) == []


def test_the_expansion_check_finds_a_planted_fuzzy_clause() -> None:
    """Rule 15: the check above, shown able to fail, at the shape the builder emits."""
    body = _body()
    body["query"]["bool"]["must"][0]["dis_max"]["queries"].append(
        {"match": {"names.words": {"query": "Smyth", "fuzziness": "AUTO"}}}
    )
    assert _expanding_clauses(body) == ["fuzziness"]
    body = _body()
    body["query"]["bool"]["must"][0]["dis_max"]["queries"].append(
        {"prefix": {"identifiers": "077"}}
    )
    assert _expanding_clauses(body) == ["prefix"]


def test_every_dis_max_takes_the_best_band_alone() -> None:
    dis_maxes = [value for key, value in _walk(_body()) if key == "dis_max"]
    assert dis_maxes
    assert all(d.get("tie_breaker", 0) == 0 for d in dis_maxes)


def test_the_bands_never_overlap() -> None:
    """Each band is a fixed score; the one variable band (some words of a mention) is bounded by the
    query's length limit, below the next band up."""
    b = q.BAND_SCORES
    assert b["identifier"] > b["name_exact"] > b["name_words"] > b["name_sounds"] > b["name_typo"]
    assert b["name_typo"] > b["mention_phrase"] > b["mention_words"]
    # A word is at least one character and a space: the limit bounds the words a query can hold.
    assert (q.MAX_QUERY_CHARS + 1) // 2 < b["mention_words"]


def test_a_query_over_the_limit_is_refused_not_cut() -> None:
    with pytest.raises(ValueError, match=str(q.MAX_QUERY_CHARS)):
        _body("x" * (q.MAX_QUERY_CHARS + 1))
    _body("x" * q.MAX_QUERY_CHARS)


# --- the bands' clauses ---------------------------------------------------------------------------


def _bands(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Each band's clause, by the name it carries."""
    queries = body["query"]["bool"]["must"][0]["dis_max"]["queries"]
    return {clause["bool"]["_name"]: clause["bool"] for clause in queries}


def test_the_identifier_band_asks_the_canonical_form_too() -> None:
    bands = _bands(_body("07700 900123"))
    terms = bands["identifier"]["must"][0]["constant_score"]["filter"]["terms"]["identifiers"]
    assert terms == ["07700 900123", "+447700900123"]
    assert bands["identifier"]["filter"] == [{"term": {"kind": "node"}}]


def test_the_sounds_like_band_needs_every_word_to_sound_alike() -> None:
    bands = _bands(_body("Mohammed Smyth"))
    words = bands["name_sounds"]["must"][0]["constant_score"]["filter"]["bool"]["must"]
    assert words == [
        {"terms": {"names_phonetic": ["MHMT"]}},
        {"terms": {"names_phonetic": ["SM0", "XMT"]}},
    ]


def test_a_word_with_no_sound_drops_the_sounds_like_band() -> None:
    assert "name_sounds" not in _bands(_body("Mohammed 42"))


def test_the_typo_band_waits_for_four_letters() -> None:
    assert "name_typo" not in _bands(_body("Jon"))
    assert "name_typo" in _bands(_body("Jonathon"))


def test_mentions_are_asked_of_text_documents_alone_and_names_of_node_documents_alone() -> None:
    for name, band in _bands(_body()).items():
        kind = "text" if name.startswith("mention") else "node"
        assert band["filter"] == [{"term": {"kind": kind}}], name


def test_the_order_is_total_and_one_node_appears_once() -> None:
    body = _body()
    assert body["sort"] == [
        {"_score": {"order": "desc"}},
        {"date": {"order": "desc", "missing": "_last"}},
        {"node_id": {"order": "asc"}},
    ]
    assert body["collapse"] == {"field": "node_id"}
    assert body["size"] == 21  # one past the limit, so `more` is known (rule 2)
    assert body["track_scores"] is True


# --- reading the reply ----------------------------------------------------------------------------


def _hit(node_id: str, score: float, kind: str = "node", **highlight: list[str]) -> dict[str, Any]:
    return {
        "_id": node_id if kind == "node" else f"text:{node_id}",
        "_score": score,
        "_source": {"node_id": node_id, "kind": kind},
        "fields": {"node_id": [node_id]},
        **({"highlight": highlight} if highlight else {}),
    }


def _reply(hits: list[dict[str, Any]], *, error: int = 0, other: int = 0) -> dict[str, Any]:
    return {
        "hits": {"hits": hits},
        "aggregations": {
            "by_type": {
                "doc_count_error_upper_bound": error,
                "sum_other_doc_count": other,
                "buckets": [{"key": "Person", "doc_count": 3}],
            },
            "mentions": {"doc_count": 7},
        },
    }


def test_a_hit_is_read_with_its_band_and_more_is_one_past_the_limit() -> None:
    b = q.BAND_SCORES
    hits = [_hit("n1", b["identifier"]), _hit("n2", b["name_sounds"]), _hit("n3", 3.0, "text")]
    result = q.read_search_response(_reply(hits), limit=2)
    assert [(h.node_id, h.band) for h in result.hits] == [
        ("n1", "identifier"),
        ("n2", "name_sounds"),
    ]
    assert result.more is True
    assert q.read_search_response(_reply(hits), limit=3).hits[2].band == "mention_some"


def test_a_score_between_bands_is_a_defect_not_a_guess() -> None:
    """A score no band gives means a clause scored by something other than its fixed score (word
    rarity, say), which is exactly what page A rules out: it is refused, never filed under a
    band."""
    with pytest.raises(ValueError, match="2950"):
        q.read_search_response(_reply([_hit("n1", 2950.0)]), limit=5)


def test_a_snippet_is_text_and_marks_never_markup() -> None:
    o, c = q.HIGHLIGHT_OPEN, q.HIGHLIGHT_CLOSE
    hit = _hit("n1", 1500, "text", text=[f"paid <b>{o}Kestrel{c}</b> & co"])
    snippet = q.read_search_response(_reply([hit]), limit=5).hits[0].snippet
    assert snippet == [
        q.SnippetPart(text="paid <b>", match=False),
        q.SnippetPart(text="Kestrel", match=True),
        q.SnippetPart(text="</b> & co", match=False),
    ]


def test_counts_are_read_by_type_with_mentions_apart() -> None:
    result = q.read_search_response(_reply([]), limit=5)
    assert result.counts == {"Person": 3}
    assert result.mentions == 7
    assert result.counts_exact is True


def test_counts_that_opensearch_says_may_be_short_are_not_shown_as_exact() -> None:
    assert q.read_search_response(_reply([], error=2), limit=5).counts_exact is False
    assert q.read_search_response(_reply([], other=4), limit=5).counts_exact is False


def test_the_by_type_counts_ask_every_type_the_ontology_has() -> None:
    aggs = _body()["aggs"]
    assert aggs["by_type"]["terms"]["field"] == "type"
    assert aggs["by_type"]["terms"]["size"] >= len(INDEX_TYPES)
    assert aggs["mentions"] == {"filter": {"term": {"kind": "text"}}}


# --- suggestions ----------------------------------------------------------------------------------


def test_a_suggestion_needs_two_characters() -> None:
    with pytest.raises(ValueError, match="2"):
        q.build_suggest_body("S", access_filter=ACCESS, limit=10)


def test_a_suggestion_asks_stored_prefixes_of_node_documents_alone() -> None:
    body = q.build_suggest_body("Smy", access_filter=ACCESS, limit=10)
    assert {"term": {"kind": "node"}} in body["query"]["bool"]["filter"]
    fields = {
        next(iter(clause["constant_score"]["filter"]["match"]))
        for clause in body["query"]["bool"]["must"][0]["dis_max"]["queries"]
    }
    assert fields == {"identifiers", "names", "identifiers.prefix", "names.prefix"}
    assert body["size"] == 11


def test_a_suggestion_reply_says_more_when_one_past_the_limit_came_back() -> None:
    hits = [_hit(f"n{i}", 1900) for i in range(3)]
    assert q.read_suggest_response({"hits": {"hits": hits}}, limit=2) == (["n0", "n1"], True)
    assert q.read_suggest_response({"hits": {"hits": hits}}, limit=3) == (["n0", "n1", "n2"], False)
