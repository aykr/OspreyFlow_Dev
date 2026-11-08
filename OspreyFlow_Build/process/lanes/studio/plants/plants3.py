"""Round 1's self-review plants: each (file, old, new, tests), run, first failure printed, restored by md5."""
import hashlib, os, re, subprocess, sys, time
from pathlib import Path as _P
ROOT = _P(__file__).resolve().parents[5]
CORE = str(ROOT / "OspreyFlow_Core")
BUILD = str(ROOT / "OspreyFlow_Build")
RUNS = f"{CORE}/services/api/recipe_runs.py"
ENG = f"{CORE}/services/ingest/engine.py"
PLAN = f"{CORE}/services/ingest/snapshot_withdrawal.py"
DUCK = f"{CORE}/packages/adapters/analytics_duckdb/adapter.py"
CH = f"{CORE}/packages/adapters/analytics_clickhouse/adapter.py"
UNIT = "tests/ingest/test_snapshot_withdrawal.py"
MET = "tests/ingest/test_metering.py::test_a_match_on_a_node_the_reader_may_not_see_reads_as_no_node_at_all"
LIVE = "tests/services/api/test_snapshot_withdrawal_tells_nothing_live.py"
LEDGER = "tests/services/api/test_row_key_withdrawal_ledger.py"
CONF = "tests/conformance/analytics_port/test_suite.py"
FIND = "        existing = await state.graph.find_node(\n            entity.type, match_key[1], match_key[2], state.principal\n        )\n"
OTHER = "        existing = await state.graph.find_node(\n            entity.type, match_key[1], match_key[2], state.principal.model_copy(update={\"id\": \"someone-else\"})\n        )\n"
LOOP = "for start in range(0, len(ids), _WITHDRAW_CHUNK):"
PLANTS = {
    "P": ("the planner withdrawing a row back again (`and not d.withdrawn_before` removed)", PLAN,
          " and not d.withdrawn_before]", "]", [UNIT], 1),
    "M": ("the engine's find_node asked under another principal (both call sites)", ENG, FIND, OTHER, [MET], 2),
    "D": ("DuckDB's withdraw_events_by_id stopping after one chunk", DUCK, LOOP,
          "for start in range(0, min(len(ids), 1), _WITHDRAW_CHUNK):", [CONF, "-k", "duckdb and withdraw"], 1),
    "K": ("ClickHouse's withdraw_events_by_id stopping after one chunk", CH,
          "for start in range(0, len(unique), _WITHDRAW_CHUNK):",
          "for start in range(0, min(len(unique), 1), _WITHDRAW_CHUNK):", [CONF, "-k", "clickhouse and withdraw"], 1),
    "G": ("add_record's move guard removed (the NOT EXISTS)", RUNS,
          '"AND NOT EXISTS (SELECT 1 FROM withdrawn_row_keys w WHERE "\n                    "w.recipe_id = k.recipe_id AND w.investigation_id = k.investigation_id "\n                    "AND w.row_key = k.row_key) RETURNING *) "',
          '"RETURNING *) "', [LEDGER], 1),
    "H": ("add_record's move guard without the case (`w.investigation_id = k.investigation_id` removed)", RUNS,
          '"w.recipe_id = k.recipe_id AND w.investigation_id = k.investigation_id "\n                    "AND w.row_key = k.row_key) RETURNING *) "',
          '"w.recipe_id = k.recipe_id "\n                    "AND w.row_key = k.row_key) RETURNING *) "', [LEDGER, LIVE], 1),
    "R": ("withdrawn_keys_kept_again joined without the case", RUNS,
          '"USING (recipe_id, investigation_id, row_key) WHERE w.withdrawn_by_load = $1"',
          '"USING (recipe_id, row_key) WHERE w.withdrawn_by_load = $1"', [LEDGER], 1),
    "S": ("restore_withdrawn_row_keys without the case", RUNS,
          '"AND k.investigation_id = w.investigation_id AND k.row_key = w.row_key) "',
          '"AND k.row_key = w.row_key) "', [LEDGER], 1),
}
env = {**os.environ, "OSPREY_LANE": "studio", "ARCADEDB_HTTP_PORT": "2491", "POSTGRES_PORT": "55433",
       "POSTGRES_PASSWORD": "throwaway", "VALKEY_PORT": "6379", "CLICKHOUSE_HTTP_PORT": "18123",
       "CLICKHOUSE_USER": "osprey", "CLICKHOUSE_PASSWORD": "throwaway"}
for letter in sys.argv[1:]:
    name, path, old, new, tests, count = PLANTS[letter]
    orig = open(path).read(); digest = hashlib.md5(orig.encode()).hexdigest()
    assert orig.count(old) == count, (letter, orig.count(old))
    t0 = time.strftime("%H:%M:%SZ", time.gmtime())
    try:
        open(path, "w").write(orig.replace(old, new))
        out = subprocess.run([f"{CORE}/.venv/bin/pytest", "-q", "-p", "no:cacheprovider", *tests],
                             cwd=BUILD, env=env, capture_output=True, text=True).stdout
    finally:
        open(path, "w").write(orig)
        assert hashlib.md5(open(path).read().encode()).hexdigest() == digest
    summary = [l for l in out.splitlines() if re.search(r"\d+ (passed|failed|deselected)", l)]
    failed = [l.split("::")[-1] for l in out.splitlines() if l.startswith("FAILED")]
    firsts = [l for l in out.splitlines() if l.startswith("E   ")][:2]
    print(f"## {letter}: {name} ({t0})\nrun: {summary[-1] if summary else out[-400:]}\nfailed: {failed}\nfirst: {firsts}\nrestored md5 {digest}\n", flush=True)
