"""The tier-1 "one-button local basemap build" — `docs/00_ARCHITECTURE.md`
§1.2 ("Tier 1 is the shipped default and it is complete. One button on the
harness's Geospatial screen downloads a Geofabrik extract, runs planetiler
to produce PMTiles, and loads the OSM-derived gazetteer") and
`docs/05_DEPLOYMENT.md` §2.2 ("Build local basemap").

There is no `osprey` CLI (`CLAUDE.md`'s own Conventions). This module is the
real functionality the eventual `osprey geo build` command wraps — a plain,
importable, directly-runnable script, the same correction already made for
`revert_load` in Phase 2. "With progress shown" here means a `progress`
callback each stage calls (default: `print`), since there is no progress
bar to draw it into yet.

**What is genuinely exercised in CI versus what cannot be.** `load_gazetteer`
need no external resource and is fully tested (`tests/test_build_local_basemap.py`)
against the synthetic OSM fixture the gazetteer connector's own tests already use.
`download_extract` and `run_planetiler` need a real network call and a real Java
process respectively — the standing rule that "CI never depends on a
third party's availability" means neither can run in CI, so both are
exercised only for their *argument-construction and error-handling* logic,
with the actual network/subprocess call injected out — the same shape
`test_websocket_auth.py` uses for a `WebSocket` it never really opens.
**Real planetiler CLI flags are unverified here** — this repo has no
network access to confirm them against the current release, and
`00_ARCHITECTURE.md` §1.2 already asks that OS Data Hub specifics be
"verified at implementation time rather than trusting this document"; the
same caution applies to planetiler's flag names below.

**`register_local_provider` moved to `scripts/geo_local_provider.py`** (26 September
2026, Stage 2 §6 part B) — that module's own docstring has the reason
(`harness/Dockerfile` doesn't copy `services/`/`adapters/` in, and this module's own
top-level imports both, which would make `register_local_provider` unreachable from
inside the harness image even though its own body needs neither). Re-imported here
unchanged; this module's own behaviour and tests are untouched by the move.
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
from scripts.geo_local_provider import register_local_provider as register_local_provider
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
from schemas.mapconfig import MapConfig

#: A deliberately small, named set — the harness's own choices
#: ("Great Britain, a US state or region, or a custom bounding box",
#: `05_DEPLOYMENT.md` §2.2). Add an entry rather than guess a URL pattern:
#: Geofabrik's own directory structure is not perfectly regular across
#: regions, so a computed URL is exactly the kind of "plausible but wrong"
#: default `01_DOMAIN_MODEL.md` §7 warns against for CRS/date guessing.
#:
#: **`rutland` added 26 September 2026, and it is the entry a first run should use.** Stage 3a's
#: own residual asked for a real basemap built on a real machine, and the three regions below it
#: are all far too large for that to be a routine step: `great-britain` is ~1.9GB of PBF and tens
#: of minutes of planetiler. Rutland is England's smallest county — 1.9MB of PBF — so the whole
#: tier-1 pipeline (download, planetiler, gazetteer, register, verify) completes in minutes on a
#: laptop while exercising every stage against genuinely real OSM data, not a fixture.
#:
#: **Its URL is under `europe/united-kingdom/`, not `europe/great-britain/`** — confirmed live, not
#: assumed. Geofabrik has renamed that region: the top-level `great-britain-latest.osm.pbf` above
#: still resolves as a legacy alias (checked directly, 26 September 2026 — 206, octet-stream), but
#: the *sub*-extract path under `great-britain/` does not. It answers 302 to Geofabrik's own home
#: page, which `httpx`'s `follow_redirects=True` would have followed to a 200 carrying HTML, so
#: `download_extract` would have written an HTML error page to disk under a `.osm.pbf` name and
#: handed it to planetiler. That is exactly the "plausible but wrong" failure this dict exists to
#: prevent, and it is why the entry below is a checked URL rather than one composed from the
#: region name.
#:
#: **`berkshire` is the one to build for the demo, and `rutland` is the one to build to prove the
#: pipeline works.** They are not interchangeable, and choosing wrongly produces a failure that
#: looks exactly like a broken basemap: the HMP fixture's ten yards sit at roughly 51.5°N,
#: -0.6°E (`tests/scenarios/fixtures/hmp.py`), which is in Berkshire. Rutland is 130km north of
#: them. A Rutland basemap is a perfectly good PMTiles file that the Glass loads, reads and draws
#: nothing from, because the viewport — which `@sigma/layer-maplibre` centres on the graph's own
#: coordinates, not on the basemap's — is over an area the extract does not cover. Found
#: precisely that way on 26 September 2026: every other check passed (no "basemap not built"
#: alert, real ranged reads answered 206, attribution rendered) and the canvas was still empty.
#:
#: **So the rule this dict now encodes: the extract must cover the data you are going to look
#: at.** It is not "pick a small region"; it is "pick the smallest region that contains your
#: fixture", and they only coincide by luck.
GEOFABRIK_REGIONS: dict[str, str] = {
    "berkshire": (
        "https://download.geofabrik.de/europe/united-kingdom/england/berkshire-latest.osm.pbf"
    ),
    "rutland": (
        "https://download.geofabrik.de/europe/united-kingdom/england/rutland-latest.osm.pbf"
    ),
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


class NotAnOsmExtractError(RuntimeError):
    """What came back down the wire was not an OSM PBF — see `_assert_is_osm_pbf`."""


#: The first bytes of every OSM PBF: a 4-byte big-endian `BlobHeader` length, then a protobuf
#: whose `type` field is the literal `OSMHeader`. Checking for that string in the first 64 bytes
#: is the cheapest real discrimination between a PBF and anything else; it is not a full format
#: parse and does not try to be.
_OSM_PBF_MAGIC = b"OSMHeader"


def _assert_is_osm_pbf(payload: bytes, *, region: str, url: str) -> None:
    """**Added 26 September 2026, after this exact failure happened for real.** `_http_get` sets
    `follow_redirects=True`, and Geofabrik answers an extract path it no longer serves with a 302
    to its own home page rather than a 404 — so `raise_for_status()` sees a 200 and hands back a
    page of HTML. Without this check `download_extract` wrote that HTML to disk under a
    `.osm.pbf` name and returned it as a success, and the failure surfaced minutes later inside
    planetiler as an unintelligible parse error naming neither the region nor the URL.

    A wrong answer that arrives with a 200 is the case `CLAUDE.md` rule 15 names: the remote
    dependency's own *refusal* did not look like a refusal, so nothing downstream could tell. The
    check belongs here, where the region and the URL are both still in hand to name."""
    if not payload.startswith(b"\x00\x00\x00") or _OSM_PBF_MAGIC not in payload[:64]:
        raise NotAnOsmExtractError(
            f"{url} did not return an OSM PBF for region {region!r} — got {len(payload)} bytes "
            f"beginning {payload[:16]!r}. Geofabrik answers a path it no longer serves with a "
            "redirect to its own home page, not a 404, so a 200 here does not mean the extract "
            "exists; check the URL in GEOFABRIK_REGIONS against Geofabrik's own current directory "
            "listing rather than assuming the region name still maps to the same path."
        )


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
    url = GEOFABRIK_REGIONS[region]
    payload = http_get(url)
    # Checked *before* the write, deliberately: a rejected download must leave no file behind at
    # all, so a later stage cannot pick up a half-plausible artefact from a failed run.
    _assert_is_osm_pbf(payload, region=region, url=url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
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
    package dependencies.

    **`--download` and `--download_dir` added 26 September 2026, running this against a real
    planetiler for the first time.** This module's own docstring had already disclosed that
    "real planetiler CLI flags are unverified here"; they were wrong, and only a real run could
    say so. Two separate faults, both fatal to a first build:

    1. The OpenMapTiles profile planetiler runs by default needs three auxiliary sources beyond
       the OSM extract (lake centrelines, water polygons, Natural Earth). Without `--download` it
       exits non-zero before reading a single node —
       `java.lang.IllegalArgumentException: data/sources/lake_centerline.shp.zip does not exist.
       Run with --download to fetch it` — so the previous flag list could never have produced
       tiles on a machine that had not already fetched them by some other route.
    2. `download_dir` defaults to the *relative* path `data/sources`, resolved against the
       working directory. Run from a checkout, as `05_DEPLOYMENT.md` §2.2 has a reader do, that
       is this repository's own `data/` — several hundred megabytes of third-party source data
       deposited inside the tree. Pinned beside the output instead, which is where the rest of
       this pipeline's artefacts already go.

    `--osm-path`, `--output` and `--force` were right as they stood, confirmed against the same
    real `--help` output; planetiler accepts either `-` or `_` in a flag name."""
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
            "--download",
            f"--download_dir={output_pmtiles_path.parent / 'sources'}",
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
