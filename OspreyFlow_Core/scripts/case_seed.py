"""The named case a demo dataset is loaded into, and who may open it.

Used by the dataset seeds (`seed_paysim`, and Enron's once it exists), which run inside the
deployment's own network where the Conduit's Postgres is reachable. It goes through the same
`InvestigationStore` the routes use, so the case has a name, its creator, and the levels ADR-052
gives; nothing here writes SQL of its own. Running a seed twice reuses the case; a case its owner
removed (ADR-052 Amendment 7) is not brought back, a fresh one is made.
"""

from __future__ import annotations

import argparse

from services.api.investigations import AccessLevel, Investigation, InvestigationStore

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
) -> Investigation:
    """The case called `name` in the seeder's unit, made if it does not exist, with `grants` set.

    The seeder is the case's creator and so its first Author, which is nobody a person signs in as:
    the levels the demo accounts hold come from `grants`."""
    existing = [case for case, _level in await store.list_for(seeder) if case.name == name]
    case = existing[0] if existing else await store.create(seeder, name=name)
    for account, level in grants.items():
        await store.set_grant(case.id, account, level, by=seeder)
    return case


async def case_from_arguments(
    *, name: str, seeder: Principal, grant_texts: list[str]
) -> Investigation:
    """`ensure_case` against the Conduit's own database, as a seed run inside the deployment sees
    it. Shared by the dataset seeds so each makes its case the same way."""
    from services.api.config import PostgresConfig

    store = await InvestigationStore.connect(PostgresConfig.from_env().dsn)
    try:
        return await ensure_case(
            store,
            name=name,
            seeder=seeder,
            grants=dict(parse_grant(text) for text in grant_texts),
        )
    finally:
        await store.close()


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


async def scope_for(args: argparse.Namespace, *, seeder: Principal) -> str:
    """The case id to write under: the one given, or the named case made now."""
    if args.investigation_scope:
        return str(args.investigation_scope)
    case = await case_from_arguments(
        name=args.case_name, seeder=seeder, grant_texts=list(args.grant)
    )
    print(f"Case {args.case_name!r} is {case.id}.")
    return case.id
