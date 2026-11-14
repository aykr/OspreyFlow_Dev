"""Rule 15's red-then-green for Parts C and E (v052-selection): each plant breaks one thing at its real call site
and the test that holds it must turn red; unplanted, each suite is green. A plant is written into the tracked file
and put back from its own bytes whatever happens (and `git diff --quiet` is asserted on each file at the end), so
run it only in this worktree with nothing else running. From OspreyFlow_Core:

    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/v052-selection/plants.py [--keyboard]

`--keyboard` adds the Playwright plants (needs the lane's own browser slot, OSPREY_PORTS_SLOT). The two shared
files' diffs (tokens_css.diff, actionRegistry.diff, every_harness.diff) are applied for the run and taken out after."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
BUILD = CORE.parent / "OspreyFlow_Build"
WS = CORE / "apps" / "workspace"

PYTEST = ["working_set/test_preview_link_count.py"]
#: (file under Core, the text as it stands, the planted text, what it breaks, the suite: py | js:<files> | kb:<grep>)
PLANTS: list[tuple[str, str, str, str, str]] = [
    ("services/api/working_set/service.py", "        and e.source in returned\n        and e.target in returned\n", "", "a link whose far end the read left out is counted", "py"),
    ("services/api/working_set/service.py", "        if (types is None or e.type in types)\n", "        if True\n", "a link of another type is counted", "py"),
    ("services/api/working_set/service.py", "        and (e.source in asked or e.target in asked)\n", "", "a link between two neighbours is counted as the node's", "py"),
    ("services/api/working_set/service.py", "            link_count=_links_at(req, subgraph),", "            link_count=len(subgraph.edges),", "every link the read returned counted", "py"),
    ("apps/workspace/src/canvas/selectionActions.ts", '  add("expand", bar.onExpand);\n  const linksAmong', '  const linksAmong', "Expand left out of the menu", "js:src/canvas/selectionActions.test.tsx"),
    ("apps/workspace/src/canvas/selectionActions.ts", '  add("clear", bar.onClear);', '  add("clear", bar.onClear);\n  add("expand", bar.onExpand);', "the menu's order not the bar's (Expand moved last)", "js:src/canvas/selectionActions.test.tsx"),
    ("apps/workspace/src/canvas/SelectionBar.tsx", "          {W.saveView}\n", "          Save view\n", "the bar's words drift from the menu's", "js:src/canvas/selectionActions.test.tsx"),
    ("apps/workspace/src/canvas/selectionActions.ts", '  add("linksAmong", linksAmong && bar.count > 1 ? () => linksAmong(degreeShown(bar.count, bar.degree ?? 1)) : undefined);', '  add("linksAmong", linksAmong ? () => linksAmong(degreeShown(bar.count, bar.degree ?? 1)) : undefined);', "Show links offered for one, as the bar does not", "js:src/canvas/selectionActions.test.tsx"),
    ("apps/workspace/src/design/primitives/RadialMenu.tsx", "    if (item.keepsOpen) {", "    if (false) {", "the fold line closes the menu", "js:src/design/primitives/RadialMenu.test.tsx"),
    ("apps/workspace/src/design/primitives/RadialMenu.tsx", '        : e.key === "Home"', '        : e.key === "Pos1"', "Home does nothing", "js:src/design/primitives/RadialMenu.test.tsx"),
    ("apps/workspace/src/design/primitives/RadialMenu.tsx", "    if (over > 0) setPlaced(", "    if (false) setPlaced(", "the menu opens over the bar", "js:src/design/primitives/RadialMenu.test.tsx"),
    ("apps/workspace/src/design/primitives/RadialMenu.tsx", '        fontFamily: "var(--ui)",', '        fontFamily: "var(--mono)",', "the menu's heading in mono", "js:src/design/primitives/RadialMenu.test.tsx"),
    ("apps/workspace/src/design/tokens.css", ":is(h1, h2, h3, h4, h5, h6).value { font-family: var(--ui); }", "", "a heading classed as a value in mono", "js:src/design/headingFace.test.ts"),
    ("apps/workspace/src/design/tokens.css", ":is(h1, h2, h3, h4, h5, h6).value { font-family: var(--ui); }", ":is(h1, h2, h3, h4, h5, h6, span).value { font-family: var(--ui); }", "a value that is not a heading out of mono", "js:src/design/headingFace.test.ts"),
    ("apps/workspace/src/design/primitives/RadialMenu.tsx", '    const boxes = [menu, ...Array.from(menu.querySelectorAll<HTMLElement>("[role=\'menuitem\']"))];', "    const boxes = [menu];", "the ring's own entries not measured against the bar", "js:src/design/primitives/RadialMenu.test.tsx"),
    ("apps/workspace/src/design/primitives/RadialMenu.tsx", "    if (menu && (document.activeElement === document.body || document.activeElement === null))", "    if (false)", "focus lost when the focused entry goes", "js:src/design/primitives/RadialMenu.test.tsx"),
    ("apps/workspace/src/design/primitives/RadialMenu.tsx", "  }, [entryIds]);", "  }, [items.length]);", "focus lost when an entry is replaced and the count is the same", "js:src/design/primitives/RadialMenu.test.tsx"),
    ("apps/workspace/src/canvas/GlassCanvas.tsx", "      const answered = typed.every((i) => i.count !== null);", "      const answered = true;", "the fold made as each count arrives", "kb:fold only once every count has answered"),
    ("apps/workspace/src/canvas/selectionActions.ts", "() => linksAmong(degreeShown(bar.count, bar.degree ?? 1))", "() => linksAmong(1)", "the menu's Show links ignores the bar's stepper", "js:src/canvas/selectionActions.test.tsx"),
    ("apps/workspace/src/canvas/SelectionBar.tsx", "  const degree = heldDegree ?? ownDegree;", "  const degree = ownDegree;", "the bar's stepper not the canvas's", "js:src/canvas/selectionActions.test.tsx"),
    ("apps/workspace/src/canvas/selectionActions.ts", '  add("ask", bar.onAsk); // offered whatever is selected, as the bar (ADR-098 Amendment 7: a question needs no Document)', '  add("ask", bar.onAsk && bar.count > 1 && false ? bar.onAsk : undefined);', "the menu leaves out Ask, which the bar offers", "js:src/canvas/selectionActions.test.tsx"),
    ("apps/workspace/src/canvas/GlassCanvas.tsx", "      const shownTypes = emptyTypesShown || !answered ? typed : typed.filter((i) => i.count !== 0);", '      const shownTypes = emptyTypesShown || !answered ? typed : typed.filter((i) => typeof i.count === "number" && i.count > 0);', "a type whose count failed folded away", "kb:a link type whose count failed is shown"),
    ("apps/workspace/src/canvas/GlassCanvas.tsx", '  return e.key === "\\\\" || e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey);', '  return e.key === "\\\\" || (e.key === "F10" && e.shiftKey);', "the ContextMenu key opens nothing", "kb:ContextMenu key opens the menu"),
    ("apps/workspace/src/canvas/GlassCanvas.tsx", "      if (selected.has(nodeId)) return;\n      setSelected(new Set([nodeId]));", "      return;\n      setSelected(new Set([nodeId]));", "a menu on an unselected node leaves the selection", "kb:Shift\\+F10 opens the menu"),
    ("apps/workspace/src/canvas/GlassCanvas.tsx", "      const shownTypes = emptyTypesShown || !answered ? typed : typed.filter((i) => i.count !== 0);", "      const shownTypes = typed;", "the types with no links not folded", "kb:link types with no links fold"),
]


def suite(kind: str) -> tuple[int, str]:
    env = {**os.environ, "PYTHONPYCACHEPREFIX": tempfile.mkdtemp(prefix="plant-pyc-")}
    if kind == "py":
        env = {k: v for k, v in env.items() if k != "OSPREY_LANE"}
        env.update(ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", POSTGRES_PASSWORD="throwaway", VALKEY_PORT="59993",
                   CLICKHOUSE_HTTP_PORT="59994")
        cmd = [str(CORE / ".venv/bin/python"), "-m", "pytest", "-c", str(BUILD / "pytest.ini"), "-p", "no:cacheprovider", "-q",
               *[str(BUILD / "tests/services/api" / f) for f in PYTEST]]
        done = subprocess.run(cmd, cwd=CORE, capture_output=True, text=True, env=env, check=False)
    elif kind.startswith("js:"):
        done = subprocess.run(["npx", "vitest", "run", *kind[3:].split(",")], cwd=WS, capture_output=True, text=True, env=env, check=False)
    else:
        done = subprocess.run(["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts", "keyboard/keyboard.spec.ts",
                               "-g", kind[3:], "--reporter=line"], cwd=WS, capture_output=True, text=True, env=env, check=False)
    out = (done.stdout + done.stderr).splitlines()
    # vitest's own count line, pytest's and Playwright's summaries; never a test's title that holds the word
    lines = [ln for ln in out if ln.strip().startswith("Tests ")] or [
        ln for ln in out if re.search(r"^\s*(\d+ (passed|failed)\b|=+ .*(passed|failed))", ln) or re.search(r"\d+ (passed|failed) in ", ln)]
    return done.returncode, (lines[-1].strip() if lines else (done.stdout + done.stderr)[-200:].strip())


#: The shared files' changes, sent to the orchestrator as diffs (its ruling of 13 November 2026): applied for the
#: run, taken out again after, so the plants on tokens.css and the registry's ids are run as they will be merged.
DIFFS = [Path(__file__).with_name(n) for n in ("tokens_css.diff", "actionRegistry.diff", "every_harness.diff")]


def main() -> int:
    repo = CORE.parent
    for diff in DIFFS:
        subprocess.run(["git", "apply", str(diff)], cwd=repo, check=True)
    try:
        return run_plants()
    finally:
        for diff in reversed(DIFFS):
            subprocess.run(["git", "apply", "-R", str(diff)], cwd=repo, check=True)


def run_plants() -> int:
    keyboard = "--keyboard" in sys.argv
    plants = [p for p in PLANTS if keyboard or not p[4].startswith("kb:")]
    bad = 0
    for kind in sorted({p[4] for p in plants}):
        code, said = suite(kind)
        print(f"{'GREEN' if code == 0 else 'RED  '} unplanted {kind}: {said}")
        bad += code != 0
    touched: set[str] = set()
    for file, line, planted, what, kind in plants:
        path = CORE / file
        original = path.read_bytes()
        text = original.decode()
        if text.count(line) != 1:
            print(f"MISS  {what}: the text is not in {file} exactly once")
            bad += 1
            continue
        touched.add(file)
        try:
            path.write_text(text.replace(line, planted))
            code, said = suite(kind)
        finally:
            path.write_bytes(original)
        print(f"{'RED  ' if code else 'GREEN'} {what}: {said}")
        bad += code == 0
    shared = {"apps/workspace/src/design/tokens.css", "apps/workspace/keyboard/actionRegistry.ts", "apps/workspace/a11y/every-harness.spec.ts"}
    for file in sorted(touched - shared):  # the shared two differ by their diffs while applied
        if subprocess.run(["git", "diff", "--quiet", "--", file], cwd=CORE, check=False).returncode:
            print(f"DIRTY {file} differs from the index after the plants")
            bad += 1
    print("every plant red, unplanted green" if not bad else f"{bad} plant(s) not shown red")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
