"""The harness image builds its own frontend (`apps/harness`) from a build context that copies only
named parts of `apps/workspace` and of `packages/design` (`harness/Dockerfile`'s `frontend-builder`
stage). Every file of those two folders the harness frontend reaches by import must be under one of
those `COPY` lines, or the image stops building while every local build, which sees the whole tree,
still passes. (`packages/design` joined the walk with PL4b, when `tokens.css` moved there: before, the
walk followed imports into `apps/workspace` only, and a `COPY packages/design` removed from the stage
would have passed. The three stylesheets that moved after it, PL4b2, joined it too: the walk
follows a stylesheet's `@import`, so `primitives.css` reaches `scale.css` and `panelType.css`.)

It has happened twice: on 9 October 2026, when the admin console first imported the Glass's theme
module, and on 31 October 2026, when that module began importing `src/brand/brand.ts` (ADR-132).
This case follows the imports, so the third time fails here rather than in the image build.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.layout import CORE

DOCKERFILE = CORE / "harness" / "Dockerfile"
HARNESS_SRC = CORE / "apps" / "harness" / "src"
WORKSPACE = CORE / "apps" / "workspace"
DESIGN = CORE / "packages" / "design"

_IMPORT = re.compile(
    r"""^\s*(?:import|export)\b[^'"]*?from\s+['"]([^'"]+)['"]|^\s*import\s+['"]([^'"]+)['"]""",
    re.M,
)
_CSS_IMPORT = re.compile(r"""^\s*@import\s+(?:url\()?\s*['"]([^'"]+)['"]""", re.M)
_SUFFIXES = ("", ".ts", ".tsx", ".css", "/index.ts", "/index.tsx")


def _resolve(importer: Path, spec: str) -> Path | None:
    if not spec.startswith("."):
        return None  # a package, installed by `npm ci`
    base = (importer.parent / spec).resolve()
    for suffix in _SUFFIXES:
        candidate = Path(str(base) + suffix)
        if candidate.is_file():
            return candidate
    return None


def _reached_workspace_files() -> set[Path]:
    """Every file under `apps/workspace` or `packages/design` the harness frontend's non-test sources
    reach by import."""
    pending = [
        path
        for path in HARNESS_SRC.rglob("*")
        if path.suffix in {".ts", ".tsx"} and ".test." not in path.name
    ]
    seen: set[Path] = set()
    reached: set[Path] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        text = current.read_text(encoding="utf-8")
        if current.suffix == ".css":
            # A stylesheet reaches what it `@import`s (`primitives.css` pulls in `./scale.css`
            # and `./panelType.css`).
            specs = [m.group(1) for m in _CSS_IMPORT.finditer(text)]
        else:
            specs = [m.group(1) or m.group(2) for m in _IMPORT.finditer(text)]
        for spec in specs:
            target = _resolve(current, spec)
            if target is None:
                continue
            if target.is_relative_to(WORKSPACE.resolve()) or target.is_relative_to(DESIGN.resolve()):
                reached.add(target)
            pending.append(target)
    return reached


def _copied_paths(dockerfile: str | None = None) -> list[Path]:
    """The `apps/workspace/...` and `packages/design...` sources the frontend-builder stage copies."""
    text = dockerfile if dockerfile is not None else DOCKERFILE.read_text(encoding="utf-8")
    stage = text.split("AS frontend-builder", 1)[1].split("\nFROM ", 1)[0]
    return [
        (CORE / source).resolve()
        for source in re.findall(
            r"^COPY\s+(apps/workspace/\S+|packages/design(?:/\S*)?)\s+\S+\s*$", stage, re.M
        )
    ]


def _missing(copied: list[Path], reached: set[Path]) -> list[str]:
    return sorted(
        str(path.relative_to(CORE.resolve()))
        for path in reached
        if path.name != "package.json" and not any(path.is_relative_to(c) for c in copied)
    )


def test_every_workspace_file_the_harness_frontend_imports_is_copied_into_its_build() -> None:
    reached = _reached_workspace_files()
    assert reached, "the walk found nothing: the import pattern no longer matches the sources"
    missing = _missing(_copied_paths(), reached)
    assert missing == [], f"add a COPY to harness/Dockerfile's frontend-builder for: {missing}"


def test_the_walk_reaches_the_design_tokens_in_packages_design() -> None:
    reached = {str(p.relative_to(CORE.resolve())) for p in _reached_workspace_files()}
    assert "packages/design/tokens.css" in reached


def test_the_walk_reaches_primitives_css_and_the_two_it_imports_in_packages_design() -> None:
    """`primitives.css` moved to `packages/design` with `scale.css` and `panelType.css` (PL4b2): the
    entrance imports the first, and the first imports the other two by `./`, so the walk follows
    `@import` inside `packages/design` too."""
    reached = {str(p.relative_to(CORE.resolve())) for p in _reached_workspace_files()}
    for name in ("primitives.css", "scale.css", "panelType.css"):
        assert f"packages/design/{name}" in reached, f"the walk does not reach {name}"
        assert f"apps/workspace/src/design/{name}" not in reached


def test_the_stage_without_its_copy_of_packages_design_is_found() -> None:
    """Red for the line this change adds (rule 15): the real stage, with only that line taken out, as
    the shape the Dockerfile really has, is missing exactly the tokens file."""
    real = DOCKERFILE.read_text(encoding="utf-8")
    line = "COPY packages/design ./packages/design\n"
    assert line in real, "harness/Dockerfile no longer copies packages/design"
    assert _missing(_copied_paths(real), _reached_workspace_files()) == []
    planted = real.replace(line, "", 1)
    assert _missing(_copied_paths(planted), _reached_workspace_files()) == sorted(
        f"packages/design/{name}"
        for name in ("panelType.css", "primitives.css", "scale.css", "tokens.css")
    )


def test_the_walk_reaches_the_theme_module_the_admin_console_shares() -> None:
    """The case above is only as good as its walk: it must reach what the harness really imports."""
    reached = {str(p.relative_to(CORE.resolve())) for p in _reached_workspace_files()}
    assert "apps/workspace/src/theme/theme.ts" in reached
    assert "apps/workspace/src/theme/ThemeToggle.tsx" in reached
