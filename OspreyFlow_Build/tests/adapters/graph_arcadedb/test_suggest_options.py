"""Search options for the Glass search box: ignore case, match mode and entity types (ADR-061).

Seen, 3 October 2026: the owner asked for a case-insensitive tick box and a filter panel. The
default (starts with, case-sensitive, every type) must read exactly as ADR-059 had it; the options
only change what is asked of the store.

The store here evaluates each predicate form the builder can write and refuses any it does not
recognise (rule 15). Java's `\\Q..\\E` quoting is translated for Python's `re`. Whether ArcadeDB's
Gremlin engine honours `TextP.regex('(?iu)...')` is NOT proven here: the conformance suite has
the live cases, and they need a live store.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest
from adapters.graph_arcadedb import builders
from adapters.graph_arcadedb.naming import physical_type_name
from ports.graph import SuggestOptions
from schemas.domain import Principal

from tests.adapters.graph_arcadedb.edge_store import CountingStore, make_adapter
from tests.adapters.graph_arcadedb.test_suggest_nodes import _element_map

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
IDS = ["Jeff.Sorensen@enron.com", "jeff.danforth@enron.com", "ajeffries@x.org", "C13"]


def _java_pattern(pattern: str) -> str:
    """The subset of Java regex the builder writes, in Python's `re` terms."""
    out = pattern.replace("(?iu)", "(?i)")
    return re.sub(r"\\Q(.*?)\\E", lambda m: re.escape(m.group(1)), out)


class _OptionStore(CountingStore):
    def __init__(self, ids: list[str]) -> None:
        super().__init__()
        self.ids = ids

    async def gremlin(self, query: str, **_: Any) -> list[Any]:  # type: ignore[override]
        self.queries.append(query)
        if not query.startswith("g.V().hasLabel("):
            raise RuntimeError(f"unexpected query: {query}")
        match = re.search(
            r"TextP\.(startingWith|containing|regex)\('((?:[^'\\]|\\.)*)'\)", query
        )
        if match:
            kind, raw = match.groups()
            arg = raw.replace("\\'", "'").replace("\\\\", "\\")
            if kind == "startingWith":
                hit = lambda v: v.startswith(arg)
            elif kind == "containing":
                hit = lambda v: arg in v
            else:
                rx = re.compile(_java_pattern(arg))
                hit = lambda v: rx.search(v) is not None
        else:
            eq = re.search(r"P\.eq\('((?:[^'\\]|\\.)*)'\)", query)
            if not eq:
                raise RuntimeError(f"no predicate in: {query}")
            arg = eq.group(1).replace("\\'", "'").replace("\\\\", "\\")
            hit = lambda v: v == arg
        limit = int(query.split(".limit(")[1].split(")")[0])
        return [_element_map(i) for i in self.ids if hit(i)][:limit]


def _ids(prefix: str, **options: Any) -> list[str]:
    store = _OptionStore(IDS)
    found = asyncio.run(
        make_adapter(store).suggest_nodes(
            prefix, PRINCIPAL, limit=10, options=SuggestOptions(**options)
        )
    )
    return [n.properties["value_normalised"] for n in found.nodes]


def test_the_default_is_still_starts_with_and_case_sensitive() -> None:
    assert _ids("jeff") == ["jeff.danforth@enron.com"]


def test_ignore_case_finds_either_case() -> None:
    assert _ids("jeff", ignore_case=True) == [
        "Jeff.Sorensen@enron.com",
        "jeff.danforth@enron.com",
    ]
    assert _ids("c13", ignore_case=True) == ["C13"]


def test_contains_finds_the_text_anywhere_and_is_case_sensitive_unless_asked() -> None:
    assert _ids("jeff", mode="contains") == [
        "jeff.danforth@enron.com",
        "ajeffries@x.org",
    ]
    assert _ids("JEFF", mode="contains", ignore_case=True) == [
        "Jeff.Sorensen@enron.com",
        "jeff.danforth@enron.com",
        "ajeffries@x.org",
    ]


