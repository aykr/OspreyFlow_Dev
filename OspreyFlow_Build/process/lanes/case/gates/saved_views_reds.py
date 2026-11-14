"""Saved views and the way back (the owner's exception of 14 November 2026, ADR-145 Amendment 17, ADR-144 Amendment 6):
each test's red, a plant at the real call site.

Run on the server, through `stack_lease.sh offline case`, from the worktree
at the commit under test with nothing else changed, the head passed in from the local checkout's `git rev-parse`:
    head=$(git rev-parse --short HEAD); OspreyFlow_Build/scripts/stack_lease.sh offline case -- sh -c \
      "PLANT_HEAD=$head python3 OspreyFlow_Build/process/lanes/case/gates/saved_views_reds.py" > .../saved-views-reds.$head.log

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
BANNER = "OspreyFlow_Core/apps/workspace/src/views/ViewLensBanner.tsx"
CONTEXT = "OspreyFlow_Core/apps/workspace/src/shell/ContextBanner.tsx"
APPF = "OspreyFlow_Core/apps/workspace/src/App.tsx"
TOPBAR = "OspreyFlow_Core/apps/workspace/src/shell/TopBar.tsx"
WAY = "the saved view opened from the case line takes focus to its strip"
APPVIEWS = "a saved view opened from the case line takes focus to its strip"
CLOSED = {}

# (what, [(file from the root, old, new)], runner, test file, test name)
PLANTS = [
    ("focus left where it was when a saved view opens (not the strip)",
     [(BANNER, "  useEffect(() => strip.current?.focus(), []);\n", "")],
     "browser", "keyboard/views.spec.ts", "ospreyflow dark: a saved view opened from the case line takes focus to its strip"),
    ("Back to the whole case not first in the strip (a control before it)",
     [(BANNER, "      {/* ADR-145 Amendment 17: the way back is the first thing in the strip; under GOV.UK, GOV.UK's back link. */}\n",
       "      <button type=\"button\" className=\"btn\">Share</button>\n")],
     "jsdom", "src/App.views.test.tsx", APPVIEWS),
    ("the case line not naming the open saved view",
     [(CONTEXT, "          {openView && <span className=\"context-banner__open-view\">› Saved view: {openView}</span>}\n", "")],
     "browser", "keyboard/views.spec.ts", "ospreyflow light: a saved view opened from the case line takes focus to its strip"),
    ("the back link not returning focus to Saved views",
     [(APPF, "    requestAnimationFrame(() => focusSavedViewsButton());\n", "    requestAnimationFrame(() => undefined);\n")],
     "jsdom", "src/App.views.test.tsx", APPVIEWS),
    ("the GOV.UK look's back link not GOV.UK's",
     [(BANNER, "className={govuk ? \"govuk-back-link view-lens-banner__whole\" : \"view-lens-banner__whole\"}", "className=\"view-lens-banner__whole\"")],
     "browser", "keyboard/views.spec.ts", "govuk light: a saved view opened from the case line takes focus to its strip"),
    ("no whole-case strip with none open",
     [(APPF, "            {view === \"graph\" && !lens && investigationId && <WholeCaseStrip />}\n", "")],
     "jsdom", "src/App.views.test.tsx", APPVIEWS),
    ("Saved views without its count",
     [(CONTEXT, "                {savedViewsLabel(savedViews)}\n", "                {savedViewsLabel(null)}\n")],
     "jsdom", "src/App.views.test.tsx", APPVIEWS),
    ("More without its name (More views' old name back)",
     [(TOPBAR, "          buttonName={moreOpen ? undefined : MORE_NAME}\n          panelLabel={MORE_NAME}", "          panelLabel=\"More views\"")],
     "browser", "keyboard/shell.spec.ts", "each view is chosen by keyboard: Graph, Map, Drawing board and Reports"),
]


def main() -> int:
    head = os.environ.get("PLANT_HEAD", "(no PLANT_HEAD given)")
    print(f"# saved-views reds at {head} (the local checkout's, passed in); each plant restored from the file's own text")
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
