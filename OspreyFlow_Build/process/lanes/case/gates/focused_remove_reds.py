"""focused-remove (a node dropped, or the graph cleared, while the canvas arranges; the expansion prompts modal, their
choices one component): each test's red, a plant at the real call site.

Run from the worktree root at the commit under test, with process/lanes/case/shared-files-expand-cap.diff applied (the
expand-cap keyboard spec imports its registry) and nothing else changed:
    python3 OspreyFlow_Build/process/lanes/case/gates/focused_remove_reds.py > OspreyFlow_Build/process/lanes/case/gates/focused-remove-reds.<head>.log

Each plant replaces one exact string in one file (refused if it is not there exactly once), runs the named test
(vitest, or Playwright on the lane's slot 2), records the result and restores the file with `git checkout`. A plant
whose test stays green is a failure of this record.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
WS = ROOT / "OspreyFlow_Core/apps/workspace"
SPEC = "keyboard/canvas-expand-cap.spec.ts"
CANVAS = "src/canvas/GlassCanvas.tsx"

# (what, file, old, new, runner, test file, test name)
REMOVE = "keyboard/canvas-remove-while-arranging.spec.ts"
PLANTS = [
    ("a node dropped mid-move left in the animation's targets",
     CANVAS, '        if (animating) delete animating[key];', '        void key;',
     "browser", REMOVE, "a node taken out while the canvas arranges"),
    ("the graph cleared mid-move left in the animation's targets",
     CANVAS, '        if (animating) for (const id of Object.keys(animating)) delete animating[id];', '        void animating;',
     "browser", REMOVE, "a snapshot that clears the graph while the canvas arranges"),
    ("a modal popover letting Tab out",
     "src/design/primitives/Popover.tsx", '        modal\n          ? (e) => {', '        false\n          ? (e) => {',
     "jsdom", "src/design/primitives/Popover.test.tsx", "as a modal prompt it is the named alertdialog"),
    ("a modal popover not saying so (aria-modal)",
     "src/design/primitives/Popover.tsx", '      aria-modal={modal ? true : undefined}\n', '',
     "jsdom", "src/design/primitives/Popover.test.tsx", "as a modal prompt it is the named alertdialog"),
    ("every popover made modal",
     "src/design/primitives/Popover.tsx", 'role = "dialog", label, modal = false }', 'role = "dialog", label, modal = true }',
     "jsdom", "src/design/primitives/Popover.test.tsx", "without them it is an unnamed dialog"),
    ("the cap's refusal not modal",
     "src/canvas/CapRefusalPrompt.tsx", 'label="Too large to expand" modal>', 'label="Too large to expand">',
     "browser", SPEC, "the cap's refusal is modal"),
    ("the large expansion's prompt not modal",
     "src/canvas/LargeExpansionPrompt.tsx", 'label="Large expansion" modal>', 'label="Large expansion">',
     "browser", SPEC, "the large expansion's prompt is modal too"),
    ("the shared choices handing over a type's label, not its type",
     "src/canvas/NarrowingChoices.tsx", 'onClick={() => onChooseType(option.edgeType)}', 'onClick={() => onChooseType(linkTypeName(option.edgeType, edgeTypes))}',
     "jsdom", "src/canvas/CapRefusalPrompt.test.tsx", "hands over its type"),
]


def main() -> int:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    dirty = [l[3:] for l in subprocess.run(["git", "status", "--porcelain", "--", str(WS)], capture_output=True, text=True, cwd=ROOT).stdout.splitlines()]
    if [d for d in dirty if not d.endswith("keyboard/actionRegistry.ts")]:
        print("refused: the workspace has uncommitted changes other than the shared diff; plants restore with git checkout")
        return 2
    print(f"# focused-remove reds at {head}; each plant restored with `git checkout -- <file>`")
    stayed = 0
    for n, (what, path, old, new, runner, test_file, name) in enumerate(PLANTS, 1):
        target = WS / path
        text = target.read_text()
        if text.count(old) != 1:
            print(f"## {n}. {what}\nrefused: the planted string is in {path} {text.count(old)} times, not once")
            stayed += 1
            continue
        target.write_text(text.replace(old, new))
        try:
            if runner == "jsdom":
                cmd = ["npx", "vitest", "run", test_file, "-t", name]
                env = os.environ
            else:
                cmd = ["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts", test_file, "-g", re.escape(name), "--workers=1"]
                env = {**os.environ, "OSPREY_PORTS_SLOT": "2"}
            run = subprocess.run(cmd, capture_output=True, text=True, cwd=WS, env=env)
        finally:
            subprocess.run(["git", "checkout", "--", str(target)], check=True, cwd=ROOT)
        out = run.stdout + run.stderr
        lines = [l for l in out.splitlines() if any(k in l for k in ("×", "✘", "✓", "AssertionError", "Error:", "Expected", "Received", "Tests ", " passed", " failed"))]
        print(f"## {n}. {what}\nplant in {path}; {' '.join(cmd)}; exit {run.returncode}")
        print("\n".join(lines[:14]))
        if run.returncode == 0:
            stayed += 1
            print("STAYED GREEN")
        elif not re.search(r"\d+ failed", out):
            stayed += 1
            print("NO TEST FAILED (the run failed otherwise): not a red")
    print(f"# {len(PLANTS) - stayed} of {len(PLANTS)} red")
    return 1 if stayed else 0


if __name__ == "__main__":
    sys.exit(main())
