"""Loads a public dataset the administrator added (`06_DECISIONS.md` ADR-138 decision 3).

    (ospreyflow demo add public --file <path> --manifest <dataset.yaml>)

Run inside the deployment's network by `scripts.seed_internal public --public-id <id>`, with the
dataset's staged folder (`scripts.public_dataset stage`: the file, `dataset.yaml`, `recipe.yaml`)
mounted read-only at `--data-dir`. The file is checked against its manifest's SHA-256 again here,
so a file changed after it was placed is refused before anything is written. Its rows go through
the Ingest Studio's own engine (`load_with_rules`, the path every recipe run takes) into a dataset
of its own (`public-<id>`, ADR-099) and a case named from the manifest; the timeline events the
load makes go to the deployment's analytics store.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import os
import sys
from pathlib import Path
from typing import cast

import yaml
from scripts.case_seed import add_case_arguments, check_case_arguments, scope_for
from services.api.dataset_scope import stamping
from services.api.studio_publish import load_with_rules

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from demo_fixtures.datasets import SeedDataset
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from ports.graph import GraphPort
from schemas.domain import Principal
from schemas.ingest import Recipe
from schemas.public_dataset import PublicDatasetManifest

_CREATED_BY = "public-dataset-seed-worker"


class PublicSeedRefused(Exception):
    """Something to fix before anything is written."""


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.seed_public")
    add_case_arguments(parser)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--attested-checkout", action="store_true")
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "unit-1"))
    parser.add_argument(
        "--principal-id", default=os.environ.get("OSPREY_PRINCIPAL_ID", _CREATED_BY)
    )
    parser.add_argument("--clearance", default=os.environ.get("OSPREY_CLEARANCE", "OFFICIAL"))
    parser.add_argument(
        "--analytics-db-path", default=os.environ.get("ANALYTICS_DB_PATH", "analytics.duckdb")
    )
    args = parser.parse_args(argv)
    check_case_arguments(parser, args)
    return args


def read_staged(folder: Path) -> tuple[PublicDatasetManifest, Recipe, list[dict[str, str]]]:
    """The staged manifest, recipe and rows, the file checked against the manifest first."""
    manifest = PublicDatasetManifest.model_validate(
        yaml.safe_load((folder / "dataset.yaml").read_text(encoding="utf-8"))
    )
    recipe = Recipe.model_validate(
        yaml.safe_load((folder / "recipe.yaml").read_text(encoding="utf-8"))
    )
    file = folder / manifest.file.name
    if manifest.file.sha256 is None:
        raise PublicSeedRefused(f"{manifest.name}'s manifest records no checksum; nothing loaded")
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    if digest != manifest.file.sha256:
        raise PublicSeedRefused(
            f"{file.name} no longer matches its manifest's checksum; nothing was loaded. Add it "
            "again with ospreyflow demo add public."
        )
    with file.open(newline="", encoding=manifest.file.encoding) as handle:
        rows = list(csv.DictReader(handle, delimiter=manifest.file.delimiter))
    return manifest, recipe, rows


def seed_dataset(manifest: PublicDatasetManifest) -> SeedDataset:
    return SeedDataset(
        id=f"public-{manifest.id}",
        name=manifest.name,
        source=f"public:{manifest.id}",
        domains=tuple(manifest.domains),
    )


async def _run(args: argparse.Namespace) -> int:
    if not args.attested_checkout:
        raise PublicSeedRefused("run by scripts.seed_internal, from a checkout")
    # `seed_internal` mounts the whole demo data folder; the dataset is placed under public/<id>.
    folder = args.data_dir
    if not (folder / "dataset.yaml").is_file():
        folder = args.data_dir / "public" / args.dataset_id
    manifest, recipe, rows = read_staged(folder)
    if manifest.id != args.dataset_id:
        raise PublicSeedRefused(f"{folder} holds {manifest.id}, not {args.dataset_id}")
    dataset = seed_dataset(manifest)
    scheme = load_uk_le_scheme()
    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    await client.create_database_if_absent()
    graph = cast(GraphPort, stamping(GraphArcadeDBAdapter(client, scheme), dataset=dataset.id))
    ontology = load_deployment_ontology()
    try:
        await graph.apply_schema(ontology)
        principal = Principal(
            id=args.principal_id, clearance=args.clearance, org_unit=args.org_unit
        )
        scope = await scope_for(args, seeder=principal, dataset=dataset)
        report, events, _held = await load_with_rules(
            recipe, rows, principal, graph=graph, ontology=ontology,
            load_id=f"public:{manifest.id}:{scope}", investigation_scope=scope,
            source=manifest.file.name, scheme=scheme,
        )  # fmt: skip
    finally:
        await client.aclose()
    if events:
        import duckdb

        from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
        from adapters.analytics_duckdb.schema import create_events_table

        connection = duckdb.connect(args.analytics_db_path)
        try:
            create_events_table(connection)
            await AnalyticsDuckDBAdapter(connection, scheme).load_events(events)
        finally:
            connection.close()
    rejected = len(report.rejections)
    print(
        f"Loaded {manifest.name}: {len(rows)} rows, {rejected} rejected, {len(events)} timeline "
        "events."
    )
    for rejection in report.rejections[:5]:
        print(f"  rejected: {rejection}")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(_run(_parse_args(argv if argv is not None else sys.argv[1:])))
    except PublicSeedRefused as refusal:
        print(f"seed_public: {refusal}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
