"""The GOV.UK scroll and type step's plants (rule 15). Each is planted alone, the step's two specs run, and the files
restored from git. A plant counts as red only when every case it must fail fails and no other does.

Run from the repository root: python OspreyFlow_Build/process/lanes/admin/govuk_scroll/plants.py
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
WS = ROOT / "OspreyFlow_Core/apps/workspace"
FRAME = "OspreyFlow_Core/apps/workspace/src/brand/BrandFrame.tsx"
HOLD = "OspreyFlow_Core/apps/workspace/src/brand/containInnerScroll.ts"
PRIMS = "OspreyFlow_Core/apps/workspace/src/design/primitives.css"
ADMIN = "OspreyFlow_Core/apps/workspace/src/admin/admin.css"
SYSTEM = "OspreyFlow_Core/apps/workspace/src/admin/sections/System.tsx"

#: (name, [(file, site, replacement)], the assertion messages that must fail, and no other assertion)
PLANTS = [
    ("the rule never installed (main's shape)",
     [(FRAME, '(appearance.brand === "govuk" ? containInnerScroll() : undefined)', "(undefined)")],
     ["the page did not move"]),
    ("a box at its end left to move the page", [(HOLD, "  return inside; //", "  return false && inside; //")],
     ["the page did not move"]),
    ("every wheel inside a box held, wherever the box stands", [(HOLD, "    if (further) return false;", "    if (further) inside = true;")],
     ["itself scrolled to its end", "the drawer scrolled", "the list scrolled to its end"]),
    ("overscroll-behavior on every box under GOV.UK (the first fix's shape: a sideways table swallows a vertical wheel)",
     [(PRIMS, '@import "./panelType.css";\n', '@import "./panelType.css";\n[data-brand="govuk"] body * { overscroll-behavior: contain; }\n')],
     ["itself scrolled to its end", "the drawer scrolled", "then the drawer scrolled"]),
    ("Admin's place left a scroll box under GOV.UK (the side list then sticks to it, not to the page)",
     [(ADMIN, '[data-brand="govuk"] #main-content .admin-place { flex: none; overflow-y: visible; }\n', "")],
     ["the side list stays in view"]),
    ("Admin's one-scroller rule reaching the standard look",
     [(ADMIN, '[data-brand="govuk"] #main-content .admin-place { flex: none; overflow-y: visible; }',
       '#main-content .admin-place { flex: none; overflow-y: visible; }'),
      (ADMIN, '[data-brand="govuk"] #main-content :has(> .admin-place)', '#main-content :has(> .admin-place)')],
     ["the one scroller"]),
    ("App's root left at the window's height under GOV.UK (Admin drawn over the footer)",
     [(ADMIN, '[data-brand="govuk"] #main-content :has(> .admin-place) { height: auto !important; min-height: var(--workspace-height, 100vh); }\n', "")],
     ["the footer follows Admin's place"]),
    ("the side list not kept in view",
     [(ADMIN, '  [data-brand="govuk"] #main-content .admin-place .admin-nav { position: sticky; top: 0; }\n', "")],
     ["the side list stays in view"]),
    ("a part's name back in mono", [(SYSTEM, '<span className="admin-system__name">{c.name}</span>', '<span className="value">{c.name}</span>')],
     ["the parts' names in the page's face"]),
    ("the version back in mono", [(SYSTEM, '<p className="admin-system__version" style', '<p className="value" style')],
     ["the version in the page's face"]),
    ("the marking ceiling back in mono", [(SYSTEM, '<p className="admin-system__marking" style', '<p className="value" style')],
     ["the marking ceiling in the page's face"]),
    ("the converted views back in mono", [(SYSTEM, '<p className="admin-system__converted" style', '<p className="value" style')],
     ["the converted views in the page's face"]),
    ("a model's id back as main drew it (the browser's monospace, not the token)",
     [(SYSTEM, '<code className="identifier">{m.model}</code>', "<code>{m.model}</code>")],
     ["a model's id in mono, a value to copy"]),
]


def main() -> int:
    if subprocess.run(["git", "diff", "--quiet"], cwd=ROOT).returncode:
        sys.exit("the tree has changes: commit them first, since each plant is restored from git")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"# GOV.UK scroll and type plants at {head}")
    missed = 0
    for name, sites, must in PLANTS:
        for path, old, new in sites:
            text = (ROOT / path).read_text(encoding="utf-8")
            assert text.count(old) == 1, f"{name}: {old!r} is not there exactly once"
            (ROOT / path).write_text(text.replace(old, new), encoding="utf-8")
        try:
            out = subprocess.run(["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts",
                                  "frame-scroll.spec.ts", "admin-frame.spec.ts", "--reporter=line"], cwd=WS,
                                 capture_output=True, text=True, env={**os.environ, "OSPREY_PORTS_SLOT": "1"}).stdout
        finally:
            subprocess.run(["git", "checkout", "--", *{p for p, _, _ in sites}], cwd=ROOT, check=True)
        failed = re.findall(r"^\s+\d+\) \S+ › (.+?)\s*$", out, re.M)
        said = re.findall(r"^\s+Error: (.+?)\n", out, re.M)
        if not failed and "passed" not in out:
            sys.exit(f"{name}: nothing ran:\n{out[-1500:]}")
        # Each failure is one of the assertions the plant must fail, by its message, and each of those failed.
        missing = [m for m in must if not any(m in e for e in said)]
        stray = [e for e in said if not any(m in e for m in must)]
        red = bool(failed) and not missing and not stray
        missed += not red
        print(f"== {name}: {'RED where it must be' if red else 'MISSED'}; failed {len(failed)}: {said}"
              + (f"; not failed: {missing}" if missing else ""))
    print(f"plants: {len(PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
