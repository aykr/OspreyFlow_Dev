"""v052-fixes (ADR-145 Amendment 14): the jsdom tests' reds, each a plant at the real call site.

Run from the worktree root on a clean tree at the commit under test:
    python3 OspreyFlow_Build/process/lanes/case/gates/v052_fixes_unit_reds.py > OspreyFlow_Build/process/lanes/case/gates/v052-fixes-unit-reds.log

Each plant replaces one exact string in one file (refused if the string is not there exactly once), runs the
named vitest file filtered to the named test, records the result, and restores the file with
`git checkout -- <file>`. A plant whose test stays green is a failure of this record.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
WS = ROOT / "OspreyFlow_Core/apps/workspace"

PLANTS = [
    # Fix 4, the dataset named once (Amendment 14 decision 4)
    ("the cross-link names the dataset again (main's words)",
     "src/shell/ContextBanner.tsx", 'return { label: "Open this case\'s data in the Ingest Studio ↗", onFollow: go.toStudio };',
     'return { label: `Open ${datasets && datasets.length === 1 ? datasets[0] : "this case\'s data"} in the Ingest Studio ↗`, onFollow: go.toStudio };',
     "src/App.chrome.test.tsx", "names the case's one dataset once"),
    ("the scope badge drawn beside the case in the Glass (main's)",
     "src/App.tsx", 'showScope={!(app === "glass" && caseContext.datasets !== null)}', "showScope={true}",
     "src/App.chrome.test.tsx", "names the case's one dataset once"),
    ("no words for a case reading no dataset (7b1fbca's banner)",
     "src/shell/ContextBanner.tsx", '{datasets.length > 0 ? `reads ${names(datasets)}` : "reads no dataset"}',
     '{datasets.length > 0 ? `reads ${names(datasets)}` : null}',
     "src/App.chrome.test.tsx", "a case that reads no dataset says so once"),
    ("the badge dropped in the Glass whatever the banner says (7b1fbca's)",
     "src/App.tsx", 'showScope={!(app === "glass" && caseContext.datasets !== null)}', 'showScope={app !== "glass"}',
     "src/App.chrome.test.tsx", "cannot be read"),
    ("CaseSwitcher ignores showScope",
     "src/investigation/CaseSwitcher.tsx", "const scope = showScope ? scopeBadge(current?.datasets) : null;", "const scope = scopeBadge(current?.datasets);",
     "src/investigation/CaseSwitcher.test.tsx", "is left out with showScope false"),
    # Fix 2, drawers under the top navigation (Amendment 14 decision 2)
    ("the drawer at the stylesheet's top 0 (main's)",
     "src/design/primitives/Drawer.tsx", "style={top === null ? undefined : { top }}", "style={undefined}",
     "src/design/primitives/Drawer.test.tsx", "opens under the top bar"),
    ("the drawer under the top bar alone, over the context row (7b1fbca's)",
     "src/design/primitives/Drawer.tsx", 'const CHROME_ABOVE = ".top-bar, .context-banner, .context-banner--govuk";', 'const CHROME_ABOVE = ".top-bar";',
     "src/design/primitives/Drawer.test.tsx", "opens under the context row too"),
    ("the drawer measured once, never on resize or scroll",
     "src/design/primitives/Drawer.tsx", '    window.addEventListener("resize", fit);\n    window.addEventListener("scroll", fit, { passive: true });', "",
     "src/design/primitives/Drawer.test.tsx", "is measured again"),
    ("the drawer announced as modal (main's aria-modal)",
     "src/design/primitives/Drawer.tsx", '      aria-label={title}\n', '      aria-label={title}\n      aria-modal="true"\n',
     "src/design/primitives/Drawer.test.tsx", "is not announced as modal"),
    # Fix 1, the views' rows (Amendment 14 decision 1)
    ("the views' actions as full GOV.UK buttons (main's)",
     "src/views/ViewsPanel.tsx", 'const action = govuk ? "govuk-link case-views__link" : "btn btn--quiet case-views__button";',
     'const action = govuk ? "govuk-button govuk-button--secondary case-views__button" : "btn btn--quiet case-views__button";',
     "src/views/ViewsPanel.test.tsx", "is a GOV.UK summary list"),
    # Part B, the owner's navigation decision (Amendment 15)
    ("Reports not in the one view switch (main's switch of Graph and Map)",
     "src/shell/railLayout.ts", 'export const VIEW_SWITCH = ["graph", "map", "boards", "dashboards"] as const;', 'export const VIEW_SWITCH = ["graph", "map", "boards"] as const;',
     "src/App.chrome.test.tsx", "the top bar's one view switch is Graph"),
    ("the strip keeps the Graph note (Amendment 13's)",
     "src/App.tsx", '        onViews={app === "glass" ? () => setCasesOpen("views") : undefined}',
     '        onViews={app === "glass" ? () => setCasesOpen("views") : undefined}\n        note={app === "glass" ? "Graph: the case\'s data. Saved views are under Views or Cases." : undefined}',
     "src/App.chrome.test.tsx", "the strip names no mode and says no mode's note"),
    ("the board without its sketch line",
     "src/boards/BoardsPlace.tsx", '"Drawing board: your sketch; it does not change the case\'s data. Everything drawn', '"Everything drawn',
     "src/App.chrome.test.tsx", "Drawing board is a view"),
    ("a panel's opener pressed (main's rail)",
     "src/shell/railLayout.ts", "return PANEL_OPENERS.includes(id) ? { expanded: state.open.has(id) } : { pressed: state.view === id };",
     "return { pressed: state.view === id || state.open.has(id) };",
     "src/App.chrome.test.tsx", "the rail holds the panel openers alone"),
    ("Explore only opens (main's setExploreOpen(true)): a second press leaves it open",
     "src/App.tsx", "onSelect: () => setExploreOpen((open) => !open)", "onSelect: () => setExploreOpen(true)",
     "src/App.chrome.test.tsx", "Explore opens its panel without changing the view"),
    ("a drawer that leaves focus where it was on closing (main's)",
     "src/design/primitives/Drawer.tsx", "      if (opener?.isConnected && lost) opener.focus();", "",
     "src/App.chrome.test.tsx", "History opens its panel without changing the view"),
    ("no visible word Case before the switcher",
     "src/shell/ContextBanner.tsx", '          <span className="context-banner__label" aria-hidden="true">Case</span>\n', "",
     "src/App.chrome.test.tsx", "the case line: You are in the Glass"),
    ("Views in this case opening the panel without taking it to the views",
     "src/views/ViewsPanel.tsx", "    if (takeFocus) section.current?.focus();", "",
     "src/App.chrome.test.tsx", "Views in this case opens the Cases panel at its views list"),
    ("no All cases in the switcher (its order before Part B is red in v052-navigation-app-reds.log)",
     "src/investigation/CaseSwitcher.tsx", "          {onBrowse && (", "          {false && onBrowse && (",
     "src/App.chrome.test.tsx", "the case switcher's last entry is All cases"),
]


def main() -> int:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    if subprocess.run(["git", "status", "--porcelain", "--", str(WS)], capture_output=True, text=True, cwd=ROOT).stdout.strip():
        print("refused: the workspace has uncommitted changes; plants restore with git checkout")
        return 2
    print(f"# v052-fixes jsdom reds at {head}; each plant restored with `git checkout -- <file>`")
    stayed_green = 0
    for n, (what, path, old, new, test_file, name) in enumerate(PLANTS, 1):
        target = WS / path
        text = target.read_text()
        if text.count(old) != 1:
            print(f"## {n}. {what}\nrefused: the planted string is in {path} {text.count(old)} times, not once")
            stayed_green += 1
            continue
        target.write_text(text.replace(old, new))
        try:
            # vitest's -t is a regular expression: the name is escaped, so "(Alert monitoring)" matches itself.
            run = subprocess.run(["npx", "vitest", "run", test_file, "-t", re.escape(name)], capture_output=True, text=True, cwd=WS)
        finally:
            subprocess.run(["git", "checkout", "--", str(target)], check=True, cwd=ROOT)
        out = run.stdout + run.stderr
        lines = [l for l in out.splitlines() if any(k in l for k in ("×", "AssertionError", "Tests "))]
        print(f"## {n}. {what}\nplant in {path}; npx vitest run {test_file} -t {name!r}; exit {run.returncode}")
        print("\n".join(lines[:6]))
        if run.returncode == 0:
            stayed_green += 1
            print("STAYED GREEN")
        elif not re.search(r"Tests\s+\d+ failed", out):
            stayed_green += 1
            print("NO TEST FAILED (the run failed otherwise): not a red")
    print(f"# {len(PLANTS) - stayed_green} of {len(PLANTS)} red")
    return 1 if stayed_green else 0


if __name__ == "__main__":
    sys.exit(main())
