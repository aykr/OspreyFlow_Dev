"""The named case a demo dataset is loaded into, and who may open it.

Used by the dataset seeds (`seed_paysim`, and Enron's once it exists), which run inside the
deployment's own network where the Conduit's Postgres is reachable. It goes through the same
`InvestigationStore` the routes use, so the case has a name, its creator, and the levels ADR-052
gives; nothing here writes SQL of its own. Running a seed twice reuses the case; a case its owner
removed (ADR-052 Amendment 7) is not brought back, a fresh one is made.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime

from services.api.datasets import Dataset, DatasetStore
from services.api.investigations import AccessLevel, Investigation, InvestigationStore

from demo_fixtures.datasets import SeedDataset
from schemas.domain import Principal


def parse_grant(text: str) -> tuple[str, AccessLevel]:
    """`account=level`, as the host-side seed passes it. The account is the identity provider's
    subject (the Conduit's principal id), not a display name."""
    account, separator, level = text.partition("=")
    if not separator or not account.strip() or not level.strip() or "=" in level:
        raise ValueError(f"a grant is written account=level, not {text!r}")
    try:
        return account.strip(), AccessLevel(level.strip())
    except ValueError as error:
        raise ValueError(
            f"a grant's level is viewer, editor or author, not {level.strip()!r}"
        ) from error


async def ensure_case(
    store: InvestigationStore,
    *,
    name: str,
    seeder: Principal,
    grants: dict[str, AccessLevel],
    domains: Sequence[str] | None = None,
) -> Investigation:
    """The case called `name` in the seeder's unit, made if it does not exist, with `grants` set.

    The seeder is the case's creator and so its first Author, which is nobody a person signs in as:
    the levels the demo accounts hold come from `grants`.

    **`domains`** (ADR-126 decision 2) are the packs the seed says the case is. They are set only
    while nobody has chosen, in one atomic `UPDATE ... WHERE domains IS NULL` that the case's
    access history records, so a choice anyone has made, POLE included, is never overwritten on a
    reseed. An empty list is a setting like any other. Left out (None), the setting is untouched."""
    existing = [case for case, _level in await store.list_for(seeder) if case.name == name]
    case = existing[0] if existing else await store.create(seeder, name=name)
    for account, level in grants.items():
        await store.set_grant(case.id, account, level, by=seeder)
    if domains is not None and await store.set_domains_if_unset(case.id, domains, by=seeder):
        case = await store.get(case.id)
    return case


async def ensure_case_reads(
    store: DatasetStore, investigation_id: str, dataset: SeedDataset, *, seeder: Principal
) -> None:
    """ADR-099: the seed's dataset exists, held by the seeder's unit, and the case reads it, after
    whatever it read already. Running a seed twice changes nothing. A dataset of that id held by
    another unit is refused (`DatasetRefusedError`), never borrowed."""
    await store.register(
        Dataset(
            id=dataset.id,
            name=dataset.name,
            owning_unit=seeder.org_unit,
            created_at=datetime.now(UTC),
            created_by=seeder.id,
        )
    )
    held = await store.ids_of_case(investigation_id)
    if dataset.id not in held:
        await store.set_for_case(investigation_id, [*held, dataset.id], seeder)


async def _reads_from_arguments(
    investigation_id: str, dataset: SeedDataset, *, seeder: Principal
) -> None:
    from services.api.config import PostgresConfig
    from services.api.datasets import PostgresDatasetStore

    store = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    try:
        await ensure_case_reads(store, investigation_id, dataset, seeder=seeder)
    finally:
        await store.close()


async def case_from_arguments(
    *, name: str, seeder: Principal, grant_texts: list[str], dataset: SeedDataset
) -> Investigation:
    """`ensure_case` against the Conduit's own database, as a seed run inside the deployment sees
    it, reading the seed's `dataset` (ADR-099). Shared by the dataset seeds so each makes its case
    the same way."""
    from services.api.config import PostgresConfig

    store = await InvestigationStore.connect(PostgresConfig.from_env().dsn)
    try:
        case = await ensure_case(
            store,
            name=name,
            seeder=seeder,
            grants=dict(parse_grant(text) for text in grant_texts),
            domains=list(dataset.domains),
        )
    finally:
        await store.close()
    await _reads_from_arguments(case.id, dataset, seeder=seeder)
    return case


def add_case_arguments(parser: argparse.ArgumentParser) -> None:
    """`--investigation-scope` (an existing case) or `--case-name` (make or reuse a named one,
    shared as `--grant account=level` says), as the dataset seeds take them. Use with
    `check_case_arguments` once parsed."""
    parser.add_argument("--investigation-scope", default=None, help="Write into this case.")
    parser.add_argument("--case-name", default=None, help="Make or reuse a case of this name.")
    parser.add_argument("--grant", action="append", default=[], metavar="ACCOUNT=LEVEL")


def check_case_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if bool(args.investigation_scope) == bool(args.case_name):
        parser.error("give exactly one of --investigation-scope and --case-name")


async def scope_for(
    args: argparse.Namespace, *, seeder: Principal, dataset: SeedDataset
) -> str:
    """The case id to write under: the one given, or the named case made now. Either way the case
    reads `dataset` (ADR-099), since the seed is loading it into the case."""
    if args.investigation_scope:
        await _reads_from_arguments(str(args.investigation_scope), dataset, seeder=seeder)
        return str(args.investigation_scope)
    case = await case_from_arguments(
        name=args.case_name, seeder=seeder, grant_texts=list(args.grant), dataset=dataset
    )
    print(f"Case {args.case_name!r} is {case.id}.")
    return case.id
