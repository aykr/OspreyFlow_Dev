"""ADR-152 invariant I1: no React in `apps/pages` or `packages/glass-shared` (slice PL4a).

`OspreyFlow_Core/scripts/no_react_check.mjs [root]` checks four things: each tree's resolved packages (read from
`package-lock.json`, optional peers left out), every source file of both trees (every import form, a type and JSX
included), what the shared package's source reaches when bundled, and every bundle `pages` serves.

This test drives the real script over scratch trees (and once over the real tree) and plants each fault in the
shape the script meets it (rule 15), not as a convenient bare string:

* `import { createElement } from "react"` in a file of `packages/glass-shared` (the brief's planted fault), with
  React installed and with it not installed
* `react-dom/client`, `react/jsx-runtime`, a type-only `import type`, `require`, a dynamic import and a re-export
* JSX in a `.tsx` file that imports nothing (it compiles to `react/jsx-runtime` all the same)
* `import { create } from "zustand"` (its index re-exports the React binding) against `zustand/vanilla` (it does not)
* a package whose dependency is React, in `dependencies` and in `devDependencies`; and the lock entry `zustand` has
  today (React as an optional peer), once as npm writes it (no fault: optional peers are ignored) and once with the
  `optional` mark taken off (the fault)
* a React marker in a bundle under `apps/pages/dist`

Which test fails if the invariant is broken (rule 12): a React import in either tree fails
`test_a_react_import_fails` and `test_the_planted_createelement_import_fails_whether_or_not_react_is_installed`;
React arriving by another package fails `test_zustand_main_reaches_react_and_zustand_vanilla_does_not` and the
`test_a_dependency_*` cases; React in a served bundle fails `test_a_react_marker_in_a_served_bundle_fails`; and the
check's own blind spots (it finds nothing to look at) fail `test_a_check_with_nothing_to_look_at_does_not_pass`.
The real tree must pass (`test_the_real_tree_passes`), so the check is not red for everything.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
SCRIPT = CORE / "scripts" / "no_react_check.mjs"
REAL_LOCK = json.loads((CORE / "package-lock.json").read_text(encoding="utf-8"))


def run_check(root: Path) -> tuple[int, str]:
    node = shutil.which("node")
    assert node, "node is needed to run scripts/no_react_check.mjs"
    done = subprocess.run([node, str(SCRIPT), str(root)], cwd=CORE, capture_output=True, text=True, timeout=120)
    return done.returncode, done.stdout + done.stderr


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def lock_entry(version: str = "1.0.0", **fields: Any) -> dict[str, Any]:
    return {"version": version, "resolved": "https://registry.example/x.tgz", "license": "MIT", **fields}


def make_tree(
    root: Path,
    *,
    pages_dependencies: dict[str, str] | None = None,
    pages_dev_dependencies: dict[str, str] | None = None,
    shared_dependencies: dict[str, str] | None = None,
    packages: dict[str, dict[str, Any]] | None = None,
    install_react: bool = False,
) -> None:
    """A scratch checkout: `package.json`, a v3 `package-lock.json`, the two trees, and the few packages the
    cases name (`node_modules` holds only what a case asks for)."""
    write(root / "package.json", json.dumps({"name": "scratch", "private": True, "workspaces": ["apps/pages", "packages/glass-shared"]}))
    lock_packages: dict[str, Any] = {
        "": {"name": "scratch", "workspaces": ["apps/pages", "packages/glass-shared"]},
        "apps/pages": {
            "name": "@scratch/pages",
            "version": "0.0.0",
            "dependencies": pages_dependencies or {},
            "devDependencies": pages_dev_dependencies or {},
        },
        "packages/glass-shared": {
            "name": "@scratch/glass-shared",
            "version": "0.0.0",
            "dependencies": shared_dependencies or {},
        },
    }
    for name, entry in (packages or {}).items():
        lock_packages[f"node_modules/{name}"] = entry
    if install_react:
        lock_packages["node_modules/react"] = lock_entry("19.3.1")
        write(root / "node_modules/react/package.json", json.dumps({"name": "react", "version": "19.3.1", "main": "index.js"}))
        write(root / "node_modules/react/index.js", "exports.createElement = function () {};\nexports.version = '19';\n")
    write(root / "package-lock.json", json.dumps({"name": "scratch", "lockfileVersion": 3, "requires": True, "packages": lock_packages}))
    write(root / "apps/pages/package.json", json.dumps({"name": "@scratch/pages", "version": "0.0.0", "type": "module"}))
    write(root / "apps/pages/server/main.ts", "export const started = true;\n")
    write(root / "packages/glass-shared/package.json", json.dumps({"name": "@scratch/glass-shared", "version": "0.0.0", "type": "module"}))
    write(root / "packages/glass-shared/src/index.ts", "export const value = 1;\n")


def zustand_like(root: Path) -> None:
    """`zustand` as installed: the index re-exports the React binding, `zustand/vanilla` does not."""
    write(
        root / "node_modules/zustand/package.json",
        json.dumps(
            {
                "name": "zustand",
                "version": "5.0.2",
                "type": "module",
                "exports": {".": "./index.js", "./vanilla": "./vanilla.js"},
            }
        ),
    )
    write(root / "node_modules/zustand/vanilla.js", "export const createStore = () => ({});\n")
    write(root / "node_modules/zustand/index.js", "export * from './vanilla.js';\nexport { default as React } from 'react';\n")
    write(root / "node_modules/react/package.json", json.dumps({"name": "react", "version": "19.3.1", "main": "index.js"}))
    write(root / "node_modules/react/index.js", "module.exports = {};\n")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    make_tree(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------------------------------- green controls


def test_a_clean_tree_passes_and_says_what_it_looked_at(tree: Path) -> None:
    code, output = run_check(tree)
    assert code == 0, output
    assert output.startswith("PASS (")
    # It looked at the two trees' packages and files: a pass that saw nothing would read "0 source files".
    assert "2 source files" in output and "1 modules reached" in output


def test_the_real_tree_passes() -> None:
    code, output = run_check(CORE)
    assert code == 0, output
    assert output.startswith("PASS (")


# ---------------------------------------------------------------------------------------------------- source


@pytest.mark.parametrize("react_installed", [True, False])
def test_the_planted_createelement_import_fails_whether_or_not_react_is_installed(tmp_path: Path, react_installed: bool) -> None:
    make_tree(tmp_path, install_react=react_installed)
    # The brief's planted fault: the real call-site shape, in a file of the shared package the index does not export.
    write(tmp_path / "packages/glass-shared/src/leaf.ts", "import { createElement } from 'react';\nexport const make = createElement;\n")
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert output.startswith("FAIL")
    assert "packages/glass-shared/src/leaf.ts imports react" in output
    if react_installed:
        # With React installed, bundling the shared package reaches its modules too.
        assert "packages/glass-shared reaches node_modules/react/index.js" in output


@pytest.mark.parametrize(
    "tree_directory, filename, text, expected",
    [
        ("apps/pages", "server/view.ts", "import { renderToString } from 'react-dom/server';\n", "imports react-dom/server"),
        ("apps/pages", "server/view.ts", "import { jsx } from 'react/jsx-runtime';\nexport { jsx };\n", "imports react/jsx-runtime"),
        ("apps/pages", "server/view.ts", "import type { ReactNode } from 'react';\nexport type N = ReactNode;\n", "imports react"),
        ("apps/pages", "server/view.js", "const react = require('react');\nmodule.exports = react;\n", "imports react"),
        # A page's client module (ADR-152 decision 6; slice IS5a0): the folder the bundle step reads its entry files from.
        ("apps/pages", "modules/graph.ts", "import { createElement } from 'react';\ndocument.body.append(String(createElement('div')));\n", "imports react"),
        ("apps/pages", "modules/graph.ts", "import { createRoot } from 'react-dom/client';\nexport { createRoot };\n", "imports react-dom/client"),
        ("packages/glass-shared", "src/lazy.ts", "export const later = () => import('react-dom');\n", "imports react-dom"),
        ("packages/glass-shared", "src/reexport.ts", "export * from 'react';\n", "imports react"),
        ("packages/glass-shared", "src/typed.ts", "export type E = import('react').ReactElement;\n", "imports react"),
    ],
)
def test_a_react_import_fails(tmp_path: Path, tree_directory: str, filename: str, text: str, expected: str) -> None:
    make_tree(tmp_path)
    write(tmp_path / tree_directory / filename, text)
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert f"{tree_directory}/{filename} {expected}" in output


def test_jsx_in_a_page_module_that_imports_nothing_fails(tmp_path: Path) -> None:
    make_tree(tmp_path)
    write(tmp_path / "apps/pages/modules/panel.tsx", "export const panel = <div>hello</div>;\n")
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert "apps/pages/modules/panel.tsx holds JSX" in output


def test_a_react_marker_in_a_hashed_module_under_the_assets_folder_fails(tmp_path: Path) -> None:
    """The shape the bundle step writes: `dist/assets/<name>-<hash>.js`, an ES module (slice IS5a0)."""
    make_tree(tmp_path)
    write(tmp_path / "apps/pages/dist/assets/graph-4B5ZV6QL.js", 'var e=Symbol.for("react.transitional.element");export{e};\n')
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert "apps/pages/dist/assets/graph-4B5ZV6QL.js carries the React marker react.transitional.element" in output


def test_jsx_in_a_file_that_imports_nothing_fails(tmp_path: Path) -> None:
    make_tree(tmp_path)
    write(tmp_path / "packages/glass-shared/src/view.tsx", "export const view = <div>hello</div>;\n")
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert "packages/glass-shared/src/view.tsx holds JSX" in output


def test_a_file_named_like_react_is_not_react(tmp_path: Path) -> None:
    """Green control for the pattern: `reactive` and a local `./react` are not the package."""
    make_tree(tmp_path)
    write(tmp_path / "packages/glass-shared/src/react.ts", "export const notReact = 1;\n")
    write(tmp_path / "packages/glass-shared/src/uses.ts", "import { notReact } from './react';\nimport reactive from 'reactive-banana';\nexport { notReact, reactive };\n")
    code, output = run_check(tmp_path)
    assert code == 0, output


def test_zustand_main_reaches_react_and_zustand_vanilla_does_not(tmp_path: Path) -> None:
    make_tree(tmp_path)
    zustand_like(tmp_path)
    write(tmp_path / "packages/glass-shared/src/store.ts", "import { createStore } from 'zustand/vanilla';\nexport const store = createStore;\n")
    code, output = run_check(tmp_path)
    assert code == 0, output
    # The same store through the package's index, which re-exports the React binding: nothing in the source names
    # React, so only the bundle shows it.
    write(tmp_path / "packages/glass-shared/src/store.ts", "import { createStore } from 'zustand';\nexport const store = createStore;\n")
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert "packages/glass-shared reaches node_modules/react/index.js" in output
    assert "imports react" not in output


# ---------------------------------------------------------------------------------------------------- resolved packages


def test_a_dependency_that_depends_on_react_fails(tmp_path: Path) -> None:
    make_tree(
        tmp_path,
        pages_dependencies={"ui-kit": "^1.0.0"},
        packages={"ui-kit": lock_entry(dependencies={"react": "^19.0.0"}), "react": lock_entry("19.3.1")},
    )
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert "apps/pages resolves react: apps/pages > ui-kit > react" in output


def test_a_dev_dependency_that_depends_on_react_fails(tmp_path: Path) -> None:
    make_tree(
        tmp_path,
        pages_dev_dependencies={"component-testing": "^1.0.0"},
        packages={"component-testing": lock_entry(dependencies={"react-dom": "^19.0.0"}), "react-dom": lock_entry("19.3.1")},
    )
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert "apps/pages resolves react-dom: apps/pages > component-testing > react-dom" in output


def test_a_package_nested_under_another_is_found(tmp_path: Path) -> None:
    """npm nests a version that conflicts with the hoisted one: `node_modules/a/node_modules/react`."""
    make_tree(
        tmp_path,
        shared_dependencies={"holder": "^1.0.0"},
        packages={"holder": lock_entry(dependencies={"react": "^18.0.0"})},
    )
    lock = json.loads((tmp_path / "package-lock.json").read_text(encoding="utf-8"))
    lock["packages"]["node_modules/holder/node_modules/react"] = lock_entry("18.3.1")
    write(tmp_path / "package-lock.json", json.dumps(lock))
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert "packages/glass-shared resolves react: packages/glass-shared > holder > react" in output


def real_zustand_entry() -> dict[str, Any]:
    entry = REAL_LOCK["packages"]["node_modules/zustand"]
    assert entry["peerDependencies"]["react"], "the real lock's zustand no longer declares React as a peer"
    return copy.deepcopy(entry)


def test_an_optional_peer_is_not_followed_and_a_required_one_is(tmp_path: Path) -> None:
    # The lock entry as npm wrote it for the real `zustand`: React as a peer, marked optional.
    optional = real_zustand_entry()
    assert optional["peerDependenciesMeta"]["react"]["optional"] is True
    make_tree(
        tmp_path,
        shared_dependencies={"zustand": "^5.0.2"},
        packages={"zustand": optional, "react": lock_entry("19.3.1")},
    )
    code, output = run_check(tmp_path)
    assert code == 0, output
    # The same entry with the `optional` mark taken off: a required peer is installed, so React is resolved.
    required = copy.deepcopy(optional)
    del required["peerDependenciesMeta"]
    make_tree(
        tmp_path,
        shared_dependencies={"zustand": "^5.0.2"},
        packages={"zustand": required, "react": lock_entry("19.3.1")},
    )
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert "packages/glass-shared resolves react: packages/glass-shared > zustand > react" in output


# ---------------------------------------------------------------------------------------------------- bundles


@pytest.mark.parametrize(
    "marker",
    [
        'Symbol.for("react.transitional.element")',
        'Symbol.for("react.element")',
        'import{jsx}from"react/jsx-runtime";',
        'import{jsxDEV}from"react/jsx-dev-runtime";',
        'require("react-dom")',
    ],
)
def test_a_react_marker_in_a_served_bundle_fails(tree: Path, marker: str) -> None:
    write(tree / "apps/pages/dist/public/page.js", f"console.log('page');{marker}\n")
    code, output = run_check(tree)
    assert code == 1, output
    assert "apps/pages/dist/public/page.js carries the React marker" in output


def test_a_clean_served_bundle_passes_and_is_counted(tree: Path) -> None:
    write(tree / "apps/pages/dist/public/page.js", "console.log('a page with no framework');\n")
    code, output = run_check(tree)
    assert code == 0, output
    assert "1 bundle files" in output


# ---------------------------------------------------------------------------------------------------- blind spots


def test_a_shared_package_that_does_not_bundle_fails_in_a_line_and_not_a_stack_trace(tree: Path) -> None:
    write(tree / "packages/glass-shared/src/broken.ts", "export const = ;\n")
    code, output = run_check(tree)
    assert code == 1, output
    assert "packages/glass-shared cannot be bundled, so it cannot be checked:" in output
    assert "at async" not in output


def test_a_check_with_nothing_to_look_at_does_not_pass(tmp_path: Path) -> None:
    make_tree(tmp_path)
    (tmp_path / "package-lock.json").unlink()
    code, output = run_check(tmp_path)
    assert code == 1 and "package-lock.json not found" in output

    make_tree(tmp_path)
    lock = json.loads((tmp_path / "package-lock.json").read_text(encoding="utf-8"))
    del lock["packages"]["packages/glass-shared"]
    write(tmp_path / "package-lock.json", json.dumps(lock))
    code, output = run_check(tmp_path)
    assert code == 1 and "packages/glass-shared is not in package-lock.json" in output
