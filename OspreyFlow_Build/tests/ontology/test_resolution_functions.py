"""The closed function registry for `resolution: {blocking, comparisons}` —
`spec/06_DECISIONS.md` ADR-021, `01_DOMAIN_MODEL.md` §4."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ontology.errors import OntologyError
from ontology.loader import load_ontology
from ontology.resolution_functions import (
    ResolutionFunctionCall,
    blocking_rule_sql,
    parse_resolution_function,
    validate_resolution_config,
)


def test_parse_resolution_function_reads_name_and_single_arg() -> None:
    assert parse_resolution_function("jaro_winkler(family_name)") == ResolutionFunctionCall(
        name="jaro_winkler", args=("family_name",)
    )


def test_parse_resolution_function_reads_multiple_args() -> None:
    assert parse_resolution_function("foo(a, b)") == ResolutionFunctionCall(
        name="foo", args=("a", "b")
    )


@pytest.mark.parametrize(
    "expr", ["not a call", "jaro_winkler(", "jaro_winkler()", "jaro_winkler(family_name", "()"]
)
def test_parse_resolution_function_rejects_malformed_syntax(expr: str) -> None:
    with pytest.raises(OntologyError):
        parse_resolution_function(expr)


def test_validate_resolution_config_accepts_the_default_ontologys_own_person_block() -> None:
    validate_resolution_config(
        "Person",
        blocking=["soundex(family_name)", "year(date_of_birth)"],
        comparisons=[
            "jaro_winkler(family_name)",
            "levenshtein(given_names)",
            "exact(date_of_birth)",
        ],
    )  # no raise


def test_validate_resolution_config_rejects_an_unregistered_function() -> None:
    with pytest.raises(OntologyError, match="unregistered function 'metaphone'"):
        validate_resolution_config("Person", blocking=["metaphone(family_name)"], comparisons=[])


def test_validate_resolution_config_rejects_wrong_arity() -> None:
    with pytest.raises(OntologyError, match="takes 1 argument"):
        validate_resolution_config(
            "Person", blocking=[], comparisons=["jaro_winkler(family_name, given_names)"]
        )


def test_blocking_rule_sql_renders_expected_conditions() -> None:
    assert blocking_rule_sql(parse_resolution_function("exact(email)")) == "l.email = r.email"
    assert (
        blocking_rule_sql(parse_resolution_function("soundex(family_name)"))
        == "soundex(l.family_name) = soundex(r.family_name)"
    )
    assert (
        blocking_rule_sql(parse_resolution_function("year(date_of_birth)"))
        == "year(l.date_of_birth) = year(r.date_of_birth)"
    )


def _write(tmp_path: Path, doc: dict[str, object]) -> Path:
    path = tmp_path / "ontology.yaml"
    path.write_text(yaml.safe_dump(doc))
    return path


def test_load_ontology_rejects_an_unregistered_resolution_function(tmp_path: Path) -> None:
    doc = {
        "version": 1,
        "entity_types": [
            {
                "name": "Person",
                "pole_class": "person",
                "channel": "indigo",
                "shape": "circle",
                "resolution": {"blocking": ["metaphone(family_name)"], "comparisons": []},
            },
        ],
        "edge_types": [],
    }
    with pytest.raises(OntologyError, match="unregistered function"):
        load_ontology(_write(tmp_path, doc))


def test_load_ontology_accepts_a_valid_resolution_block(tmp_path: Path) -> None:
    doc = {
        "version": 1,
        "entity_types": [
            {
                "name": "Person",
                "pole_class": "person",
                "channel": "indigo",
                "shape": "circle",
                "resolution": {
                    "blocking": ["exact(family_name)"],
                    "comparisons": ["jaro_winkler(family_name)"],
                },
            },
        ],
        "edge_types": [],
    }
    schema = load_ontology(_write(tmp_path, doc))
    person = next(e for e in schema.entity_types if e.name == "Person")
    assert person.resolution is not None
    assert person.resolution.blocking == ["exact(family_name)"]
