"""rules-b v060-basemap: each plant breaks one change of v0.6.0 item 10 in the code's own shape and
names the test that must go red for it (rule 15). Each file is restored from the text saved before
the first plant, never from git, and checked byte for byte at the end. Run from OspreyFlow_Core.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
OSM = CORE / "services/ingest/connectors/geo/osm.py"
SCRIPT = CORE / "scripts/build_local_basemap.py"
ADMIN = CORE / "services/api/map_admin.py"
TESTS = ["../OspreyFlow_Build/tests/test_gazetteer_build_batches_and_points.py",
         "../OspreyFlow_Build/tests/ingest/test_osm_gazetteer_connector.py"]  # fmt: skip

PLANTS = [
    ("a named point that is not a settlement kept", OSM,
     'if not name or node.tags.get("place") not in SETTLEMENT_PLACES:', "if not name:",
     "test_read_osm_places_yields_settlements_only"),
    ("every place in one transaction", SCRIPT,
     "while rows := list(islice(left, GAZETTEER_BATCH)):", "while rows := list(islice(left, None)):",
     "test_the_gazetteer_commits_a_batch_at_a_time"),
    ("a failed batch left open", SCRIPT,
     "                await graph.rollback_transaction(batch_tx)\n", "",
     "test_a_failed_batch_is_rolled_back_alone_and_the_load_stops"),
    ("planetiler's heap left to the JVM", SCRIPT, '            f"-Xmx{heap}",\n', "",
     "test_planetiler_is_given_its_heap_explicitly"),
    ("the store opened but not given to the load", ADMIN,
     "unit=unit, analytics=analytics,", "unit=unit, analytics=None,",
     "test_the_cli_build_writes_the_points_when_it_can_open_the_store"),
    ("DuckDB's lock not caught", ADMIN, "    except duckdb.IOException:\n",
     "    except KeyError:\n", "test_the_cli_build_writes_the_points_when_it_can_open_the_store"),
]


def run() -> str:
    env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"}
    env.update(ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", POSTGRES_PASSWORD="throwaway",
               VALKEY_PORT="59993", CLICKHOUSE_HTTP_PORT="59994",
               PYTHONPYCACHEPREFIX=tempfile.mkdtemp())  # fmt: skip
    return subprocess.run(
        [".venv/bin/pytest", "-p", "no:cacheprovider", "-c", "../OspreyFlow_Build/pytest.ini", "-q",
         "-rA", *TESTS], check=False, capture_output=True, text=True, env=env, cwd=CORE,
    ).stdout  # fmt: skip


def main() -> int:
    saved = {path: path.read_bytes() for path in (OSM, SCRIPT, ADMIN)}
    bad = 0
    try:
        for name, path, old, new, must in PLANTS:
            text = saved[path].decode("utf-8")
            assert text.count(old) == 1, (name, text.count(old))
            path.write_bytes(text.replace(old, new).encode("utf-8"))
            out = run()
            red = sorted({line.split("::")[-1].split("[")[0].split()[0]
                          for line in out.splitlines() if line.startswith("FAILED")})  # fmt: skip
            ok = must in red
            bad += not ok
            print(f"{'RED ' if ok else 'GREEN?'} {name}: {must}; red: {red}")
            path.write_bytes(saved[path])
    finally:
        for path, text in saved.items():
            path.write_bytes(text)
    assert all(path.read_bytes() == text for path, text in saved.items())
    control = run().splitlines()[-1]
    print(f"control (restored): {control}")
    return 1 if bad or "failed" in control else 0


if __name__ == "__main__":
    sys.exit(main())
