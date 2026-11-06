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
registered for its dataset is left. No recipe is changed: each keeps running exactly as before.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PurePath

from services.api.sources import FILES_CONNECTION_ID, SourceAlreadyRegisteredError, SourceStore

from schemas.domain import Principal
from schemas.ingest import StudioRecipeDraft
from schemas.sources import RegisterSourceInput

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


async def migrate(
    recipes: Sequence[StudioRecipeDraft], store: SourceStore, *, dry_run: bool
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
            await recipes_store.current_for_migration(), sources, dry_run=dry_run
        ):
            print(line)
    finally:
        await recipes_store.close()
        await sources.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.migrate_sources", description=__doc__
    )
    parser.add_argument("--dry-run", action="store_true", help="Say what it would register.")
    args = parser.parse_args(argv)
    return asyncio.run(_main(args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
