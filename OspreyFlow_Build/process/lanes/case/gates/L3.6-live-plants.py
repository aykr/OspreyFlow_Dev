"""L3.6's live plants (rule 15): each check of the queue's query planted out at its own call site
(`alerts.queue_scope`), its live test run against the leased stack, the file restored. Run from the
worktree root, under the lease, with the stack's ports exported:
`python3 OspreyFlow_Build/process/lanes/case/gates/L3.6-live-plants.py <out>`."""
import os, pathlib, subprocess, sys

CORE = pathlib.Path("OspreyFlow_Core")
T = "../OspreyFlow_Build/tests/services/api/"
Q = T + "test_drawn_watch_queue_live.py"
PLANTS = [
    ("a drawn watch's alert reaching its owner through every case (no exclusion from the watch clause)",
     "services/api/alerts.py",
     "\"typology IS NULL AND rule_id NOT LIKE 'analyst:%' AND rule_id NOT LIKE 'drawn_watch:%'\"",
     "\"typology IS NULL AND rule_id NOT LIKE 'analyst:%'\"", Q, "through_another_case"),
    ("a drawn watch's alert read by every member of its case (no owner in its clause)",
     "services/api/alerts.py",
     "f\"OR (rule_id LIKE 'drawn_watch:%' AND investigation_id = {case} AND owner_id = {me}) \"",
     "f\"OR (rule_id LIKE 'drawn_watch:%' AND investigation_id = {case}) \"", Q, "no_one_but_its_owner"),
    ("a drawn watch's alert never queued (no clause of its own)",
     "services/api/alerts.py",
     "f\"OR (rule_id LIKE 'drawn_watch:%' AND investigation_id = {case} AND owner_id = {me}) \"",
     "", Q, "reaches_its_owner_in_its_case"),
    ("a drawn watch's alert of no kind (never queued)",
     "services/api/alerts.py",
     "\"WHEN rule_id LIKE 'drawn_watch:%' THEN 'drawn_watch' END)\"",
     "\"END)\"", Q, "reaches_its_owner_in_its_case"),
]
out = []
for words, f, old, new, test, k in PLANTS:
    p = CORE / f
    src = p.read_text()
    assert src.count(old) == 1, (words, src.count(old))
    p.write_text(src.replace(old, new))
    try:
        r = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", test, "-q",
                            "-p", "no:cacheprovider", "-k", k], cwd=CORE, capture_output=True, text=True)
    finally:
        p.write_text(src)
    tail = [l for l in r.stdout.splitlines() if l.startswith(("FAILED", "E  ")) or " passed" in l or " failed" in l][:6]
    out.append(f"## {words}\nplant in {f}; {test} -k {k}; exit {r.returncode} ({'RED' if r.returncode else 'NOT CAUGHT'})\n" + "\n".join(tail) + "\n")
pathlib.Path(sys.argv[1]).write_text("\n".join(out))
print("\n".join(l for l in out if l.startswith("##") or "exit" in l))
