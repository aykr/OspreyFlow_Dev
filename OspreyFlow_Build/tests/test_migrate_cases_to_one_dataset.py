"""`scripts.migrate_cases_to_one_dataset` (ADR-099 Amendment 12 item 9, ADR-143 decision 1).

What a mistake here would do, and the case that catches it:

- a dry run that writes: `test_a_dry_run_writes_nothing`, shown red by handing the dry run the real
  store (`test_the_dry_run_check_fails_with_the_real_store_handed_in`);
- a case left reading two datasets, or without its layer, after a real run:
  `test_the_real_run_leaves_every_seeded_case_reading_one_dataset_plus_its_layer`;
- a second run changing anything, or making a second composite of the same set:
  `test_a_second_run_changes_nothing`;
- a case it cannot place being guessed at: `test_a_case_it_cannot_place_is_reported_not_guessed`.

In memory; the Postgres half (the one-row index) is `test_migrate_cases_to_one_dataset_store.py`.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

import pytest
from scripts import migrate_cases_to_one_dataset as migration
from scripts.migrate_cases_to_one_dataset import migrate
from scripts.stamp_datasets import CaseRow
from services.api.datasets import ANALYST_LAYER, COMPOSITE, Dataset, InMemoryDatasetStore

UNIT = "unit-1"


def _dataset(dataset_id: str, name: str, unit: str = UNIT) -> Dataset:
    return Dataset(
        id=dataset_id,
        name=name,
        owning_unit=unit,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        created_by="seed",
    )


#: The seeded deployment's shape before phase 5: a case per seed reading its dataset, a case reading
#: two (as `case_seed.ensure_case_reads` used to append), and a second case naming the same two.
SEEDED = [
    CaseRow("enron-case", "Enron", UNIT, None),
    CaseRow("fixture-case", "Fixture Corp", UNIT, None),
    CaseRow("both-case", "Enron and Fixture", UNIT, None),
    CaseRow("both-again", "Both, again", UNIT, None),
    CaseRow("hmp-case", "HMP", UNIT, None),
]


@pytest.fixture
def store() -> InMemoryDatasetStore:
    held = InMemoryDatasetStore()
    for dataset_id, name in [
        ("enron", "Enron corpus"),
        ("fixture-corp", "Fixture Corp"),
        ("hmp", "HMP"),
    ]:
        held.add(_dataset(dataset_id, name))
    held.datasets["enron"] = held.datasets["enron"].model_copy(update={"egress": "any"})
    held.datasets["fixture-corp"] = held.datasets["fixture-corp"].model_copy(
        update={"egress": "contracted"}
    )
    # Written as the store held them before one dataset per case: rows, no layers.
    held.cases.update(
        {
            "enron-case": ["enron"],
            "fixture-case": ["fixture-corp"],
            "both-case": ["fixture-corp", "enron"],
            "both-again": ["enron", "fixture-corp"],
            "hmp-case": ["hmp"],
        }
    )
    return held


def _state(store: InMemoryDatasetStore) -> Any:
    return copy.deepcopy((store.datasets, store.cases))


async def test_a_dry_run_writes_nothing(store: InMemoryDatasetStore) -> None:
    before = _state(store)
    report = await migrate(store, SEEDED, write=False, say=lambda _: None)
    assert _state(store) == before
    # ... and says what it would do: two cases onto one composite, five layers.
    assert sum(new for _, _, new in report.composed) == 1
    assert len(report.composed) == 2
    assert len(report.layers_made) == 5


async def test_the_dry_run_check_fails_with_the_real_store_handed_in(
    store: InMemoryDatasetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the defect in its real shape (the dry run writing through the real store) is
    caught by the same state comparison."""
    real = migration.store_for
    monkeypatch.setattr(
        migration, "store_for", lambda s, *, write, writes: real(s, write=True, writes=writes)
    )
    before = _state(store)
    await migrate(store, SEEDED, write=False, say=lambda _: None)
    assert _state(store) != before


async def test_the_real_run_leaves_every_seeded_case_reading_one_dataset_plus_its_layer(
    store: InMemoryDatasetStore,
) -> None:
    report = await migrate(store, SEEDED, write=True, say=lambda _: None)
    assert report.unplaced == []
    for case in SEEDED:
        (chosen,) = await store.chosen_of_case(case.id)
        layer = await store.layer_of_case(case.id)
        assert layer is not None and store.datasets[layer].kind == ANALYST_LAYER
        reads = await store.ids_of_case(case.id)
        if chosen.kind == COMPOSITE:
            assert reads == [*chosen.members, chosen.id, layer]
        else:
            assert reads == [chosen.id, layer]
    # The two cases naming the same set share one composite, members in the first case's order,
    # its egress the strictest of its members'.
    (both,) = await store.chosen_of_case("both-case")
    (again,) = await store.chosen_of_case("both-again")
    assert both.id == again.id
    assert both.members == ["fixture-corp", "enron"]
    assert both.egress == "contracted"
    # Each reads exactly what it read before, plus its own layer.
    assert set(await store.ids_of_case("both-case")) - {both.id} == {
        "fixture-corp",
        "enron",
        await store.layer_of_case("both-case"),
    }


async def test_a_second_run_changes_nothing(store: InMemoryDatasetStore) -> None:
    await migrate(store, SEEDED, write=True, say=lambda _: None)
    after_first = _state(store)
    report = await migrate(store, SEEDED, write=True, say=lambda _: None)
    assert report.writes == []
    assert _state(store) == after_first


async def test_a_case_it_cannot_place_is_reported_not_guessed(
    store: InMemoryDatasetStore,
) -> None:
    store.add(_dataset("theirs", "Another unit's", unit="unit-2"))
    store.cases["empty-case"] = []
    store.cases["crossed-case"] = ["enron", "theirs"]
    cases = [
        CaseRow("empty-case", "Empty", UNIT, None),
        CaseRow("crossed-case", "Crossed", UNIT, None),
    ]
    before = _state(store)
    report = await migrate(store, cases, write=True, say=lambda _: None)
    assert [line.split(":")[0] for line in report.unplaced] == [
        "Empty (empty-case)",
        "Crossed (crossed-case)",
    ]
    assert _state(store) == before  # nothing written for either, not even a layer


async def test_a_case_naming_a_composite_beside_another_dataset_is_reported(
    store: InMemoryDatasetStore,
) -> None:
    both = Dataset(
        id="both",
        name="Both",
        owning_unit=UNIT,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        created_by="seed",
        kind=COMPOSITE,
        members=["enron", "fixture-corp"],
    )
    store.add(both)
    store.cases["odd-case"] = ["both", "hmp"]
    before = _state(store)
    report = await migrate(
        store, [CaseRow("odd-case", "Odd", UNIT, None)], write=True, say=lambda _: None
    )
    assert report.unplaced == ["Odd (odd-case): names a composite beside another dataset"]
    assert _state(store) == before
