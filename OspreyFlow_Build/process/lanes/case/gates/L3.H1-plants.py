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
  # Part 2: a home case kept (built by 3609f74, before this step; shown red here, rule 15).
  ("a dataset's home case removed like any other",
   "services/api/app.py",
   "    if await datasets.dataset_of_home_case(investigation.id) is not None:\n        raise HTTPException(",
   "    if False:\n        raise HTTPException(",
   T + "test_home_cases.py", "home_case_cannot_be_removed"),
  # Part 3: the run report's drawn-watch count, the run's own principal's alone.
  ("every owner's drawn-watch alerts counted for the loader",
   "services/api/drawn_watches.py",
   "        if self.counted_for is None or watch.owner == self.counted_for:",
   "        if True:",
   T + "test_drawn_watch_alerts.py", "counts_only_the_drawn_watch_alerts"),
  ("the run's count never put on its report",
   "services/api/recipe_run.py",
   "        report.drawn_watch_alerts = await _run_drawn_watches_best_effort(",
   "        await _run_drawn_watches_best_effort(",
   T + "test_drawn_watch_alerts.py", "dataset_it_loaded_into"),
  # The lane-reviewer's round.
  ("the loader's count lost when another owner's watch fails",
   "services/api/recipe_run.py",
   "        counted = exc.counted if isinstance(exc, DrawnWatchesFailed) else 0\n",
   "        counted = 0\n",
   T + "test_drawn_watch_alerts.py", "never_changes_the_loaders_count"),
  ("the count taken only once a watch has run whole (lost to a later failure)",
   "services/api/drawn_watches.py",
   "            counts.tell(watch)  # as each is raised, so a later failure loses none of the count\n",
   "",
   T + "test_drawn_watch_alerts.py", "counts_only_the_drawn_watch_alerts or never_changes_the_loaders_count"),
  ("a home case moved off its dataset",
   "services/api/app.py",
   "    if home_of is not None and list(body.dataset_ids) != [home_of]:",
   "    if False:",
   T + "test_home_case_kept.py", "never_moved_off_its_dataset"),
  ("the shared rule's level check skipped (a borrowed layer read with no level on its case)",
   "services/api/dataset_scope.py",
   "            and await holds_a_level(principal, original)\n",
   "",
   T + "test_unconverted_case_layer.py", "no_level_on_the_original"),
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
tests = sorted({t for *_, t, _ in PLANTS} | {T + "test_drawn_watch_alerts.py"})
r = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", *tests, "-q", "-p", "no:cacheprovider"], cwd=CORE, env=env, capture_output=True, text=True)
out.append("## restored\n" + r.stdout.strip().splitlines()[-1] + "\n")
pathlib.Path(sys.argv[1]).write_text("\n".join(out))
