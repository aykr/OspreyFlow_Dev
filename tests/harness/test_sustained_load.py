"""`05_DEPLOYMENT.md` §8 / `07_BUILD_PLAN.md` Stage 2a addendum — the named-not-built
`test_arcadedb_memory_and_query_latency_under_sustained_ingest_cycles`, built.

**What §8 already found, cited rather than repeated:** across repeated closing-pass runs against
one never-reset `ospreyflow` database, `ramOsUsed` climbed 8.651 → 9.097 → 9.396GiB and the same
query workload slowed 117s → 151s → 203s. That measurement was taken with `deploy/compose/dev.yaml`
and the closing-pass scenario test's own in-process `TestClient`. This file measures the same
question — accumulated database state, not process uptime — against **the rendered product as
installed** (`python -m harness.apply --profile local-lite`), through the real, authenticated HTTP
surface a deployed Conduit actually exposes, not an in-process shortcut.

**Opt-in via `OSPREY_TEST_SUSTAINED_LOAD=1`** — needs Docker, builds and brings up a real
`local-lite` stack, then runs `CYCLES` (6) real seed-and-query rounds against one accumulating
database. Not part of the fast unit tier; the same opt-in reasoning
`tests/harness/test_bundle_exit_test.py` and `tests/harness/test_restore_exit_test.py` already use.
**Runtime budget:** apply (build + up + grants + verify, against `--out-root`'s own default
`deploy/generated/local-lite` — see the test function's own comment for why not `tmp_path`) is
minutes; each cycle stops the Conduit, seeds HMP + Fixture Corp as one-shot containers (the same
mechanism `harness.apply`'s own `--seed` flag uses), restarts it and waits for health again, then
runs the query sample — of the same order as one closing-pass run (§8's own figures: 117-203s). Six
cycles plus one apply is budgeted at up to 40 minutes; CI should time the job accordingly rather
than guess a smaller ceiling.

**Why the query sample is answered directly against ArcadeDB/DuckDB-shaped fixture data rather than
through a browser session.** The realm's own Glass client has `directAccessGrantsEnabled: False`
(`harness/realm.py`) — there is no password grant to script — and `06_DECISIONS.md` ADR-050's own
resolution deliberately leaves interactive sign-in to a real PKCE browser flow
(`apps/workspace/keyboard/keyboard.spec.ts` is the existing, real, browser-level proof that a
session reaches these actions). This file instead mints a bearer token the same way
`harness.apply.create_investigation` already does for the post-launch seed — a client-credentials
token for the Conduit's own confidential client, exchanged (RFC 8693) for the realm's disposable
demo-analyst subject, rendered here via `--demo-analyst`. **Not `VERIFY_SUBJECT`:** its own
`receivable_handling_codes: ["R"]` is documented in `harness/realm.py` as unable to see either seed
fixture at all (both write `handling_code="P"`) — the demo analyst's `["P"]` is the realm's own
subject built to see this data.

**Fixture Corp is seeded once, on cycle 1, not every cycle — found running this file for real,
before this correction, not assumed in advance.** Its own three sub-fixtures write fixed literal
node ids (`corp-path-hub`, `corp-res-identical-1`, ...) so a demo can always reference the same
entities, but `GraphArcadeDBAdapter.upsert_nodes` is a bare `INSERT`, not a real upsert, and nothing
in `GraphPort`'s own contract or its conformance suite promises otherwise. A second seed against the
same database failed outright (`ArcadeDBError 503`, a duplicate-key exception on `mx_Person[id]`).
HMP's own structural entities are `on_match: reference` (idempotent) and its incident events are
meant to accumulate across seeds — the accumulation this test exists to characterise — so only HMP
repeats; see the test function's own comment at the seed call for the full account.

**The fixed query sample, and why each member needs no fixture-specific node lookup.** Fixture
Corp's own structural ids are literal, not generated (`tests/scenarios/fixtures/fixture_corp.py`):
`corp-path-hub`, the resolution pair `corp-res-identical-1`/`corp-res-identical-2`, and
`corp-path-spoke{length}-{length}` as each spoke's own terminal. HMP's own events are filtered by
`investigation_scope` alone, no node id needed.

- **Hotspot bins** — `POST /v1/analytics/geobins`, `EventFilter.investigation_scope` = the cycle's
  own fresh investigation.
- **One Search Around** — `POST .../expand` from `corp-path-hub`, depth 1, `ASSOCIATE_OF` — the
  Glass's own multi-step traversal builder, exercised here at the data layer.
- **One pathfinder call** — `POST /v1/paths`, `corp-path-hub` to `corp-path-spoke6-6`
  (`max_hops=6`), matching `08_ACCEPTANCE_SCENARIOS.md` B21's own shape.
- **The τ 0.99/0.95/0.80 projections** — a Search Around from `corp-res-identical-1` over
  `SAME_AS` pulls the resolvable pair into the working set (that pair merges at all three detents,
  per `generate_resolution_persons`'s own docstring), then `PUT .../resolution/threshold` at each
  of Strict/Balanced/Broad in turn.

**Characterisation, not assertion.** Per the brief this file was built against: it records the
six-cycle curve and writes it to `sustained_load_results.csv` in the current working directory for
the round's own report — it does not assert a memory or latency ceiling. Item 3's own thresholds
are Proposed against the measured numbers, not decided, in `05_DEPLOYMENT.md` §8 and
`07_BUILD_PLAN.md` Stage 2a; the owner rules on them. This test currently asserts only that all six
cycles complete and every query in the sample returns 2xx — the same "asserts nothing that would
fail today except the run completing" instruction the brief states explicitly.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import httpx
import pytest
from harness.apply import _compose, _run, create_investigation, wait_for_health
from harness.apply import main as apply_main
from harness.apply import seed as harness_seed
from harness.backup import _env_value
from harness.compare import _query as arcadedb_query
from harness.realm import CONDUIT_CLIENT_ID, DEMO_ANALYST_SUBJECT

pytestmark = pytest.mark.skipif(
    os.environ.get("OSPREY_TEST_SUSTAINED_LOAD") != "1",
    reason="needs Docker and takes up to ~40 minutes (a real apply, then 6 real seed-and-query "
    "cycles against one accumulating database); opt in with OSPREY_TEST_SUSTAINED_LOAD=1",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_LITE_PROJECT = "osprey-local-lite"
CYCLES = 6
KEYCLOAK_URL = "http://127.0.0.1:8081"
REALM = "osprey"
API_URL = "http://127.0.0.1:8080"
DATABASE = "ospreyflow"


def _teardown_local_lite_deployment() -> None:
    """The same command and reasoning `tests/harness/test_apply_env.py`'s own autouse fixture
    uses — this file is not autoused (it has exactly one test, opting into the same care
    deliberately rather than by fixture machinery)."""
    subprocess.run(
        ["docker", "compose", "-p", LOCAL_LITE_PROJECT, "down", "-v", "--remove-orphans"],
        capture_output=True,
        text=True,
        timeout=180,
    )


def _mint_token(secret: str, requested_subject: str) -> str:
    """The same two-step client-credentials-then-exchange `create_investigation` already performs,
    parameterised on the requested subject so this file can mint for the demo analyst rather than
    `VERIFY_SUBJECT` (see module docstring for why that distinction matters here)."""
    token_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"

    def post(data: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(
            token_url, data=urllib.parse.urlencode(data).encode(), method="POST"
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            result: dict[str, Any] = json.loads(response.read().decode())
            return result

    own = post(
        {
            "grant_type": "client_credentials",
            "client_id": CONDUIT_CLIENT_ID,
            "client_secret": secret,
        }
    )
    exchanged = post(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": CONDUIT_CLIENT_ID,
            "client_secret": secret,
            "subject_token": own["access_token"],
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_subject": requested_subject,
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }
    )
    return str(exchanged["access_token"])


def _arcadedb_container_id(compose_file: Path) -> str:
    result = subprocess.run(
        _compose(compose_file) + ["ps", "-q", "arcadedb"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    container_id = result.stdout.strip()
    assert container_id, "no arcadedb container found for this compose project"
    return container_id


_MEM_PATTERN = re.compile(r"([\d.]+)\s*(GiB|MiB|KiB|B)")


def _to_mib(value: float, unit: str) -> float:
    return {"GiB": value * 1024, "MiB": value, "KiB": value / 1024, "B": value / (1024 * 1024)}[
        unit
    ]


def _docker_stats_rss_mib(container_id: str) -> float:
    """`docker stats`'s own cgroup-level figure — conflates JVM heap, ArcadeDB's off-heap page
    cache and OS file-cache (07_BUILD_PLAN.md Stage 2a's own finding), which is exactly why this
    file also attempts the finer-grained `/api/v1/server` profiler reading below rather than
    relying on this number alone."""
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container_id],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    used = result.stdout.split("/")[0].strip()
    match = _MEM_PATTERN.match(used)
    assert match, f"unrecognised docker stats MemUsage format: {result.stdout!r}"
    return _to_mib(float(match.group(1)), match.group(2))


def _arcadedb_server_metrics(compose_file: Path) -> dict[str, float] | None:
    """ArcadeDB's own `/api/v1/server` profiler metrics — "if exposed" per the brief this file was
    built against, and it is: `GET /api/v1/server` (root-authenticated) returns
    `metrics.profiler.ramHeapUsed.space` / `.ramOsUsed.space` / `.ramHeapMax.space` in bytes, not
    top-level fields — the real shape, read directly against a running container while building
    this function, not guessed from `07_BUILD_PLAN.md`'s own table of the same field names (which
    does not print the request that produced them). Returns `None` rather than failing the cycle
    when the shape does not match, since this is a supplementary reading, not the primary metric
    (`docker stats`, above, is)."""
    password = _env_value(compose_file.parent / "deployment.env", "OSPREY_ARCADEDB_PASSWORD")
    completed = subprocess.run(
        _compose(compose_file)
        + [
            "exec",
            "-T",
            "arcadedb",
            "sh",
            "-c",
            f"curl -s -u root:'{password}' http://127.0.0.1:2480/api/v1/server",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        payload: dict[str, Any] = json.loads(completed.stdout)
        profiler = payload["metrics"]["profiler"]
        return {
            "ram_heap_used_mib": profiler["ramHeapUsed"]["space"] / (1024 * 1024),
            "ram_heap_max_mib": profiler["ramHeapMax"]["space"] / (1024 * 1024),
            "ram_os_used_mib": profiler["ramOsUsed"]["space"] / (1024 * 1024),
        }
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _node_edge_counts(compose_file: Path) -> tuple[int, int]:
    """The same `count(*)`-per-type mechanism `harness.compare.type_record_counts` already uses
    and already found correct against a real store (its own docstring records two wrong ways this
    one does not repeat) — bucketed here into node/edge totals rather than left as a flat per-type
    dict, since that is the shape this file's own report needs."""
    rows = arcadedb_query(compose_file, DATABASE, "SELECT FROM schema:types")
    vertex_types = [row["name"] for row in rows if row.get("type") == "vertex"]
    edge_types = [row["name"] for row in rows if row.get("type") == "edge"]

    def _sum(type_names: list[str]) -> int:
        total = 0
        for name in type_names:
            result = arcadedb_query(compose_file, DATABASE, f"SELECT count(*) AS n FROM {name}")
            total += int(result[0]["n"]) if result else 0
        return total

    return _sum(vertex_types), _sum(edge_types)


