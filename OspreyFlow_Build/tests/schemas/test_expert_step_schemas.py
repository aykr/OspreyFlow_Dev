"""The expert steps' records (ADR-140 decisions 12 and 13; the redesign's phase 8;
`schemas/staging.py`). What a mistake would do, and the case that catches it:

- a SQL step saved without its plain-words summary, which guided mode and every run report show
  (`test_a_sql_step_needs_its_summary`);
- a fuzzy match whose threshold is no threshold, or that compares a table with itself
  (`test_a_fuzzy_threshold_lies_between_nought_and_one`, `test_a_fuzzy_match_reads_two_tables`);
- either step carrying a key it does not declare (`test_an_expert_step_refuses_an_undeclared_key`);
- the methods drifting from the Splink-backed comparisons the product has
  (`test_the_fuzzy_methods_are_the_resolution_registry_s`);
- a run report's disclosure carrying a row's value (`test_the_disclosure_holds_settings_only`).
"""

from __future__ import annotations

import typing

import pytest
from pydantic import TypeAdapter, ValidationError

from ontology.resolution_functions import BLOCKING_FUNCTIONS, COMPARISON_FUNCTIONS
from schemas.ingest import ExpertStepDisclosure
from schemas.staging import (
    EXPERT_KINDS,
    FuzzyBlock,
    FuzzyMatchStep,
    FuzzyMethod,
    SqlStep,
    StagingStep,
)

STEP: TypeAdapter[StagingStep] = TypeAdapter(StagingStep)

SQL = {
    "id": "calls", "kind": "sql", "inputs": ["visits", "pin_calls"],
    "select": "SELECT v.*, list(c._ref) AS _ref_calls FROM visits v JOIN pin_calls c USING (pin)",
    "summary": "Counts each booking's PIN calls.",
}  # fmt: skip
FUZZY = {
    "id": "visitor_owner", "kind": "fuzzy_match", "left": "calls", "right": "number_owners",
    "compare": [{"left": "visitor_name", "right": "owner_name", "method": "jaro_winkler"}],
    "threshold": 0.85, "add": [{"column": "owner_name", "as": "matched_owner"}],
    "same_as": {"left": "visitor", "right": "owner"},
}  # fmt: skip


def test_the_expert_steps_are_in_the_staging_union() -> None:
    assert isinstance(STEP.validate_python(SQL), SqlStep)
    assert isinstance(STEP.validate_python(FUZZY), FuzzyMatchStep)
    assert EXPERT_KINDS == {"sql", "fuzzy_match"}


@pytest.mark.parametrize("summary", ["", "   "])
def test_a_sql_step_needs_its_summary(summary: str) -> None:
    with pytest.raises(ValidationError):
        STEP.validate_python({**SQL, "summary": summary})
    record = {k: v for k, v in SQL.items() if k != "summary"}
    with pytest.raises(ValidationError):
        STEP.validate_python(record)


@pytest.mark.parametrize("threshold", [0, 1, -0.2, 1.5])
def test_a_fuzzy_threshold_lies_between_nought_and_one(threshold: float) -> None:
    with pytest.raises(ValidationError):
        STEP.validate_python({**FUZZY, "threshold": threshold})


def test_a_fuzzy_match_reads_two_tables() -> None:
    with pytest.raises(ValidationError):
        STEP.validate_python({**FUZZY, "right": "calls"})
    with pytest.raises(ValidationError):
        STEP.validate_python({**FUZZY, "same_as": {"left": "visitor", "right": "visitor"}})


@pytest.mark.parametrize(
    ("record", "key"), [(SQL, "expression"), (SQL, "script"), (FUZZY, "where"), (FUZZY, "sql")]
)
def test_an_expert_step_refuses_an_undeclared_key(record: dict[str, object], key: str) -> None:
    with pytest.raises(ValidationError):
        STEP.validate_python({**record, key: "1 = 1"})


def test_the_fuzzy_methods_are_the_resolution_registry_s() -> None:
    assert set(typing.get_args(FuzzyMethod)) == set(COMPARISON_FUNCTIONS)
    assert set(typing.get_args(FuzzyBlock)) == set(BLOCKING_FUNCTIONS)


def test_the_disclosure_holds_settings_only() -> None:
    # Rule 3: shown whether or not the run's counts are withheld, so it carries nothing of a row:
    # no count, no cell, no key; the counts are `staging_steps`', withheld with the rest.
    assert set(ExpertStepDisclosure.model_fields) == {
        "step", "kind", "label", "summary", "select", "reads", "compares", "threshold", "same_as",
    }  # fmt: skip
