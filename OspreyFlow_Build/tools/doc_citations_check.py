"""`python -m tools.doc_citations_check` — every cited repository path names a file that exists.

## Why this gate exists

This project's whole discipline rests on naming the test. `CLAUDE.md` rule 12 makes "which test
would fail if this were violated?" part of stating an invariant, and rule 15 makes a red-then-green
demonstration part of shipping a gate. Both are enforced socially, in prose, by writing the test's
path into the comment or the document beside the claim.

**A named test that does not exist is worse than no name at all**, because it reads as a guarantee.
Someone deciding whether to trust an invariant sees a path, assumes the case was written, and moves
on. Nothing in the repository disagrees with them.

**Three such citations were found on 25 September 2026, in one afternoon, by accident:**

- `apps/workspace/Dockerfile` cited `tests/harness/test_workspace_image.py` as asserting that its
  `tokens.css` COPY "has something to copy". That file has never existed.
- `apps/workspace/keyboard/actionRegistry.ts` cited `check-registry-coverage.mjs`, "a plain Node
  script", as the static half of its keyboard-coverage mechanism. That file has never existed
  either; the real mechanism is `registryCoverage.test.ts`, which does exist and does that job.
- `06_DECISIONS.md`'s ADR-049 amendment 21 and `07_BUILD_PLAN.md` both repeated the second one,
  having copied it from the docstring.

None was malicious and none was even careless in the ordinary sense — each named a mechanism that
was real, with a filename that had drifted or been planned and never written. That is exactly why a
person cannot catch this class by reading: the sentence around the path is true.

## What it checks, and what it deliberately does not

It extracts **backticked paths** — the convention this repository uses for every file reference —
that look like repository paths with a source extension, and asserts each resolves to a file. A
path is only considered when it carries an extension this project actually writes
(`EXTENSIONS` below), which keeps it away from prose like `docs/` or `packages/adapters/<name>`.

**It does not check that the cited file contains what the sentence claims.** That would be the
better gate and it is not buildable: "asserts this COPY has something to copy" is not mechanically
comparable to a test body. This gate closes the crude half — the file is not there at all — which
is the half all three real instances fell into.

**Gitignored paths pass without an allowlist entry.** A citation of a path matched by the
repository's own `.gitignore` — `config/real_data_exceptions.yaml` is the real instance, per
`CLAUDE.md` rule 9 / ADR-035 §C3 — is a reference to something correctly absent from every clone,
the same way `tests/test_dockerignore.py` already treats `.dockerignore` matches as the ground
truth for what a build context excludes. `pathspec`'s gitignore matcher is the standard stand-in,
already a dependency (of `mypy`, which `make typecheck` requires) and already used that way there.

**Allowlist.** `tests/fixtures/citation_allowlist.txt`, one path per line, for anything else that is
deliberately absent and not covered by `.gitignore` — a file a record says was deleted, or a path
named as an example of what *not* to do. Each entry needs a stated reason in a comment above it.
Empty (and absent) on this repository today: every non-gitignored absence found on 25 September
2026 was corrected in place rather than allowlisted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path, PurePath

import pathspec

from tools.layout import REPO as REPO_ROOT
from tools.layout import rel

ALLOWLIST_PATH = REPO_ROOT / "tests" / "fixtures" / "citation_allowlist.txt"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"

#: Files that moved, old path to new. A document written before a move still names the old path;
#: that citation is history and is not rewritten (ADR-054), so it is accepted when the file is at
#: its new location. Not a pass for a file that exists at neither.
MOVED: dict[str, str] = {
    f"tests/scenarios/fixtures/{name}": f"packages/demo_fixtures/{name}"
    for name in (
        "hmp.py",
        "hmp_graph.py",
        "hmp_population.py",
        "fixture_corp.py",
        "fixture_corp_resolution.py",
        "cdr.py",
        "seizure_record.py",
        "scenario_cohorts.py",
        "hmp_yards_recipe.yaml",
        "hmp_persons_recipe.yaml",
        "hmp_families_recipe.yaml",
        "hmp_groups_recipe.yaml",
        "hmp_associates_recipe.yaml",
        "hmp_reports_recipe.yaml",
    )
}

#: The tools that moved from `scripts/` to `tools/` (ADR-054 amendment): a record that cites the old
#: name is history and stays as written.
_MOVED_TOOLS = (
    "authorized_query_check.py",
    "ci_status_check.py",
    "decision_log_publication_check.py",
    "demo_guide_check.py",
    "doc_citations_check.py",
    "doc_site.py",
    "domain_model_coverage_check.py",
    "idp_test_realm.py",
    "licence_check.mjs",
    "licence_check.py",
    "mint_dev_token.py",
    "osprey_bundle.py",
    "packaging_gate.py",
    "product_tree_link_check.py",
    "provenance_annotation_check.py",
    "publish_seed.py",
    "release_local.py",
    "route_coverage_check.py",
    "schemas_check.py",
    "simple_markdown.py",
    "test_file_coverage_check.py",
    "update_golden_baseline.py",
)
MOVED.update({f"scripts/{name}": f"tools/{name}" for name in _MOVED_TOOLS})

#: Where citations live. Documents and the code comments that carry the "name the test" habit.
SEARCH_ROOTS: tuple[str, ...] = (
    "spec", "process", "tools", "apps", "services", "packages", "scripts", "harness",
)

#: File types whose own text is scanned. Not `.json`/`.lock`/`.yaml` — a path in a config file is a
#: configured path, not a citation, and it is already enforced by whatever reads it.
SCANNED_SUFFIXES = frozenset({".md", ".py", ".ts", ".tsx", ".mjs", ".css"})

#: Extensions that make a backticked token a *file* citation rather than prose. A bare `docs/` or
#: `packages/adapters/<name>` is a directory or a placeholder and is not checked.
EXTENSIONS = ("py", "ts", "tsx", "mjs", "css", "html", "yaml", "yml", "sh", "toml")

#: A backticked repository path. Anchored on the directories this project actually has, so a
#: backticked `node_modules/x.js` from quoted upstream output is not treated as our own claim.
CITATION = re.compile(
    r"`((?:docs|apps|services|packages|scripts|tools|harness|tests|deploy|config)/"
    r"[A-Za-z0-9_./-]+\.(?:" + "|".join(EXTENSIONS) + r"))`"
)

#: Skipped wholesale. `graphify-out` is generated, `.venv`/`node_modules` are vendored, and a
#: citation inside this gate's own docstring is a description of the problem, not an instance.
SKIP_DIRECTORIES = frozenset({"node_modules", ".venv", "graphify-out", "dist", "__pycache__"})
SKIP_FILES = frozenset({"tools/doc_citations_check.py", "tests/test_doc_citations_check.py"})


def load_allowlist(path: Path = ALLOWLIST_PATH) -> set[str]:
    if not path.exists():
        return set()
    return {
        line.strip().split()[0]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def load_gitignore_spec(root: Path = REPO_ROOT) -> pathspec.PathSpec:
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        return pathspec.PathSpec.from_lines("gitignore", [])
    return pathspec.PathSpec.from_lines(
        "gitignore", gitignore_path.read_text(encoding="utf-8").splitlines()
    )


def scanned_files(root: Path = REPO_ROOT) -> list[Path]:
    found = []
    for directory in SEARCH_ROOTS:
        base = root / directory
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            if SKIP_DIRECTORIES & set(PurePath(rel(path, root)).parts):
                continue
            if str(rel(path, root)) in SKIP_FILES:
                continue
            found.append(path)
    return sorted(found)


def citations_in(text: str) -> list[str]:
    """Every backticked repository path with a source extension, in order of appearance."""
    return CITATION.findall(text)


def find_broken(root: Path = REPO_ROOT) -> list[str]:
    """`"<citing file>:<line>: <cited path>"` for every citation naming a file that is not there."""
    allowlist = load_allowlist()
    gitignore = load_gitignore_spec(root)
    broken = []
    for path in scanned_files(root):
        relative = str(rel(path, root))
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            for cited in citations_in(line):
                if (
                    cited in allowlist
                    or (root / cited).exists()
                    or (root / MOVED.get(cited, cited)).exists()
                    or gitignore.match_file(cited)
                ):
                    continue
                broken.append(f"{relative}:{number}: cites '{cited}', which does not exist")
    return broken


def main() -> int:
    broken = find_broken()
    if broken:
        print(
            f"doc-citations-check: {len(broken)} citation(s) name a file that does not exist. A "
            "named test that is not there reads as a guarantee and is worse than no name:",
            file=sys.stderr,
        )
        for problem in broken:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nEither correct the path, write the file, or add it to "
            f"{rel(ALLOWLIST_PATH, REPO_ROOT)} with a stated reason.",
            file=sys.stderr,
        )
        return 1
    print(f"doc-citations-check: {len(scanned_files())} file(s) scanned, every cited path exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
