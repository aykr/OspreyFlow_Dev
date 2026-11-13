"""The search index's access filter (ADR-149, reserved; page A §1, read and ruled by the owner on
13 November 2026): `services/api/search_access.py`, the graph's three axes as an OpenSearch filter,
plus the narrower rule on a Document's text.

The filter is checked against the Conduit's own statement of the rule, `principal_may_view` and
`in_case_datasets` (the same rule `AccessFilter` compiles into the traversal), over every
combination of the uk-le scheme's markings, units, datasets and both document kinds. It is checked
by evaluating the emitted filter in a small interpreter of the clauses it uses. What a mistake would
do, and the case that catches it:

- any axis dropped, loosened or tightened: classification, a restricted code, its unit scope, the
  case's datasets, a text's unit (`test_the_filter_agrees_with_the_conduits_rule_everywhere`, shown
  able to fail by `test_the_agreement_check_finds_each_axis_dropped`);
- a code the scheme does not define read as visible, not denied
  (`test_a_code_the_scheme_does_not_define_is_never_visible`);
- an unknown clearance or an empty case seeing anything
  (`test_an_unknown_clearance_sees_nothing`, `test_an_empty_case_sees_nothing`);
- the Conduit's unlimited background principal used for a reader's search
  (`test_a_principal_with_no_case_limit_is_refused`).

The live half, the leak test against a real index, is
`tests/services/search_index/test_search_leak_live.py`.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest
from services.api import search_access as sa

from ontology.handling import in_case_datasets, load_handling_scheme, principal_may_view
from schemas.domain import Handling, Principal

SCHEME = load_handling_scheme(
    Path(__file__).parents[4] / "OspreyFlow_Core/packages/ontology/handling/uk-le.yaml"
)
UNITS = ["unit-1", "unit-2"]
DATASETS = [["ds-1"], ["ds-2"], ["ds-1", "ds-2"]]


# --- an interpreter for the clauses the filter uses -----------------------------------------------


def _values(doc: dict[str, Any], field: str) -> list[Any]:
    value = doc.get(field)
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def matches(query: dict[str, Any], doc: dict[str, Any]) -> bool:
    ((kind, body),) = query.items()
    if kind == "term":
        ((field, value),) = body.items()
        return value in _values(doc, field)
    if kind == "terms":
        ((field, wanted),) = body.items()
        return any(v in wanted for v in _values(doc, field))
    if kind == "bool":
        unknown = set(body) - {"filter", "must", "should", "minimum_should_match", "_name"}
        assert not unknown, f"the interpreter does not know {unknown}"
        if not all(matches(c, doc) for c in body.get("filter", []) + body.get("must", [])):
            return False
        should = body.get("should", [])
        if should:
            # OpenSearch's own default: a `should` beside a `filter` or `must` is optional (0), one
            # alone needs a match (1). Defaulting to 1 always would accept a part that lost its
            # `minimum_should_match` and matches everything in OpenSearch (the lane review).
            alone = not body.get("filter") and not body.get("must")
            need: int = body.get("minimum_should_match", 1 if alone else 0)
            return sum(matches(c, doc) for c in should) >= need
        return True
    raise AssertionError(f"the interpreter does not know {kind}")


# --- the oracle: the Conduit's own rule -----------------------------------------------------------


def _visible(doc: dict[str, Any], principal: Principal) -> bool:
    if doc["handling_code"] not in SCHEME.handling_codes:
        return False  # `AccessFilter` denies a code it does not know; `principal_may_view` raises
    handling = Handling(
        classification=doc["handling_classification"],
        handling_code=doc["handling_code"],
        owning_unit=doc["owning_unit"],
        originator=doc["originator"],
    )
    if not principal_may_view(handling, principal, SCHEME):
        return False
    if not in_case_datasets(doc["datasets"], principal):
        return False
    return doc["kind"] == "node" or doc.get("text_owning_unit") == principal.org_unit


def _docs() -> list[dict[str, Any]]:
    docs = []
    for cls, code, owner, origin, datasets, kind, text_unit in itertools.product(
        SCHEME.classification,
        [*SCHEME.handling_codes, "UNDEFINED"],
        UNITS,
        UNITS,
        DATASETS,
        ["node", "text"],
        UNITS,
    ):
        if kind == "node" and text_unit != UNITS[0]:
            continue  # a node document has no text unit; one copy of it is enough
        doc: dict[str, Any] = {
            "kind": kind,
            "handling_classification": cls,
            "handling_code": code,
            "owning_unit": owner,
            "originator": origin,
            "datasets": datasets,
        }
        if kind == "text":
            doc["text_owning_unit"] = text_unit
        docs.append(doc)
    return docs


def _principals() -> list[Principal]:
    return [
        Principal(
            id="reader",
            clearance=clearance,
            org_unit=unit,
            receivable_handling_codes=receivable,
            datasets=datasets,
        )
        for clearance, unit, receivable, datasets in itertools.product(
            SCHEME.classification,
            UNITS,
            [[], ["R"], ["R", "C"]],
            [["ds-1"], ["ds-1", "ds-2"]],
        )
    ]


def _disagreements(filter_for: Any) -> list[tuple[dict[str, Any], Principal]]:
    docs = _docs()
    wrong = []
    for principal in _principals():
        query = filter_for(SCHEME, principal)
        wrong += [(d, principal) for d in docs if matches(query, d) != _visible(d, principal)]
    return wrong


def test_the_filter_agrees_with_the_conduits_rule_everywhere() -> None:
    assert len(_docs()) * len(_principals()) > 10_000
    assert _disagreements(sa.index_access_filter) == []


def _replaced(clause: str, by: dict[str, Any]) -> Any:
    """The filter with its `clause` (by the name the filter gives it) replaced, everything else
    as built."""

    def filter_for(scheme: Any, principal: Principal) -> dict[str, Any]:
        query = sa.index_access_filter(scheme, principal)
        parts = query["bool"]["filter"]
        names = [part["bool"]["_name"] for part in parts]
        assert clause in names, names
        return {
            "bool": {
                "filter": [
                    by if part["bool"]["_name"] == clause else _unnamed(part) for part in parts
                ]
            }
        }

    return filter_for


def _unnamed(part: dict[str, Any]) -> dict[str, Any]:
    return {"bool": {k: v for k, v in part["bool"].items() if k != "_name"}}


EVERYTHING: dict[str, Any] = {"bool": {}}
ANY_DEFINED_CODE = {"terms": {"handling_code": list(SCHEME.handling_codes)}}


@pytest.mark.parametrize(
    ("clause", "by"),
    [
        ("classification", EVERYTHING),
        ("handling_code", EVERYTHING),
        ("handling_code", ANY_DEFINED_CODE),  # the restricted code's unit scope dropped
        ("datasets", EVERYTHING),
        ("text_unit", EVERYTHING),
    ],
)
def test_the_agreement_check_finds_each_axis_dropped(clause: str, by: dict[str, Any]) -> None:
    """Rule 15: the check above shown able to fail, once per axis, at the filter's own shape."""
    assert _disagreements(_replaced(clause, by))


