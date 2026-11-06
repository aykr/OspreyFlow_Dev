"""Registers each existing recipe's source as a source of its dataset (`06_DECISIONS.md` ADR-140
Amendment 4; redesign phase 3).

    python -m scripts.migrate_sources --dry-run    # says what it would register; writes nothing
    python -m scripts.migrate_sources              # registers it; a second run registers nothing

Run where the Conduit's Postgres is reachable (`POSTGRES_*`), as `scripts.stamp_datasets` is.

For each recipe at its current version that names a dataset and a file, its file becomes one source
of its dataset, carrying the recipe's connector, handling (marking and units) and legal basis, on
the deployment's Files connection, named by the file's name. Recipes reading one file under the
same governance make one source. **Recipes reading one file under different governance register
nothing for it**, and the command names the file and the recipes: which marking is right is a
person's call, made by registering it by hand on the Studio's Sources tab. A file already
registered for its dataset is left. No recipe's mapping or governance is changed.

**Then each pipeline's folder watch moves onto the source it reads** (ADR-110 Amendment 6 point 7,
the owner's ruling "Watches move; cron stays"), with its owner, the time it was set (a file counts
only if it arrived after) and whether it is paused, with why: chapter 9's paused watches become
paused source policies. The source reads each file as before, a full snapshot keeping every row.
The pipeline's own watch is cleared; its cron schedule stays on it, until SQL and API sources take
schedules (phase 9). Moving a watch is not a governance edit: no pipeline then needs attention.
**Left for a person, and named:** a source whose pipelines watch it under different patterns or for
different owners; a source a keyless pipeline reads (a refresh never runs one, Amendment 6 point 2);
a source with a refresh policy of its own; a recipe whose file is not registered.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Protocol

from services.api.sources import FILES_CONNECTION_ID, SourceAlreadyRegisteredError, SourceStore

from schemas.domain import Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from schemas.sources import RegisterSourceInput, SourceRefresh, SourceTable

#: Who the registered sources say made them.
MIGRATION = Principal(id="migrate_sources", clearance="OFFICIAL", org_unit="system")


@dataclass
class Planned:
    dataset_id: str
    body: RegisterSourceInput
    recipes: list[str]


@dataclass
class Conflict:
    dataset_id: str
    location: str
    recipes: list[str]


@dataclass
class Plan:
    register: list[Planned] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    #: Recipes naming no dataset or no file.
    left: int = 0
    #: Files already registered for their dataset.
    already: int = 0


def _governance(recipe: StudioRecipeDraft) -> tuple[str, str, str | None]:
    import json

    return (recipe.connector_profile or "generic-csv", json.dumps(recipe.handling, sort_keys=True),
            recipe.legal_basis)  # fmt: skip


def plan(recipes: Sequence[StudioRecipeDraft], *, registered: set[tuple[str, str]]) -> Plan:
    out = Plan()
    groups: dict[tuple[str, str], list[StudioRecipeDraft]] = {}
    for recipe in recipes:
        if not recipe.dataset_id or not recipe.source_location:
            out.left += 1
            continue
        groups.setdefault((recipe.dataset_id, recipe.source_location), []).append(recipe)
    for (dataset_id, location), group in groups.items():
        if (dataset_id, location) in registered:
            out.already += 1
            continue
        labels = list(dict.fromkeys(r.label for r in group))
        if len({_governance(r) for r in group}) > 1:
            out.conflicts.append(Conflict(dataset_id, location, labels))
            continue
        first = group[0]
        body = RegisterSourceInput(
            connection_id=FILES_CONNECTION_ID,
            name=PurePath(location).name or location,
            location=location,
            connector_profile=first.connector_profile or "generic-csv",
            handling=first.handling,
            legal_basis=first.legal_basis,
        )
        out.register.append(Planned(dataset_id, body, labels))
    return out


_DEPLOYED = (StudioRecipeStatus.PUBLISHED, StudioRecipeStatus.FLAGGED)


class RecipeWatches(Protocol):
    async def clear_watch(self, recipe_id: str) -> None: ...


@dataclass
class WatchMove:
    source_id: str | None
    name: str
    dataset_id: str
    refresh: SourceRefresh
    recipe_ids: list[str]
    labels: list[str]


@dataclass
class WatchPlan:
    moves: list[WatchMove] = field(default_factory=list)
    left: list[str] = field(default_factory=list)


def plan_watches(
    recipes: Sequence[StudioRecipeDraft],
    sources: dict[tuple[str, str], SourceTable | None],
) -> WatchPlan:
    """Which watches move onto which source, and which are left and why (the module docstring).
    `sources`: each (dataset, file) a deployed recipe reads, with its registered source, or `None`
    for one a dry run would register (no policy yet) and absent for one that is not registered."""
    out = WatchPlan()
    groups: dict[tuple[str, str], list[StudioRecipeDraft]] = {}
    for recipe in recipes:
        if recipe.status in _DEPLOYED and recipe.dataset_id and recipe.source_location:
            groups.setdefault((recipe.dataset_id, recipe.source_location), []).append(recipe)
    for (dataset_id, location), group in groups.items():
        watching = [r for r in group if r.schedule_watch]
        if not watching:
            continue
        name = PurePath(location).name or location
        labels = list(dict.fromkeys(r.label for r in watching))
        where = f"{name} for {dataset_id}"
        if (dataset_id, location) not in sources:
            out.left.append(
                f"left the watches on {where}: the file is not registered as a source; register "
                "it by hand on the Studio's Sources tab, then run this again"
            )
            continue
        source = sources[(dataset_id, location)]
        if source is not None and source.refresh.trigger != "manual":
            out.left.append(
                f"left the watches of {', '.join(labels)}: {where} has a refresh policy of its own"
            )
            continue
        if len({r.schedule_watch for r in watching}) > 1:
            out.left.append(
                f"left the watches on {where}: {', '.join(labels)} watch it under different "
                "patterns; set the source's refresh by hand on its page"
            )
            continue
        if len({r.schedule_owner for r in watching}) > 1:
            out.left.append(
                f"left the watches on {where}: {', '.join(labels)} watch it for different owners; "
                "set the source's refresh by hand on its page"
            )
            continue
        keyless = list(dict.fromkeys(r.label for r in group if r.deduplicate is None))
        if keyless:
            out.left.append(
                f"left the watches on {where}: {', '.join(keyless)} has no deduplication key, so a "
                "refresh would load its rows again; give it a key and run this again"
            )
            continue
        paused = [r for r in watching if r.schedule_paused]
        set_times = [r.schedule_set_at for r in watching if r.schedule_set_at is not None]
        refresh = SourceRefresh(
            trigger="watch",
            pattern=watching[0].schedule_watch,
            owner=watching[0].schedule_owner,
            set_at=min(set_times) if set_times else None,
            paused=bool(paused),
            paused_reason=paused[0].schedule_paused_reason if paused else None,
        )
        out.moves.append(
            WatchMove(
                source_id=source.id if source is not None else None,
                name=name,
                dataset_id=dataset_id,
                refresh=refresh,
                recipe_ids=[r.recipe_id for r in watching],
                labels=labels,
            )
        )
    return out


async def move_watches(
    recipes: Sequence[StudioRecipeDraft],
    store: SourceStore,
    watches: RecipeWatches,
    *,
    dry_run: bool,
    planned: Sequence[Planned] = (),
) -> list[str]:
    datasets = {r.dataset_id for r in recipes if r.dataset_id}
    sources: dict[tuple[str, str], SourceTable | None] = {
        (d, s.location): s for d in datasets for s in await store.list_for(d)
    }
    for item in planned:
        sources.setdefault((item.dataset_id, item.body.location), None)
    plan_ = plan_watches(recipes, sources)
    said: list[str] = []
    for move in plan_.moves:
        if not dry_run:
            assert move.source_id is not None
            # The source first: were the run to stop between, the pipeline's own watch is set
            # aside while its source watches (Amendment 7 point 2), so nothing runs twice.
            await store.adopt_refresh(move.source_id, move.refresh)
            for recipe_id in move.recipe_ids:
                await watches.clear_watch(recipe_id)
        verb = "would move" if dry_run else "moved"
        state = ", paused" if move.refresh.paused else ""
        said.append(
            f"{verb} the watch of {', '.join(move.labels)} onto {move.name} for "
            f"{move.dataset_id}{state}"
        )
    said.extend(plan_.left)
    said.append(f"{len(plan_.moves)} watch(es) to move, {len(plan_.left)} left for a person")
    return said


async def migrate(
    recipes: Sequence[StudioRecipeDraft],
    store: SourceStore,
    *,
    dry_run: bool,
    watches: RecipeWatches | None = None,
) -> list[str]:
    datasets = {r.dataset_id for r in recipes if r.dataset_id}
    registered = {(d, s.location) for d in datasets for s in await store.list_for(d)}
    planned = plan(recipes, registered=registered)
    said: list[str] = []
    for item in planned.register:
        verb = "would register" if dry_run else "registered"
        if not dry_run:
            try:
                await store.register(item.dataset_id, item.body, MIGRATION)
            except SourceAlreadyRegisteredError:
                verb = "already registered"
        said.append(
            f"{verb} {item.body.name} for {item.dataset_id}, read by {', '.join(item.recipes)}"
        )
    for conflict in planned.conflicts:
        said.append(
            f"left {PurePath(conflict.location).name} for {conflict.dataset_id}: "
            f"{', '.join(conflict.recipes)} read it under different governance; register it by "
            "hand on the Studio's Sources tab"
        )
    said.append(
        f"{len(planned.register)} to register, {planned.already} already registered, "
        f"{len(planned.conflicts)} left for a person, {planned.left} recipe(s) naming no "
        "dataset or no file"
    )
    if watches is not None:
        said.extend(
            await move_watches(recipes, store, watches, dry_run=dry_run, planned=planned.register)
        )
    return said


async def _main(dry_run: bool) -> int:
    from services.api.config import PostgresConfig
    from services.api.sources import PostgresSourceStore
    from services.api.studio_recipes import StudioRecipeStore

    dsn = PostgresConfig.from_env().dsn
    recipes_store = await StudioRecipeStore.connect(dsn)
    sources = await PostgresSourceStore.connect(dsn)
    try:
        for line in await migrate(
            await recipes_store.current_for_migration(),
            sources,
            dry_run=dry_run,
            watches=recipes_store,
        ):
            print(line)
    finally:
        await recipes_store.close()
        await sources.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.migrate_sources", description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Say what it would register.")
    args = parser.parse_args(argv)
    return asyncio.run(_main(args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
