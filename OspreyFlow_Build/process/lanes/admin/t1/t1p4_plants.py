"""T1 part 4's plants, offline: each lever taken out at its real call site, the whole test file run, then put back.

Run from OspreyFlow_Core, on the closed offline ports and with no lane:
    env -u OSPREY_LANE ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 CLICKHOUSE_HTTP_PORT=59994 \\
      .venv/bin/python ../OspreyFlow_Build/process/lanes/admin/t1/t1p4_plants.py > ../OspreyFlow_Build/process/lanes/admin/gates/t1p4_plants_offline.txt
It prints, for the unplanted tree and then for each plant, the failed tests by name; a plant whose run has no failure is
marked NOT RED, and the script exits 1. Each file is restored from its own text whatever happens.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parents[4]
PLUGIN = "tests/worker_isolation.py"
PROOF = "tests/test_worker_isolation.py"
LEASE = "scripts/stack_lease.sh"
LEASE_TESTS = "tests/test_stack_lease.py"

#: (what is planted, the file, the text at its real call site, what replaces it, the test file run)
PLANTS: list[tuple[str, str, str, str, str]] = [
    ("ArcadeDB's from_env not redirected", PLUGIN,
     '        redirect_arcadedb(names["OSPREY_ARCADEDB_DATABASE"])\n', "        pass\n", PROOF),
    ("POSTGRES_DB not per worker", PLUGIN,
     '"POSTGRES_DB": f"{SHARED}_x{run}_t{started}_{worker}",', '"POSTGRES_DB": SHARED,', PROOF),
    ("VALKEY_DB left at 0", PLUGIN, '"VALKEY_DB": str(first + n),', '"VALKEY_DB": "0",', PROOF),
    ("MINIO_BUCKET_PREFIX not set", PLUGIN,
     '"MINIO_BUCKET_PREFIX": f"{SHARED}-x{run}-t{started}-{worker}-",', '"MINIO_BUCKET_PREFIX": "",', PROOF),
    ("ANALYTICS_DB_PATH not set", PLUGIN,
     '        os.environ["ANALYTICS_DB_PATH"] = str(self.folder / "analytics.duckdb")\n', "", PROOF),
    ("a per-test conformance_* name rewritten too", PLUGIN,
     'if database == SHARED else database', 'if database else database', PROOF),
    ("serial files not grouped", PLUGIN,
     '            item.add_marker(pytest.mark.xdist_group("serial"))\n', "            pass\n", PROOF),
    ("the group added after xdist reads it", PLUGIN,
     "@pytest.hookimpl(tryfirst=True)\ndef pytest_collection_modifyitems",
     "@pytest.hookimpl(trylast=True)\ndef pytest_collection_modifyitems", PROOF),
    ("a serial test kept on the worker's own graph", PLUGIN,
     '    if serial:\n        _TARGET["database"] = SHARED\n', "    if serial:\n        pass\n", PROOF),
    ("a worker known by the inherited PYTEST_XDIST_WORKER", PLUGIN,
     '    workerinput = getattr(config, "workerinput", None)',
     ('    workerinput = getattr(config, "workerinput", None) or ({"workerid": os.environ["PYTEST_XDIST_WORKER"],'
     ' "testrunuid": os.environ.get("PYTEST_XDIST_TESTRUNUID", ""), "workercount": 1}'
     ' if "PYTEST_XDIST_WORKER" in os.environ else None)'), PROOF),
    ("-n without --dist loadgroup let through", PLUGIN,
     'if config.getoption("dist", default="no") != "loadgroup":',
     'if config.getoption("dist", default="no") == "never":', PROOF),
    ("more workers than Valkey databases let start", PLUGIN,
     "        if taken + workers > MOST_WORKERS:\n", "        if False:\n", PROOF),
    ("the controller not exporting the databases it took", PLUGIN,
     "        os.environ[TAKEN] = str(taken + workers)", "        pass", PROOF),
    ("a nested run's workers from db 1 again", PLUGIN,
     '    first = _taken() - int(workerinput["workercount"]) + 1\n', "    first = 1\n", PROOF),
    ("-n auto given every CPU", PLUGIN,
     "    return max(1, min(cpus, MOST_WORKERS - _taken()))\n", "    return cpus\n", PROOF),
    ("the sweep blind to a name's age", PLUGIN,
     " and now - int(m.group(1)) >= STALE_AFTER]", "]", PROOF),
    ("a store that fails to clear stops the rest", PLUGIN,
     ("            except Exception as error:  # noqa: BLE001  (each store tried; the first failure raised below)\n"
     "                failures.append(error)\n"),
     "            except Exception:  # noqa: BLE001\n                raise\n", PROOF),
    ("a start that fails part-way not cleared", PLUGIN,
     ('    _STATE["worker"] = state  # before start(), so a start that fails part-way is still cleared\n'
     "    state.start()\n"),
     '    state.start()\n    _STATE["worker"] = state\n', PROOF),
    ("the check: Valkey given no db not counted as db 0", PROOF,
     '        if db is None and name == "Valkey" or isinstance(db, ast.Constant)', "        if isinstance(db, ast.Constant)",
     PROOF),
    ("the check: Valkey's db given by position missed", PROOF,
     "        if db is None and len(node.args) >= 3:", "        if False:", PROOF),
    ("the check: a **{..., \"db\": 0} literal missed", PROOF,
     "        if db is None and isinstance(unpacked, ast.Dict):", "        if False:", PROOF),
    ("the check: a fixed compose project missed", PROOF, '|\\"compose\\",\\s*\\"-p\\"', "", PROOF),
    ("the check: a multiprocessing child missed", PROOF, "|\\bmultiprocessing\\b|ProcessPoolExecutor", "", PROOF),
    ("the check: a -m scripts./cli child missed", PROOF, "|services\\.|scripts\\.|cli\\b)", "|services\\.)", PROOF),
    ("up never sets max_connections", LEASE, '    [ "$cmd" = up ] && { pg_connections "$s" || exit 1; }\n', "",
     LEASE_TESTS),
    ("ALTER SYSTEM without the restart", LEASE,
     '    docker_for "$s" restart "$c" >/dev/null ||', "    true ||", LEASE_TESTS),
    ("one try, no wait for a starting Postgres", LEASE,
     'tries="${OSPREY_PG_READY_TRIES:-60}"', "tries=1", LEASE_TESTS),
]  # fmt: skip


def failed(test_file: str) -> list[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_XDIST_") and k != "OSPREY_WORKER_VALKEY_TAKEN"}
    ran = subprocess.run(
        [".venv/bin/pytest", "-c", str(BUILD / "pytest.ini"), "-q", "-p", "no:cacheprovider", "-rf",
         str(BUILD / test_file)],
        check=False, env=env, capture_output=True, text=True, timeout=900,
    )  # fmt: skip
    names = re.findall(r"^FAILED \S+::(\S+)", ran.stdout, re.MULTILINE)
    if ran.returncode not in (0, 1):
        names.append(f"(pytest exit {ran.returncode}: {ran.stdout.strip().splitlines()[-1:]})")
    return names


def main() -> int:
    bad = 0
    for test_file in sorted({p[4] for p in PLANTS}):
        unplanted = failed(test_file)
        print(f"UNPLANTED {test_file}: {'green' if not unplanted else unplanted}")
        bad |= bool(unplanted)
    for what, rel, old, new, test_file in PLANTS:
        path = BUILD / rel
        text = path.read_text()
        if text.count(old) != 1:
            print(f"PLANT {what}: the call site is not in {rel} once (found {text.count(old)})")
            bad = 1
            continue
        try:
            path.write_text(text.replace(old, new))
            red = failed(test_file)
        finally:
            path.write_text(text)
        print(f"PLANT {what} ({rel}): " + (f"{len(red)} failed: {', '.join(red)}" if red else "NOT RED"))
        bad |= not red
    return bad


if __name__ == "__main__":
    sys.exit(main())
