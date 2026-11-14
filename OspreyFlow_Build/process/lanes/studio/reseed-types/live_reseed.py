"""The live half of CARRIES' "A type refusal stops a reseed" (the orchestrator, 14 November 2026): each of
the four packs whose ids persist from one seed to the next is seeded by main's seed path onto a leased
stack, then reseeded once at main. For each run it records the exit, any refusal's words (ADR-124
Amendment 18 refuses a write onto an id another type holds, and other shapes too), and the pack's
node counts before and after.

Run on the leased stack, from the repository root:

    OspreyFlow_Build/scripts/stack_lease.sh remote studio -- \\
        OspreyFlow_Core/.venv/bin/python OspreyFlow_Build/process/lanes/studio/reseed-types/live_reseed.py

It runs each seed as `seed_internal` does (`python -m <script> --case-name <the pack's case>`), with the
environment the PID live test gives its seed (`tests/ingest/test_pid_seed_live.py`): its own ingest and
recipe folders, no sign-in, and post-ingest resolution off. It exits 1 if any run exits non-zero or
any refusal's words appear.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
sys.path[:0] = [str(CORE), str(CORE / "packages")]

from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig  # noqa: E402

from demo_fixtures import datasets  # noqa: E402

PACKS = [
    ("fixture-corp", "scripts.seed_fixture_corp", datasets.FIXTURE_CORP),
    ("cyber-intrusion", "scripts.seed_cyber_intrusion", datasets.CYBER_INTRUSION),
    ("prison-intelligence", "scripts.seed_pid", datasets.PID),
    ("prison-intelligence-scale", "scripts.seed_pid_scale", datasets.PID_SCALE),
]
#: ADR-124 Amendment 18's refusals, and any other refusal a write can meet, in their own words.
REFUSAL = re.compile(
    r"held by a node of another type|give it an id of its own|refus|Traceback|Error:", re.IGNORECASE
)
SCRATCH = Path(tempfile.mkdtemp(prefix="reseed-live-"))


def environment() -> dict[str, str]:
    env = dict(os.environ)
    env["OSPREY_INGEST_ROOT"] = str(SCRATCH / "ingest")
    env["OSPREY_RECIPE_REPO_ROOT"] = str(SCRATCH / "recipes")
    env.setdefault("OIDC_JWKS_URL", "http://localhost:9/jwks")
    env["OSPREY_POST_INGEST_RESOLUTION"] = "off"
    env["PYTHONPATH"] = os.pathsep.join([str(CORE), str(CORE / "packages")])
    return env


async def counts(dataset_id: str) -> dict[str, int]:
    """The pack's nodes by type, by its dataset, as the store holds them now."""
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    found: dict[str, int] = {}
    try:
        await client.create_database_if_absent()
        types = await client.sql("SELECT name FROM schema:types WHERE type = 'vertex'")
        for row in types:
            name = str(row["name"])
            counted = await client.sql(
                f"SELECT count(*) AS n FROM `{name}` WHERE datasets CONTAINS :d",
                params={"d": dataset_id},
            )
            n = int(counted[0]["n"]) if counted else 0
            if n:
                found[name] = n
    finally:
        await client.aclose()
    return found


def seed(module: str, case_name: str) -> tuple[int, str]:
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-m", module, "--case-name", case_name],
        cwd=CORE,
        env=environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout + done.stderr


def main() -> int:
    bad = 0
    for pack, module, dataset in PACKS:
        print(f"=== {pack} ({module}, dataset {dataset.id})", flush=True)
        print("before:", asyncio.run(counts(dataset.id)), flush=True)
        for run in ("seed (as main)", "reseed (at main)"):
            code, said = seed(module, dataset.case_name or "")
            refusals = [ln for ln in said.splitlines() if REFUSAL.search(ln)]
            after = asyncio.run(counts(dataset.id))
            print(f"{run}: exit {code}; {len(refusals)} refusal line(s)", flush=True)
            for line in refusals[:20]:
                print("   refusal:", line.strip()[:300], flush=True)
            print(f"after {run}:", after, flush=True)
            if code != 0:
                print("   last lines:", *said.splitlines()[-15:], sep="\n     ", flush=True)
            bad += code != 0 or bool(refusals)
    print(f"=== {'every run clean' if not bad else f'{bad} run(s) not clean'}", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
