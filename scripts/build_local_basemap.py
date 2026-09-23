"""The tier-1 "one-button local basemap build" — `docs/00_ARCHITECTURE.md`
§1.2 ("Tier 1 is the shipped default and it is complete. One button on the
harness's Geospatial screen downloads a Geofabrik extract, runs planetiler
to produce PMTiles, and loads the OSM-derived gazetteer") and
`docs/05_DEPLOYMENT.md` §2.2 ("Build local basemap").

**No harness exists yet** (`harness/` is Phase 8 scope)
and there is no `osprey` CLI (`CLAUDE.md`'s own Conventions,
reconfirmed for Phase 5). This module is the real functionality the
eventual `osprey geo build`/harness button wraps — a plain, importable,
directly-runnable script now, the same correction already made for
`revert_load` in Phase 2. "With progress shown" here means a `progress`
callback each stage calls (default: `print`), since there is no progress
bar to draw it into yet.

**What is genuinely exercised in CI versus what cannot be.** `load_gazetteer`
and `register_local_provider` need no external resource and are fully
tested (`tests/test_build_local_basemap.py`) against the synthetic OSM
fixture the gazetteer connector's own tests already use. `download_extract`
and `run_planetiler` need a real network call and a real Java process
respectively — the standing rule that "CI never depends on a
third party's availability" means neither can run in CI, so both are
exercised only for their *argument-construction and error-handling* logic,
with the actual network/subprocess call injected out — the same shape
`test_websocket_auth.py` uses for a `WebSocket` it never really opens.
**Real planetiler CLI flags are unverified here** — this repo has no
network access to confirm them against the current release, and
`00_ARCHITECTURE.md` §1.2 already asks that OS Data Hub specifics be
"verified at implementation time rather than trusting this document"; the
same caution applies to planetiler's flag names below.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml
from services.ingest.connectors.geo.osm import read_osm_places
from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.graph import GraphPort
from schemas.domain import OntologySchema, Principal, TxId
from schemas.ingest import LoadReport
from schemas.mapconfig import ClientScope, MapConfig, MapProvider, MapSourceKind, ProviderLicence

#: A deliberately small, named set — the harness's own choices
#: ("Great Britain, a US state or region, or a custom bounding box",
#: `05_DEPLOYMENT.md` §2.2). Add an entry rather than guess a URL pattern:
#: Geofabrik's own directory structure is not perfectly regular across
#: regions, so a computed URL is exactly the kind of "plausible but wrong"
#: default `01_DOMAIN_MODEL.md` §7 warns against for CRS/date guessing.
GEOFABRIK_REGIONS: dict[str, str] = {
    "great-britain": "https://download.geofabrik.de/europe/great-britain-latest.osm.pbf",
    "california": "https://download.geofabrik.de/north-america/us/california-latest.osm.pbf",
    "texas": "https://download.geofabrik.de/north-america/us/texas-latest.osm.pbf",
}

_OSM_GAZETTEER_RECIPE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests" / "scenarios" / "fixtures" / "osm_gazetteer_recipe.yaml"
)


class UnknownRegionError(ValueError):
    pass


class PlanetilerNotAvailableError(RuntimeError):
    pass


def _http_get(url: str) -> bytes:
    with httpx.Client(follow_redirects=True, timeout=300.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def download_extract(
    region: str, dest: Path, *, http_get: Callable[[str], bytes] = _http_get
) -> Path:
    """A named region only — never a guessed or computed URL. An unknown
    region name is rejected with the region named, not silently attempted
    against a pattern that may or may not resolve (the same "rejected,
    named and counted" discipline `01_DOMAIN_MODEL.md` §7 applies to an
    ambiguous date order or an undeclared CRS)."""
    if region not in GEOFABRIK_REGIONS:
        raise UnknownRegionError(
            f"{region!r} is not a known Geofabrik region — add it to GEOFABRIK_REGIONS "
            f"rather than guess its download URL. Known regions: {sorted(GEOFABRIK_REGIONS)}"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(http_get(GEOFABRIK_REGIONS[region]))
    return dest


def run_planetiler(
    osm_pbf_path: Path,
    output_pmtiles_path: Path,
    *,
    jar_path: Path,
    subprocess_run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> Path:
    """Shells out to a real `planetiler.jar` — this is a Java tool, not a
    Python or npm dependency, so it is never resolved by `pip`/`npm` and
    never appears in the licence-check gate the way a package dependency
    would; confirm its own licence (Apache-2.0, per planetiler's own
    repository, at the time a real jar is pinned) separately from
    `docs/00_ARCHITECTURE.md` §7's allowlist, which only governs installed
    package dependencies."""
    if not jar_path.is_file():
        raise PlanetilerNotAvailableError(
            f"planetiler jar not found at {jar_path} — download a release jar and pass its "
            "path, or set it up before calling this function. Never silently skipped: a "
            "missing tile output is a build failure, not a degraded basemap."
        )
    output_pmtiles_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess_run(
        [
            "java", "-jar", str(jar_path),
            f"--osm-path={osm_pbf_path}",
            f"--output={output_pmtiles_path}",
            "--force",
        ],
        check=True,
    )
    return output_pmtiles_path


async def load_gazetteer(
    osm_pbf_path: Path,
    *,
    graph: GraphPort,
    ontology: OntologySchema,
    tx: TxId,
    principal: Principal,
    load_id: str,
) -> LoadReport:
    """The connector + recipe-engine path — `services/ingest/connectors/
    geo/osm.py`, needing no network or external process, so this is what
    `tests/test_build_local_basemap.py` actually exercises end to end."""
    recipe = load_recipe(_OSM_GAZETTEER_RECIPE_PATH)
    report, _events = await run_recipe(
        recipe,
        read_osm_places(str(osm_pbf_path)),
        graph=graph,
        ontology=ontology,
        tx=tx,
        principal=principal,
        load_id=load_id,
        investigation_scope="reference-data",
        source=str(osm_pbf_path),
    )
    return report


def _default_licence() -> ProviderLicence:
    return ProviderLicence(id="ODbL", redistributable=True, client_scope=ClientScope.OPEN)


def register_local_provider(
    config_path: Path,
    *,
    provider_id: str,
    label: str,
    pmtiles_path: Path,
    make_default: bool = True,
) -> MapConfig:
    """Upserts one tier-1 provider entry into `osprey.yaml`'s `map:`
    section — replaces an existing entry with the same id, otherwise
    appends. Starts a fresh `MapConfig` if `config_path` does not exist
    yet, rather than requiring a caller to have one already.

    **Known limitation, not a silent one.** This round-trips through
    `yaml.safe_dump`, which does not preserve comments or key ordering in
    an existing file — fine for a script whose whole job is to *produce*
    this section, wrong for hand-maintained prose elsewhere in the same
    file. The harness (Phase 8) is the real, comment-preserving answer
    (`05_DEPLOYMENT.md` §2.1: "the generated artefacts are shown before
    anything runs" as a diff); this script predates it."""
    provider = MapProvider(
        id=provider_id,
        label=label,
        kind=MapSourceKind.VECTOR,
        source=f"file://{pmtiles_path}",
        style="bundled:osprey-dark",
        attribution="© OpenStreetMap contributors",
        licence=_default_licence(),
    )

    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text())
        existing = MapConfig.model_validate(raw["map"])
        providers = [p for p in existing.providers if p.id != provider_id] + [provider]
        default = provider_id if make_default else existing.default
    else:
        providers = [provider]
        default = provider_id

    config = MapConfig(default=default, providers=providers)
    config_path.write_text(
        yaml.safe_dump({"map": config.model_dump(mode="json", exclude_none=True)}, sort_keys=False)
    )
    return config


