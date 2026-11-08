"""Golden tests for Derive's closed catalogue (ADR-140 decision 11; `09_INGEST_STUDIO.md` §9,
rule 8: guided mode holds no expression language, so every operation a Derive step may name is a
Knowledge Adapter with a golden file here).

Each operation's golden file, `golden/derive/<operation>.json`, lists cells in, declared settings,
and either the value out or the words of the refusal. What a mistake would do, and the case that
catches it:

- an operation in the catalogue with no golden file, so nothing checks what it does
  (`test_every_operation_has_a_golden_file`), or a golden file for an operation that is not in it
  (`test_every_golden_file_names_an_operation`);
- an operation that guesses instead of refusing (each golden file's `refused` cases);
- a name that is not in the catalogue run anyway, as an expression would be
  (`test_a_name_outside_the_catalogue_is_refused`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from knowledge_adapters.derive import DERIVE_OPERATIONS, derive
from knowledge_adapters.errors import NormalisationError
from schemas.staging import DeriveOperation

GOLDEN = Path(__file__).parent / "golden" / "derive"


def _cases() -> list[tuple[str, int, dict[str, Any]]]:
    out: list[tuple[str, int, dict[str, Any]]] = []
    for path in sorted(GOLDEN.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for i, case in enumerate(data["cases"]):
            out.append((data["operation"], i, case))
    return out


@pytest.mark.parametrize(("operation", "index", "case"), _cases())
def test_each_operation_gives_its_golden_value_or_refuses_in_words(
    operation: str, index: int, case: dict[str, Any]
) -> None:
    if "refused" in case:
        with pytest.raises(NormalisationError) as caught:
            derive(operation, case["values"], case["params"])
        assert caught.value.adapter == f"derive.{operation}"
        assert case["refused"] in caught.value.reason, (index, caught.value.reason)
    else:
        assert derive(operation, case["values"], case["params"]) == case["expected"], index


def test_every_operation_has_a_golden_file() -> None:
    golden = {path.stem for path in GOLDEN.glob("*.json")}
    assert set(DERIVE_OPERATIONS) <= golden, set(DERIVE_OPERATIONS) - golden


def test_every_golden_file_names_an_operation() -> None:
    for path in GOLDEN.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["operation"] == path.stem
        assert data["operation"] in DERIVE_OPERATIONS
        assert any("refused" in c for c in data["cases"]), f"{path.stem} never shows a refusal"


@pytest.mark.parametrize("name", ["eval", "lambda row: row['a']", "a + b", "__import__"])
def test_a_name_outside_the_catalogue_is_refused(name: str) -> None:
    with pytest.raises(NormalisationError) as caught:
        derive(name, ["1", "2"], {})
    assert "not in Derive's catalogue" in caught.value.reason


def test_the_catalogue_is_the_brief_s_and_no_more() -> None:
    """The brief §6's list, as named operations; a new one is a decision, not a drive-by."""
    assert set(DERIVE_OPERATIONS) == {
        "concat",
        "split",
        "substring",
        "date_parse",
        "arithmetic",
        "case_when",
        "normalise",
    }


def test_the_recipe_schema_offers_exactly_this_catalogue() -> None:
    """`schemas.staging.DeriveOperation` is what a recipe may name; the two lists are one."""
    assert set(DeriveOperation.__args__) == set(DERIVE_OPERATIONS)
