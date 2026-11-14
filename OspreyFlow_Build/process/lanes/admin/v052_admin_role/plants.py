"""Route A2's plants (rule 15). Each is planted alone, the test it names run, and the file restored from git. A plant
counts as red only when the named test fails and every other test of its file passes, so a plant that breaks the
file some other way counts as missed.

Run from the repository root: python OspreyFlow_Build/process/lanes/admin/v052_admin_role/plants.py
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
PEOPLE = "OspreyFlow_Core/apps/workspace/src/admin/sections/People.tsx"
APP = "OspreyFlow_Core/services/api/app.py"
VITEST = "src/admin/PeopleAdminRole.test.tsx"
ENTRA = "tests/services/api/test_entra_people.py"
LIST = "tests/test_admin_giver_rights.py"

#: (name, file, site, replacement, how to run, the test names that must fail, and no others)
PLANTS = [
    ("the Glass offers every role (no giver rule)", PEOPLE,
     "  if (!ctx.giver) return [];", "  return [];", "vitest",
     ["a people manager alone is not offered Admin", "each administration right the giver lacks is named"]),
    ("a role the person holds is withheld too (taking it away refused)", PEOPLE,
     "const notOffered = (role: string) => !(person.roles ?? []).includes(role) && withheldRights(role, ctx).length > 0;",
     "const notOffered = (role: string) => withheldRights(role, ctx).length > 0;", "vitest",
     ["a person who already holds Admin keeps the box offered", "a people manager alone is not offered Admin"]),
    ("the words name the first right alone", PEOPLE,
     "it carries ${listed(rights.map(rightName))}, which", "it carries ${rightName(rights[0])}, which", "vitest",
     ["a people manager alone is not offered Admin"]),
    ("the invite form offers every role", PEOPLE,
     "                disabled={withheldRights(role.id, ctx).length > 0}\n", "", "vitest",
     ["a people manager alone is not offered Admin"]),
    ("the giver's rights never reach People", "OspreyFlow_Core/apps/workspace/src/admin/AdminPlace.tsx",
     "people: (api, rights) => <People api={api} rights={rights} />", "people: (api) => <People api={api} />", "vitest",
     ["a people manager alone is not offered Admin", "each administration right the giver lacks is named"]),
    ("the Conduit's roles route without the giver rule", APP,
     "            _may_give(principal, body.roles, before.roles, current)\n", "", "pytest-entra",
     ["admin-role", "single-right"]),
    ("the Glass's list of administration rights short of one", PEOPLE,
     '"manage_geospatial", "read_audit", "read_export_ledger", "manage_models",',
     '"manage_geospatial", "read_export_ledger", "manage_models",', "pytest-list",
     ["test_the_glass_withholds_by_the_conduit_s_administration_rights"]),
]


def run(how: str) -> str:
    if how == "vitest":
        return subprocess.run(["npx", "vitest", "run", VITEST], cwd=ROOT / "OspreyFlow_Core/apps/workspace",
                              capture_output=True, text=True).stdout
    env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"} | {
        "PYTHONPYCACHEPREFIX": tempfile.mkdtemp(), "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992",
        "POSTGRES_PASSWORD": "throwaway", "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
    target = [ENTRA, "-k", "people_manager_alone"] if how == "pytest-entra" else [LIST]
    return subprocess.run([os.environ.get("OSPREY_PY", "../OspreyFlow_Core/.venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "-rf", "--tb=no", *target], cwd=ROOT / "OspreyFlow_Build", capture_output=True, text=True,
                          env=env).stdout


def failures(out: str, how: str) -> list[str]:
    if how == "vitest":
        return re.findall(r"^\s+× (.+?) \d+ms$", out, re.M)
    return re.findall(r"^FAILED (\S+)", out, re.M)


def main() -> int:
    if subprocess.run(["git", "diff", "--quiet"], cwd=ROOT).returncode:
        sys.exit("the tree has changes: commit them first, since each plant is restored from git")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"# route A2 plants at {head}")
    missed = 0
    for name, path, site, new, how, must in PLANTS:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert text.count(site) == 1, f"{name}: the site is not there exactly once"
        (ROOT / path).write_text(text.replace(site, new), encoding="utf-8")
        try:
            out = run(how)
        finally:
            subprocess.run(["git", "checkout", "--", path], cwd=ROOT, check=True)
        failed = failures(out, how)
        if not failed and not re.search(r"passed", out):
            sys.exit(f"{name}: nothing ran:\n{out[-1500:]}")
        hit = all(any(m in f for f in failed) for m in must)
        stray = [f for f in failed if not any(m in f for m in must)]
        red = hit and not stray
        missed += not red
        print(f"== {name}: {'RED where it must be' if red else 'MISSED'}; failed: {failed}")
    print(f"plants: {len(PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
