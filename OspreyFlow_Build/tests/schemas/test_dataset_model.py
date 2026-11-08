"""`schemas.dataset_model` (L3.1b; `01_DOMAIN_MODEL.md` §2.2b): what each shape refuses on its own,
before any store or route sees it. The stores' rules (one live and at most one draft; a revert as
N+2; the home case kept) are their own tests, in L3.1b's later steps.

What a mistake here would do, and the case that catches it:

- a property naming no type, or a type naming one: `test_a_property_names_its_type_and_a_type_none`;
- an extension retired in the version that added it, or before:
  `test_an_extension_is_retired_after_it_was_added`;
- a dataset made live with no one answering for it (ADR-145 Amendment 4 decision 4):
  `test_owners_name_someone`;
- a field the shape does not know taken silently (`extra="forbid"`):
  `test_an_unknown_field_is_refused`.

Each is shown red by `test_each_refusal_fails_with_its_check_removed`, which rebuilds the shape
without its validator.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError, create_model

from schemas.dataset_model import (
    DatasetOwners,
    DatasetOwnerSetting,
    HomeCase,
    MakeLiveInput,
    ModelExtension,
    ReferenceList,
    TargetModel,
)

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def test_a_property_names_its_type_and_a_type_none() -> None:
    ModelExtension(name="shoe_size", kind="property", on_type="Person", added_in=2)
    ModelExtension(name="Vessel", kind="entity_type", added_in=2)
    with pytest.raises(ValidationError, match="names the type it is on"):
        ModelExtension(name="shoe_size", kind="property", added_in=2)
    with pytest.raises(ValidationError, match="names the type it is on"):
        ModelExtension(name="Vessel", kind="entity_type", on_type="Person", added_in=2)


def test_an_extension_is_retired_after_it_was_added() -> None:
    ModelExtension(name="Vessel", kind="entity_type", added_in=2, retired_in=3)
    for retired in (2, 1):
        with pytest.raises(ValidationError, match="retired after"):
            ModelExtension(name="Vessel", kind="entity_type", added_in=2, retired_in=retired)


def test_owners_name_someone() -> None:
    DatasetOwners(people=["a.author"])
    DatasetOwners(team="Prison intel data team")
    DatasetOwners(people=["a.author"], team="Prison intel data team")
    with pytest.raises(ValidationError, match="cannot go live without someone"):
        DatasetOwners()
    with pytest.raises(ValidationError, match="cannot go live without someone"):
        MakeLiveInput(version=2, owners={"people": []})  # type: ignore[arg-type]
    assert MakeLiveInput(version=2).owners is None  # not the first Make live


def test_an_unknown_field_is_refused() -> None:
    shapes: list[tuple[type[BaseModel], dict[str, Any]]] = [
        (TargetModel, {"dataset_id": "d", "version": 1, "state": "live", "created_at": NOW,
                       "created_by": "a"}),
        (ReferenceList, {"id": "l", "dataset_id": "d", "name": "OFSI", "kind": "screening",
                         "key_column": "id", "version": 1}),
        (HomeCase, {"dataset_id": "d", "investigation_id": "c", "made_at": NOW, "made_by": "a"}),
        (DatasetOwnerSetting, {}),
    ]  # fmt: skip
    for shape, fields in shapes:
        shape(**fields)
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            shape(**fields, steward="someone")
    assert DatasetOwnerSetting().owners_may_be == "people_and_teams"


def _without_validators(shape: type[BaseModel]) -> type[BaseModel]:
    """`shape` with its fields and none of its validators: the refusal planted out."""
    fields = {name: (f.annotation, f) for name, f in shape.model_fields.items()}
    return create_model(f"{shape.__name__}Unchecked", **fields)  # type: ignore[call-overload,no-any-return]


def test_each_refusal_fails_with_its_check_removed() -> None:
    """Rule 15, red: each shape above rebuilt without its validator takes what it refused."""
    extension = _without_validators(ModelExtension)
    extension(name="shoe_size", kind="property", added_in=2)
    extension(name="Vessel", kind="entity_type", added_in=2, retired_in=2)
    _without_validators(DatasetOwners)()
