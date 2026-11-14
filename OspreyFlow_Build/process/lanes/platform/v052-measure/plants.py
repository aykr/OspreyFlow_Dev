"""The timer's checks, each removed in turn at its own site; its tests run with a fresh PYTHONPYCACHEPREFIX;
restored. Run from OspreyFlow_Core with the repository as its argument."""
import pathlib, subprocess, sys, tempfile
repo = pathlib.Path(sys.argv[1]); core = repo / "OspreyFlow_Core"; venv = pathlib.Path(sys.argv[2])
SCRIPT = core / "scripts/measure_search.py"
PLANTS = [
    ("the failure figure not judged", '        if p95 > budget["fail_ms"]:', "        if False:"),
    ("a fallback answer counted as the index's", '    if query["class"] not in SUGGEST_CLASSES and answer.get("source", "index") != "index":', "    if False:"),
    ("the ranking not checked", "    expected = query.get(\"expect_first\")", "    expected = None"),
    ("a class with no budget measured", "    if unbudgeted:", "    if False:"),
]
for what, old, new in PLANTS:
    text = SCRIPT.read_text(); assert text.count(old) == 1, what
    SCRIPT.write_text(text.replace(old, new))
    try:
        env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": ".:packages:../OspreyFlow_Build", "ARCADEDB_HTTP_PORT": "59991",
               "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway", "VALKEY_PORT": "59993",
               "CLICKHOUSE_HTTP_PORT": "59994", "PYTHONPYCACHEPREFIX": tempfile.mkdtemp()}
        done = subprocess.run([str(venv / "pytest"), "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider", "-q", "-rf",
                               "../OspreyFlow_Build/tests/test_measure_search.py"], cwd=core, env=env, capture_output=True, text=True)
    finally:
        SCRIPT.write_text(text)
    print(f"Plant: {what}:")
    print("\n".join(l.split(" - ")[0].replace("../OspreyFlow_Build/", "") for l in done.stdout.splitlines()
                    if l.startswith("FAILED") or " passed" in l or " failed" in l))
