"""The rule editor's work (`spec/06_DECISIONS.md` ADR-146 decision 3 and Amendment 6, L2.11): which
datasets a rule may be declared on, with each one's live domain model and the lists it may read; and
whether *Make live* waits for a second person. The routes in `app.py` do the wiring; this does the
work.

**The declared dataset** is one of the case's chosen datasets, a source or a composite
(`datasets.chosen_of_case`): never a layer or a drawn dataset, whose items only the case may see.
Anything else is refused exactly as a missing dataset (`DatasetNotOffered`, 404
`dataset_not_found`), so a rule cannot learn of a dataset its case does not read (rule 3).

**Its model.** The conditions offer only the dataset's live domain model's types and links: the
deployment's ontology narrowed to the model's packs, as boards read it (C14), its whole ontology
while the dataset has no model yet. A composite's model is its members' together; while any member
has none, the whole ontology.

**The second person.** ADR-146 says *Make live* "needs a second person when the dataset's policy
asks (ADR-145 A3)". The only per-dataset policy is *Promotion of drawn items* (`promotion_policy`),
so it is read here too (Amendment 6, the lane's decision of 10 November 2026, for the owner to
overrule): *Second person reviews* asks for one. A composite has no policy of its own: it asks for a
second person when any member does.
"""

from __future__ import annotations

from collections.abc import Sequence

from schemas.dataset_model import ReferenceList
from schemas.domain import OntologySchema
from schemas.list_connector import OfferedList
from schemas.rule_editor import RuleDatasetOffer

from .datasets import COMPOSITE, SOURCE, Dataset, DatasetStore
from .link_types import public_ontology
from .list_connector import ListRows, ListStore, offered_lists
from .target_models import TargetModelStore

#: The kinds a rule may be declared on.
RULE_DATASET_KINDS = (SOURCE, COMPOSITE)


class DatasetNotOffered(Exception):
    """The dataset named is not one of the case's own sources or composites: refused exactly as a
    dataset that does not exist."""


async def declared_dataset(
    investigation_id: str, dataset_id: str, datasets: DatasetStore
) -> Dataset:
    """The case's own source or composite named `dataset_id`, or `DatasetNotOffered`."""
    for dataset in await datasets.chosen_of_case(investigation_id):
        if dataset.id == dataset_id and dataset.kind in RULE_DATASET_KINDS:
            return dataset
    raise DatasetNotOffered(dataset_id)


async def _members(dataset: Dataset, datasets: DatasetStore) -> list[Dataset]:
    if dataset.kind != COMPOSITE:
        return [dataset]
    found = await datasets.egress_of(dataset.members)
    return [found[m] for m in dataset.members if m in found]


async def needs_second_person(dataset: Dataset, datasets: DatasetStore) -> bool:
    """Whether *Make live* waits for another person: the dataset's own policy, or for a composite
    any member's."""
    return any(
        d.promotion_policy == "second_person_reviews" for d in await _members(dataset, datasets)
    )


async def _packs(
    dataset: Dataset, datasets: DatasetStore, models: TargetModelStore | None
) -> set[str] | None:
    if models is None:
        return None
    packs: set[str] = set()
    for member in await _members(dataset, datasets):
        live = await models.live(member.id)
        if live is None:
            return None
        packs |= set(live.packs)
    return packs


def ontology_in(ontology: OntologySchema, packs: set[str] | None) -> OntologySchema:
    """The ontology as the dataset's model has it: the core's types and those of its packs, with no
    proposal's own labels (`public_ontology`). `None` is no model yet: the whole ontology."""
    shown = public_ontology(ontology)
    if packs is None:
        return shown

    def kept(name: str) -> bool:
        pack = ontology.type_packs.get(name)
        return pack is None or pack in packs

    return shown.model_copy(
        update={
            "entity_types": [t for t in shown.entity_types if kept(t.name)],
            "edge_types": [t for t in shown.edge_types if kept(t.name)],
            "type_packs": {k: v for k, v in shown.type_packs.items() if v in packs},
            "packs": {k: v for k, v in shown.packs.items() if k in packs},
        }
    )


async def dataset_ontology(
    dataset: Dataset,
    ontology: OntologySchema,
    *,
    datasets: DatasetStore,
    models: TargetModelStore | None,
) -> OntologySchema:
    """The ontology a rule on `dataset` is checked against, and its conditions offered from."""
    return ontology_in(ontology, await _packs(dataset, datasets, models))


async def own_lists(
    dataset_id: str, models: TargetModelStore, rows_kept: ListRows
) -> list[ReferenceList]:
    """The dataset's own lists with rows kept, whose ids its live domain model names (ADR-140
    Amendment 12): each at the highest version kept."""
    live = await models.live(dataset_id)
    named = set(live.reference_lists) if live is not None else set()
    return [r for r in rows_kept.kept(dataset_id) if r.id in named]


async def lists_of(
    dataset: Dataset,
    *,
    datasets: DatasetStore,
    models: TargetModelStore | None,
    lists: ListStore | None,
    rows_kept: ListRows | None,
) -> list[OfferedList]:
    """The lists a rule on `dataset` may read, as the save gate reads them: each member's own and
    the deployment-wide lists it subscribes to."""
    if models is None or lists is None or rows_kept is None:
        return []
    found: dict[str, OfferedList] = {}
    for member in await _members(dataset, datasets):
        own = await own_lists(member.id, models, rows_kept)
        for offered in await offered_lists(member.id, store=lists, own=own):
            found.setdefault(offered.id, offered)
    return sorted(found.values(), key=lambda o: (o.deployment_wide, o.name.lower()))


async def offered_datasets(
    investigation_id: str,
    ontology: OntologySchema,
    *,
    datasets: DatasetStore,
    models: TargetModelStore | None,
    lists: ListStore | None,
    rows_kept: ListRows | None,
) -> list[RuleDatasetOffer]:
    """Every dataset the case's rules may be declared on, each with its model and lists."""
    offers: list[RuleDatasetOffer] = []
    chosen: Sequence[Dataset] = await datasets.chosen_of_case(investigation_id)
    for dataset in chosen:
        if dataset.kind not in RULE_DATASET_KINDS:
            continue
        offers.append(
            RuleDatasetOffer(
                id=dataset.id,
                name=dataset.name,
                kind="composite" if dataset.kind == COMPOSITE else "source",
                second_person=await needs_second_person(dataset, datasets),
                ontology=await dataset_ontology(
                    dataset, ontology, datasets=datasets, models=models
                ),
                lists=await lists_of(
                    dataset, datasets=datasets, models=models, lists=lists, rows_kept=rows_kept
                ),
            )
        )
    return offers
