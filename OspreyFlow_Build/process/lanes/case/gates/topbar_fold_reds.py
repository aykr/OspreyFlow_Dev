"""The top bar's fold (the owner's ruling of 14 November 2026, spec 02 §2.0, `BAR_FOLD_ORDER`): each test's red, a
plant at the real call site.

Run on Linux, since the widths are Linux's: on the server, through `stack_lease.sh offline case`, from the worktree
at the commit under test with nothing else changed, the head passed in from the local checkout's `git rev-parse`:
    head=$(git rev-parse --short HEAD); OspreyFlow_Build/scripts/stack_lease.sh offline case -- sh -c \
      "PLANT_HEAD=$head python3 OspreyFlow_Build/process/lanes/case/gates/topbar_fold_reds.py" > .../topbar-fold-reds.$head.log

Each plant replaces exact strings in files (refused if one is not there exactly once), runs the named test (vitest, or
Playwright on the lane's slot 2), records the result and writes each file's own text back. Never `git checkout`: the
server's copy is rsynced without its `.git`, whose HEAD there is stale (found in this record's first run, 14 November
2026, which restored an old TopBar.tsx after the first plant and so measured every later plant against no fold at
all). A plant whose test stays green, or fails before the assertion it is named for, is a failure of this record.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
BUILD = ROOT / "OspreyFlow_Build"
WS = CORE / "apps/workspace"
TOPBAR = "OspreyFlow_Core/apps/workspace/src/shell/TopBar.tsx"
PLACES = "OspreyFlow_Core/apps/workspace/src/shell/PlaceSwitcher.tsx"
CSS = "OspreyFlow_Core/apps/workspace/src/design/primitives.css"
LAYOUT = "OspreyFlow_Core/apps/workspace/src/shell/railLayout.ts"
CLOSED = {}

# (what, [(file from the root, old, new)], runner, test file, test name)
PLANTS = [
    ("no fold: the bar keeps every item and wraps",
     [(TOPBAR, "  const count = fold.key === key ? fold.count : 0;\n", "  const count = 0;\n")],
     "browser", "keyboard/top-bar.spec.ts", "ospreyflow dark, every place and Build a report: at 1024 wide the bar folds and stays one line, 44 high"),
    ("no fold, with a wider font",
     [(TOPBAR, "  const count = fold.key === key ? fold.count : 0;\n", "  const count = 0;\n")],
     "browser", "keyboard/top-bar.spec.ts", "govuk light, the four views: at 1024 wide with a wider font the bar folds further and stays one line"),
    ("a folded view left out of More views",
     [(TOPBAR, "  const menuViews = [...views.filter((view) => folded.has(view.id)), ...moreViews];\n", "  const menuViews = [...moreViews];\n")],
     "browser", "keyboard/shell.spec.ts", "ospreyflow: at 1024 wide every folded view is chosen under More views by keyboard"),
    ("a folded Build a report dropped, not put under More views",
     [(TOPBAR, "              {linkFolded && (\n", "              {false && linkFolded && (\n")],
     "browser", "keyboard/shell.spec.ts", "govuk: at 1024 wide every folded view is chosen under More views by keyboard"),
    ("the places never folded into one menu",
     [(PLACES, "  if (folded && !govuk && places.length > 1) {\n", "  if (folded && !govuk && places.length > 99) {\n")],
     "browser", "keyboard/shell.spec.ts", "at 1024 wide the folded places are one menu"),
    ("a wider bar never unfolding (a narrower one still folds)",
     [(TOPBAR, "        flushSync(() => setFold((current) => ({ ...current, count: 0, pass: current.pass + 1 })));\n      } else if (barWraps(element)) {\n",
       "        if (barWraps(element)) flushSync(() => setFold((current) => ({ ...current, count: Math.min(current.count + 1, stepCount.current) })));\n      } else if (barWraps(element)) {\n")],
     "browser", "keyboard/top-bar.spec.ts", "at 1440 wide the four views' bar folds nothing"),
    ("the two-line padding by breakpoint again (main's), on a folded one-line bar",
     [(CSS, ".top-bar--wrapped { padding-top: var(--sp-6); padding-bottom: var(--sp-6); }",
       "@media (max-width: 1099px) { .top-bar { padding-top: var(--sp-6); padding-bottom: var(--sp-6); } }")],
     "browser", "keyboard/top-bar.spec.ts", "ospreyflow light, the four views: at 1024 wide the bar folds and stays one line, 44 high"),
    ("the two lines never given their room once everything has folded",
     [(TOPBAR, "    else setWrapped(wraps);\n", "    else setWrapped(false);\n")],
     "browser", "keyboard/top-bar.spec.ts", "at 700 wide, with everything folded, whole items wrap to two lines"),
    ("Graph first in the fold order",
     [(LAYOUT, 'export const BAR_FOLD_ORDER = ["build-a-report", "dashboards", "boards", "map", "dossier", "places", "graph"] as const;',
       'export const BAR_FOLD_ORDER = ["graph", "build-a-report", "dashboards", "boards", "map", "dossier", "places"] as const;')],
     "jsdom", "src/shell/topBarFold.test.tsx", "folds Build a report, then Reports"),
]


def main() -> int:
    head = os.environ.get("PLANT_HEAD", "(no PLANT_HEAD given)")
    print(f"# top-bar fold reds at {head} (the local checkout's, passed in); each plant restored from the file's own text")
    stayed = 0
    for n, (what, edits, runner, test_file, name) in enumerate(PLANTS, 1):
        bad = [(f, (ROOT / f).read_text().count(o)) for f, o, _ in edits if (ROOT / f).read_text().count(o) != 1]
        if bad:
            print(f"## {n}. {what}\nrefused: a planted string is not there exactly once: {bad}")
            stayed += 1
            continue
        saved = {f: (ROOT / f).read_text() for f, _, _ in edits}
        for f, o, nw in edits:
            (ROOT / f).write_text((ROOT / f).read_text().replace(o, nw))
        try:
            if runner == "pytest":
                cmd = [str(CORE / ".venv/bin/python"), "-m", "pytest", "-p", "no:cacheprovider", "-q", f"{test_file}::{name}"]
                env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"} | CLOSED
                cwd = BUILD
            elif runner == "jsdom":
                cmd, env, cwd = ["npx", "vitest", "run", test_file, "-t", name], os.environ, WS
            else:
                cmd = ["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts", test_file, "-g", re.escape(name), "--workers=1"]
                env, cwd = {**os.environ, "OSPREY_PORTS_SLOT": "2"}, WS
            run = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env)
        finally:
            for f, text in saved.items():
                (ROOT / f).write_text(text)
        out = run.stdout + run.stderr
        lines = [l for l in out.splitlines() if any(k in l for k in ("×", "✘", "AssertionError", "assert ", "Error:", "FAILED", "Expected", "Received", " passed", " failed"))]
        print(f"## {n}. {what}\nplant in {', '.join(sorted({f for f, _, _ in edits}))}; {' '.join(cmd[-4:])}; exit {run.returncode}")
        print("\n".join(lines[:12]))
        if run.returncode == 0:
            stayed += 1
            print("STAYED GREEN")
        elif not re.search(r"\d+ failed|FAILED|×|✘", out):
            stayed += 1
            print("NO TEST FAILED (the run failed otherwise): not a red")
    print(f"# {len(PLANTS) - stayed} of {len(PLANTS)} red")
    return 1 if stayed else 0


if __name__ == "__main__":
    sys.exit(main())
