"""The GOV.UK panels step's plants (rule 15). Each is planted alone in the CSS, the measuring spec run, and the files
restored from git. A plant counts as red only when every case it must fail fails and no other does.

Run from the repository root: python OspreyFlow_Build/process/lanes/admin/govuk_panels/plants.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
WS = ROOT / "OspreyFlow_Core/apps/workspace"
TYPE = "OspreyFlow_Core/apps/workspace/src/design/panelType.css"
PRIMS = "OspreyFlow_Core/apps/workspace/src/design/primitives.css"
SAVED, STRIP, MORE, NARROW, CASE = ("the saved views panel", "the open view's strip", "the top bar's More menu in",
                                    "the top bar's More menu, folded narrow", "the case switcher's menu")
LOOK = {"dark": "dark look", "light": "light look", "govuk": "govuk look"}

#: (name, [(file, site, replacement)], the cases that must fail: (panel, look))
PLANTS = [
    ("the panel type sheet not loaded", [(PRIMS, '@import "./panelType.css";\n', "")],
     [(SAVED, "dark"), (SAVED, "light"), (SAVED, "govuk"), (STRIP, "govuk")]),
    ("GOV.UK's tags left at the Design System's size", [(TYPE, ") .govuk-tag {", ") .govuk-tag-not-this {")],
     [(SAVED, "govuk"), (STRIP, "govuk")]),
    ("a panel's bare heading left at the browser's size", [(TYPE, ":where(h2, h3, h4, h5, h6):where(.label) {", ":where(h6.not-this) {")],
     [(SAVED, "dark"), (SAVED, "light")]),
    ("GOV.UK's summary list left at the Design System's size",
     [(TYPE, ".govuk-summary-list, .govuk-summary-list__key, .govuk-summary-list__value, .govuk-summary-list__actions,", "")],
     [(SAVED, "govuk")]),
    ("a menu's items drawn off the scale", [(TYPE, "/* GOV.UK Frontend's type classes, on the page's scale",
                                            ".menu-panel .menu-panel__item { font-size: var(--fs-16); }\n/* GOV.UK Frontend's type classes, on the page's scale")],
     [(MORE, "dark"), (MORE, "light"), (MORE, "govuk"), (NARROW, "dark"), (NARROW, "light"), (NARROW, "govuk"),
      (CASE, "dark"), (CASE, "light"), (CASE, "govuk")]),
    ("GOV.UK's links left at the Design System's size", [(TYPE, ".govuk-link, .govuk-back-link, ", ".govuk-back-link, ")],
     [(SAVED, "govuk")]),
]


def failed_titles(out: str) -> list[str]:
    return re.findall(r"^\s+\d+\) \S+ › (.+?) is on the page's type scale", out, re.M)


def main() -> int:
    if subprocess.run(["git", "diff", "--quiet"], cwd=ROOT).returncode:
        sys.exit("the tree has changes: commit them first, since each plant is restored from git")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"# GOV.UK panels plants at {head}")
    missed = 0
    for name, sites, must in PLANTS:
        for path, old, new in sites:
            text = (ROOT / path).read_text(encoding="utf-8")
            assert text.count(old) == 1, f"{name}: {old!r} is not there exactly once"
            (ROOT / path).write_text(text.replace(old, new), encoding="utf-8")
        try:
            out = subprocess.run(["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts",
                                  "glass-panels-look.spec.ts", "--reporter=line"], cwd=WS, capture_output=True, text=True,
                                 env={**__import__("os").environ, "OSPREY_PORTS_SLOT": "1"}).stdout
        finally:
            subprocess.run(["git", "checkout", "--", *{p for p, _, _ in sites}], cwd=ROOT, check=True)
        failed = failed_titles(out)
        if not failed and "passed" not in out:
            sys.exit(f"{name}: nothing ran:\n{out[-1500:]}")
        def hit(panel: str, look: str) -> bool:
            return any(f.startswith(panel) and f.endswith(f"in the {LOOK[look]}") for f in failed)
        missing = [m for m in must if not hit(*m)]
        stray = [f for f in failed if not any(f.startswith(p) and f.endswith(f"in the {LOOK[lk]}") for p, lk in must)]
        red = not missing and not stray
        missed += not red
        print(f"== {name}: {'RED where it must be' if red else 'MISSED'}; failed: {failed}"
              + (f"; not failed: {missing}" if missing else ""))
    print(f"plants: {len(PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