def _run_query_sample(token: str, investigation_id: str) -> float:
    """The fixed query sample — module docstring has the full account of what each call is and
    why it needs no fixture-specific lookup. Returns the sample's own wall time."""
    headers = {"Authorization": f"Bearer {token}"}
    start = time.monotonic()
    with httpx.Client(base_url=API_URL, timeout=60.0) as client:
        response = client.post(
            "/v1/analytics/geobins",
            headers=headers,
            json={
                "filter": {"investigation_scope": investigation_id},
                "precision": 8,
            },
        )
        response.raise_for_status()

        response = client.post(
            f"/v1/investigations/{investigation_id}/expand",
            headers=headers,
            json={
                "request": {
                    "node_ids": ["corp-path-hub"],
                    "depth": 1,
                    "edge_types": ["ASSOCIATE_OF"],
                }
            },
        )
        response.raise_for_status()

        response = client.post(
            "/v1/paths",
            headers=headers,
            json={
                "source": "corp-path-hub",
                "target": "corp-path-spoke6-6",
                "max_hops": 6,
                "k": 3,
            },
        )
        response.raise_for_status()

        response = client.post(
            f"/v1/investigations/{investigation_id}/expand",
            headers=headers,
            json={
                "request": {
                    "node_ids": ["corp-res-identical-1"],
                    "depth": 1,
                    "edge_types": ["SAME_AS"],
                }
            },
        )
        response.raise_for_status()

        for tau in (0.99, 0.95, 0.80):
            response = client.put(
                f"/v1/investigations/{investigation_id}/resolution/threshold",
                headers=headers,
                json={"threshold": tau},
            )
            response.raise_for_status()

    return time.monotonic() - start


