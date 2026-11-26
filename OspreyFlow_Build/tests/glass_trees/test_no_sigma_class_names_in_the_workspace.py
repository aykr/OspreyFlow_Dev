"""No test, harness or source file of the React workspace finds the canvas by a class name Sigma 3 gives its own
elements (`canvas.sigma-nodes`, `.sigma-labels`, `canvas.sigma-communityLinks`, ...) (slice WS4a, case 12).

Sigma 4 has no `canvas.sigma-nodes` (ADR-152 decision 9), so a gate that waits on one never fires on Sigma 4: the
budget gate's readiness would time out at 60 seconds instead of giving a figure, and WS4's port could not be judged by
the gate it is held to. The canvas marks itself instead (`src/canvas/canvasMarks.ts`): `data-canvas-state` on the
"Network canvas" application element, and `data-canvas-layer` on each layer it draws on. Only that file knows which
renderer layer is which.

Which test fails if the invariant is broken (rule 12): a `sigma-` class name left in, or added to, any file of the
workspace fails `test_no_file_of_the_workspace_names_a_sigma_class`; the scan itself is shown able to find one by
`test_the_scan_finds_each_shape_a_sigma_class_name_was_written_in`, over the five shapes the tree actually used
before WS4a (read at `41ed4f195`: `perf/harness.tsx:78`, `perf/perf.spec.ts:110`, `perf/community-links.spec.ts:15`,
`keyboard/link-selection.spec.ts:142`, `keyboard/canvas-look.spec.ts:201`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core" / "apps" / "workspace"
SUFFIXES = {".ts", ".tsx", ".js", ".mjs", ".css", ".html"}
SKIP = {"node_modules", "dist", "test-results", "playwright-report"}
# A Sigma class name as a selector or a class string: `.sigma-x`, `canvas.sigma-x`, `"sigma-x"`, `'sigma-x`, a
# template's `sigma-${id}`. Not `@sigma/node-border` (a package) nor `network-canvas__sigma` (the workspace's own).
SIGMA_CLASS = re.compile(r"""(?<![\w/@-])sigma-(?:[A-Za-z]|\$\{)""")


def sigma_class_names(text: str) -> list[str]:
    return [m.group(0) for m in SIGMA_CLASS.finditer(text)]


def workspace_files() -> list[Path]:
    found = []
    for path in WORKSPACE.rglob("*"):
        if path.suffix in SUFFIXES and path.is_file() and not SKIP.intersection(path.relative_to(WORKSPACE).parts):
            found.append(path)
    return found


def test_the_scan_reads_the_whole_workspace() -> None:
    files = {p.relative_to(WORKSPACE).as_posix() for p in workspace_files()}
    for expected in ("perf/harness.tsx", "perf/perf.spec.ts", "keyboard/canvas-look.spec.ts", "src/canvas/GlassCanvas.tsx"):
        assert expected in files


@pytest.mark.parametrize(
    "line",
    [
        'const canvas = container.querySelector("canvas.sigma-nodes");',
        'const canvas = page.locator("canvas.sigma-nodes");',
        'document.querySelector<HTMLCanvasElement>("canvas.sigma-communityLinks");',
        '"button, select, .canvas-zoom, .sigma-nodes, .sigma-labels, .sigma-hovers { visibility: hidden }"',
        "const name = `sigma-${id}`;",
    ],
)
def test_the_scan_finds_each_shape_a_sigma_class_name_was_written_in(line: str) -> None:
    assert sigma_class_names(line)


@pytest.mark.parametrize(
    "line",
    [
        'import { createNodeBorderProgram } from "@sigma/node-border";',
        '<div className="network-canvas__sigma" />',
        'import Sigma from "sigma";',
        "// sigma.kill() empties its container",
        'page.locator(\'[data-canvas-layer="labels"]\')',
    ],
)
def test_the_scan_leaves_what_is_not_a_sigma_class_name(line: str) -> None:
    assert sigma_class_names(line) == []


def test_no_file_of_the_workspace_names_a_sigma_class() -> None:
    found = []
    for path in workspace_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if sigma_class_names(line):
                found.append(f"{path.relative_to(WORKSPACE).as_posix()}:{number}: {line.strip()[:120]}")
    assert found == [], "Sigma's own class names; use the canvas's marks (src/canvas/canvasMarks.ts):\n" + "\n".join(found)
