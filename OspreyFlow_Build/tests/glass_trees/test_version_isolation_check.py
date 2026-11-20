"""ADR-152 invariant I13: the shared package imports no `sigma`, `@sigma/*` or `maplibre-gl`, as a value or a type;
and each front end's bundle holds a drawing library only at a version its own manifest asks for (slice PL4a).

Two halves, each shown red here:

* `OspreyFlow_Core/scripts/version_isolation_check.mjs [root]` bundles the workspace's `src/main.tsx` and every source
  file of `packages/glass-shared/src` as the build does, and fails on a drawing library the shared package reaches or
  a version outside the range the tree's own `package.json` gives (read from the manifest, not written in the script).
* the `no-restricted-imports` block for `packages/glass-shared/**` in `OspreyFlow_Core/eslint.config.js`
  (`allowTypeImports: false`) is the **type** half: a bundler drops an import used only as a type, so the script cannot
  see one. `test_a_type_only_import_is_invisible_to_the_script_and_red_in_lint` shows both at once.

The owner's evidence (`isolation_check_red_green.txt`) had five cases: a clean pass, a planted `sigma`, a planted
`maplibre-gl`, a planted type import and a graphology-only pass; each is a test below, over a scratch checkout whose
packages are written to be the shape the build meets (a nested copy of a package at another version, as npm installs
one; a symlinked workspace package).

Which test fails if the invariant is broken (rule 12): a value import of a drawing library in the shared package fails
`test_the_shared_package_importing_a_drawing_library_fails`; a second version in a front end's bundle fails
`test_a_second_version_in_the_bundle_fails`; a type import fails `test_the_lint_rule_refuses_*`; a range edited in a
manifest fails `test_the_pin_is_read_from_the_manifest`; and a check that bundles nothing fails
`test_a_check_with_nothing_to_bundle_does_not_pass`. The real tree must pass `test_the_real_tree_passes`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
SCRIPT = CORE / "scripts" / "version_isolation_check.mjs"


def node() -> str:
    found = shutil.which("node")
    assert found, "node is needed"
    return found


def run_check(root: Path) -> tuple[int, str]:
    done = subprocess.run([node(), str(SCRIPT), str(root)], cwd=CORE, capture_output=True, text=True, timeout=120)
    return done.returncode, done.stdout + done.stderr


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def package(root: Path, name: str, version: str, source: str = "export default {};\n", *, under: str = "node_modules") -> None:
    directory = root / under / name
    write(directory / "package.json", json.dumps({"name": name, "version": version, "type": "module", "main": "index.js"}))
    write(directory / "index.js", source)


def make_tree(
    root: Path,
    *,
    sigma_range: str = "^3.0.0",
    sigma_version: str = "3.0.3",
    maplibre_range: str = ">=6.4.1 <7",
    maplibre_version: str = "6.19.0",
) -> None:
    """A scratch checkout shaped like this one: a workspace that draws with Sigma and MapLibre through a Sigma
    plugin, and a shared package symlinked into `node_modules` as an npm workspace package is."""
    write(root / "package.json", json.dumps({"name": "scratch", "private": True, "workspaces": ["apps/workspace", "packages/glass-shared"]}))
    write(
        root / "apps/workspace/package.json",
        json.dumps(
            {
                "name": "@scratch/workspace",
                "private": True,
                "dependencies": {
                    "@scratch/glass-shared": "*",
                    "@sigma/node-border": "^3.0.0",
                    "graphology": "^0.26.0",
                    "maplibre-gl": maplibre_range,
                    "sigma": sigma_range,
                },
            }
        ),
    )
    write(
        root / "apps/workspace/src/main.tsx",
        "import Sigma from 'sigma';\nimport maplibregl from 'maplibre-gl';\nimport Graph from 'graphology';\n"
        "import { border } from '@sigma/node-border';\nimport { shared } from '@scratch/glass-shared';\n"
        "console.log(Sigma, maplibregl, Graph, border, shared);\n",
    )
    write(root / "packages/glass-shared/package.json", json.dumps({"name": "@scratch/glass-shared", "version": "0.0.0", "type": "module", "main": "src/index.ts"}))
    write(root / "packages/glass-shared/src/index.ts", "export const shared = 1;\n")
    package(root, "sigma", sigma_version, "export default function Sigma() {}\n")
    package(root, "maplibre-gl", maplibre_version, "export default { map: true };\n")
    package(root, "graphology", "0.26.0", "export default class Graph {}\n")
    package(root, "@sigma/node-border", "3.0.0", "import Sigma from 'sigma';\nexport const border = Sigma;\nexport default border;\n")
    (root / "node_modules/@scratch").mkdir(parents=True, exist_ok=True)
    os.symlink(root / "packages/glass-shared", root / "node_modules/@scratch/glass-shared", target_is_directory=True)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    make_tree(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------------------------------- green controls


def test_a_clean_tree_passes(tree: Path) -> None:
    code, output = run_check(tree)
    assert code == 0, output
    assert "apps/workspace @sigma/node-border@3.0.0 maplibre-gl@6.19.0 sigma@3.0.3" in output
    assert "packages/glass-shared (no drawing library)" in output
    assert output.rstrip().endswith("PASS")


def test_the_real_tree_passes() -> None:
    code, output = run_check(CORE)
    assert code == 0, output
    assert output.rstrip().endswith("PASS")
    workspace = next(line for line in output.splitlines() if line.startswith("apps/workspace "))
    assert "sigma@3." in workspace and "maplibre-gl@6." in workspace
    assert "packages/glass-shared (no drawing library)" in output


def test_a_graphology_only_shared_package_passes(tree: Path) -> None:
    """The owner's fifth case: graphology is not a drawing library; both front ends may use it."""
    write(tree / "packages/glass-shared/src/graph.ts", "import Graph from 'graphology';\nexport const graph = new Graph();\n")
    code, output = run_check(tree)
    assert code == 0, output
    assert "packages/glass-shared (no drawing library)" in output


