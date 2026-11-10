"""L3.H1's offline plants (rule 15): each check planted out at its own call site, its tests run, the
file restored. Run from the worktree root: `python3 OspreyFlow_Build/process/lanes/case/gates/
L3.H1-plants.py <out>`."""
import os, pathlib, subprocess, sys

CORE = pathlib.Path("OspreyFlow_Core")
T = "../OspreyFlow_Build/tests/services/api/"
PLANTS = [
  # Part 1: the one read-set rule, caught through both of its callers' own tests.
  ("the shared read-set rule keeping a borrowed layer for anyone (scope_to_case's caller)",
   "services/api/dataset_scope.py",
   "    if borrowed is not None and borrowed in datasets and not holds_the_original:",
   "    if False:",
   T + "test_unconverted_case_layer.py", "no_level_on_the_original"),
  ("the shared read-set rule keeping a borrowed layer for anyone (the drawn watches' caller)",
   "services/api/dataset_scope.py",
   "    if borrowed is not None and borrowed in datasets and not holds_the_original:",
   "    if False:",
   T + "test_drawn_watch_alerts.py", "borrowed_layer"),
]
env = dict(os.environ, ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", POSTGRES_PASSWORD="throwaway", VALKEY_PORT="59993", CLICKHOUSE_HTTP_PORT="59994")
env.pop("OSPREY_LANE", None)
out = []
for words, f, old, new, test, k in PLANTS:
    p = CORE / f
    src = p.read_text()
    assert src.count(old) == 1, (words, src.count(old))
    p.write_text(src.replace(old, new))
    try:
        r = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", test, "-q", "-p", "no:cacheprovider", "-k", k], cwd=CORE, env=env, capture_output=True, text=True)
    finally:
        p.write_text(src)
    lines = r.stdout.splitlines()
    tail = [l for l in lines if l.startswith("FAILED") or " passed" in l or " failed" in l]
    tail += [l for l in lines if l.startswith("E  ")][:3]
    out.append(f"## {words}\nplant in {f}; -k {k}; exit {r.returncode}\n" + "\n".join(tail) + "\n")
    print(words, "->", "RED" if r.returncode == 1 else f"NOT RED (exit {r.returncode})")
tests = sorted({t for *_, t, _ in PLANTS})
r = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", *tests, "-q", "-p", "no:cacheprovider"], cwd=CORE, env=env, capture_output=True, text=True)
out.append("## restored\n" + r.stdout.strip().splitlines()[-1] + "\n")
pathlib.Path(sys.argv[1]).write_text("\n".join(out))
