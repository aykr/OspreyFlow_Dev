"""v052-fixes (ADR-145 Amendment 14): the browser (Playwright keyboard) reds, each a plant at the real call site.

Run from the worktree root on a clean tree at the commit under test:
    python3 OspreyFlow_Build/process/lanes/case/gates/v052_fixes_browser_reds.py > OspreyFlow_Build/process/lanes/case/gates/v052-fixes-browser-reds.log

Each plant replaces one exact string in one file (refused if the string is not there exactly once), runs the
named Playwright keyboard file (the lane's slot 2, OSPREY_PORTS_SLOT=2) filtered to the named test, records the result, and restores the file with
`git checkout -- <file>`. A plant whose test stays green is a failure of this record.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
WS = ROOT / "OspreyFlow_Core/apps/workspace"

PLANTS = [
    ("the views' rows as on main (summary list, three GOV.UK buttons): red under GOV.UK",
     [("src/views/ViewsPanel.tsx", 'const action = govuk ? "govuk-link case-views__link" : "btn btn--quiet case-views__button";',
       'const action = govuk ? "govuk-button govuk-button--secondary case-views__button" : "btn btn--quiet case-views__button";'),
      ("src/views/views.css", ".case-views--govuk .govuk-summary-list .govuk-summary-list__row {", ".case-views--govuk .not-the-row {")],
     "keyboard/views.spec.ts", "in the Cases drawer each view's name, tag and actions fit"),
    ("the drawer at the stylesheet's top 0 (main's)",
     [("src/design/primitives/Drawer.tsx", "style={top === null ? undefined : { top }}", "style={undefined}")],
     "keyboard/shell.spec.ts", "an open drawer starts under the top bar and the context row"),
    ("the drawer under the top bar alone, over the context row's cross-link (7b1fbca's)",
     [("src/design/primitives/Drawer.tsx", 'const CHROME_ABOVE = ".top-bar, .context-banner, .context-banner--govuk";', 'const CHROME_ABOVE = ".top-bar";')],
     "keyboard/shell.spec.ts", "an open drawer starts under the top bar and the context row"),
    ("the drawer measured once, never on resize",
     [("src/design/primitives/Drawer.tsx", '    window.addEventListener("resize", fit);\n', ""),
      ("src/design/primitives/Drawer.tsx", "    const observer = typeof ResizeObserver !== \"undefined\" ? new ResizeObserver(fit) : null;", "    const observer = null as ResizeObserver | null;")],
     "keyboard/shell.spec.ts", "an open drawer starts under the top bar and the context row"),
    ("Reports not in the one view switch (main's switch)",
     [("src/shell/railLayout.ts", 'export const VIEW_SWITCH = ["graph", "map", "boards", "dashboards"] as const;', 'export const VIEW_SWITCH = ["graph", "map", "boards"] as const;')],
     "keyboard/shell.spec.ts", "exactly one view is current"),
    ("a drawer that leaves focus where it was on closing (main's)",
     [("src/design/primitives/Drawer.tsx", "      if (opener?.isConnected && lost) opener.focus();", "")],
     "keyboard/shell.spec.ts", "each rail panel is opened and closed by keyboard"),
    ("the case line without Views in this case",
     [("src/shell/ContextBanner.tsx", "      {place === \"glass\" && caseSwitcher && (\n", "      {place === \"glass\" && caseSwitcher && false && (\n")],
     "keyboard/shell.spec.ts", "the case line's Views in this case opens the Cases panel"),
    ("Build a report not drawn beside the switch (TopBar ignoring besideViews)",
     [("src/shell/TopBar.tsx", "      {besideViews}\n", "")],
     "keyboard/shell.spec.ts", "Build a report follows Reports by keyboard"),

]


def main() -> int:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    if subprocess.run(["git", "status", "--porcelain", "--", str(WS)], capture_output=True, text=True, cwd=ROOT).stdout.strip():
        print("refused: the workspace has uncommitted changes; plants restore with git checkout")
        return 2
    print(f"# v052-fixes browser reds at {head}; each plant restored with `git checkout -- <file>`")
    stayed_green = 0
    # Optional plant numbers as arguments run those alone (a later addition, without rerunning the rest).
    only = {int(a) for a in sys.argv[1:]}
    for n, (what, edits, test_file, name) in enumerate(PLANTS, 1):
        if only and n not in only:
            continue
        bad = [(p, (WS / p).read_text().count(o)) for p, o, _ in edits if (WS / p).read_text().count(o) != 1]
        if bad:
            print(f"## {n}. {what}\nrefused: a planted string is not there exactly once: {bad}")
            stayed_green += 1
            continue
        for p, o, nw in edits:
            (WS / p).write_text((WS / p).read_text().replace(o, nw))
        path = ", ".join(sorted({p for p, _, _ in edits}))
        try:
            # -g is a regular expression: the name is escaped, so parentheses in a name match themselves.
            run = subprocess.run(["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts", test_file, "-g", re.escape(name)],
                                 capture_output=True, text=True, cwd=WS, env={**os.environ, "OSPREY_PORTS_SLOT": "2"})
        finally:
            subprocess.run(["git", "checkout", "--", *sorted({str(WS / p) for p, _, _ in edits})], check=True, cwd=ROOT)
        out = run.stdout + run.stderr
        lines = [l for l in out.splitlines() if any(k in l for k in ("✘", "✓", "Error:", "Expected", "Received", " passed", " failed"))]
        print(f"## {n}. {what}\nplant in {path}; OSPREY_PORTS_SLOT=2 npx playwright test --config keyboard/playwright.config.ts {test_file} -g {name!r}; exit {run.returncode}")
        print("\n".join(lines[:24]))
        if run.returncode == 0:
            stayed_green += 1
            print("STAYED GREEN")
        elif not re.search(r"\d+ failed", out):
            stayed_green += 1
            print("NO TEST FAILED (the run failed otherwise): not a red")
    ran = len(only) if only else len(PLANTS)
    print(f"# {ran - stayed_green} of {ran} red")
    return 1 if stayed_green else 0


if __name__ == "__main__":
    sys.exit(main())
