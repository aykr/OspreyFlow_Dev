"""The rule editor's declared dataset, its model and its second person (`spec/06_DECISIONS.md`
ADR-146 decision 3 and Amendment 6, L2.11), offline over the in-memory stores.

What a mistake would do, and the case that catches it:
- a rule declared on a layer, a drawn dataset or another case's dataset (rule 3):
  `test_a_rule_is_declared_only_on_the_cases_own_source_or_composite`;
- a condition offered a type outside the dataset's live model (red with a second dataset's type
  offered, as ADR-146's test list asks): `test_the_conditions_offer_no_type_outside_the_datasets_live_model`;
- a composite whose member asks for a second person going live on one person's say:
  `test_a_composite_asks_for_a_second_person_when_any_member_does`;
- a rule reading a list its dataset may not, another dataset's above all (rule 3), or its rows read
  as another type's: `test_a_rule_reads_only_a_list_its_dataset_may_and_its_subjects_rows`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from schemas.domain import EdgeTypeDef, EntityTypeDef, OntologySchema
from services.api.datasets import COMPOSITE, DRAWN, Dataset, InMemoryDatasetStore
from schemas.dataset_model import ReferenceList
from services.api.list_connector import InMemoryListRows
from services.api.rule_editor import (
    DatasetNotOffered,
    ListNotOffered,
    list_entries,
    declared_dataset,
    dataset_ontology,
    needs_second_person,
    offered_datasets,
)

T0 = datetime(2026, 11, 10, tzinfo=UTC)
ONTOLOGY = OntologySchema(
    version=1,
    entity_types=[
        EntityTypeDef(name=n, pole_class="person", channel="c", shape="s")
        for n in ("Person", "Prisoner", "Account")
    ],
    edge_types=[
        EdgeTypeDef.model_validate({"name": "VISITED", "from": ["Person"], "to": ["Prisoner"]}),
        EdgeTypeDef.model_validate({"name": "PAID", "from": ["Account"], "to": ["Account"]}),
    ],
    type_packs={"Prisoner": "prison", "VISITED": "prison", "Account": "finance", "PAID": "finance"},
    packs={"prison": 1, "finance": 1},
)


class _Models:
    """Each dataset's live model, by its packs; a dataset absent has none yet."""

    def __init__(self, packs: dict[str, list[str]], lists: dict[str, list[str]] | None = None) -> None:
        self.packs = packs
        self.lists = lists or {}

    async def live(self, dataset_id: str) -> Any:
        if dataset_id not in self.packs:
            return None
        return SimpleNamespace(packs=self.packs[dataset_id], reference_lists=self.lists.get(dataset_id, []))


class _NoDeploymentLists:
    async def lists(self) -> list[Any]:
        return []

    async def subscribed(self, dataset_id: str) -> list[str]:
        return []


def _dataset(id_: str, **extra: Any) -> Dataset:
    return Dataset(
        id=id_, name=id_, owning_unit="unit-1", created_at=T0, created_by="eng", **extra
    )


@pytest.fixture
def datasets() -> InMemoryDatasetStore:
    store = InMemoryDatasetStore()
    store.add(_dataset("ds-prison"))
    store.add(_dataset("ds-finance", promotion_policy="second_person_reviews"))
    store.add(_dataset("ds-both", kind=COMPOSITE, members=["ds-prison", "ds-finance"]))
    store.add(_dataset("ds-drawn", kind=DRAWN))
    store.add(_dataset("ds-elsewhere"))
    store.cases["case-1"] = ["ds-prison", "ds-both", "ds-drawn"]
    return store


async def test_a_rule_is_declared_only_on_the_cases_own_source_or_composite(
    datasets: InMemoryDatasetStore,
) -> None:
    assert (await declared_dataset("case-1", "ds-prison", datasets)).id == "ds-prison"
    assert (await declared_dataset("case-1", "ds-both", datasets)).id == "ds-both"
    for refused in ("ds-drawn", "ds-elsewhere", "ds-missing"):
        with pytest.raises(DatasetNotOffered):
            await declared_dataset("case-1", refused, datasets)
    offered = await offered_datasets(
        "case-1", ONTOLOGY, datasets=datasets, models=None, lists=None, rows_kept=None
    )
    assert [(o.id, o.kind) for o in offered] == [("ds-prison", "source"), ("ds-both", "composite")]


