"""The suppression mark read back and asked why (v0.5.2 route rows S7 and S8, spec 02 §9.5): each test's red, a plant
at the real call site.

Run on the server, through `stack_lease.sh offline case`, from the worktree
at the commit under test with nothing else changed, the head passed in from the local checkout's `git rev-parse`:
    head=$(git rev-parse --short HEAD); OspreyFlow_Build/scripts/stack_lease.sh offline case -- sh -c \
      "PLANT_HEAD=$head python3 OspreyFlow_Build/process/lanes/case/gates/suppression_marks_reds.py" > .../suppression-marks-reds.$head.log

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
SUPPRESSION = "OspreyFlow_Core/services/api/suppression.py"
APP = "OspreyFlow_Core/services/api/app.py"
CANVAS = "OspreyFlow_Core/apps/workspace/src/canvas/GlassCanvas.tsx"
READ = "tests/services/api/working_set/test_suppression_marks_read.py"
ROUTES = "tests/services/api/test_explore_routes.py"
CLOSED = {"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994", "OPENSEARCH_PORT": "59999"}

# (what, [(file from the root, old, new)], runner, test file, test name)
PLANTS = [
    ("the canvas marks read over the whole working set, not the reader's projection",
     [(SUPPRESSION, "    nodes, _ = await working_set.visible_membership(investigation_id, principal)\n",
       "    nodes, _ = await working_set.current_membership(investigation_id)  # type: ignore[attr-defined]\n")],
     "pytest", READ, "test_a_mark_on_a_node_the_reader_may_not_see_is_never_asked_about"),
    ("the canvas never reading its marks back",
     [(CANVAS, "      void read();\n      const again = () => {", "      const again = () => {"),
      (CANVAS, '      graph.on("nodeAdded", again);\n', "")],
     "browser", "keyboard/keyboard.spec.ts", "a mark read back after a reload offers Remove"),
    ("the fixed reason again, nothing asked",
     [(CANVAS, "      setReasonPrompt({\n        x: anchor.x,\n        y: anchor.y,\n        title: \"Mark this record for suppression (hides nothing yet)\",",
       "      if (anchor) return void writeSuppressionMark(nodeId, \"Marked from the canvas\", anchor);\n      setReasonPrompt({\n        x: anchor.x,\n        y: anchor.y,\n        title: \"Mark this record for suppression (hides nothing yet)\",")],
     "browser", "keyboard/keyboard.spec.ts", "the radial list reaches Mark for suppression, and the mark toggles"),
    ("the server taking a reason of spaces alone",
     [(APP, "        if not value.strip():\n            raise ValueError(\"a suppression mark needs a reason\")",
       "        if False:\n            raise ValueError(\"a suppression mark needs a reason\")")],
     "pytest", ROUTES, "test_a_suppression_mark_needs_words_and_keeps_them_trimmed"),
    ("the route asking the working set with a principal not the case's",
     [(APP, "    found = await marks_on_the_canvas(working_set, marks, investigation.id, principal)\n",
       "    found = await marks_on_the_canvas(\n        working_set, marks, investigation.id, principal.model_copy(update={\"datasets\": None})\n    )\n")],
     "pytest", ROUTES, "test_the_canvas_marks_are_read_as_the_case_reader_and_audited"),
]


def main() -> int:
    head = os.environ.get("PLANT_HEAD", "(no PLANT_HEAD given)")
    print(f"# suppression-marks reds at {head} (the local checkout's, passed in); each plant restored from the file's own text")
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
