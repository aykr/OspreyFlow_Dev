"""v0.6.0 #6's gate, shown to fail for each reason it claims (rule 15; the lane review of 15 November 2026). Each plant
goes alone in `keyboard/govuk-type-pass.spec.ts`, a slice of the pass runs, and the file is restored from git. A plant
counts as red only when the run fails where it must and passes elsewhere.

Run from the repository root, on a local Playwright slot: OSPREY_PORTS_SLOT=<n> python OspreyFlow_Build/process/lanes/admin/v060_i6/plants_gate.py
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
WS = ROOT / "OspreyFlow_Core/apps/workspace"
SPEC = "OspreyFlow_Core/apps/workspace/keyboard/govuk-type-pass.spec.ts"
GUARD = "the pass found every-harness's pages and their states"
PAGE = "alert-figures-harness.html under GOV.UK"   # one page, its base state

PLANTS = [
    ("a state left out for its characters (the first draft's filter)",
     'return new Function(`return (${LITERAL});`)() as Record<string, string[]>;',
     'const all = new Function(`return (${LITERAL});`)() as Record<string, string[]>;\n'
     '  return Object.fromEntries(Object.entries(all).map(([k, v]) => [k, v.filter((q) => /^[\\w=&%,.:#-]*$/.test(q))]));',
     GUARD),
    ("the brand never applied",
     'const query = [state, STANDARD ? "" : "brand=govuk"].filter(Boolean).join("&");',
     'const query = [state].filter(Boolean).join("&");',
     PAGE),
    ("nothing measured, so nothing found",
     "          measured += 1;\n          if (face === mono",
     "          if (face === mono",
     PAGE),
]


def run(grep: str) -> tuple[int, str]:
    done = subprocess.run(["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts",
                           "keyboard/govuk-type-pass.spec.ts", "-g", grep, "--reporter=line"],
                          cwd=WS, capture_output=True, text=True, env=os.environ.copy())
    return done.returncode, done.stdout + done.stderr


def main() -> int:
    if not os.environ.get("OSPREY_PORTS_SLOT"):
        sys.exit("set OSPREY_PORTS_SLOT to the local Playwright slot the orchestrator gave")
    if subprocess.run(["git", "diff", "--quiet"], cwd=ROOT).returncode:
        sys.exit("the tree has changes: commit them first, since each plant is restored from git")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"# v0.6.0 #6 gate plants at {head}")
    missed = 0
    for grep in (GUARD, PAGE):
        code, out = run(re.escape(grep))
        ok = code == 0 and " passed" in out and " failed" not in out
        print(f"== unplanted, {grep!r}: {'passes' if ok else 'FAILS UNPLANTED'}")
        missed += not ok
    for name, old, new, grep in PLANTS:
        text = (ROOT / SPEC).read_text(encoding="utf-8")
        assert text.count(old) == 1, f"{name}: {old!r} is not there exactly once"
        (ROOT / SPEC).write_text(text.replace(old, new), encoding="utf-8")
        try:
            code, out = run(re.escape(grep))
        finally:
            subprocess.run(["git", "checkout", "--", SPEC], cwd=ROOT, check=True)
        why = re.findall(r"^\s+(Error: .*|.*(?:Expected|Received).*)$", out, re.M)[:3]
        red = code != 0 and " failed" in out
        missed += not red
        print(f"== {name}: {'RED' if red else 'MISSED'} on {grep!r}; {why}")
    print(f"plants: {len(PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
