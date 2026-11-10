"""Every Studio lookup caller names the dataset's subscribed lists (CARRIES rows 36 and 41; ADR-140
Amendment 16): the functions a sample, Test and a run go through take `subscribed` with no default,
so a caller left on an empty default, which reads no subscribed list and leaves every Lookup of one
unmatched, fails mypy and its call at once instead (rule 12). Red before: each had `= ()`."""

from __future__ import annotations

import inspect

import pytest
from services.ingest import reference_list_import, staged_run, staging_catalogue

FUNCTIONS = [
    reference_list_import.lists_for_run,
    staging_catalogue.readable_lists,
    staging_catalogue.staging_rule_violations,
    staging_catalogue.run_staging,
    staged_run.prepare_staged_load,
    staged_run.run_staged_recipe,
    staged_run.dry_run_staged_recipe,
]


@pytest.mark.parametrize("function", FUNCTIONS, ids=lambda f: f.__name__)
def test_subscribed_must_be_given(function: object) -> None:
    parameter = inspect.signature(function).parameters["subscribed"]  # type: ignore[arg-type]
    assert parameter.default is inspect.Parameter.empty
