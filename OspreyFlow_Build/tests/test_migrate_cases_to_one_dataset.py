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

from tests.services.api.unconverted import made_before_l3_2

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


async def test_a_case_made_a_composite_is_told_it_is_now_read_only(
    store: InMemoryDatasetStore,
) -> None:
    """ADR-099 Amendment 15: the migration's own words say what a composite case can still do,
    for each case it makes one, in a dry run as in the real one, and none for a source's case."""
    for write in (False, True):
        lines: list[str] = []
        await migrate(store, SEEDED, write=write, say=lines.append)
        said = {line.split(":")[0].strip(): line for line in lines}
        for case in ("both-case", "both-again"):
            (line,) = [v for k, v in said.items() if f"({case})" in k]
            assert "read-only for now" in line and "load in a case that reads" in line
        assert not any("read-only" in v for k, v in said.items() if "(enron-case)" in k)
    # Run again: the composite case is kept, and told so again.
    lines = []
    await migrate(store, SEEDED, write=True, say=lines.append)
    (again,) = [line for line in lines if "(both-case)" in line]
    assert "kept" in again and "read-only for now" in again


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
            assert reads == [chosen.id, *chosen.members, layer]
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


async def test_a_case_made_from_another_before_l3_1_keeps_an_empty_layer_of_its_own(
    store: InMemoryDatasetStore,
) -> None:
    """The temporary exception to ADR-144 Amendment 1 decision 2 (ADR-143 Amendment 1): a case made
    from another before L3.1 records only `branched_from`, as an alert jump's case does, whose maker
    may hold no level on the original (rule 3), so it keeps a layer of its own, and the run names
    it. A branch made from now on holds none (`test_analyst_layer.py`)."""
    store.cases["branch"] = ["enron"]
    cases = [
        CaseRow("enron-case", "Enron", UNIT, None),
        CaseRow("branch", "Branch of Enron", UNIT, "enron-case"),
    ]
    lines: list[str] = []
    report = await migrate(store, cases, write=True, say=lines.append)
    assert report.layers_made == ["enron-case", "branch"]
    parent = await store.layer_of_case("enron-case")
    branch = await store.layer_of_case("branch")
    assert parent and branch and parent != branch
    assert await store.ids_of_case("branch") == ["enron", branch]
    assert await store.read_only_layer_of("branch") is None
    (said,) = [line for line in lines if "made from another case" in line]
    assert said.strip().startswith("1 existing case made from another case keeps an empty layer")
    assert "Branch of Enron (branch)" in said and "L3.2 retires it" in said


async def test_the_migrated_case_check_fails_with_a_branchs_link_swapped_in(
    store: InMemoryDatasetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red: given what a branch made now gets (its original's layer, read-only, none of
    its own), the migrated case holds no layer and reads the original's."""

    async def as_a_branch_now(case: CaseRow, through: Any) -> None:
        if case.branched_from:
            store.layer_reads[case.id] = await store.layer_of_case(case.branched_from)  # type: ignore[assignment]
            return
        await through.ensure_layer(case.id, unit=case.owning_unit, created_by="t")

    monkeypatch.setattr(migration, "_give_a_layer", as_a_branch_now)
    store.cases["branch"] = ["enron"]
    cases = [
        CaseRow("enron-case", "Enron", UNIT, None),
        CaseRow("branch", "Branch of Enron", UNIT, "enron-case"),
    ]
    await migrate(store, cases, write=True, say=lambda _: None)
    assert await store.layer_of_case("branch") is None
    assert await store.read_only_layer_of("branch") == await store.layer_of_case("enron-case")


async def test_a_branch_reading_its_originals_layer_is_named_and_given_none(
    store: InMemoryDatasetStore,
) -> None:
    """The final L3.1 review's second blocker, in memory (the Postgres half, at `_main`, is in
    `test_migrate_cases_to_one_dataset_store.py`): a branch made since L3.1 reads its original's
    layer through a link and is refused a layer of its own. The run names it, gives it none, and
    goes on; a second run changes nothing."""
    cases = [CaseRow("enron-case", "Enron", UNIT, None)]
    await migrate(store, cases, write=True, say=lambda _: None)
    await made_before_l3_2(store, "enron-case", "twig")
    cases.append(CaseRow("twig", "Twig", UNIT, "enron-case"))
    for write in (False, True):
        lines: list[str] = []
        report = await migrate(store, cases, write=write, say=lines.append)
        assert report.writes == [] and report.layers_made == []
        assert report.read_their_originals_layer == ["Twig (twig)"]
        (said,) = [line for line in lines if "made since L3.1" in line]
        assert said.strip() == (
            "1 branch made since L3.1 reads its original's layer and is given none: Twig (twig)"
        )
    assert await store.layer_of_case("twig") is None


async def test_the_branch_is_refused_a_layer_with_its_link_unread(
    store: InMemoryDatasetStore,
) -> None:
    """Rule 15, red: the run as it was, reading no link, asks for the branch's layer and stops."""
    from services.api.datasets import ReadOnlyLayerError

    class _LinksUnread:
        def __init__(self, inner: InMemoryDatasetStore) -> None:
            self._inner = inner

        async def read_only_layer_of(self, investigation_id: str) -> None:
            return None

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

    await migrate(store, [CaseRow("enron-case", "Enron", UNIT, None)], write=True, say=print)
    await made_before_l3_2(store, "enron-case", "twig")
    with pytest.raises(ReadOnlyLayerError):
        await migrate(
            _LinksUnread(store),  # type: ignore[arg-type]
            [CaseRow("twig", "Twig", UNIT, "enron-case")],
            write=True,
            say=lambda _: None,
        )


async def test_a_legacy_branch_naming_several_datasets_is_counted_and_the_dry_run_agrees(
    store: InMemoryDatasetStore,
) -> None:
    """The final L3.1 review's 3a: a case made from another before L3.1 that names several datasets
    had its layer made inside `compose_for_case`, uncounted and unnamed, and the dry run said one
    write more than the real run made. Now its layer is made first, counted and named, and the dry
    run's writes are the real run's."""
    store.cases["legacy-both"] = ["enron", "fixture-corp"]
    cases = [
        CaseRow("enron-case", "Enron", UNIT, None),
        CaseRow("legacy-both", "Legacy both", UNIT, "enron-case"),
    ]
    dry_lines: list[str] = []
    dry = await migrate(store, cases, write=False, say=dry_lines.append)
    lines: list[str] = []
    real = await migrate(store, cases, write=True, say=lines.append)
    assert len(dry.writes) == len(real.writes)
    assert [w.split()[0] for w in dry.writes] == [
        "make", "make", "create", "set", "case",
    ]  # fmt: skip
    assert [w.split()[0] for w in real.writes] == [
        "ensure_layer", "ensure_layer", "create_composite", "set_egress", "set_for_case",
    ]  # fmt: skip
    assert real.layers_made == ["enron-case", "legacy-both"]
    assert real.kept_their_own_layer == ["Legacy both (legacy-both)"]
    assert any("Legacy both (legacy-both)" in line and "L3.2 retires it" in line for line in lines)
    assert await store.layer_of_case("legacy-both") is not None
