"""ADR-127 decision 5: a draft's `deduplicate` is judged at save (`recipe_rules.deduplicate_problems`).

It is judged by the same shapes `engine.dedup_key` resolves, so what passes here is what a run can
key: a key names a source column (a literal alone puts every row in one group, so a file loads as one
row), a column the source has when its header is known, and a multi-column binding declares a
transform of the right arity. Each case below is a defect a run would have met row by row, or never
seen (a literal-only key loads one row and says nothing)."""

from __future__ import annotations

import pytest
from services.ingest.recipe_rules import deduplicate_problems

from schemas.ingest import DeduplicateConfig, FieldBinding

COLUMNS = ["payer", "payee", "paid_at", "easting", "northing"]


def _config(*bindings: FieldBinding) -> DeduplicateConfig:
    return DeduplicateConfig(key=list(bindings))


def test_a_key_of_source_columns_passes() -> None:
    config = _config(
        FieldBinding(field="payer"),
        FieldBinding(field="paid_at", transform="datetime"),
        FieldBinding(fields=["easting", "northing"], transform="coordinate_lon"),
    )
    assert deduplicate_problems(config, COLUMNS) == []


def test_a_literal_beside_a_column_is_a_salt_and_passes() -> None:
    config = _config(FieldBinding(field="payer"), FieldBinding(literal="cash"))
    assert deduplicate_problems(config, COLUMNS) == []


@pytest.mark.parametrize(
    ("config", "said"),
    [
        (_config(FieldBinding(field="ghost")), "'ghost'"),
        (_config(FieldBinding(fields=["easting", "ghost"], transform="coordinate_lon")), "'ghost'"),
        (_config(FieldBinding(literal="x")), "names no source column"),
        (_config(FieldBinding()), "names no source column"),
        (_config(FieldBinding(fields=["payer", "payee"])), "must declare a `transform`"),
        (_config(FieldBinding(fields=["payer"], transform="datetime")), "does not support"),
        (_config(FieldBinding(fields=["easting"], transform="coordinate_lon")), "takes 2 field(s)"),
    ],
    ids=["unknown", "unknown in fields", "literal alone", "empty binding", "no transform",
         "single-column transform", "wrong arity"],
)  # fmt: skip
def test_what_a_run_could_not_key_is_refused_in_words(config: DeduplicateConfig, said: str) -> None:
    assert said in " ".join(deduplicate_problems(config, COLUMNS))


def test_with_no_columns_known_only_the_shape_is_judged() -> None:
    assert deduplicate_problems(_config(FieldBinding(field="anything")), None) == []
    assert deduplicate_problems(_config(FieldBinding(literal="x")), None) != []