@dataclass(frozen=True)
class BasemapBuildResult:
    pmtiles_path: Path
    gazetteer_report: LoadReport
    map_config: MapConfig


async def build_local_basemap(
    *,
    region: str,
    output_dir: Path,
    planetiler_jar_path: Path,
    osprey_config_path: Path,
    graph: GraphPort,
    ontology: OntologySchema,
    tx: TxId,
    principal: Principal,
    progress: Callable[[str], None] = print,
    downloader: Callable[[str, Path], Path] = download_extract,
    planetiler_runner: Callable[..., Path] = run_planetiler,
) -> BasemapBuildResult:
    """The full tier-1 pipeline in one call — `00_ARCHITECTURE.md` §1.2's
    "one button." Each stage's own function is independently callable and
    independently tested; this is only the ordering. `output_dir` is
    created here, once, rather than left to each injectable stage — a
    caller substituting its own `downloader`/`planetiler_runner` (as the
    tests do) should not also have to reimplement that."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pbf_path = output_dir / f"{region}.osm.pbf"
    pmtiles_path = output_dir / f"{region}.pmtiles"

    progress(f"Downloading the {region!r} Geofabrik extract...")
    downloader(region, pbf_path)

    progress("Running planetiler...")
    planetiler_runner(pbf_path, pmtiles_path, jar_path=planetiler_jar_path)

    progress("Loading the OSM-derived gazetteer...")
    report = await load_gazetteer(
        pbf_path, graph=graph, ontology=ontology, tx=tx, principal=principal,
        load_id=f"load-osm-gazetteer-{region}",
    )
    progress(
        f"Gazetteer load: {report.nodes_created} places created, "
        f"{report.nodes_referenced} already known, {len(report.rejections)} rejected."
    )

    progress(f"Registering provider osm-local-{region}...")
    config = register_local_provider(
        osprey_config_path,
        provider_id=f"osm-local-{region}",
        label=f"OpenStreetMap ({region})",
        pmtiles_path=pmtiles_path,
    )

    return BasemapBuildResult(pmtiles_path=pmtiles_path, gazetteer_report=report, map_config=config)


# --- CLI entrypoint, mirroring services/ingest/__main__.py's shape -----------
#
# Not an `osprey geo build` command — there is no unified `osprey` CLI
# (`CLAUDE.md`'s own Conventions), and this module's own docstring records
# that as deliberate for now. `python -m scripts.build_local_basemap` is
# what that eventual command wraps.


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_local_basemap",
        description="Tier-1 one-button local basemap build: download, planetiler, gazetteer load.",
    )
    parser.add_argument("--region", required=True, choices=sorted(GEOFABRIK_REGIONS))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--planetiler-jar", required=True)
    parser.add_argument("--osprey-config", default="osprey.yaml")
    parser.add_argument(
        "--principal-id", default=os.environ.get("OSPREY_PRINCIPAL_ID", "geo-build-worker")
    )
    parser.add_argument("--clearance", default=os.environ.get("OSPREY_CLEARANCE", "OFFICIAL"))
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "unit-1"))
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
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
        result = await build_local_basemap(
            region=args.region,
            output_dir=Path(args.output_dir),
            planetiler_jar_path=Path(args.planetiler_jar),
            osprey_config_path=Path(args.osprey_config),
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=principal,
        )
        await graph.commit_transaction(tx)
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    finally:
        await client.aclose()

    print(f"PMTiles written to {result.pmtiles_path}")
    print(
        f"Gazetteer: {result.gazetteer_report.nodes_created} places created, "
        f"{result.gazetteer_report.nodes_referenced} already known, "
        f"{len(result.gazetteer_report.rejections)} rejected."
    )
    return 1 if result.gazetteer_report.rejections else 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
