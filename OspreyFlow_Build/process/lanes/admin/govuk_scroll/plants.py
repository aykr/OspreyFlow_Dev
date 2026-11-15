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
PRIMS = "OspreyFlow_Core/apps/workspace/src/design/primitives.css"
FRAME = "OspreyFlow_Core/apps/workspace/src/design/frame.css"
ADMIN = "OspreyFlow_Core/apps/workspace/src/admin/admin.css"
SYSTEM = "OspreyFlow_Core/apps/workspace/src/admin/sections/System.tsx"
DRAWER = "wheeling past a drawer's body's end"
OVERLAY = "wheeling past the empty canvas's start overlay's end"
SCROLL = "Admin in the page's frame in the govuk look"
FACE = [f"Admin › System in the {look} look" for look in ("dark", "light", "govuk")]

#: (name, [(file, site, replacement)], the cases that must fail, by the start of their titles)
PLANTS = [
    ("the inner-scroll sheet not loaded", [(PRIMS, '@import "./frame.css";\n', "")], [DRAWER, OVERLAY]),
    ("inner scrollers left to chain to the page", [(FRAME, "overscroll-behavior: contain;", "overscroll-behavior: auto;")],
     [DRAWER, OVERLAY]),
    ("Admin left scrolling in its own box under GOV.UK",
     [(ADMIN, '[data-brand="govuk"] #main-content .admin-place { flex: none; overflow-y: visible; }\n', "")], [SCROLL]),
    ("App's root left at the window's height under GOV.UK (Admin drawn over the footer)",
     [(ADMIN, '[data-brand="govuk"] #main-content :has(> .admin-place) { height: auto !important; min-height: var(--workspace-height, 100vh); }\n', "")],
     [SCROLL]),
    ("the side list not kept in view", [(ADMIN, "[data-brand=\"govuk\"] #main-content .admin-place .admin-nav { position: sticky; top: 0; }\n", "")], [SCROLL]),
    ("a part's name back in mono", [(SYSTEM, '<span className="admin-system__name">{c.name}</span>', '<span className="value">{c.name}</span>')], FACE),
    ("the version back in mono", [(SYSTEM, '<p className="admin-system__version" style', '<p className="value" style')], FACE),
    ("the marking ceiling back in mono", [(SYSTEM, '<p className="admin-system__marking" style', '<p className="value" style')], FACE),
    ("a model's id no longer marked a value", [(SYSTEM, '<code className="identifier">{m.model}</code>', "<span>{m.model}</span>")], FACE),
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
        if not failed and "passed" not in out:
            sys.exit(f"{name}: nothing ran:\n{out[-1500:]}")
        missing = [m for m in must if not any(f.startswith(m) or m in f for f in failed)]
        stray = [f for f in failed if not any(f.startswith(m) or m in f for m in must)]
        red = not missing and not stray
        missed += not red
        print(f"== {name}: {'RED where it must be' if red else 'MISSED'}; failed: {failed}" + (f"; not failed: {missing}" if missing else ""))
    print(f"plants: {len(PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
