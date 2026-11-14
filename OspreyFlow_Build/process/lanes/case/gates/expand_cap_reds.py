"""expand-cap (rule 2; spec/00 §4: an expansion the working set's cap refuses offers the cap's choices): each test's
red, a plant at the real call site.

Run from the worktree root at the commit under test, with process/lanes/case/shared-files-expand-cap.diff applied
(git apply; the keyboard spec imports its registry) and nothing else changed:
    python3 OspreyFlow_Build/process/lanes/case/gates/expand_cap_reds.py > OspreyFlow_Build/process/lanes/case/gates/expand-cap-reds.<head>.log

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
PLANTS = [
    ("the 409 taken as any failure again ('Expand failed (409). Try again.')",
     CANVAS, '        if (response.status === 409) {', '        if (false) {',
     "browser", SPEC, "says the cap's own figure"),
    ("no narrowing offered at the cap",
     CANVAS, '            const options = edgeType === null ? await narrowingFor(nodeId, depth) : [];\n            setCapRefusal(',
     '            const options: NarrowingOption[] = [];\n            setCapRefusal(',
     "browser", SPEC, "says the cap's own figure"),
    ("a type chosen expanding by every type again",
     CANVAS, '              setCapRefusal(null);\n              void expandNode(nodeId, edgeType, x, y, depth);',
     '              setCapRefusal(null);\n              void expandNode(nodeId, null, x, y, depth);',
     "browser", SPEC, "says the cap's own figure"),
    ("Save a smaller view not offered on the canvas",
     CANVAS, '            onSaveSmallerView={\n              onSaveSmallerView\n',
     '            onSaveSmallerView={\n              false && onSaveSmallerView\n',
     "browser", SPEC, "is saved as a smaller view by keyboard"),
    ("Escape not putting the refusal away",
     CANVAS, '            onCancel={() => setCapRefusal(null)}', '            onCancel={() => undefined}',
     "browser", SPEC, "Escape puts the refusal away"),
    ("the App not handling Save a smaller view",
     "src/App.tsx", '                onSaveSmallerView={(refused, subject) => setExpansionOverCap({ refused, subject })}\n', '',
     "jsdom", "src/App.expandCap.test.tsx", "Save a smaller view opens the save form"),
    ("the App giving the expansion the case's own words",
     "src/App.tsx", '          title="This expansion is too large"\n', '',
     "jsdom", "src/App.expandCap.test.tsx", "Save a smaller view opens the save form"),
    ("Try again offered with nothing to resync",
     "src/workingset/ViewOverCapDialog.tsx", '        {onTryAgain && (', '        {(onTryAgain ?? true) && (',
     "jsdom", "src/workingset/ViewOverCapDialog.test.tsx", "for an expansion the cap refused"),
    ("the dialog's reason ignored",
     "src/workingset/ViewOverCapDialog.tsx", '      <p className="view-over-cap__why">{why}</p>', '      <p className="view-over-cap__why">{title}</p>',
     "jsdom", "src/workingset/ViewOverCapDialog.test.tsx", "for an expansion the cap refused"),
    # After the lane review of 0b2f8eb.
    ("any 409 taken for the cap's (the review's)",
     CANVAS, '          if (body?.error === "limit_exceeded" && typeof body.cap === "number" && typeof body.would_be === "number") {',
     '          if (true) {',
     "browser", SPEC, "a 409 that is not the cap's"),
    ("a chosen relationship sending the first one offered (the review's)",
     "src/canvas/CapRefusalPrompt.tsx", 'onClick={() => onChooseType(option.edgeType)}', 'onClick={() => onChooseType(options[0]!.edgeType)}',
     "browser", SPEC, "says the cap's own figure"),
    ("a refusal kept for a node taken out (the review's)",
     CANVAS, '        {capRefusal && graph.hasNode(capRefusal.nodeId) && (', '        {capRefusal && (',
     "browser", SPEC, "a node taken out while its refusal is open"),
    ("a typed expansion's refusal offering narrowing (the review's)",
     CANVAS, '            const options = edgeType === null ? await narrowingFor(nodeId, depth) : [];\n            // Gone while',
     '            const options = await narrowingFor(nodeId, depth);\n            // Gone while',
     "browser", SPEC, "an expansion by one link type the cap refuses"),
    ("the batch hand-off with another depth (the review's)",
     CANVAS, 'onRunExpansionAsBatch({ nodeId, edgeType, depth, refused });', 'onRunExpansionAsBatch({ nodeId, edgeType, depth: 3, refused });',
     "browser", SPEC, "Run as a batch job hands the refused expansion up"),
    ("the batch choice under another name (the review's; case-b finds it by this one)",
     "src/canvas/CapRefusalPrompt.tsx", '              Run as a batch job\n', '              Run it as a batch\n',
     "jsdom", "src/canvas/CapRefusalPrompt.test.tsx", "the batch choice (ADR-151)"),
    ("the reason with no name reading 'Expanding it' (the review's)",
     "src/App.tsx", ': "This expansion"} would', ': "Expanding it"} would',
     "jsdom", "src/App.expandCap.test.tsx", "with no name for the node"),
]


def main() -> int:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    dirty = [l[3:] for l in subprocess.run(["git", "status", "--porcelain", "--", str(WS)], capture_output=True, text=True, cwd=ROOT).stdout.splitlines()]
    if [d for d in dirty if not d.endswith("keyboard/actionRegistry.ts")]:
        print("refused: the workspace has uncommitted changes other than the shared diff; plants restore with git checkout")
        return 2
    print(f"# expand-cap reds at {head}; each plant restored with `git checkout -- <file>`")
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
