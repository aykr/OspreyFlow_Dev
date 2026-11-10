"""A dataset's home case is kept while its dataset exists (ADR-145 Amendment 4 decision 2; L3.H1):
removing it is refused (`test_home_cases.py::test_a_home_case_cannot_be_removed`), and so is moving
it off its dataset, which would leave the dataset's reports, alerts and promotion reviews in a case
that no longer reads it — a drawn dataset's for good, since a case may choose only a source or a
composite. Refused in words naming nothing beyond the case, before anything is written; a working
case reading the same dataset is moved as ever. Red with the check planted out at its call site
(`app.set_case_datasets_route`)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from services.api.datasets import Dataset

from .test_home_cases import _as, _make_live, world  # noqa: F401


def test_a_home_case_is_never_moved_off_its_dataset(world: SimpleNamespace) -> None:  # noqa: F811
    world.datasets.add(
        Dataset(id="ds-b", name="Visits", owning_unit="unit-1",
                created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="eng-1")
    )  # fmt: skip
    assert _make_live(world, {"people": ["ana-1"]}).status_code == 200
    home = world.datasets.homes["ds-a"].investigation_id
    path = f"/v1/investigations/{home}/datasets"
    refused = world.client.put(path, json={"dataset_ids": ["ds-b"]}, headers=_as("analyst"))
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["error"] == "home_case_kept"
    assert "ds-a" not in detail["message"] and "Prison records" not in detail["message"]
    assert world.datasets.cases[home] == ["ds-a"]
    assert not [e for e in world.audit.entries if e["action"] == "set_case_datasets"]
    # Its own dataset again: nothing changes, and it is not refused.
    again = world.client.put(path, json={"dataset_ids": ["ds-a"]}, headers=_as("analyst"))
    assert again.status_code == 200, again.text
    # A working case reading the same dataset is moved as ever.
    moved = world.client.put(
        "/v1/investigations/case-a/datasets", json={"dataset_ids": ["ds-b"]}, headers=_as("analyst")
    )
    assert moved.status_code == 200, moved.text
