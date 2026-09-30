"""The named case a demo dataset is loaded into, and who may open it.

Used by the dataset seeds (`seed_paysim`, and Enron's once it exists), which run inside the
deployment's own network where the Conduit's Postgres is reachable. It goes through the same
`InvestigationStore` the routes use, so the case has a name, its creator, and the levels ADR-052
gives; nothing here writes SQL of its own. Running a seed twice reuses the case; a case its owner
removed (ADR-052 Amendment 7) is not brought back, a fresh one is made.
"""

from __future__ import annotations

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