# ---------------------------------------------------------------------------------------------------- the bundle


@pytest.mark.parametrize(
    "specifier, reached",
    [
        ("sigma", "node_modules/sigma/index.js"),
        ("maplibre-gl", "node_modules/maplibre-gl/index.js"),
        ("@sigma/node-border", "node_modules/@sigma/node-border/index.js"),
    ],
)
def test_the_shared_package_importing_a_drawing_library_fails(tree: Path, specifier: str, reached: str) -> None:
    # In a file the shared package's index does not export: every source file is looked at.
    write(tree / "packages/glass-shared/src/draw.ts", f"import Thing from '{specifier}';\nexport const thing = Thing;\n")
    code, output = run_check(tree)
    assert code == 1, output
    assert output.startswith("apps/workspace") or "FAIL" in output
    assert f"glass-shared reaches {reached}" in output


def test_a_second_version_in_the_bundle_fails(tree: Path) -> None:
    """The owner's second case, in the shape npm makes it: a plugin carries its own nested copy of `sigma`."""
    package(tree, "sigma", "4.0.6", "export default function Sigma4() {}\n", under="node_modules/@sigma/node-border/node_modules")
    code, output = run_check(tree)
    assert code == 1, output
    assert "apps/workspace: bundles sigma@4.0.6, package.json asks for ^3.0.0" in output
    assert "node_modules/@sigma/node-border/node_modules/sigma/index.js" in output


def test_a_second_maplibre_in_the_bundle_fails(tree: Path) -> None:
    """The owner's third case: a nested `maplibre-gl` at a version outside the manifest's range."""
    write(tree / "node_modules/@sigma/node-border/index.js", "import Sigma from 'sigma';\nimport map from 'maplibre-gl';\nexport const border = [Sigma, map];\nexport default border;\n")
    package(tree, "maplibre-gl", "4.7.1", "export default { old: true };\n", under="node_modules/@sigma/node-border/node_modules")
    code, output = run_check(tree)
    assert code == 1, output
    assert "apps/workspace: bundles maplibre-gl@4.7.1, package.json asks for >=6.4.1 <7" in output


@pytest.mark.parametrize(
    "sigma_version, range_text, passes",
    [
        ("3.0.3", "^3.0.0", True),
        ("3.0.3", "~3.0.0", True),
        ("3.0.3", "~3.1.0", False),
        ("3.0.3", ">=3 <4", True),
        ("3.0.3", "3.0.3", True),
        ("3.0.3", "3.0.4", False),
        ("3.0.3", "^3.0.4", False),
        ("3.0.3", "3.x", True),
        ("3.0.3", "^2.0.0", False),
        ("3.0.3", "^2 || ^3", True),
        ("3.0.3", ">=3.0.3", True),
        ("3.0.3", "<3.0.3", False),
        ("3.0.3", "*", True),
        ("0.2.5", "^0.2.0", True),
        ("0.3.0", "^0.2.0", False),
        ("4.0.0-rc.1", "^3.0.0", False),
    ],
)
def test_the_pin_is_read_from_the_manifest(tmp_path: Path, sigma_version: str, range_text: str, passes: bool) -> None:
    """No pin is written in the script: the same bundle passes or fails with what `package.json` says."""
    make_tree(tmp_path, sigma_version=sigma_version, sigma_range=range_text)
    code, output = run_check(tmp_path)
    assert (code == 0) is passes, output
    if not passes:
        assert f"bundles sigma@{sigma_version}, package.json asks for {range_text}" in output


