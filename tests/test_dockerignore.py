"""`.dockerignore` — `spec/06_DECISIONS.md` ADR-035 §C2's named mechanism, and the build-context
half of ADR-034 §B7's two artefact-hygiene assertions. The file's own header has the full reasoning,
including why it is a defence for images that do not exist yet rather than a fix for a live leak.

**On the matcher.** `pathspec`'s gitignore matcher is the standard stand-in for Docker's own
`patternmatcher`, not the identical implementation — the two diverge on unanchored directory names
(gitignore matches at any depth, Docker's only at the context root). Every path asserted below is
either at the root or under an explicitly-rooted pattern, where the two agree, so the divergence
does not reach these assertions; anything added later that relies on depth behaviour needs checking
against `docker build` itself, not against this test alone. (`gitwildmatch`, the name most examples
still use, is deprecated as of `pathspec` 1.1.1 and emits a warning per pattern per spec built —
hence `gitignore` here, and hence the module-level cache below rather than one spec per
parametrised case.)

`pathspec` reaches this environment as a required dependency of `mypy`, which `make typecheck` and
`make ci` both already need. It is not declared directly in `pyproject.toml`. If that ever changes
this module fails at import — loudly, and in the safe direction: this test cannot go vacuously green
by losing its own matcher, which is the failure mode that would matter.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pathspec
import pytest
from scripts.product_tree_link_check import PRIVATE_TREE_MARKERS

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERIGNORE_PATH = REPO_ROOT / ".dockerignore"


def _spec(text: str) -> pathspec.PathSpec:
    return pathspec.PathSpec.from_lines("gitignore", text.splitlines())


@functools.lru_cache(maxsize=1)
def _repo_spec() -> pathspec.PathSpec:
    return _spec(DOCKERIGNORE_PATH.read_text(encoding="utf-8"))


#: Every path ADR-035 §C2 and ADR-034 §B7 require to stay out of a build context. Written as real
#: repository paths, not pattern strings — the question this file answers is "would this file reach
#: the daemon," which is a question about paths.
MUST_BE_EXCLUDED: tuple[str, ...] = (
    ".git/config",
    ".venv/bin/python",
    "node_modules/some-package/index.js",
    "apps/workspace/node_modules/some-package/index.js",
    "data/analytics.duckdb",
    "OspreyFlow_Data/enron/maildir.tar.gz",
    "OspreyFlow_Data/_local-runtime/analytics.duckdb",
    "backups/2026-09-24T00-00-00Z-local-lite-abc1234/manifest.json",
    "config/real_data_exceptions.yaml",
    "demo-data/enron/maildir.tar.gz",
    "tests/test_dockerignore.py",
    "tests/fixtures/product_tree_link_allowlist.txt",
    "process/07_BUILD_PLAN.md",
    "spec/design/OspreyFlow_Brand_Foundations.html",
    "process/archive/anything.md",
    "graphify-out/graph.json",
    ".playwright-mcp/trace.zip",
    ".claude/settings.json",
    ".claude/commands/phase.md",
    "CLAUDE.md",
    "process/prototypes/ingest-map/app.js",
    "deploy/compose/dev.yaml",
    "Claude outputs/note.md",
    "__pycache__/x.cpython-312.pyc",
    "scripts/__pycache__/licence_check.cpython-312.pyc",
)

#: The other half, and the half that makes the list above mean something: a `.dockerignore` that
#: excluded everything would pass every assertion above and produce an unbuildable image.
MUST_BE_INCLUDED: tuple[str, ...] = (
    "packages/schemas/domain.py",
    "packages/schemas/mapconfig.py",
    "packages/ports/graph.py",
    "packages/adapters/graph_arcadedb/client.py",
    "services/api/app.py",
    "services/ingest/staging.py",
    "apps/workspace/src/main.tsx",
    "pyproject.toml",
    "uv.lock",
    "osprey.yaml",
    "README.md",
    # Round 14a (Trigger A): `06_DECISIONS.md` moved to `spec/` as product spec, no longer a
    # private-tree marker; `tokens.css` moved out of `spec/design/` into the product tree
    # entirely, so it is now ordinary product source needing no exception at all.
    "spec/06_DECISIONS.md",
    "apps/workspace/src/design/tokens.css",
)


def test_the_dockerignore_file_exists() -> None:
    """ADR-035 §C2 names it; before 24 September 2026 it did not exist, which is the gap this file
    and its test close."""
    assert DOCKERIGNORE_PATH.is_file()


@pytest.mark.parametrize("path", MUST_BE_EXCLUDED)
def test_private_and_local_paths_are_excluded_from_the_build_context(path: str) -> None:
    assert _repo_spec().match_file(path), f"{path} would be sent to the Docker daemon"


@pytest.mark.parametrize("path", MUST_BE_INCLUDED)
def test_product_source_is_not_excluded(path: str) -> None:
    assert not _repo_spec().match_file(path), f"{path} is product source and must reach the build"


def test_every_private_tree_marker_resolves_to_a_real_path_that_is_excluded() -> None:
    """Imports `PRIVATE_TREE_MARKERS` from `scripts/product_tree_link_check.py` rather than
    restating it — the same "imported rather than redeclared" precedent ADR-034 §B9 set when that
    gate reused `route_coverage_check.py`'s own `APACHE_DOC_PATHS`. A marker added there must not
    silently go unexcluded here.

    The `resolved` counter is the vacuity guard: a loop over markers that happen to match no real
    file asserts nothing, and would pass just as well against an empty `.dockerignore`.
    """
    spec = _repo_spec()
    resolved = 0
    for marker in PRIVATE_TREE_MARKERS:
        # A directory marker (round 14a: `process/`, `.claude/`) must glob *into* it, not just
        # match the directory's own name — `**/process*` matches the `process` directory itself
        # (skipped below, not a file) and nothing inside it, which would let this whole marker
        # contribute zero real files without the loop's own vacuity guard ever noticing.
        pattern = f"**/{marker.rstrip('/')}/**" if marker.endswith("/") else f"**/{marker}"
        for real_path in REPO_ROOT.glob(pattern):
            if not real_path.is_file():
                continue
            rel = real_path.relative_to(REPO_ROOT).as_posix()
            resolved += 1
            assert spec.match_file(rel), f"private-tree marker {marker!r} reachable at {rel}"
    assert resolved >= len(PRIVATE_TREE_MARKERS) - 2, (
        f"only {resolved} real file(s) matched any private-tree marker — the loop above is not "
        f"actually checking anything"
    )


# --- Rule 15, second clause ---------------------------------------------------
#
# `CLAUDE.md` rule 15: "An injection that any default-deny fallthrough would have caught proves
# nothing about the specific branch it was meant to exercise." A `.dockerignore` has no fallthrough
# — an unmatched path is *included* — so the analogous trap is the opposite one: a path that some
# broader pattern already excludes, credited to the specific line meant to exclude it. The two cases
# below delete one line each and assert the path it names stops being excluded, which is the only
# way to show that line is load-bearing rather than shadowed.


def _without_line(needle: str) -> pathspec.PathSpec:
    text = DOCKERIGNORE_PATH.read_text(encoding="utf-8")
    kept = [line for line in text.splitlines() if line.strip() != needle]
    assert len(kept) == len(text.splitlines()) - 1, (
        f"expected exactly one line equal to {needle!r} in .dockerignore; "
        f"removed {len(text.splitlines()) - len(kept)}"
    )
    return _spec("\n".join(kept))


def test_the_real_data_exceptions_line_is_what_excludes_the_real_data_exceptions_file() -> None:
    """The planted path is the real one — `config/real_data_exceptions.yaml`, the shape
    `scripts/real_data_exceptions.py`'s own `CONFIG_PATH` actually resolves to — not a
    hand-written approximation. With its line removed it is included, so the assertion in
    `MUST_BE_EXCLUDED` above is attributable to that line and to nothing else.
    """
    assert _repo_spec().match_file("config/real_data_exceptions.yaml")
    assert not _without_line("config/real_data_exceptions.yaml").match_file(
        "config/real_data_exceptions.yaml"
    )


def test_the_claude_md_line_is_what_excludes_claude_md() -> None:
    """`CLAUDE.md` is the one `PRIVATE_TREE_MARKERS` entry sitting at the repository root rather
    than under `docs/`, so no directory rule shadows it — exactly the case most likely to be assumed
    covered."""
    assert _repo_spec().match_file("CLAUDE.md")
    assert not _without_line("CLAUDE.md").match_file("CLAUDE.md")


# --- tokens.css moved into the product tree at Trigger A (round 14a, ADR-034 §B8); it needs no
# negation exception any more (see tests/harness/test_service_inventory.py for its own coverage
# of that move) — the three tests that used to prove the negation mechanism here were deleted with
# the mechanism itself, not repaired.
