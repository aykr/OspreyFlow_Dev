"""rules-b analytics-field's offline plants (rule 15): each protection removed at its real call
site, and the tests that name it run with a fresh bytecode cache; then every file restored and the
tests run as a control. Run from OspreyFlow_Core with the closed offline ports. DuckDB only here:
ClickHouse's cases need a leased stack (its plant is in live.txt)."""

import os
import subprocess
import tempfile

DUCK = "packages/adapters/analytics_duckdb/adapter.py"
APP = "services/api/app.py"
SUITE = "../OspreyFlow_Build/tests/conformance/analytics_port/test_suite.py"
ROUTE = "../OspreyFlow_Build/tests/services/api/test_analytics_field_refused.py"
DUCK_CASES = "duckdb and (field_name or smuggle)"
GUARD = "        raise AnalyticsFieldRefused\n"
PLANTS = [
    ("the adapter's bare ValueError, as before this change", DUCK, GUARD,
     '        raise ValueError(f"not a safe field name for a SQL literal: {field!r}")\n',
     [(SUITE, DUCK_CASES), (ROUTE, "")]),
    ("the guard dropped: the name reaches SQL", DUCK,
     '    if not field.replace("_", "").isalnum() or not field:\n' + GUARD, "",
     [(SUITE, DUCK_CASES), (ROUTE, "")]),
    ("geocode's property past the guard", DUCK,
     "        prop = _safe_field_name(req.property)\n", "        prop = req.property\n",
     [(SUITE, "duckdb and geocode_events")]),
    ("no handler: the routes answer a bare 500", APP,
     "@app.exception_handler(AnalyticsFieldRefused)\n", "", [(ROUTE, "")]),
    ("the handler answers 400", APP,
     "        status_code=422, content={\"error\": \"field_name_refused\"",
     "        status_code=400, content={\"error\": \"field_name_refused\"", [(ROUTE, "")]),
]
ENV = dict(os.environ, ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", VALKEY_PORT="59993",
           CLICKHOUSE_HTTP_PORT="59994")
ENV.pop("OSPREY_LANE", None)


def run(target: str, k: str) -> subprocess.CompletedProcess[str]:
    env = dict(ENV, PYTHONPYCACHEPREFIX=tempfile.mkdtemp(prefix="plant-pyc-"))
    args = [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p",
            "no:cacheprovider", target]
    return subprocess.run(args + (["-k", k] if k else []), capture_output=True, text=True, env=env)


originals = {p: open(p).read() for p in (DUCK, APP)}
try:
    for name, path, before, after, targets in PLANTS:
        assert originals[path].count(before) == 1, (name, originals[path].count(before))
        open(path, "w").write(originals[path].replace(before, after))
        for target, k in targets:
            r = run(target, k)
            tail = r.stdout.strip().splitlines()[-1]
            print(f"{'RED  ' if r.returncode else 'GREEN?!'} | {name} | {target.rsplit('/', 1)[-1]}"
                  f"{' -k ' + repr(k) if k else ''} | {tail}")
        open(path, "w").write(originals[path])
    for target, k in [(SUITE, "duckdb"), (ROUTE, "")]:
        print("CONTROL (unplanted, fresh cache):", target.rsplit("/", 1)[-1],
              run(target, k).stdout.strip().splitlines()[-1])
finally:
    for path, text in originals.items():
        open(path, "w").write(text)
