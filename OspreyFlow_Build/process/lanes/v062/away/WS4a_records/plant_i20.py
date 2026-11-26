"""WS4a: each planted fault in same_drawing_versions_check.mjs, at its own branch, and which tests it turns red."""
import subprocess, sys, pathlib
REPO = pathlib.Path.home() / "away-ws4a"
SCRIPT = REPO / "OspreyFlow_Core/scripts/same_drawing_versions_check.mjs"
PLANTS = [
    ("the window never consulted", "    if (!entry) failures.push(", "    if (false) failures.push("),
    ("a link not followed", "  if (entry?.link) {", "  if (false) {"),
    ("no release refusal", "  if (release && window.entries.length) {", "  if (false) {"),
    ("a nested duplicate allowed", "      if (versions.size > 1) {", "      if (false) {"),
    ("any day accepted", "  if (!m) return false;", "  return true;"),
    ("a stale entry allowed", "    if (!differing.has(entry.package)) {", "    if (false) {"),
    ("devDependencies of a front end unread", "      ...(workspace ? entry.devDependencies : {}),", "      ...{},"),
]
original = SCRIPT.read_text()
out = []
try:
    for name, old, new in PLANTS:
        assert original.count(old) == 1, name
        SCRIPT.write_text(original.replace(old, new))
        p = subprocess.run(["bash", str(pathlib.Path.home() / "osprey-d246/d246_ns.sh"), ".venv/bin/python", "-m", "pytest",
                            "-c", "../OspreyFlow_Build/pytest.ini", "../OspreyFlow_Build/tests/glass_trees/test_same_drawing_versions.py",
                            "-q", "-p", "no:cacheprovider", "-rf"], env={"REPO": str(REPO), "PATH": "/usr/bin:/bin", "HOME": str(pathlib.Path.home())},
                           capture_output=True, text=True)
        failed = [l.split("::")[1].split(" ")[0] for l in p.stdout.splitlines() if l.startswith("FAILED")]
        summary = [l for l in p.stdout.splitlines() if " passed" in l or " failed" in l][-1:]
        out.append(f"PLANT {name}: {summary} red: {failed}")
        print(out[-1], flush=True)
finally:
    SCRIPT.write_text(original)