def test_a_code_the_scheme_does_not_define_is_never_visible() -> None:
    reader = Principal(
        id="r",
        clearance="SECRET",
        org_unit="unit-1",
        receivable_handling_codes=["R"],
        datasets=["ds-1"],
    )
    doc = {
        "kind": "node",
        "handling_classification": "PUBLIC",
        "handling_code": "UNDEFINED",
        "owning_unit": "unit-1",
        "originator": "unit-1",
        "datasets": ["ds-1"],
    }
    assert not matches(sa.index_access_filter(SCHEME, reader), doc)


def test_an_unknown_clearance_sees_nothing() -> None:
    reader = Principal(id="r", clearance="TOP-HAT", org_unit="unit-1", datasets=["ds-1"])
    query = sa.index_access_filter(SCHEME, reader)
    assert not any(matches(query, d) for d in _docs())


def test_an_empty_case_sees_nothing() -> None:
    reader = Principal(id="r", clearance="SECRET", org_unit="unit-1", datasets=[])
    query = sa.index_access_filter(SCHEME, reader)
    assert not any(matches(query, d) for d in _docs())


def test_a_principal_with_no_case_limit_is_refused() -> None:
    """`datasets is None` is the Conduit's own background work, never a reader's search."""
    with pytest.raises(ValueError, match="case"):
        sa.index_access_filter(SCHEME, Principal(id="bg", clearance="SECRET", org_unit="unit-1"))


def test_the_interpreter_reads_a_should_beside_a_filter_as_opensearch_does() -> None:
    """The fake must refuse what OpenSearch refuses (rule 15's second worked example): a `should`
    beside a `filter` with no `minimum_should_match` is optional, so it matches what fails it."""
    doc = {"kind": "node", "handling_code": "R"}
    loose = {
        "bool": {
            "filter": [{"term": {"kind": "node"}}],
            "should": [{"term": {"handling_code": "P"}}],
        }
    }
    assert matches(loose, doc)
    strict = {"bool": {"should": [{"term": {"handling_code": "P"}}]}}
    assert not matches(strict, doc)
