"""Round 1's plants: each (file, old, new, tests), run, first failure printed, restored by md5."""
import hashlib, os, re, subprocess, sys, time
from pathlib import Path as _P
ROOT = _P(__file__).resolve().parents[5]
CORE = str(ROOT / "OspreyFlow_Core")
BUILD = str(ROOT / "OspreyFlow_Build")
PUB = f"{CORE}/services/api/studio_publish.py"
RUNS = f"{CORE}/services/api/recipe_runs.py"
LIVE = "tests/services/api/test_snapshot_withdrawal_tells_nothing_live.py"
LEDGER = "tests/services/api/test_row_key_withdrawal_ledger.py"
ANCHOR = "                await _withdraw_dropped_rows(recipe, rows, report, sink, investigation_scope)\n"
E = ANCHOR + '''                from services.ingest.engine import row_group_keys as _rgk
                _d = await sink.dropped_row_keys(recipe.id, investigation_scope,
                    present={k for k in _rgk(recipe, rows) if k is not None})
                _e = sorted({e for d in _d for e in (d.edge_ids or ())})
                async with sink._ledger._pool.acquire() as _c:  # e: a count from every case's loads
                    _n = int(await _c.fetchval(
                        "SELECT count(DISTINCT x) FROM recipe_runs, jsonb_array_elements(load_records) AS rec, "
                        "jsonb_array_elements_text(COALESCE(rec->'touched_edge_ids', '[]'::jsonb)) AS x "
                        "WHERE load_records IS NOT NULL AND rec->>'reverted_at' IS NULL "
                        "AND NOT (rec->>'load_id' = ANY($2::text[])) AND x = ANY($1::text[])",
                        _e, sorted({d.load_id for d in _d} | {report.load_id})) or 0)
                report.links_kept_an_occurrence = _n
                if _n:
                    report.refresh_notes = [*report.refresh_notes, f"{_n} link kept an occurrence from a dropped row"]
'''
PLANTS = [
    ("e: a count told to the loader from other cases' loads (the old links_kept_an_occurrence and words)", PUB, ANCHOR, E, [LIVE]),
    ("f: withdrawn_before asked without the case", RUNS,
     '"AND w.investigation_id = k.investigation_id AND w.row_key = k.row_key) "\n                "AS withdrawn_before',
     '"AND w.row_key = k.row_key) "\n                "AS withdrawn_before', [LIVE, LEDGER]),
    ("g: withdrawn_row_keys_among asked without the case", RUNS,
     '"SELECT row_key FROM withdrawn_row_keys WHERE recipe_id = $1 "\n                    "AND investigation_id = $2 AND row_key = ANY($3::text[])",\n',
     '"SELECT row_key FROM withdrawn_row_keys WHERE recipe_id = $1 "\n                    "AND $2::text IS NOT NULL AND row_key = ANY($3::text[])",\n', [LEDGER]),
]
env = {**os.environ, "OSPREY_LANE": "studio", "ARCADEDB_HTTP_PORT": "2491", "POSTGRES_PORT": "55433",
       "POSTGRES_PASSWORD": "throwaway", "VALKEY_PORT": "6379", "CLICKHOUSE_HTTP_PORT": "18123"}
only = sys.argv[1:]
for name, path, old, new, tests in PLANTS:
    if only and name[0] not in only:
        continue
    orig = open(path).read(); digest = hashlib.md5(orig.encode()).hexdigest()
    assert orig.count(old) == 1, name
    try:
        open(path, "w").write(orig.replace(old, new))
        out = subprocess.run([f"{CORE}/.venv/bin/pytest", "-q", "-p", "no:cacheprovider", *tests],
                             cwd=BUILD, env=env, capture_output=True, text=True).stdout
    finally:
        open(path, "w").write(orig)
        assert hashlib.md5(open(path).read().encode()).hexdigest() == digest
    summary = [l for l in out.splitlines() if re.search(r"\d+ (passed|failed)", l)]
    failed = [l.split("::")[-1] for l in out.splitlines() if l.startswith("FAILED")]
    firsts = [l for l in out.splitlines() if l.startswith("E   ")][:2]
    print(f"## {name} ({time.strftime('%H:%M:%SZ', time.gmtime())})\nrun: {summary[-1] if summary else out[-400:]}\nfailed: {failed}\nfirst: {firsts}\nrestored md5 {digest}\n")
