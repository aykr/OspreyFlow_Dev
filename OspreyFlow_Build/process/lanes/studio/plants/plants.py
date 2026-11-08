"""Plant each restored behaviour in studio_publish.py, run the tests, restore by md5."""
import hashlib, os, re, subprocess, sys, time
from pathlib import Path as _P
ROOT = _P(__file__).resolve().parents[5]
CORE = str(ROOT / "OspreyFlow_Core")
BUILD = str(ROOT / "OspreyFlow_Build")
TARGET = f"{CORE}/services/api/studio_publish.py"
ANCHOR = "                await _withdraw_dropped_rows(recipe, rows, report, sink, investigation_scope)\n"
BASE = '''                from services.ingest.engine import row_group_keys as _rgk
                _present = {k for k in _rgk(recipe, rows) if k is not None}
                _dropped = await sink.dropped_row_keys(recipe.id, investigation_scope, present=_present)
                _gone = list(dict.fromkeys(e for d in _dropped for e in (d.edge_ids or ())))
                _keep: set[str] = set()
'''
KEPT_BY_OTHER_ROWS = '''                async with sink._ledger._pool.acquire() as _c:  # elements_kept_by_other_rows
                    _keep |= {r["x"] for r in await _c.fetch(
                        "SELECT DISTINCT x FROM loaded_row_keys, unnest(edge_ids) AS x "
                        "WHERE x = ANY($1::text[]) AND NOT (recipe_id = $2 AND investigation_id = $3 "
                        "AND row_key = ANY($4::text[]))",
                        _gone, recipe.id, investigation_scope, [d.row_key for d in _dropped])}
'''
IN_OTHER_RECORDS = '''                async with sink._ledger._pool.acquire() as _c:  # elements_in_other_records
                    _keep |= {r["x"] for r in await _c.fetch(
                        "SELECT DISTINCT x FROM recipe_runs, jsonb_array_elements(load_records) AS rec, "
                        "jsonb_array_elements_text(COALESCE(rec->'touched_edge_ids', '[]'::jsonb)) AS x "
                        "WHERE load_records IS NOT NULL AND rec->>'reverted_at' IS NULL "
                        "AND NOT (rec->>'load_id' = ANY($2::text[])) AND x = ANY($1::text[])",
                        _gone, sorted({d.load_id for d in _dropped} | {report.load_id}))}
'''
TAIL = '''                _gone = [e for e in _gone if e not in _keep]
                if _gone:
                    await graph.withdraw_elements([], _gone, report.load_id, tx)
                report.withdrawn_edge_ids = _gone
'''
PLANTS = {
    "a: a dropped row's links withdrawn": BASE + TAIL,
    "b: links withdrawn unless another row of any case holds them (elements_kept_by_other_rows)": BASE + KEPT_BY_OTHER_ROWS + TAIL,
    "c: links withdrawn unless another load's record lists them (elements_in_other_records)": BASE + IN_OTHER_RECORDS + TAIL,
}
ANCHOR_D = "    ids = await sink.withdrawn_event_ids(report.load_id)\n"
PLANT_D = """    _links = [r["x"] for r in await sink._ledger._pool.fetch(
        "SELECT DISTINCT unnest(edge_ids) AS x FROM withdrawn_row_keys WHERE withdrawn_by_load = $1",
        report.load_id)]
    if _links:
        ids = [r[0] for r in analytics._con.execute(
            "SELECT event_id FROM events WHERE edge_id IN (" + ",".join("?" for _ in _links) + ")",
            _links).fetchall()]
"""
TESTS = sys.argv[1:]
orig = open(TARGET).read()
digest = hashlib.md5(orig.encode()).hexdigest()
env = {**os.environ, "OSPREY_LANE": "studio", "ARCADEDB_HTTP_PORT": "2491", "POSTGRES_PORT": "55433", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "6379", "CLICKHOUSE_HTTP_PORT": "18123"}
try:
    PLANTS["d: the rows' events withdrawn by their links, end to end"] = None
    for name, code in PLANTS.items():
        if os.environ.get('ONLY') and name[0] not in os.environ['ONLY']:
            continue
        if code is None:
            assert orig.count(ANCHOR_D) == 1
            open(TARGET, "w").write(orig.replace(ANCHOR_D, ANCHOR_D + PLANT_D))
        else:
            assert orig.count(ANCHOR) == 1
            open(TARGET, "w").write(orig.replace(ANCHOR, ANCHOR + code))
        out = subprocess.run([f"{CORE}/.venv/bin/pytest", "-q", "-p", "no:cacheprovider", *TESTS],
                             cwd=BUILD, env=env, capture_output=True, text=True).stdout
        summary = [l for l in out.splitlines() if re.search(r"\d+ (passed|failed)", l)]
        firsts = [l for l in out.splitlines() if l.startswith("E   ")][:3]
        failed = [l.split("::")[-1] for l in out.splitlines() if l.startswith("FAILED")]
        print(f"## {name} ({time.strftime('%H:%M:%SZ', time.gmtime())})\nrun: {summary[-1] if summary else out[-500:]}\nfailed: {failed}\nfirst: {firsts}\n")
finally:
    open(TARGET, "w").write(orig)
    assert hashlib.md5(open(TARGET).read().encode()).hexdigest() == digest
    print("restored, md5", digest)
