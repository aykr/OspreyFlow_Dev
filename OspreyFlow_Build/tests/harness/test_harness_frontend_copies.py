"""The harness image builds its own frontend (`apps/harness`) from a build context that copies only
named parts of `apps/workspace` (`harness/Dockerfile`'s `frontend-builder` stage). Every workspace
file the harness frontend reaches by import must be under one of those `COPY` lines, or the image
stops building while every local build, which sees the whole tree, still passes.

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

_IMPORT = re.compile(
    r"""^\s*(?:import|export)\b[^'"]*?from\s+['"]([^'"]+)['"]|^\s*import\s+['"]([^'"]+)['"]""",
    re.M,
)
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
    """Every file under `apps/workspace` the harness frontend's non-test sources reach by import."""
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
        if current.suffix == ".css":
            continue
        for match in _IMPORT.finditer(current.read_text(encoding="utf-8")):
            target = _resolve(current, match.group(1) or match.group(2))
            if target is None:
                continue
            if target.is_relative_to(WORKSPACE.resolve()):
                reached.add(target)
            pending.append(target)
    return reached


def _copied_workspace_paths() -> list[Path]:
    """The `apps/workspace/...` sources the frontend-builder stage copies."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    stage = text.split("AS frontend-builder", 1)[1].split("\nFROM ", 1)[0]
    return [
        (CORE / source).resolve()
        for source in re.findall(r"^COPY\s+(apps/workspace/\S+)\s+\S+\s*$", stage, re.M)
    ]


def test_every_workspace_file_the_harness_frontend_imports_is_copied_into_its_build() -> None:
    copied = _copied_workspace_paths()
    reached = _reached_workspace_files()
    assert reached, "the walk found nothing: the import pattern no longer matches the sources"
    missing = sorted(
        str(path.relative_to(CORE.resolve()))
        for path in reached
        if path.name != "package.json" and not any(path.is_relative_to(c) for c in copied)
    )
    assert missing == [], f"add a COPY to harness/Dockerfile's frontend-builder for: {missing}"


def test_the_walk_reaches_the_theme_module_the_admin_console_shares() -> None:
    """The case above is only as good as its walk: it must reach what the harness really imports."""
    reached = {str(p.relative_to(CORE.resolve())) for p in _reached_workspace_files()}
    assert "apps/workspace/src/theme/theme.ts" in reached
    assert "apps/workspace/src/theme/ThemeToggle.tsx" in reached
