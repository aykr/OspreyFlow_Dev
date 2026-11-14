"""4c's am15 live section on the leased stack, then its live plants, each restored (run from the worktree root)."""
import os, shutil, subprocess, sys
ROOT = "/Users/ayankar/dev/osprey-wt/platform-b"
EP = "OspreyFlow_Core/services/api/entra_people.py"
LIVE = "../OspreyFlow_Build/tests/services/api/test_entra_people_live.py"
def remote(k: str) -> tuple[int, list[str]]:
    cmd = ("cd OspreyFlow_Core && PYTHONPYCACHEPREFIX=$(mktemp -d) .venv/bin/python -m pytest -c ../OspreyFlow_Build/pytest.ini "
           f"-p no:cacheprovider -q -rA {LIVE}" + (f" -k {k}" if k else ""))
    r = subprocess.run(["bash", "OspreyFlow_Build/scripts/stack_lease.sh", "remote", "platform-b", "--", "sh", "-c", cmd],
                       cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout + r.stderr).splitlines()
    return r.returncode, [l for l in out if l.startswith(("PASSED", "FAILED", "ERROR"))] + [l for l in out if " passed" in l or " failed" in l or " error" in l][-1:]
src = open(os.path.join(ROOT, EP)).read()
lines = src.split("\n")
# the audit plant: the Access write's audit row moved after its transaction has committed
i = src.index('                    action="set_person_access",')
a = src.rindex("            if audit is not None:\n", 0, i)
b = src.index("        return before, after\n", i)
audit_after = ("        if audit is not None:\n            await audit.record(principal=by, action=\"set_person_access\",\n"
               "                               resolved_query={\"user_id\": oid}, result_cardinality=1)\n")
PLANTS = [
 ("the seed's values given past its role gate (round 2's should 4)",
  src.replace("if access and (added is not None or nobody_administers):", "if access:"), "am15_a_recorded_person"),
 ("the Access write's audit row after its transaction commits (round 1's should 4, round 2's should 7)",
  src[:a] + src[b:].replace("        return before, after\n", audit_after + "        return before, after\n", 1), "am15_a_value_is_never_kept"),
 ("the store's own clearance limit removed (rule 3)",
  src.replace("or order.index(access.clearance) > order.index(mine.clearance)", "or False"), "am15_the_store_s_limits"),
]
which = sys.argv[1] if len(sys.argv) > 1 else "all"
if which in ("all", "green"):
    rc, out = remote(""); print(f"== the whole live file (32), unplanted: exit {rc}"); print("\n".join(out))
if which in ("all", "plants"):
    path = os.path.join(ROOT, EP); keep = path + ".plantkeep"; shutil.copy2(path, keep)
    try:
        for name, planted, k in PLANTS:
            assert planted != src, name
            open(path, "w").write(planted)
            rc, out = remote(k); print(f"== {name}\n  planted, -k {k}: exit {rc}"); print("\n".join("    " + l for l in out))
            open(path, "w").write(src)
    finally:
        shutil.move(keep, path)
    rc, out = remote("am15"); print(f"== restored, -k am15: exit {rc}"); print("\n".join(out))
