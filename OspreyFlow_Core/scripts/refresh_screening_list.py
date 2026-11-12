"""Refreshes a subscribed screening list (`06_DECISIONS.md` ADR-133 decision 4, stage (c)) — the
operator's form of the Lists screen's *Refresh now*. Run as
`python -m scripts.refresh_screening_list "<list name>"`, with the Conduit's environment (it opens
the same stores the Conduit does, `services/api/run_resources.py`).

The list is read from its file in the ingest folder through its connector, admitted under rule
9 (synthetic only when every file is one of the repository's own; a real list only when this
device's `real_data_exceptions.yaml` names its dataset), applied as a new version, and every
customer of every case with a screening rule re-screened against the changed entries only, as each
rule's deployer. What happened is printed in words and recorded, as the route records it. `--list`
prints the subscriptions.

A list's schedule is ADR-133 stage (d)'s scheduled trigger: the pipeline scheduler runs Studio
recipes as their owners and cannot run a list. Until then, an operator may run this from the host's
own scheduler.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from services.api.config import ApiConfig
from services.api.run_resources import build_run_resources
from services.api.screening_refresh import ListNotSubscribed, Rescreener, refresh
from services.resolve.trigger import service_principal


async def _run(list_name: str | None) -> int:
    resources = await build_run_resources(ApiConfig.from_env())
    try:
        store = resources.screening_lists
        if list_name is None:
            for status in await store.subscriptions(cleared=None):
                failure = f" — {status.failure}" if status.failure else ""
                print(
                    f"{status.list_name}: {status.source}, version {status.version or 'none'}, "
                    f"{status.entries:,} entries{failure}"
                )
            return 0
        operator = service_principal(resources.handling_scheme).model_copy(
            update={"id": f"operator:{getpass.getuser()}"}
        )
        rescreen = Rescreener(
            rules=resources.typology_rules,
            datasets=resources.datasets_store,
            graph=resources.graph,
            scheme=resources.handling_scheme,
            alert_store=resources.alerts_store,
            audit=resources.audit,
            valkey=resources.valkey,
            principal_for_owner=resources.principal_resolver.resolve_for_owner,
            runner=operator,
        )
        try:
            update = await refresh(list_name, store=store, rescreen=rescreen)
        except ListNotSubscribed:
            print(f"No list is subscribed as “{list_name}”.", file=sys.stderr)
            return 2
        await resources.audit.record(
            principal=operator, action="screening_list_refreshed", investigation_id=None,
            resolved_query={"list_name": list_name, "outcome": update.outcome,
                            "version": update.version, "alerts": update.alerts},
            result_cardinality=update.alerts,
        )  # fmt: skip
        print(update.words)
        return 0 if update.outcome in ("updated", "unchanged") else 1
    finally:
        await resources.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.refresh_screening_list")
    parser.add_argument("list_name", nargs="?")
    parser.add_argument("--list", action="store_true", help="print the subscriptions")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if not args.list and not args.list_name:
        parser.error("name a list, or give --list")
    return asyncio.run(_run(None if args.list else args.list_name))


if __name__ == "__main__":
    raise SystemExit(main())
