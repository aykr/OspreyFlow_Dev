"""The POC seed path (ADR-148 Amendment 14): spec 08's three seeds into one named case, as the
`ospreyflow-seed` Job runs them in the api image on a `cloud-platform` deployment, with the
Conduit and the worker scaled to none for its length (the recovery runbook's seed block).

`harness.apply` seeds a local deployment the same way, but makes its case through the Conduit as
Keycloak's verify identity; a cloud-platform deployment signs in with Entra ID, which has no
such identity and no token exchange. So the case is made here, through the `InvestigationStore`
the routes use (`scripts.case_seed`), by a seed principal no person signs in as, and its first
Author is the deployment's first administrator (`cloud_platform.claims.first_administrators`,
which the Job reads from the settings the Conduit is given): the one person sure to exist when
the seed runs.

A seed that fails stops the run there, named, and the Job fails with it: never "seeded" over a
dataset that is not there (rule 2). Running it again reuses the case; each seed adds what it
can without writing anything twice, and HMP refuses in words if an earlier run wrote its graph
but not its events.

Refused before anything is written: a deployment whose highest marking is below the seeds' data
(HMP's and Fixture Corp's reach SECRET), and a first administrator who has not signed in yet (the
case is made in their own unit, as Entra gave it)."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
from collections.abc import Callable
from typing import Any, Protocol

from scripts.case_seed import case_from_arguments

from demo_fixtures.datasets import HMP, domains_for
from schemas.domain import Principal

#: Spec 08's seeds, in `harness.apply`'s order (the scenarios build on the other two's places).
SEEDS = {
    "hmp": "scripts.seed_hmp_fixture",
    "fixture-corp": "scripts.seed_fixture_corp",
    "scenarios": "scripts.seed_scenarios",
}
CASE_NAME = "Acceptance scenarios (spec 08)"
#: The case's creator: nobody a person signs in as (`case_seed.ensure_case`).
SEEDER_ID = "poc-seed"
#: The highest marking each seed writes: HMP's and Fixture Corp's as `seed_internal.DATASETS`
#: declares them (proved against what they write by `tests/test_seed_internal_ceiling.py`), the
#: scenarios' OFFICIAL (`seed_scenarios._handling`). Held to `DATASETS` by
#: `tests/test_seed_poc.py`.
SEED_MARKINGS = {"hmp": "SECRET", "fixture-corp": "SECRET", "scenarios": "OFFICIAL"}


class SeedRefused(Exception):
    """A seed that cannot go on, said in words before anything is written."""


class _People(Protocol):
    async def one(self, oid: str) -> Any: ...


def _ceiling_refusal() -> str | None:
    """ADR-148 decision 10: the seeds' data against the deployment's highest marking (its rendered
    `OSPREY_HIGHEST_MARKING`), judged before anything is written, so no seed is partly written."""
    from services.ingest.ceiling import CeilingUnknown, DeploymentCeiling

    from ontology.handling import load_uk_le_scheme

    try:
        ceiling = DeploymentCeiling.of(
            os.environ.get("OSPREY_HIGHEST_MARKING", "").strip(), load_uk_le_scheme()
        )
    except CeilingUnknown as error:
        return f"{error}, so nothing was seeded"
    above = [
        f"{name} ({marking})" for name, marking in SEED_MARKINGS.items() if ceiling.above(marking)
    ]
    if not above:
        return None
    return (
        f"this deployment's highest marking is {ceiling.marking}, and spec 08's seeds hold data "
        f"above it: {', '.join(above)}; so nothing was seeded (INSTALL.md step 9)"
    )


async def author_unit(people: _People, oid: str) -> str:
    """The first administrator's own unit, as Entra gave it at their sign-in (the people store's
    record, this tenant's alone): the case is made in it, or they could not open it. One never
    signed in has none yet, and is refused."""
    from services.api.identity_admin import IdentityAdminRefused

    try:
        person = await people.one(oid)
    except IdentityAdminRefused:
        person = None
    if person is None or not person.signed_in or not person.org_unit:
        raise SeedRefused(
            f"the first administrator {oid} has not signed in yet, so their unit is not known: "
            "the case is made in it (INSTALL.md step 6 first, then step 9)"
        )
    return str(person.org_unit)


async def _unit(args: argparse.Namespace) -> str:
    """The case's unit: the first administrator's own on Entra; given, off it (no default)."""
    from services.api.config import PostgresConfig
    from services.api.entra_people import EntraPeopleStore

    from principal_auth import ClaimMapping

    mapping = ClaimMapping.from_env()
    if not mapping.is_entra:
        if not args.org_unit:
            raise SeedRefused("--org-unit (or OSPREY_ORG_UNIT) names the case's unit off Entra")
        return str(args.org_unit)
    assert mapping.tenant_id is not None
    store = await EntraPeopleStore.connect(PostgresConfig.from_env().dsn, mapping.tenant_id)
    try:
        unit = await author_unit(store, args.author.strip())
    finally:
        await store.close()
    if args.org_unit and args.org_unit != unit:
        raise SeedRefused(
            f"--org-unit {args.org_unit} is not the first administrator's own unit, {unit}"
        )
    return unit


def _seed_main(module: str) -> Callable[[list[str]], int]:
    main: Callable[[list[str]], int] = importlib.import_module(module).main
    return main


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.seed_poc", description=__doc__)
    first = os.environ.get("OSPREY_FIRST_ADMINISTRATORS", "").split(",")[0].strip()
    parser.add_argument(
        "--author",
        default=first or None,
        required=not first,
        help="The case's first Author's Entra object id (oid); by default the deployment's first "
        "administrator (OSPREY_FIRST_ADMINISTRATORS, the settings the Conduit is given).",
    )
    parser.add_argument("--case-name", default=CASE_NAME)
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT") or None)
    args = parser.parse_args(argv)
    if not args.author.strip():
        parser.error("--author is empty: the case needs a first Author who can sign in")
    return args


async def _case(args: argparse.Namespace, unit: str) -> str:
    seeder = Principal(id=SEEDER_ID, clearance="SECRET", org_unit=unit)
    case = await case_from_arguments(
        name=args.case_name,
        seeder=seeder,
        grant_texts=[f"{args.author.strip()}=author"],
        dataset=HMP,
        domains=domains_for(SEEDS),
    )
    return str(case.id)


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    refused = _ceiling_refusal()
    if refused:
        print(f"seed: refused: {refused}", file=sys.stderr)
        return 1
    try:
        unit = asyncio.run(_unit(args))
        scope = asyncio.run(_case(args, unit))
    except SeedRefused as error:
        print(f"seed: refused: {error}", file=sys.stderr)
        return 1
    except BaseException as error:  # the case named, however it failed (SystemExit included)
        print(f"seed: the case could not be made: {error!r}; no seed was run", file=sys.stderr)
        return 1
    # Each seed's principal, and so the dataset it registers, in the case's unit.
    os.environ["OSPREY_ORG_UNIT"] = unit
    print(f"seed: case {args.case_name!r} is {scope}, in unit {unit}", flush=True)
    for dataset, module in SEEDS.items():
        print(f"seed: {dataset} ...", flush=True)
        try:
            code = _seed_main(module)(["--investigation-scope", scope])
        except BaseException as error:  # every failure stops the run, named (SystemExit too)
            print(
                f"seed: {dataset} failed: {error!r}; the seeds after it were not run",
                file=sys.stderr,
            )
            return 1
        if code != 0:
            print(
                f"seed: {dataset} failed (exit {code}); the seeds after it were not run",
                file=sys.stderr,
            )
            return 1
    print(f"seed: done, {', '.join(SEEDS)} in case {scope}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
