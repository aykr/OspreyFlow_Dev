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

from collections.abc import Awaitable, Callable, Sequence
from datetime import date

from services.ingest.staging_catalogue import readable_lists

from schemas.dataset_model import ReferenceList
from schemas.domain import OntologySchema, TypologyRule
from schemas.list_connector import OfferedList
from schemas.rule_editor import RuleDatasetOffer

from .datasets import COMPOSITE, SOURCE, Dataset, DatasetStore, read_set
from .link_types import public_ontology
from .list_connector import ListRows, ListStore, deployment_references, offered_lists
from .screening import ScreeningEntry
from .target_models import TargetModelStore

#: The kinds a rule may be declared on.
RULE_DATASET_KINDS = (SOURCE, COMPOSITE)


class ListNotOffered(Exception):
    """The list named is not one the rule's dataset may read: refused exactly as a list that does
    not exist (rule 3)."""


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
    members = await _members(dataset, datasets)
    if dataset.kind == COMPOSITE and len(members) < len(dataset.members):
        return True  # a member it can no longer read is asked about as strictly as it could be
    return any(d.promotion_policy == "second_person_reviews" for d in members)


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


def _day(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def entries_of_rows(
    reference: ReferenceList, rows: Sequence[dict[str, object]], entity_type: str
) -> list[ScreeningEntry]:
    """A Studio screening list's rows (`staging_catalogue.SCREENING_COLUMNS`) as the entries
    `screen` reads: those of the subject's type alone, each name and alias screened."""
    found: list[ScreeningEntry] = []
    for row in rows:
        if str(row.get("entity_type") or "") != entity_type:
            continue
        name = str(row.get("primary_name") or "").strip()
        if not name:
            continue
        listing = str(row.get("listing") or "sanction")
        found.append(
            ScreeningEntry(
                id=str(row.get("ref") or name),
                list_name=reference.name,
                listing=listing if listing in ("sanction", "pep", "adverse_media") else "sanction",  # type: ignore[arg-type]
                entity_type=entity_type,  # type: ignore[arg-type]
                name=name,
                date_of_birth=_day(row.get("date_of_birth")),
                country=str(row.get("nationality") or "") or None,
                aliases=tuple(a for a in str(row.get("aliases") or "").split("|") if a),
            )
        )
    return found


async def list_entries(
    dataset: Dataset,
    list_id: str,
    entity_type: str,
    *,
    datasets: DatasetStore,
    models: TargetModelStore | None,
    lists: ListStore | None,
    rows_kept: ListRows | None,
) -> list[ScreeningEntry]:
    """The entries of the list a rule on `dataset` names, read only where the save gate lets the
    dataset read it (`readable_lists`: its own, or a deployment-wide list it subscribes to by id).
    Any other list, another dataset's above all, is `ListNotOffered`, never read (rule 3)."""
    if models is None or lists is None or rows_kept is None:
        raise ListNotOffered(list_id)
    wide = await deployment_references(lists)
    for member in await _members(dataset, datasets):
        own = await own_lists(member.id, models, rows_kept)
        readable, clashes = readable_lists(
            [*own, *wide], dataset_id=member.id, subscribed=await lists.subscribed(member.id)
        )
        for ref in readable.values():
            if ref.id == list_id and ref.name not in clashes:
                return entries_of_rows(ref, rows_kept.read(ref) or [], entity_type)
    raise ListNotOffered(list_id)


#: What a rule's run reads a named Studio list through: (the rule, the list's id, the subject's
#: type) -> its entries, within the rule's own dataset (`list_entries`).
RuleListReader = Callable[[TypologyRule, str, str], Awaitable[list[ScreeningEntry]]]


def rule_list_reader(
    *,
    datasets: DatasetStore,
    models: TargetModelStore | None,
    lists: ListStore | None,
    rows_kept: ListRows | None,
) -> RuleListReader:
    """The reader every run of a rule with a named list uses: the list read within the rule's
    declared dataset alone, so a rule never reads a list its dataset may not."""

    async def read(rule: TypologyRule, list_id: str, entity_type: str) -> list[ScreeningEntry]:
        if rule.dataset_id is None:
            raise ListNotOffered(list_id)
        # The rule's case must still read its dataset (rule 3, the lane-reviewer's item 13).
        try:
            dataset = await declared_dataset(rule.investigation_id, rule.dataset_id, datasets)
        except DatasetNotOffered as gone:
            raise ListNotOffered(list_id) from gone
        return await list_entries(
            dataset, list_id, entity_type, datasets=datasets, models=models, lists=lists,
            rows_kept=rows_kept,
        )  # fmt: skip

    return read


def rule_reach(dataset: Dataset) -> list[str]:
    """What a rule on `dataset` reads, as its author: the dataset, and a composite's members with
    it (`datasets.read_set`, no layer). A run, a refresh and *Test* each read exactly this."""
    return read_set([dataset], None)


#: (the rule) -> the dataset ids its author reads it within; `None` when its case no longer reads
#: its dataset, which no run then reads at all.
RuleReach = Callable[[TypologyRule], Awaitable[list[str] | None]]


def rule_reach_of(datasets: DatasetStore) -> RuleReach:
    async def reach(rule: TypologyRule) -> list[str] | None:
        if rule.dataset_id is None:
            return None
        try:
            dataset = await declared_dataset(rule.investigation_id, rule.dataset_id, datasets)
        except DatasetNotOffered:
            return None
        return rule_reach(dataset)

    return reach


async def reads_the_list(
    rule: TypologyRule,
    list_id: str,
    owner: str,
    *,
    datasets: DatasetStore,
    models: TargetModelStore | None,
    lists: ListStore | None,
    rows_kept: ListRows | None,
) -> bool:
    """Whether `rule` reads the list `list_id` kept by `owner` (a dataset, or the deployment's
    `DEPLOYMENT_WIDE`): list ids repeat across datasets, so a refresh of one dataset's list starts
    only the rules that read that dataset's (the lane-reviewer's item 6)."""
    if rule.dataset_id is None or models is None or lists is None or rows_kept is None:
        return False
    try:
        dataset = await declared_dataset(rule.investigation_id, rule.dataset_id, datasets)
    except DatasetNotOffered:
        return False
    wide = await deployment_references(lists)
    for member in await _members(dataset, datasets):
        own = await own_lists(member.id, models, rows_kept)
        readable, clashes = readable_lists(
            [*own, *wide], dataset_id=member.id, subscribed=await lists.subscribed(member.id)
        )
        if any(r.id == list_id and r.dataset_id == owner and r.name not in clashes
               for r in readable.values()):  # fmt: skip
            return True
    return False