def test_arcadedb_memory_and_query_latency_under_sustained_ingest_cycles() -> None:
    # No `--out-root` override: `harness/render.py`'s own `BUILD_CONTEXT_FROM_OUTPUT_DIR`
    # ("../../../") assumes the rendered output sits at `--out-root`'s own default depth beneath
    # this repository (`deploy/generated/<profile>/`) — real, not a convention this file can skip,
    # found running this test against a `tmp_path` render first: `docker compose build` failed with
    # `lstat .../apps: no such file or directory`, `apps/` being three levels above the real
    # `deploy/generated/local-lite/` and nowhere near a `tmp_path`. Gitignored
    # (`.gitignore`: `/deploy/generated/`), so this is real generated output, not a fixture.
    apply_main(
        [
            "--profile",
            "local-lite",
            "--demo-analyst",
            "--keycloak-url",
            KEYCLOAK_URL,
            "--realm",
            REALM,
        ]
    )

    out_dir = REPO_ROOT / "deploy" / "generated" / "local-lite"
    compose_file = out_dir / "compose.yaml"
    env_path = out_dir / "deployment.env"
    secret = _env_value(env_path, "OSPREY_OIDC_CLIENT_SECRET")

    results: list[dict[str, Any]] = []
    try:
        for cycle in range(1, CYCLES + 1):
            investigation_id = create_investigation(KEYCLOAK_URL, REALM, secret, API_URL)

            # `fixture-corp` only on cycle 1 — real finding, not an assumption: `seed_fixture_
            # corp.py`'s own three sub-fixtures use fixed literal node ids (`corp-path-hub`,
            # `corp-res-identical-1`, ...) so a demo can always reference the same entities, and
            # `GraphArcadeDBAdapter.upsert_nodes` (`packages/adapters/graph_arcadedb/adapter.py`)
            # is a bare `INSERT`, not a real upsert — no docstring on `GraphPort.upsert_nodes`
            # promises otherwise, and no conformance case exercises calling it twice with the same
            # id. Measured directly running this test before this fix: cycle 2's fixture-corp
            # reseed failed outright, `ArcadeDBError 503: "Found duplicate key in index"` on
            # `mx_Person[id]` for `corp-res-distinct-2`. HMP's own structural entities are
            # `on_match: reference` (idempotent by design) and its incident events are meant to
            # accumulate across seeds — that accumulation is this test's own subject — so only HMP
            # repeats.
            datasets = ["hmp", "fixture-corp"] if cycle == 1 else ["hmp"]
            _run(_compose(compose_file) + ["stop", "api"], stage="cycle-seed")
            harness_seed(compose_file, datasets, investigation_id)
            _run(_compose(compose_file) + ["start", "api"], stage="cycle-seed")
            wait_for_health(compose_file, timeout_seconds=180)

            token = _mint_token(secret, DEMO_ANALYST_SUBJECT)
            wall_seconds = _run_query_sample(token, investigation_id)

            container_id = _arcadedb_container_id(compose_file)
            rss_mib = _docker_stats_rss_mib(container_id)
            server_metrics = _arcadedb_server_metrics(compose_file)
            node_count, edge_count = _node_edge_counts(compose_file)

            row = {
                "cycle": cycle,
                "investigation_id": investigation_id,
                "arcadedb_rss_mib": round(rss_mib, 1),
                "query_sample_wall_seconds": round(wall_seconds, 2),
                "node_count": node_count,
                "edge_count": edge_count,
                "server_ram_heap_used_mib": (server_metrics or {}).get("ram_heap_used_mib"),
                "server_ram_heap_max_mib": (server_metrics or {}).get("ram_heap_max_mib"),
                "server_ram_os_used_mib": (server_metrics or {}).get("ram_os_used_mib"),
            }
            results.append(row)
            print(f"cycle {cycle}: {row}")
    finally:
        results_path = Path.cwd() / "sustained_load_results.csv"
        if results:
            with results_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(results[0].keys()))
                writer.writeheader()
                writer.writerows(results)
        _teardown_local_lite_deployment()

    assert len(results) == CYCLES, (
        f"only {len(results)}/{CYCLES} cycles completed — see sustained_load_results.csv for "
        "whichever ones did"
    )
