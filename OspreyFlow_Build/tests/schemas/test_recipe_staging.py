"""The recipe's `staging:` list and a staged row's source identity (ADR-140 decision 11; the
orchestrator's settlement of 8 November 2026, Q1 and Q2; `schemas/staging.py`).

What a mistake would do, and the case that catches it:

- every published recipe re-serialised with a `staging` key it never had, so its committed YAML
  changes under it (`test_a_recipe_without_staging_serialises_byte_for_byte_as_before`; shown red
  with the field defaulting to an empty list, which `exclude_none` keeps);
- every element's stored provenance gaining two null keys
  (`test_a_source_ref_without_staging_identity_is_stored_as_before`);
- a step that holds an expression, under a key of its own or as an operation outside the
  catalogue (`test_a_step_refuses_an_expression_under_any_key`,
  `test_a_derive_outside_the_catalogue_is_refused`) — rule 8;
- a join with a guessed key (`test_a_join_must_name_both_keys`);
- a staging list that does not survive its own YAML (`test_a_staging_list_round_trips_its_yaml`).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import TypeAdapter, ValidationError
from services.api.studio_publish import serialise_recipe
from services.ingest.recipe_loader import load_recipe

from schemas.domain import SourceRef
from schemas.ingest import Recipe
from schemas.staging import StagingStep

REPO = Path(__file__).resolve().parents[3]
STEPS = TypeAdapter(list[StagingStep])


def _committed_recipes() -> list[Recipe]:
    listed = subprocess.run(
        ["git", "ls-files", "*.yaml"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    recipes = []
    for name in listed:
        path = REPO / name
        if "\nrow_template:" not in path.read_text(encoding="utf-8"):
            continue
        try:
            recipes.append(load_recipe(path))
        except (ValidationError, ValueError):
            continue  # a fixture of a refused recipe; not a published one
    return recipes


def test_a_recipe_without_staging_serialises_byte_for_byte_as_before() -> None:
    recipes = _committed_recipes()
    assert len(recipes) >= 40, len(recipes)
    for recipe in recipes:
        assert recipe.staging is None
        text = serialise_recipe(recipe)
        before = yaml.safe_dump(
            recipe.model_dump(mode="json", by_alias=True, exclude_none=True, exclude={"staging"}),
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )
        assert text == before, recipe.id
        assert "staging" not in yaml.safe_load(text), recipe.id


def test_a_source_ref_without_staging_identity_is_stored_as_before() -> None:
    plain = SourceRef(document_id="calls.csv", locator="row 4", excerpt_hash="")
    assert plain.model_dump(mode="json") == {
        "document_id": "calls.csv",
        "locator": "row 4",
        "excerpt_hash": "",
    }
    staged = SourceRef(
        document_id="number_owners", locator="row 2", excerpt_hash="", row_key="k1", load_id="ld-2"
    )
    dumped = staged.model_dump(mode="json")
    assert dumped["row_key"] == "k1" and dumped["load_id"] == "ld-2"
    assert SourceRef.model_validate(dumped) == staged


VISITS: list[dict[str, Any]] = [
    {
        "id": "with_establishment",
        "kind": "lookup",
        "input": "visit_bookings",
        "list": "establishments",
        "on": "estab_id",
        "add": [{"column": "name", "as": "establishment_name"}],
    },
    {
        "id": "with_owner",
        "kind": "join",
        "left": "with_establishment",
        "right": "number_owners",
        "left_key": "contact_number",
        "right_key": "number",
        "normalise": "msisdn",
        "how": "left",
        "add": [{"column": "owner_name"}],
    },
    {
        "id": "kept",
        "kind": "filter",
        "input": "with_owner",
        "keep": [{"field": "booking_id", "is": "not_null"}],
    },
    {
        "id": "named",
        "kind": "derive",
        "input": "kept",
        "column": "visitor_full_name",
        "operation": "concat",
        "columns": ["visitor_given", "visitor_family"],
    },
]


def test_a_staging_list_round_trips_its_yaml() -> None:
    steps = STEPS.validate_python(VISITS)
    text = yaml.safe_dump(
        STEPS.dump_python(steps, mode="json", by_alias=True, exclude_none=True), sort_keys=False
    )
    assert (
        "list: establishments" in text
        and "as: establishment_name" in text
        and "is: not_null" in text
    )
    assert STEPS.validate_python(yaml.safe_load(text)) == steps


@pytest.mark.parametrize("key", ["expression", "sql", "python", "code", "where"])
def test_a_step_refuses_an_expression_under_any_key(key: str) -> None:
    step = {**VISITS[2], key: "booking_id IS NOT NULL OR 1=1"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        STEPS.validate_python([step])


def test_a_derive_outside_the_catalogue_is_refused() -> None:
    with pytest.raises(ValidationError):
        STEPS.validate_python([{**VISITS[3], "operation": "eval"}])
    with pytest.raises(ValidationError):
        STEPS.validate_python([{**VISITS[0], "kind": "sql"}])


def test_a_join_must_name_both_keys() -> None:
    for missing in ("left_key", "right_key"):
        step = {k: v for k, v in VISITS[1].items() if k != missing}
        with pytest.raises(ValidationError, match=missing):
            STEPS.validate_python([step])


def test_a_filter_condition_names_exactly_one_test() -> None:
    with pytest.raises(ValidationError, match="exactly one of is, equals or in"):
        STEPS.validate_python(
            [{**VISITS[2], "keep": [{"field": "a", "is": "null", "equals": "x"}]}]
        )
    with pytest.raises(ValidationError, match="exactly one of is, equals or in"):
        STEPS.validate_python([{**VISITS[2], "keep": [{"field": "a"}]}])


@pytest.mark.parametrize("key", ["sql", "expression", "python", "code"])
def test_a_derive_s_settings_refuse_any_key_its_operation_does_not_read(key: str) -> None:
    """Rule 8 inside a Derive: its settings are typed per operation, so an expression cannot ride
    in under a settings key either (the review's S3 plant, round 1)."""
    step = {**VISITS[3], "settings": {"separator": " ", key: "SELECT 1"}}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        STEPS.validate_python([step])


@pytest.mark.parametrize(
    ("operation", "columns", "settings", "words"),
    [
        ("split", ["a"], {"part": -1}, "greater than or equal to 0"),
        ("split", ["a", "b"], {}, "split reads 1 column(s), not 2"),
        ("concat", ["a"], {}, "concat reads at least 2 column(s), not 1"),
        ("substring", ["a"], {"length": 0}, "greater than or equal to 1"),
        ("arithmetic", ["a", "b"], {"op": "power"}, "'add', 'subtract', 'multiply' or 'divide'"),
        ("arithmetic", ["a"], {"op": "add"}, "one column with a constant, or two columns"),
        ("arithmetic", ["a"], {"op": "add", "constant": "ten"}, "constant is not a number"),
        ("case_when", ["a"], {"cases": []}, "at least 1 item"),
        ("case_when", ["a"], {"cases": [{"equals": "V"}]}, "then"),
        (
            "case_when",
            ["a"],
            {"cases": [{"equals": "V", "then": "a"}, {"equals": "V", "then": "b"}]},
            "names V twice",
        ),
        ("normalise", ["a"], {}, "adapter"),
        ("date_parse", ["a"], {"date_order": "ymd"}, "'dmy' or 'mdy'"),
    ],
)
def test_a_derive_with_settings_or_columns_its_operation_cannot_read_is_refused_at_the_gate(
    operation: str, columns: list[str], settings: dict[str, Any], words: str
) -> None:
    step = {
        "id": "d",
        "kind": "derive",
        "input": "t",
        "column": "c",
        "operation": operation,
        "columns": columns,
        "settings": settings,
    }
    with pytest.raises(ValidationError, match=re.escape(words)):
        STEPS.validate_python([step])
