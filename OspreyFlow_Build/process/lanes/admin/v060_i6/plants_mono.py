"""v0.6.0 #6's mono-words plants (rule 15): each site put back to `.value` (main's shape) alone, the face spec run,
and the file restored from git. A plant counts as red only when the cases it must fail fail, in every look, and no
other.

Run from the repository root: python OspreyFlow_Build/process/lanes/admin/v060_i6/plants_mono.py
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
WS = ROOT / "OspreyFlow_Core/apps/workspace"
A = "OspreyFlow_Core/apps/workspace/src/admin/"
LOOKS = ("dark", "light", "govuk")

PLANTS = [
    ("a role's label", A + "sections/Roles.tsx", '<span className="admin-words">{role.label}</span>', '<span className="value">{role.label}</span>', "Roles"),
    ("a custom role's name", A + "sections/Roles.tsx", '<span className="admin-words">{role.name}</span>', '<span className="value">{role.name}</span>', "Roles"),
    ("a schedule's label", A + "Schedules.tsx", '<span className="admin-words">{s.label}</span>', '<span className="value">{s.label}</span>', "Operations"),
    ("the tips' role labels", A + "tips.tsx", '<dt className="admin-words">{r.label}</dt>', '<dt className="value">{r.label}</dt>', "People and roles"),
    ("'Levels in a case'", A + "tips.tsx", '<dt className="admin-words">Levels in a case</dt>', '<dt className="value">Levels in a case</dt>', "People and roles"),
    ("an arrival's sign-in name", A + "sections/People.tsx", '<span className="admin-words">{them}</span>', '<span className="value">{them}</span>', "People and roles"),
]


def main() -> int:
    if subprocess.run(["git", "diff", "--quiet"], cwd=ROOT).returncode:
        sys.exit("the tree has changes: commit them first, since each plant is restored from git")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"# v0.6.0 #6 mono-words plants at {head}")
    missed = 0
    for name, path, old, new, page in PLANTS:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert text.count(old) == 1, f"{name}: the site is not there exactly once"
        (ROOT / path).write_text(text.replace(old, new), encoding="utf-8")
        try:
            out = subprocess.run(["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts",
                                  "admin-words-face.spec.ts", "--reporter=line"], cwd=WS, capture_output=True, text=True,
                                 env={**os.environ, "OSPREY_PORTS_SLOT": os.environ.get("OSPREY_PORTS_SLOT") or sys.exit("set OSPREY_PORTS_SLOT to your local Playwright slot")}).stdout
        finally:
            subprocess.run(["git", "checkout", "--", path], cwd=ROOT, check=True)
        failed = re.findall(r"^\s+\d+\) \S+ › (.+?) in the (\w+) look", out, re.M)
        if not failed and "passed" not in out:
            sys.exit(f"{name}: nothing ran:\n{out[-1500:]}")
        red = sorted(failed) == sorted((page, look) for look in LOOKS)
        missed += not red
        print(f"== {name}: {'RED where it must be' if red else 'MISSED'}; failed: {failed}")
    print(f"plants: {len(PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
