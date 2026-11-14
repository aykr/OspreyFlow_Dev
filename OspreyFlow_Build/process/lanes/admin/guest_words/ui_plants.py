"""The Guests words' plants (rule 15): each planted alone in People.tsx, PeopleEntraAdministrator.test.tsx run, and
the tree restored from git. A plant counts as red only when the tests that fail are exactly the ones it must fail,
so a plant that breaks the render, or any other test, counts as missed.

Run from the repository root: python OspreyFlow_Build/process/lanes/admin/guest_words/ui_plants.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
WS = ROOT / "OspreyFlow_Core/apps/workspace"
PEOPLE = "src/admin/sections/People.tsx"

PLANTS = [
    ("the verb by the count alone, as first built (handling codes alone read 'is')",
     "  return fields.length > 1 || fields[0] === \"handling_codes\";", "  return fields.length > 1;",
     {"with handling_codes set here", "says People's own words in the same order and number, whatever order the Conduit serves"}),
    ("the old token clause kept beside the new one",
     '    ...(token.length ? [`${here.length ? "their" : "the same"} ${fieldList(token)} from their token`] : []),',
     '    ...(token.length ? [`${here.length ? "their" : "the same"} ${fieldList(token)} from their token`] : []),\n'
     '    ...(here.length ? ["the same clearance, unit and handling codes from their token"] : []),',
     {"with clearance set here", "with org_unit set here", "with handling_codes set here", "with clearance, org_unit set here",
      "with clearance, handling_codes set here", "with org_unit, handling_codes set here",
      "with clearance, org_unit, handling_codes set here"}),
    ("the values listed in the order the Conduit serves (sorted)",
     "  const ws = EVERY_FIELD.filter((f) => fields.includes(f)).map((f) => FIELD_WORDS[f]);",
     "  const ws = fields.map((f) => FIELD_WORDS[f]);",
     {"says People's own words in the same order and number, whatever order the Conduit serves"}),
]


def main() -> int:
    if subprocess.run(["git", "diff", "--quiet", "--", f"OspreyFlow_Core/apps/workspace/{PEOPLE}"], cwd=ROOT).returncode:
        sys.exit(f"{PEOPLE} has changes: commit them first, since each plant is restored from git")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"# Guests words plants at {head}")
    missed = 0
    for name, old, new, must in PLANTS:
        path = WS / PEOPLE
        s = path.read_text()
        assert s.count(old) == 1, name
        path.write_text(s.replace(old, new))
        try:
            out = subprocess.run(["npx", "vitest", "run", "src/admin/PeopleEntraAdministrator.test.tsx"],
                                 cwd=WS, capture_output=True, text=True).stdout
        finally:
            subprocess.run(["git", "checkout", "--", PEOPLE], cwd=WS, check=True)
        failed = {m.strip() for m in re.findall(r"^\s+× (.*?)(?: \d+ms)?$", out, re.M)}
        red = failed == must
        missed += not red
        print(f"== {name}: {'RED, exactly the tests it must fail' if red else 'MISSED'}")
        print(f"   failed: {sorted(failed)}")
        if not red:
            print(f"   must fail: {sorted(must)}")
    print(f"plants: {len(PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
