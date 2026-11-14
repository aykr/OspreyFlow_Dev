"""The search index's access filter (ADR-149, reserved; page A §1, read and ruled by the owner on
13 November 2026). It is the graph's own rule, `graph_arcadedb/access_filter.py`, written for the
index's documents (ADR-150 decision 3), with the one rule the graph does not need: a Document's
text is read only by the unit that holds it (`review.get_document_text`).

It goes in the query's own filter (`search_index_query`), never after retrieval, so hits, counts
and suggestions are all limited by it (rule 3). `tests/services/api/test_search_access.py` checks
it against `principal_may_view` and `in_case_datasets` over every combination of markings, and the
leak test checks it against a real index.

Each part is a `bool` carrying a `_name`, so a test can name the part it replaces. A named query
changes nothing in what matches.
"""

from __future__ import annotations

from typing import Any

from ontology.handling import HandlingScheme, is_restricted
from schemas.domain import Principal


def _part(name: str, **clauses: Any) -> dict[str, Any]:
    return {"bool": {"_name": name, **clauses}}


def index_access_filter(scheme: HandlingScheme, principal: Principal) -> dict[str, Any]:
    """Everything `principal` may see in the index, and nothing else:

    1. **classification:** no higher than the principal's clearance. An unknown clearance clears
       nothing.
    2. **handling code:** a code the scheme defines and does not restrict; or a restricted code the
       principal may receive, on a record its unit owns or originated. A code the scheme does not
       define matches neither, so it is never visible.
    3. **datasets:** one of the case's. An empty case sees nothing.
    4. **a text's unit:** a node's document passes; a Document's text passes only for the unit that
       holds it.
    """
    if principal.datasets is None:
        raise ValueError(
            "a search is always read for a case: a principal with no case limit is the Conduit's "
            "own background work"
        )
    if principal.clearance in scheme.classification:
        rank = scheme.classification.index(principal.clearance)
        allowed = scheme.classification[: rank + 1]
    else:
        allowed = []
    unrestricted = [code for code in scheme.handling_codes if not is_restricted(code, scheme)]
    receivable = sorted(
        code for code in set(principal.receivable_handling_codes) if is_restricted(code, scheme)
    )
    unit = principal.org_unit
    return {
        "bool": {
            "filter": [
                _part("classification", filter=[{"terms": {"handling_classification": allowed}}]),
                _part(
                    "handling_code",
                    should=[
                        {"terms": {"handling_code": unrestricted}},
                        {
                            "bool": {
                                "filter": [
                                    {"terms": {"handling_code": receivable}},
                                    {
                                        "bool": {
                                            "should": [
                                                {"term": {"owning_unit": unit}},
                                                {"term": {"originator": unit}},
                                            ],
                                            "minimum_should_match": 1,
                                        }
                                    },
                                ]
                            }
                        },
                    ],
                    minimum_should_match=1,
                ),
                _part(
                    "datasets", filter=[{"terms": {"datasets": sorted(set(principal.datasets))}}]
                ),
                _part(
                    "text_unit",
                    should=[
                        {"term": {"kind": "node"}},
                        {
                            "bool": {
                                "filter": [
                                    {"term": {"kind": "text"}},
                                    {"term": {"text_owning_unit": unit}},
                                ]
                            }
                        },
                    ],
                    minimum_should_match=1,
                ),
            ]
        }
    }
