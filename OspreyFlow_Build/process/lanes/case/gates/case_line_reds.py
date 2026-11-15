"""The case line on one type size, held to one line (the owner's word and ruling, 15 November 2026): each test's red, a
plant at the real call site.

Run on Linux, since the widths are Linux's: on the server, through `stack_lease.sh offline case`, from the worktree
at the commit under test with nothing else changed, the head passed in from the local checkout's `git rev-parse`:
    head=$(git rev-parse --short HEAD); OspreyFlow_Build/scripts/stack_lease.sh offline case -- sh -c \
      "PLANT_HEAD=$head python3 OspreyFlow_Build/process/lanes/case/gates/case_line_reds.py" > .../case-line-reds.$head.log

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
CSS = "OspreyFlow_Core/apps/workspace/src/shell/places.css"
BANNER = "OspreyFlow_Core/apps/workspace/src/shell/ContextBanner.tsx"
SPEC = "keyboard/case-line-type.spec.ts"
CLOSED = {}

# (what, [(file from the root, old, new)], runner, test file, test name)
PLANTS = [
    ("the standard look's row at its old 12 px",
     [(CSS, "  font-size: var(--fs-13); line-height: var(--lh-13); color: var(--text-secondary);\n}", "  font-size: var(--fs-12); line-height: var(--lh-12); color: var(--text-secondary);\n}")],
     "browser", SPEC, "ospreyflow dark: every part of the case line is on the top bar's font size"),
    ("the GOV.UK row at the notification banner's 19 px",
     [(CSS, "  padding: var(--sp-2) var(--sp-16); gap: var(--sp-8); font-size: var(--fs-13); line-height: var(--lh-13);\n", "  padding: var(--sp-2) var(--sp-16); gap: var(--sp-8);\n")],
     "browser", SPEC, "govuk light: every part of the case line is on the top bar's font size"),
    ("the row's controls on a button's own type, not the row's",
     [(CSS, ":is(.context-banner, .context-banner--govuk) :is(button, a, .menu-button__label) { font-size: inherit; line-height: inherit; }", ""),
      (CSS, ".context-banner--folded :is(.btn, .govuk-link) { min-height: 24px; padding-top: 0; padding-bottom: 0; font-size: inherit; line-height: inherit; }",
       ".context-banner--folded :is(.btn, .govuk-link) { min-height: 24px; padding-top: 0; padding-bottom: 0; line-height: 24px; }")],
     "browser", SPEC, "govuk light: every part of the case line is on the top bar's font size"),
    ("(a) the cross-link never taking its short words",
     [(BANNER, "          {short && crossLink.shortLabel ? crossLink.shortLabel : crossLink.label}", "          {crossLink.label}")],
     "browser", SPEC, "ospreyflow light: the cross-link keeps its full words with room"),
    ("(b) the line never held to one line by the ellipsis",
     [(CSS, ".context-banner--squeezed, .context-banner--govuk .govuk-notification-banner__content.context-banner--squeezed { flex-wrap: nowrap; }", "")],
     "browser", SPEC, "ospreyflow dark: at 1024 wide, the long names, the case line is one line high"),
    ("(b) the reads line's whole words not in its title",
     [(BANNER, "          <span className=\"context-banner__fit\" title={datasets.length > 0 ? `reads ${names(datasets)}` : undefined}>", "          <span className=\"context-banner__fit\">")],
     "browser", SPEC, "govuk light: the long names give way with an ellipsis"),
    ("(b) something else giving way too (the switcher shrinking with them)",
     [(CSS, ".context-banner--squeezed > * { flex-shrink: 0; }", ".context-banner--squeezed > * { flex-shrink: 0; }\n.context-banner--squeezed > .menu { flex-shrink: 1; min-width: 0; overflow: hidden; }")],
     "browser", SPEC, "ospreyflow dark: the long names give way with an ellipsis"),
]


def main() -> int:
    head = os.environ.get("PLANT_HEAD", "(no PLANT_HEAD given)")
    print(f"# case-line reds at {head} (the local checkout's, passed in); each plant restored from the file's own text")
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
