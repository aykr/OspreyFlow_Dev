"""Batch entrypoint for `services/ingest` — one container run loads one
recipe against one source file, per ADR-013 (batch and micro-batch only, no
streaming lane). This is the container's own process entrypoint, invoked
directly by whatever schedules the batch (a Kubernetes Job, `docker run`,
cron) — not an `osprey` unified CLI, which this build deliberately does not
have.

Connection details come from the environment, the same variables
`adapters/graph_arcadedb`'s conformance suite reads
(`ARCADEDB_HOST`/`ARCADEDB_HTTP_PORT`/`ARCADEDB_ROOT_PASSWORD`) plus
`staging.py`'s `MINIO_ENDPOINT`/`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`/
`MINIO_BUCKET` — a container gets these from its deployment, not from
flags.

`run_recipe` stages every resolved row to Parquet in object storage and
reads it back before writing the graph (`03_CONDUIT_MIDDLEWARE.md` §5.1);
what this entrypoint does not yet do is write the `EventRecord`s onward
into the analytics store's own served Parquet dataset — they are reported
as a count only. That is a separate, later step (populating
`adapters/analytics_duckdb`'s actual served dataset, not just its
conformance-test fixture), not something to silently pretend is done here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal

from .connectors.csv_connector import read_csv
from .engine import run_recipe
from .recipe_loader import load_recipe


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m services.ingest",
        description="Run one ingest recipe against one source file.",
    )
    parser.add_argument("--recipe", required=True, help="Path to the recipe YAML file")
    parser.add_argument("--source", required=True, help="Path to the source CSV file")
    parser.add_argument("--investigation-scope", required=True)
    parser.add_argument("--load-id", required=True)
    parser.add_argument(
        "--principal-id", default=os.environ.get("OSPREY_PRINCIPAL_ID", "ingest-worker")
    )
    parser.add_argument("--clearance", default=os.environ.get("OSPREY_CLEARANCE", "OFFICIAL"))
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "unit-1"))
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    recipe = load_recipe(args.recipe)
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, scheme)
    await graph.apply_schema(ontology)

    principal = Principal(id=args.principal_id, clearance=args.clearance, org_unit=args.org_unit)
    tx = await graph.begin_transaction()
    try:
        report, events = await run_recipe(
            recipe,
            read_csv(args.source),
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=principal,
            load_id=args.load_id,
            investigation_scope=args.investigation_scope,
            source=args.source,
        )
        await graph.commit_transaction(tx)
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    finally:
        await client.aclose()

    print(json.dumps(report.model_dump(mode="json"), indent=2))
    print(
        f"{len(events)} analytics events produced — staged to Parquet and loaded to the graph; "
        "not yet written onward into the analytics store's own served dataset",
        file=sys.stderr,
    )
    return 1 if report.rejections else 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
