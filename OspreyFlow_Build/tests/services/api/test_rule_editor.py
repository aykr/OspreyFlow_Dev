"""The rule editor's declared dataset, its model and its second person (`spec/06_DECISIONS.md`
ADR-146 decision 3 and Amendment 6, L2.11), offline over the in-memory stores.

What a mistake would do, and the case that catches it:
- a rule declared on a layer, a drawn dataset or another case's dataset (rule 3):
  `test_a_rule_is_declared_only_on_the_cases_own_source_or_composite`;
- a condition offered a type outside the dataset's live model (red with a second dataset's type
  offered, as ADR-146's test list asks): `test_the_conditions_offer_no_type_outside_the_datasets_live_model`;
- a composite whose member asks for a second person going live on one person's say:
  `test_a_composite_asks_for_a_second_person_when_any_member_does`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from schemas.domain import EdgeTypeDef, EntityTypeDef, OntologySchema
from services.api.datasets import COMPOSITE, DRAWN, Dataset, InMemoryDatasetStore
from services.api.rule_editor import (
    DatasetNotOffered,
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

    def __init__(self, packs: dict[str, list[str]]) -> None:
        self.packs = packs

    async def live(self, dataset_id: str) -> Any:
        if dataset_id not in self.packs:
            return None
        return SimpleNamespace(packs=self.packs[dataset_id], reference_lists=[])


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
