"""`scripts.seed_target_models` (ADR-126 Amendment 3; L3.1b step 3), in memory.

What a mistake here would do, and the case that catches it:

- a case's packs reaching a dataset it does not read (the orchestrator's condition):
  `test_a_datasets_packs_are_only_those_its_own_cases_chose`, red with the union taken over every
  case (`test_the_union_check_fails_taken_over_every_case`);
- a dataset left with no model, so its cases lose their packs:
  `test_every_dataset_but_a_layer_is_given_version_one_live`;
- a dataset that has a model given a second first one, or a second run writing:
  `test_a_dataset_with_a_model_is_kept_and_a_second_run_changes_nothing`;
- a dry run that writes, or that plans other writes than the real run makes:
  `test_the_dry_run_writes_nothing_and_plans_what_the_real_run_makes`.
"""

from __future__ import annotations

from typing import Any

import pytest
from scripts import seed_target_models as seeding
from scripts.seed_target_models import DatasetRow, seed
from services.api.target_models import CORE_TYPES_FOR_TESTS, InMemoryTargetModelStore

PACK_VERSIONS = {"fibo": 1, "niem": 3, "stix": 1}
DATASETS = [
    DatasetRow("ds-bank", "Bank records", "source"),
    DatasetRow("ds-prison", "Prison records", "source"),
    DatasetRow("ds-quiet", "Nobody's", "source"),
    DatasetRow("comp-both", "Bank + Prison", "composite"),
    DatasetRow("layer-1", "Case one's layer", "analyst_layer"),
]
#: The one dataset each case chose.
CHOSEN = {
    "case-kyc": "ds-bank",
    "case-kyc-2": "ds-bank",
    "case-prison": "ds-prison",
    "case-both": "comp-both",
}
DOMAINS = {
    "case-kyc": ["fibo"],
    "case-kyc-2": ["fibo", "stix"],
    "case-prison": ["niem"],
    "case-both": [],
}


def _store() -> InMemoryTargetModelStore:
    return InMemoryTargetModelStore(core_types=CORE_TYPES_FOR_TESTS)


async def _run(
    store: InMemoryTargetModelStore, *, write: bool = True, with_a_model: Any = ()
) -> Any:
    return await seed(
        DATASETS, CHOSEN, DOMAINS, set(with_a_model),
        store=store, pack_versions=PACK_VERSIONS, write=write, say=lambda _: None,
    )  # fmt: skip


async def test_a_datasets_packs_are_only_those_its_own_cases_chose() -> None:
    """The bank's two cases chose FIBO and STIX; the prison's case, NIEM. Neither's reaches the
    other, and the composite, chosen by a case that chose none, gets none of its members'."""
    store = _store()
    await _run(store)
    packs = {d.id: (await store.live(d.id)).packs for d in DATASETS if d.kind != "analyst_layer"}  # type: ignore[union-attr]
    assert packs == {
        "ds-bank": {"fibo": 1, "stix": 1},
        "ds-prison": {"niem": 3},
        "ds-quiet": {},
        "comp-both": {},
    }


async def test_the_union_check_fails_taken_over_every_case(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 15, red: the union taken over every case, as a query reading all of `investigations`
    would, puts the prison case's NIEM into the bank's model."""

    def every_case(dataset_id: str, chosen: Any, domains: Any) -> list[str]:
        return sorted({p for packs in domains.values() for p in packs})

    monkeypatch.setattr(seeding, "packs_for", every_case)
    store = _store()
    await _run(store)
    assert "niem" in (await store.live("ds-bank")).packs  # type: ignore[union-attr]


async def test_every_dataset_but_a_layer_is_given_version_one_live() -> None:
    store = _store()
    report = await _run(store)
    for dataset in DATASETS:
        live = await store.live(dataset.id)
        if dataset.kind == "analyst_layer":
            assert live is None
        else:
            assert live is not None and (live.version, live.state) == (1, "live")
    assert [label for label, _ in report.seeded] == [
        "Bank + Prison (comp-both)", "Bank records (ds-bank)", "Nobody's (ds-quiet)",
        "Prison records (ds-prison)",
    ]  # fmt: skip


async def test_a_dataset_with_a_model_is_kept_and_a_second_run_changes_nothing() -> None:
    store = _store()
    first = await _run(store, with_a_model=["ds-quiet"])
    assert first.kept == ["Nobody's (ds-quiet)"] and await store.live("ds-quiet") is None
    seeded = {d.id for d in DATASETS if d.kind != "analyst_layer"} - {"ds-quiet"}
    again = await _run(store, with_a_model=[*seeded, "ds-quiet"])
    assert again.writes == [] and again.seeded == []


async def test_the_dry_run_writes_nothing_and_plans_what_the_real_run_makes() -> None:
    store = _store()
    lines: list[str] = []
    dry = await seed(
        DATASETS, CHOSEN, DOMAINS, set(), store=store, pack_versions=PACK_VERSIONS, write=False,
        say=lines.append,
    )  # fmt: skip
    assert all([await store.live(d.id) is None for d in DATASETS])
    real = await _run(store)
    assert len(dry.writes) == len(real.writes) == 3 * 4
    assert any("Bank records (ds-bank): version 1, live, fibo, stix" in line for line in lines)
    assert any(
        "Nobody's (ds-quiet): version 1, live, the POLE core alone" in line for line in lines
    )