def test_a_range_the_check_cannot_read_fails_and_does_not_pass(tmp_path: Path) -> None:
    make_tree(tmp_path, sigma_range="github:jacomyal/sigma.js")
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert 'cannot read the range "github:jacomyal/sigma.js" that package.json gives sigma' in output


def test_a_tree_that_does_not_bundle_fails_in_a_line_and_not_a_stack_trace(tree: Path) -> None:
    write(tree / "packages/glass-shared/src/broken.ts", "export const = ;\n")
    code, output = run_check(tree)
    assert code == 1, output
    assert "packages/glass-shared cannot be bundled, so it cannot be checked:" in output
    assert "at async" not in output


def test_a_check_with_nothing_to_bundle_does_not_pass(tree: Path) -> None:
    (tree / "apps/workspace/src/main.tsx").unlink()
    code, output = run_check(tree)
    assert code == 1, output
    assert "apps/workspace: entry not found: src/main.tsx" in output

    shutil.rmtree(tree / "packages/glass-shared/src")
    code, output = run_check(tree)
    assert code == 1, output
    assert "packages/glass-shared/src has no source file to bundle" in output


# ---------------------------------------------------------------------------------------------------- the type half: lint


def lint(source: str) -> list[dict[str, object]]:
    """ESLint over `source` as if it were `packages/glass-shared/src/planted.ts`, with the real config."""
    done = subprocess.run(
        [node(), str(CORE / "node_modules/eslint/bin/eslint.js"), "--stdin", "--stdin-filename", "packages/glass-shared/src/planted.ts", "--format", "json"],
        cwd=CORE,
        input=source,
        capture_output=True,
        text=True,
        timeout=120,
    )
    report = json.loads(done.stdout)
    assert len(report) == 1, done.stdout + done.stderr
    return list(report[0]["messages"])


@pytest.mark.parametrize(
    "source, rule",
    [
        ('import type { Map } from "maplibre-gl";\nexport type M = Map;\n', "@typescript-eslint/no-restricted-imports"),
        ('import type Sigma from "sigma";\nexport type S = Sigma;\n', "@typescript-eslint/no-restricted-imports"),
        ('import { type NodeBorder } from "@sigma/node-border";\nexport type B = NodeBorder;\n', "@typescript-eslint/no-restricted-imports"),
        ('import type { Foo } from "sigma/utils";\nexport type F = Foo;\n', "@typescript-eslint/no-restricted-imports"),
        ('export type { Map } from "maplibre-gl";\n', "@typescript-eslint/no-restricted-imports"),
        ('import type { ReactNode } from "react";\nexport type N = ReactNode;\n', "@typescript-eslint/no-restricted-imports"),
        ('import type { Root } from "react-dom/client";\nexport type R = Root;\n', "@typescript-eslint/no-restricted-imports"),
        ('export type M = import("maplibre-gl").Map;\n', "no-restricted-syntax"),
        ('export type S = import("@sigma/layer-maplibre").Layer;\n', "no-restricted-syntax"),
        ('export const later = () => import("sigma");\n', "no-restricted-syntax"),
        ('import Sigma from "sigma";\nexport default Sigma;\n', "@typescript-eslint/no-restricted-imports"),
    ],
)
def test_the_lint_rule_refuses_a_drawing_library_or_react_by_any_import_form(source: str, rule: str) -> None:
    """The planted `import type` of the owner's evidence, and the other forms a type can name a library by."""
    messages = lint(source)
    assert [m["ruleId"] for m in messages if m["severity"] == 2] == [rule], messages


@pytest.mark.parametrize(
    "source",
    [
        'import type { Graph } from "graphology-types";\nexport type G = Graph;\n',
        'import Graph from "graphology";\nexport const g = new Graph();\n',
        'import { local } from "./sigma";\nexport const l = local;\n',
        'export type L = import("./local").Thing;\n',
        'import { createStore } from "zustand/vanilla";\nexport const s = createStore;\n',
        'import type { Reactive } from "reactive-banana";\nexport type R = Reactive;\n',
    ],
)
def test_the_lint_rule_lets_other_imports_through(source: str) -> None:
    assert [m for m in lint(source) if m["severity"] == 2] == [], source


def test_a_type_only_import_is_invisible_to_the_script_and_red_in_lint(tree: Path) -> None:
    """The owner's fourth case, both halves at once: a bundler drops `import type`, so the script passes; the lint
    rule is what refuses it. If a later bundler kept type imports, the first assertion would say so."""
    source = 'import type { Map } from "maplibre-gl";\nexport type M = Map;\n'
    write(tree / "packages/glass-shared/src/types.ts", source)
    code, output = run_check(tree)
    assert code == 0, output
    assert [m["ruleId"] for m in lint(source) if m["severity"] == 2] == ["@typescript-eslint/no-restricted-imports"]
