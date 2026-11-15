"""Show all on graph and Save as a view under an Ask & Chat answer (v0.6.0 #5): each test's red, a plant at the real
call site.

Run on the server, through `stack_lease.sh offline case`, from the worktree
at the commit under test with nothing else changed, the head passed in from the local checkout's `git rev-parse`:
    head=$(git rev-parse --short HEAD); OspreyFlow_Build/scripts/stack_lease.sh offline case -- sh -c \
      "PLANT_HEAD=$head python3 OspreyFlow_Build/process/lanes/case/gates/show_all_reds.py" > .../show-all-reds.$head.log

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
SERVICE = "OspreyFlow_Core/services/api/working_set/service.py"
SHOW = "OspreyFlow_Core/apps/workspace/src/questions/showAnswer.ts"
ACTIONS = "OspreyFlow_Core/apps/workspace/src/questions/AnswerActions.tsx"
SPEC = "keyboard/questions.spec.ts"
TESTS = "tests/services/api/working_set/test_add_by_ids.py"
CLOSED = {"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994", "OPENSEARCH_PORT": "59999"}

# (what, [(file from the root, old, new)], runner, test file, test name)
PLANTS = [
    ("what was not shown never counted",
     [(SERVICE, "        return AddedByIds(outcome=outcome, not_shown=asked - shown)", "        return AddedByIds(outcome=outcome, not_shown=0 * (asked - shown))")],
     "pytest", TESTS, "test_a_node_the_reader_may_not_see_is_left_out_counted_and_never_named"),
    ("a link put on with an end the reader cannot see",
     [(SERVICE, "            and vault_edges[i].source in verified\n            and vault_edges[i].target in verified\n", "")],
     "pytest", TESTS, "test_a_link_whose_ends_the_reader_cannot_both_see_is_left_out_and_counted"),
    ("the answer's items added but not selected",
     [(SHOW, "      drawn.highlightNodes(ids.nodeIds);\n", "")],
     "browser", SPEC, "Show all on graph under an answer puts every item"),
    ("how many could not be shown never said",
     [(SHOW, "    if (added.notShown > 0) now.say(", "    if (added.notShown > 99) now.say(")],
     "browser", SPEC, "Show all on graph under an answer puts every item"),
    ("the cap's refusal said as a bare error, its figures lost",
     [(SHOW, "    if (added.kind === \"limit_exceeded\") {\n      now.say(", "    if (added.kind === \"limit_exceeded\") {\n      now.say(\"Something went wrong.\" ||")],
     "browser", SPEC, "Show all on graph past the working set's cap"),
    ("the records a search found left out of the answer's items",
     [(ACTIONS, "  for (const source of entry.search_citations ?? []) for (const id of source.node_ids) nodeIds.add(id);\n", "")],
     "jsdom", "src/questions/AnswerActions.test.tsx", "are every id its markers stand for"),
    ("the saved view offered no name of the question's",
     [(ACTIONS, "          defaultName={answerViewName(entry.question)}", "          defaultName=\"\"")],
     "browser", SPEC, "Save as a view under an answer saves its items"),
]


def main() -> int:
    head = os.environ.get("PLANT_HEAD", "(no PLANT_HEAD given)")
    print(f"# show-all reds at {head} (the local checkout's, passed in); each plant restored from the file's own text")
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
