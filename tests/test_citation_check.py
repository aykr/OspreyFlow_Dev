"""`scripts/citation_check.py`'s own red-then-green demonstration.

`CLAUDE.md` rule 15: a gate's first green is not a result. This gate was written *because* it was
already red — three citations to files that had never existed, found by accident in one afternoon
on 25 September 2026 — so its red state is on record before its green one. These cases keep it
that way, because the real violations have since been corrected and a gate that has only ever seen
content it passes has been exercised, not tested.

**The planted violation takes the shape the real ones took**: a backticked repository path with a
source extension, inside a comment or a document, naming something that is not there. Not a
hand-written string fed to the matcher — the check has to fail on a file laid out the way the
repository's own files are.
"""

from __future__ import annotations

from pathlib import Path

from scripts.citation_check import citations_in, find_broken, load_allowlist


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """A miniature repository with the directory layout the gate scans."""
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return tmp_path


def test_a_citation_to_a_file_that_does_not_exist_is_flagged(tmp_path: Path) -> None:
    """Red. The real shape: `apps/workspace/Dockerfile` cited a `tests/harness/…py` that had never
    been written, and the sentence around it was true, which is why reading did not catch it."""
    root = _repo(
        tmp_path,
        {
            "services/api/history.py": (
                '"""The narrower-clearance case is '
                '`tests/services/api/test_history.py`\'s job."""\n'
            ),
        },
    )

    broken = find_broken(root)

    assert len(broken) == 1, broken
    assert "tests/services/api/test_history.py" in broken[0]
    assert "services/api/history.py:1" in broken[0]


def test_a_citation_to_a_file_that_exists_is_not_flagged(tmp_path: Path) -> None:
    """Green, and it must be the *same* citation — otherwise the case above could be passing
    because the matcher flags everything."""
    root = _repo(
        tmp_path,
        {
            "services/api/history.py": (
                '"""The narrower-clearance case is '
                '`tests/services/api/test_history.py`\'s job."""\n'
            ),
            "tests/services/api/test_history.py": "def test_it() -> None: ...\n",
        },
    )

    assert find_broken(root) == []


def test_prose_that_is_not_a_file_citation_is_left_alone(tmp_path: Path) -> None:
    """A gate that fires on prose is one people learn to ignore.

    `docs/` and `packages/adapters/<name>` are a directory and a placeholder; neither is a claim
    that a file exists, and both appear throughout this repository's own documents.
    """
    root = _repo(
        tmp_path,
        {
            "docs/00_ARCHITECTURE.md": (
                "Adapters live in `packages/adapters/<name>`. The pack is in `docs/`.\n"
                "Ports are `Protocol` classes in `packages/ports`.\n"
            )
        },
    )

    assert find_broken(root) == []


def test_an_allowlisted_path_is_not_flagged(tmp_path: Path) -> None:
    """`config/real_data_exceptions.yaml` is gitignored by design and every citation of it is a
    citation of something correctly absent. Without an allowlist this gate could not be green on
    this repository at all, which would make it a gate nobody runs."""
    root = _repo(
        tmp_path,
        {
            "scripts/real_data_exceptions.py": (
                '"""Reads `config/real_data_exceptions.yaml` when present."""\n'
            ),
            "tests/fixtures/citation_allowlist.txt": (
                "# gitignored by design\nconfig/real_data_exceptions.yaml\n"
            ),
        },
    )

    # `find_broken` reads the repository's own allowlist, not the miniature one, so this asserts
    # the entry is really there rather than that the mechanism could work.
    assert "config/real_data_exceptions.yaml" in load_allowlist()
    assert find_broken(root) == []


def test_the_extractor_reads_a_backticked_path_and_nothing_else() -> None:
    """The matcher's own boundary, asserted directly so a widening is deliberate."""
    assert citations_in("see `tests/a/b_test.py` and `scripts/x.py`") == [
        "tests/a/b_test.py",
        "scripts/x.py",
    ]
    assert citations_in("see tests/a/b_test.py") == [], "an unbackticked path is not a citation"
    assert citations_in("`node_modules/left-pad/index.js`") == [], (
        "a vendored path is not this repository's own claim"
    )
    assert citations_in("`docs/`") == [], "a directory is not a file citation"


def test_the_repository_itself_is_clean() -> None:
    """The gate's current state, asserted so a new broken citation fails a test rather than
    waiting to be noticed by accident — which is how all three of the originals were found."""
    broken = find_broken()

    assert broken == [], "new citation(s) name a file that does not exist:\n  " + "\n  ".join(
        broken
    )