async def test_the_conditions_offer_no_type_outside_the_datasets_live_model(
    datasets: InMemoryDatasetStore,
) -> None:
    models = _Models({"ds-prison": ["prison"], "ds-finance": ["finance"]})
    prison = await dataset_ontology(
        datasets.datasets["ds-prison"], ONTOLOGY, datasets=datasets, models=models  # type: ignore[arg-type]
    )
    assert {t.name for t in prison.entity_types} == {"Person", "Prisoner"}
    assert {t.name for t in prison.edge_types} == {"VISITED"}
    both = await dataset_ontology(
        datasets.datasets["ds-both"], ONTOLOGY, datasets=datasets, models=models  # type: ignore[arg-type]
    )
    assert {t.name for t in both.entity_types} == {"Person", "Prisoner", "Account"}


async def test_a_dataset_with_no_live_model_yet_offers_the_whole_ontology(
    datasets: InMemoryDatasetStore,
) -> None:
    models = _Models({"ds-prison": ["prison"]})  # ds-finance has no model yet
    both = await dataset_ontology(
        datasets.datasets["ds-both"], ONTOLOGY, datasets=datasets, models=models  # type: ignore[arg-type]
    )
    assert {t.name for t in both.entity_types} == {"Person", "Prisoner", "Account"}


async def test_a_composite_asks_for_a_second_person_when_any_member_does(
    datasets: InMemoryDatasetStore,
) -> None:
    assert not await needs_second_person(datasets.datasets["ds-prison"], datasets)
    assert await needs_second_person(datasets.datasets["ds-finance"], datasets)
    assert await needs_second_person(datasets.datasets["ds-both"], datasets)


def _screening(id_: str, dataset_id: str, name: str) -> ReferenceList:
    return ReferenceList(id=id_, dataset_id=dataset_id, name=name, kind="screening", key_column="ref", version=1)


async def test_a_rule_reads_only_a_list_its_dataset_may_and_its_subjects_rows(
    datasets: InMemoryDatasetStore,
) -> None:
    rows = InMemoryListRows()
    own = _screening("l-prison", "ds-prison", "Prison watch")
    other = _screening("l-finance", "ds-finance", "Ledger watch")
    rows.write(own, [
        {"ref": "P1", "primary_name": "Ada Okafor", "aliases": "A. Okafor|Ada O", "date_of_birth": "1980-02-01",
         "nationality": "GB", "identifiers": "", "programme": "", "listing": "sanction", "entity_type": "Person"},
        {"ref": "O1", "primary_name": "Okafor Holdings", "aliases": "", "date_of_birth": "", "nationality": "",
         "identifiers": "", "programme": "", "listing": "sanction", "entity_type": "Organisation"},
    ])  # fmt: skip
    rows.write(other, [{"ref": "X", "primary_name": "Someone Else", "entity_type": "Person"}])
    models = _Models({"ds-prison": ["prison"], "ds-finance": ["finance"]},
                     {"ds-prison": ["l-prison"], "ds-finance": ["l-finance"]})  # fmt: skip
    kw: dict[str, Any] = {"datasets": datasets, "models": models, "lists": _NoDeploymentLists(), "rows_kept": rows}
    (entry,) = await list_entries(datasets.datasets["ds-prison"], "l-prison", "Person", **kw)
    assert (entry.name, entry.aliases, entry.list_name, str(entry.date_of_birth)) == (
        "Ada Okafor", ("A. Okafor", "Ada O"), "Prison watch", "1980-02-01")  # fmt: skip
    for refused in ("l-finance", "l-missing"):
        with pytest.raises(ListNotOffered):
            await list_entries(datasets.datasets["ds-prison"], refused, "Person", **kw)
    # A composite reads each member's own lists, and no other.
    (both,) = await list_entries(datasets.datasets["ds-both"], "l-finance", "Person", **kw)
    assert both.name == "Someone Else"
