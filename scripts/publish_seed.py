"""`python -m scripts.publish_seed` — ADR-034 §B4/§B5: build the publishable tree as a new,
seeded git repository, so Trigger B is a rehearsed, scripted act rather than a manual, one-off
judgement made for the first time on the day it matters.

**What this produces.** From a given commit of this checkout (`HEAD` by default), copies every
git-tracked file that is not excluded from publication into a fresh directory, `git init`s it,
sets a neutral commit identity (ADR-034 §B5's own third, already-neutral identity: `OspreyFlow
<331628805+ospreyflow@users.noreply.github.com>` — not `git config --global`, which would touch
this checkout's own identity too), and makes a single initial commit. No `git clone`, no
`--mirror`, no history import of any kind: the seeded repository's own `git log` has exactly one
commit, by construction, not by a squash of many.

**`--dry-run` lists what would be included and excluded, by path, and does nothing else** — no
directory created, no git command run. The exclusion set is applied to every path `git ls-tree`
reports for the given commit, not the live working tree (so an uncommitted change is never
accidentally seeded, and a commit other than `HEAD` seeds exactly what was tracked then, not what
happens to be on disk now).

**The exclusion set is not `PRIVATE_TREE_MARKERS` alone, and a first version of this script that
used only that list leaked a real file — found running this round's own rehearsal, not assumed
safe from the constant's name.** `scripts.product_tree_link_check.PRIVATE_TREE_MARKERS` is scoped
correctly for what it was built for — flagging a citation inside an Apache-scoped document that
points at a private-tree file — and that gate deliberately does **not** treat `spec/06_DECISIONS.
md` as private, because `06_DECISIONS.md` is allowed to cite `process/`/`CLAUDE.md` freely; it
lives in `spec/` and is binding on this build the same footing as the numbered spec files
(ADR-031's own reasoning). But ADR-034 §B2 is explicit and separate: `06_DECISIONS.md` itself is
"Excluded and private" from the Apache 2.0/publication scope, even though it physically sits in
`spec/` — a location decision and a publication decision that ADR-034 §B2's own text says
"visibly disagree" for this one file. Reusing `PRIVATE_TREE_MARKERS` as this script's own
publication-exclusion set conflated the two axes and would have seeded `06_DECISIONS.md` — the
entire internal decision log, deliberation, mistakes and all — into a public repository.
`PUBLICATION_EXCLUSIONS` below is `PRIVATE_TREE_MARKERS` plus this one path, named separately so
the reason it differs is not lost the next time either list changes.

**What this does not do.** It does not push anywhere, does not create or touch any GitHub
repository or account, and does not decide the §B4 open items (organisation conversion, the
copyright year, per-file headers) — those are named, not resolved, in `07_BUILD_PLAN.md`'s own
Trigger B rehearsal entry. Trigger B itself remains an explicit, owner-only act; this script is
rehearsal tooling for the day it fires, not a step of firing it.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.product_tree_link_check import PRIVATE_TREE_MARKERS  # noqa: E402

#: ADR-034 §B5's own third identity table row — already neutral, not one of the two personal
#: identities that table exists to keep out of a published repository.
NEUTRAL_NAME = "OspreyFlow"
NEUTRAL_EMAIL = "331628805+ospreyflow@users.noreply.github.com"

#: This script's own exclusion set — `PRIVATE_TREE_MARKERS` plus `06_DECISIONS.md`, per ADR-034
#: §B2's explicit "Excluded and private" ruling on that one file. See this module's own docstring
#: for why the two lists are not the same one.
PUBLICATION_EXCLUSIONS: tuple[str, ...] = (*PRIVATE_TREE_MARKERS, "spec/06_DECISIONS.md")


def is_private_tree_path(rel_path: str) -> bool:
    """A path is excluded from publication if it equals a bare-file marker (`CLAUDE.md`,
    `.graphifyignore`, `spec/06_DECISIONS.md`) or sits under a directory marker (`process/`,
    `.claude/`). Deliberately not a substring match — `product_tree_link_check.py`'s own
    imprecise-on-purpose matching is right for scanning prose for a citation; a real file tree
    needs an exact path decision, not "contains the text somewhere," or a file merely named
    `not-process/thing.md` would be wrongly excluded."""
    for marker in PUBLICATION_EXCLUSIONS:
        if marker.endswith("/"):
            if rel_path == marker.rstrip("/") or rel_path.startswith(marker):
                return True
        elif rel_path == marker:
            return True
    return False


def list_tracked_files(commit: str, repo_root: Path = REPO_ROOT) -> list[str]:
    """Every path git tracked *at that commit* — not the live working tree, so an uncommitted
    change or a commit other than `HEAD` is handled correctly by construction."""
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def classify(paths: list[str]) -> tuple[list[str], list[str]]:
    """Returns `(included, excluded)`, both sorted, for a reproducible `--dry-run` listing."""
    included = sorted(p for p in paths if not is_private_tree_path(p))
    excluded = sorted(p for p in paths if is_private_tree_path(p))
    return included, excluded


def seed_tree(
    commit: str, dest_dir: Path, repo_root: Path = REPO_ROOT
) -> tuple[list[str], list[str]]:
    """Materialises every included file's content *as it was at `commit`* (via `git show`, not a
    working-tree copy) under `dest_dir`. Returns `(included, excluded)`. Does not initialise git —
    `init_neutral_repo` below does that as a separate, visible step."""
    included, excluded = classify(list_tracked_files(commit, repo_root))
    dest_dir.mkdir(parents=True, exist_ok=True)
    for rel in included:
        content = subprocess.run(
            ["git", "show", f"{commit}:{rel}"],
            cwd=repo_root,
            capture_output=True,
            check=True,
        ).stdout
        dst = dest_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(content)
    return included, excluded


def init_neutral_repo(dest_dir: Path) -> None:
    """`git init` plus a single initial commit, under the neutral identity, scoped to this one
    repository (`git config` with no `--global`) so the checkout that ran this script keeps its
    own identity untouched."""
    subprocess.run(["git", "init", "-q"], cwd=dest_dir, check=True)
    subprocess.run(["git", "config", "user.name", NEUTRAL_NAME], cwd=dest_dir, check=True)
    subprocess.run(["git", "config", "user.email", NEUTRAL_EMAIL], cwd=dest_dir, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest_dir, check=True)
    commit_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": NEUTRAL_NAME,
        "GIT_AUTHOR_EMAIL": NEUTRAL_EMAIL,
        "GIT_COMMITTER_NAME": NEUTRAL_NAME,
        "GIT_COMMITTER_EMAIL": NEUTRAL_EMAIL,
    }
    subprocess.run(
        ["git", "commit", "-q", "-m", "Initial commit"],
        cwd=dest_dir,
        check=True,
        env=commit_env,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD", help="Commit to seed from (default: HEAD).")
    parser.add_argument("--out", type=Path, help="Destination directory for the seeded tree.")
    parser.add_argument(
        "--dry-run", action="store_true", help="List included/excluded paths; create nothing."
    )
    args = parser.parse_args()

    included, excluded = classify(list_tracked_files(args.commit))

    if args.dry_run:
        print(f"publish-seed --dry-run: {len(included)} file(s) would be included, "
              f"{len(excluded)} excluded (private-tree):")
        for path in excluded:
            print(f"  EXCLUDE {path}")
        return 0

    if args.out is None:
        parser.error("--out is required unless --dry-run")
    seed_tree(args.commit, args.out)
    init_neutral_repo(args.out)
    print(
        f"publish-seed: seeded {len(included)} file(s) into {args.out}, "
        f"{len(excluded)} private-tree file(s) excluded, 1 commit, no inherited history."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
