"""Golden tests for `split` (ADR-127 Amendment 15): a delimited cell becomes a list of text, for a
`string[]` property such as `Person.aliases`.

Not a normaliser of one identifier but the one adapter whose output is a list. What a mistake would
do, and the case that catches it:

- a part kept with its padding, so `"Cally V "` and `"Cally V"` are two aliases
  (`test_each_part_is_trimmed`);
- an empty part kept, writing an alias of nothing (`test_empty_parts_are_dropped`);
- the order a source gave lost (`test_the_order_of_the_source_is_kept`);
- one name written twice, which a list of aliases says nothing by (`test_a_repeated_part_is_kept_once_at_its_first_place`);
- an empty or blank cell read as one empty alias (`test_an_empty_or_blank_cell_is_an_empty_list`);
- a delimiter that cannot be told apart from nothing (`test_an_empty_delimiter_is_refused`);
- the adapter missing from the registry the Map inspector offers
  (`test_split_is_in_the_registry_and_takes_one_column`)."""

from __future__ import annotations

import pytest

from knowledge_adapters import ARITY, REGISTRY
from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.split import split
from services.ingest.transforms import apply_transform


def test_a_cell_becomes_its_parts_on_the_pipe_by_default() -> None:
    assert split("Cally V|Cal|Big C") == ["Cally V", "Cal", "Big C"]


def test_a_single_name_is_a_list_of_one() -> None:
    assert split("Cally V") == ["Cally V"]


def test_each_part_is_trimmed() -> None:
    assert split("  Cally V |  Cal\t| Big C  ") == ["Cally V", "Cal", "Big C"]


def test_empty_parts_are_dropped() -> None:
    assert split("a||b| |c|") == ["a", "b", "c"]
    assert split("|") == []


def test_the_order_of_the_source_is_kept() -> None:
    assert split("c|a|b") == ["c", "a", "b"]


def test_a_repeated_part_is_kept_once_at_its_first_place() -> None:
    assert split("a|b|a|c|b") == ["a", "b", "c"]
    # Case is part of a name: these are two.
    assert split("Cal|cal") == ["Cal", "cal"]


@pytest.mark.parametrize("cell", ["", " ", "\t  "])
def test_an_empty_or_blank_cell_is_an_empty_list(cell: str) -> None:
    assert split(cell) == []


def test_another_delimiter_is_an_argument() -> None:
    assert split("a;b; c", delimiter=";") == ["a", "b", "c"]
    assert split("a|b;c", delimiter=";") == ["a|b", "c"]
    assert split("a::b", delimiter="::") == ["a", "b"]


def test_an_empty_delimiter_is_refused() -> None:
    with pytest.raises(NormalisationError, match="delimiter"):
        split("a|b", delimiter="")


def test_split_is_in_the_registry_and_takes_one_column() -> None:
    assert REGISTRY["split"] is split
    assert "split" not in ARITY, "a one-column adapter declares no arity"


def test_a_recipe_names_it_with_its_delimiter_as_any_adapter_takes_an_argument() -> None:
    assert apply_transform("split", "a|b") == ["a", "b"]
    assert apply_transform("split(delimiter=;)", "a;b") == ["a", "b"]