def test_exact_matches_the_whole_value_only() -> None:
    assert _ids("C13", mode="exact") == ["C13"]
    assert _ids("C1", mode="exact") == []
    assert _ids("c13", mode="exact") == []
    assert _ids("c13", mode="exact", ignore_case=True) == ["C13"]


def test_regex_characters_in_what_is_typed_are_text_not_a_pattern() -> None:
    """Catches typed text being read as a regular expression: `.` must not match any character,
    and `\\E` in the text must not end the quoted section early."""
    store = _OptionStore(["a.b", "axb", "a\\Eb"])
    adapter = make_adapter(store)

    def run(text: str) -> list[str]:
        found = asyncio.run(
            adapter.suggest_nodes(
                text,
                PRINCIPAL,
                options=SuggestOptions(mode="contains", ignore_case=True),
            )
        )
        return [n.properties["value_normalised"] for n in found.nodes]

    assert run("a.b") == ["a.b"]
    assert run("a\\Eb") == ["a\\Eb"]


def test_types_narrow_the_scan_to_those_types() -> None:
    store = _OptionStore(IDS)
    asyncio.run(
        make_adapter(store).suggest_nodes(
            "jef", PRINCIPAL, options=SuggestOptions(types=("Endpoint",))
        )
    )
    query = store.queries[0]
    labels = query.split("hasLabel(")[1].split(")")[0]
    assert labels == f"'{physical_type_name('Endpoint')}'"


def test_an_unknown_type_is_refused_not_ignored() -> None:
    store = _OptionStore(IDS)
    with pytest.raises(ValueError, match="Nonsense"):
        asyncio.run(
            make_adapter(store).suggest_nodes(
                "jef", PRINCIPAL, options=SuggestOptions(types=("Nonsense",))
            )
        )
    assert store.queries == []


def test_a_type_that_carries_no_string_identifier_gives_nothing_and_asks_the_store_nothing() -> (
    None
):
    from ontology.loader import load_default_ontology

    schema = load_default_ontology()
    barren = next(
        (
            e.name
            for e in schema.entity_types
            if physical_type_name(e.name) not in builders.suggestion_scope(schema)[0]
        ),
        None,
    )
    if barren is None:
        pytest.skip("every type in the shipped ontology carries a string identifier")
    store = _OptionStore(IDS)
    found = asyncio.run(
        make_adapter(store).suggest_nodes(
            "jef", PRINCIPAL, options=SuggestOptions(types=(barren,))
        )
    )
    assert found.nodes == [] and found.more is False and store.queries == []


def test_the_access_step_and_the_limit_survive_every_option() -> None:
    for mode in ("starts_with", "contains", "exact"):
        for ignore_case in (False, True):
            store = _OptionStore(IDS)
            graph = make_adapter(store)
            asyncio.run(
                graph.suggest_nodes(
                    "jef",
                    PRINCIPAL,
                    limit=7,
                    options=SuggestOptions(mode=mode, ignore_case=ignore_case),
                )
            )
            query = store.queries[0]
            assert graph._access.gremlin_has_step(PRINCIPAL) in query, (
                mode,
                ignore_case,
            )
            assert ".limit(8)" in query, (mode, ignore_case)


def test_the_regex_quote_matches_javas_pattern_quote() -> None:
    assert builders.java_regex_quote("a.b") == "\\Qa.b\\E"
    assert builders.java_regex_quote("a\\Eb") == "\\Qa\\E\\\\E\\Qb\\E"


def test_exact_ignoring_case_does_not_match_a_longer_value() -> None:
    """Catches the end of the pattern being dropped: `c13` must not find `C130`."""
    store = _OptionStore(["C13", "C130", "xC13"])
    found = asyncio.run(
        make_adapter(store).suggest_nodes(
            "c13", PRINCIPAL, options=SuggestOptions(mode="exact", ignore_case=True)
        )
    )
    assert [n.properties["value_normalised"] for n in found.nodes] == ["C13"]
