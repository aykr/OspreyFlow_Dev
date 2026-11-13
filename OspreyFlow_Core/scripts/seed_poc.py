"""The POC seed path (ADR-148 Amendment 14): spec 08's three seeds into one named case, as the
`ospreyflow-seed` Job runs them in the api image on a `cloud-platform` deployment, with the Conduit
and the worker scaled to none for its length (the recovery runbook's seed block).

`harness.apply` seeds a local deployment the same way, but makes its case through the Conduit as
Keycloak's verify identity; a cloud-platform deployment signs in with Entra ID, which has no such
identity and no token exchange. So the case is made here, through the `InvestigationStore` the
routes use (`scripts.case_seed`), by a seed principal no person signs in as, and its first Author
is the deployment's first administrator (`cloud_platform.claims.first_administrators`, rendered
into the Job's arguments): the one person sure to exist when the seed runs.

A seed that fails stops the run there, named, and the Job fails with it: never "seeded" over a
dataset that is not there (rule 2). Running it again reuses the case and adds only what is missing,
as each seed does.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
from collections.abc import Callable

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


def _seed_main(module: str) -> Callable[[list[str]], int]:
    main: Callable[[list[str]], int] = importlib.import_module(module).main
    return main


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.seed_poc", description=__doc__)
    parser.add_argument(
        "--author", required=True, help="The first administrator's Entra object id (oid)."
    )
    parser.add_argument("--case-name", default=CASE_NAME)
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "unit-1"))
    args = parser.parse_args(argv)
    if not args.author.strip():
        parser.error("--author is empty: the case needs a first Author who can sign in")
    return args


async def _case(args: argparse.Namespace) -> str:
    seeder = Principal(id=SEEDER_ID, clearance="SECRET", org_unit=args.org_unit)
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
    scope = asyncio.run(_case(args))
    print(f"seed: case {args.case_name!r} is {scope}", flush=True)
    for dataset, module in SEEDS.items():
        print(f"seed: {dataset} ...", flush=True)
        try:
            code = _seed_main(module)(["--investigation-scope", scope])
        except Exception as error:  # noqa: BLE001 - every failure stops the run, named
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
