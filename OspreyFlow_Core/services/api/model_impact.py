"""What making a dataset's draft model live would change, and doing it (R12, ADR-140 decision 5).

- **The changed types:** the types of every pack added, removed or kept at another pinned version,
  and every extension added, retired or in force again. A pack's types are the ones it defines in
  the loaded ontology (`type_packs`), never a core type it only widens, and never written down
  here.
- **The pipelines it affects:** the dataset's deployed pipelines (published or already flagged)
  whose row template writes one of those types. Read from what each writes, not from the model
  version it pinned, so a pipeline deployed against any earlier version is found alike.
- **Make live** is the only step that changes what runs. It makes the draft live, then marks
  exactly those pipelines as needing attention and pauses their schedules with the reason
  (ADR-110 decision 4 blocks a flagged pipeline's scheduled and watched runs). Every other
  pipeline is untouched, and loaded data is never rewritten.
- **The cases listed** are those reading the dataset (directly, or through a composite of it) that
  the reader may open, and **the composites named** are those one of the reader's own cases reads.
  Others are neither listed, named nor counted (rule 7).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from schemas.dataset_model import (
    ImpactedCase,
    ImpactedPipeline,
    ModelImpact,
    TargetModel,
)
from schemas.domain import DomainPack
from schemas.ingest import StudioRecipeDraft


def pack_types_of(type_packs: Mapping[str, str]) -> dict[str, frozenset[str]]:
    """Each pack's own entity and link types, from the loaded ontology's `type_packs` (ADR-120
    Amendment 1): the types a pack defines, never a core type it only widens, since widening a
    link's ends changes nothing a pipeline already writes."""
    found: dict[str, set[str]] = {}
    for type_name, pack in type_packs.items():
        found.setdefault(pack, set()).add(type_name)
    return {pack: frozenset(types) for pack, types in found.items()}


@dataclass(frozen=True)
class Changes:
    """What a draft changes against the live version (empty for none)."""

    packs_added: list[DomainPack]
    packs_removed: list[DomainPack]
    packs_repinned: list[DomainPack]
    extensions_added: list[str]
    extensions_retired: list[str]
    extensions_restored: list[str]
    changed_types: list[str]


def changes_of(
    live: TargetModel | None, draft: TargetModel, pack_types: Mapping[str, frozenset[str]]
) -> Changes:
    before_packs = dict(live.packs) if live is not None else {}
    after_packs = dict(draft.packs)
    added = sorted(set(after_packs) - set(before_packs))
    removed = sorted(set(before_packs) - set(after_packs))
    repinned = sorted(
        p for p in set(before_packs) & set(after_packs) if before_packs[p] != after_packs[p]
    )
    before_ext = {e.name: e for e in (live.extensions if live is not None else [])}
    ext_added = sorted(e.name for e in draft.extensions if e.name not in before_ext)
    ext_retired = sorted(
        e.name
        for e in draft.extensions
        if e.name in before_ext
        and e.retired_in is not None
        and before_ext[e.name].retired_in is None
    )
    ext_restored = sorted(
        e.name
        for e in draft.extensions
        if e.name in before_ext
        and e.retired_in is None
        and before_ext[e.name].retired_in is not None
    )
    types: set[str] = {*ext_added, *ext_retired, *ext_restored}
    for pack in (*added, *removed, *repinned):
        types |= pack_types.get(pack, frozenset())
    return Changes(
        packs_added=added,
        packs_removed=removed,
        packs_repinned=repinned,
        extensions_added=ext_added,
        extensions_retired=ext_retired,
        extensions_restored=ext_restored,
        changed_types=sorted(types),
    )


def _writes(recipe: StudioRecipeDraft) -> set[str]:
    """The entity and link types a deployed pipeline's row template writes."""
    template = recipe.row_template
    if template is None:
        return set()
    return {*(e.type for e in template.entities), *(e.type for e in template.edges)}


def affected_pipelines(
    recipes: Sequence[StudioRecipeDraft], changed: Sequence[str]
) -> list[ImpactedPipeline]:
    changed_set = set(changed)
    found = [
        ImpactedPipeline(
            recipe_id=r.recipe_id, label=r.label, writes=sorted(_writes(r) & changed_set)
        )
        for r in recipes
    ]
    return sorted((p for p in found if p.writes), key=lambda p: (p.label, p.recipe_id))


class _Recipes(Protocol):
    async def feeding(self, dataset_ids: Sequence[str]) -> list[StudioRecipeDraft]: ...


class _Cases(Protocol):
    async def list_for(self, principal: Any) -> Sequence[tuple[Any, Any]]: ...


class _Datasets(Protocol):
    async def cases_reading(self, dataset_id: str) -> list[str]: ...
    async def composites_of(self, dataset_id: str) -> list[Any]: ...
    async def chosen_of_case(self, investigation_id: str) -> list[Any]: ...


async def impact_of(
    dataset_id: str,
    live: TargetModel | None,
    draft: TargetModel,
    *,
    pack_types: Mapping[str, frozenset[str]],
    recipes: _Recipes,
    datasets: _Datasets,
    cases: _Cases,
    reader: Any,
) -> ModelImpact:
    changes = changes_of(live, draft, pack_types)
    pipelines = affected_pipelines(await recipes.feeding([dataset_id]), changes.changed_types)
    reading = set(await datasets.cases_reading(dataset_id))
    theirs = [case for case, _level in await cases.list_for(reader)]
    visible = [
        ImpactedCase(investigation_id=case.id, name=case.name)
        for case in theirs
        if case.id in reading
    ]
    # A composite is named only when one of the reader's own cases reads it (rule 7).
    read_by_them = {d.id for case in theirs for d in await datasets.chosen_of_case(case.id)}
    return ModelImpact(
        dataset_id=dataset_id,
        live_version=live.version if live is not None else None,
        draft_version=draft.version,
        pipelines=pipelines,
        cases=sorted(visible, key=lambda c: (c.name or "", c.investigation_id)),
        composites=sorted(
            d.name for d in await datasets.composites_of(dataset_id) if d.id in read_by_them
        ),
        packs_added=changes.packs_added,
        packs_removed=changes.packs_removed,
        packs_repinned=changes.packs_repinned,
        extensions_added=changes.extensions_added,
        extensions_retired=changes.extensions_retired,
        extensions_restored=changes.extensions_restored,
        changed_types=changes.changed_types,
    )


def flag_reason(live: TargetModel, pipeline: ImpactedPipeline) -> str:
    """The words a flagged pipeline carries, and its paused schedule says."""
    return (
        f"the dataset's domain model version {live.version} changes "
        + ", ".join(pipeline.writes)
        + ", which this pipeline writes: check its mapping and deploy it again"
    )
