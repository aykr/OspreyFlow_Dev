"""Core stands alone (`06_DECISIONS.md` ADR-114 decision 1, Amendment 2 rulings 1 and 3): nothing
committed in the product folder names this one, its Makefile's own recipes run without it, the gates
live in this folder's Makefile, and the root Makefile sends each target to the folder that has it.

What a mistake would do, and the case that catches it:
- a recipe, script or config in Core reaching into `../OspreyFlow_Build` again —
  `test_nothing_committed_in_core_names_the_build_folder`;
- a gate left in Core's Makefile, or Core's own `check` needing a Build tool —
  `test_cores_makefile_recipes_run_without_this_folder`;
- a gate dropped in the move — `test_builds_ci_runs_cores_check_and_every_gate`;
- the root Makefile sending a gate to Core, or a product target to Build —
  `test_the_root_makefile_sends_each_target_where_it_lives`;
- `harness bundle` still dispatching to a Build module — `test_the_harness_no_longer_bundles`.
"""

from __future__ import annotations

import re
import subprocess

from tools.layout import BUILD, CORE, ROOT

#: The gates `make ci` ran from Core before the move (ADR-114 Amendment 2), every one kept.
GATES = (
    "licence-check", "schemas-check", "authorized-query-check", "demo-guide-check",
    "domain-model-coverage-check", "route-coverage-check", "product-tree-link-check",
    "decision-log-publication-check", "provenance-annotation-check", "test-file-coverage-check",
    "citation-check", "conformance-guard", "bundle",
)  # fmt: skip


def _committed_core_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "OspreyFlow_Core"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout  # fmt: skip
    return [line for line in out.splitlines() if line]


def _recipes(makefile: str) -> dict[str, list[str]]:
    """Each target's recipe lines (tab-indented), joined over trailing backslashes."""
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in makefile.splitlines():
        head = re.match(r"^([A-Za-z0-9_.-]+):(?!=)", line)
        if head:
            current = head.group(1)
            found.setdefault(current, [])
        elif line.startswith("\t") and current is not None:
            found[current].append(line.strip())
        elif line and not line.startswith("#") and not line.startswith("\t"):
            current = None
    return found


def test_nothing_committed_in_core_names_the_build_folder() -> None:
    offenders = []
    for name in _committed_core_files():
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        if "OspreyFlow_Build" in text:
            offenders.append(name)
    assert offenders == [], f"Core names the Build folder in: {offenders}"


def test_cores_makefile_recipes_run_without_this_folder() -> None:
    recipes = _recipes((CORE / "Makefile").read_text(encoding="utf-8"))
    assert "check" in recipes, "Core keeps a check target of its own gates"
    leaking = {t: r for t, r in recipes.items() if any("tools." in line or "../" in line for line in r)}
    assert leaking == {}, f"Core recipes that need another folder: {sorted(leaking)}"
    assert not set(GATES) & set(recipes), "every gate moved to Build's Makefile"


def test_builds_ci_runs_cores_check_and_every_gate() -> None:
    makefile = (BUILD / "Makefile").read_text(encoding="utf-8")
    ci = re.search(r"^ci:(.*)$", makefile, re.MULTILINE)
    assert ci is not None, "Build's Makefile has a ci target"
    assert set(GATES) <= set(ci.group(1).split()), "ci depends on every gate"
    assert "core-check" in ci.group(1).split(), "ci runs Core's own check"
    assert set(GATES) <= set(_recipes(makefile)), "each gate is a target in Build's Makefile"


def test_the_root_makefile_sends_each_target_where_it_lives() -> None:
    def dry(target: str) -> str:
        return subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True, text=True).stdout

    assert "tools.route_coverage_check" in dry("route-coverage-check")
    assert "scripts.launch" in dry("launch")


def test_the_harness_no_longer_bundles() -> None:
    dispatcher = (CORE / "harness" / "__main__.py").read_text(encoding="utf-8")
    assert "osprey_bundle" not in dispatcher and '"bundle"' not in dispatcher
