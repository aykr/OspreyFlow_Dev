"""Where a repository path lives, now that the tree has three folders (`06_DECISIONS.md` ADR-054).

Documents, checks and tests name files by their repository-relative name: `spec/06_DECISIONS.md`,
`harness/apply.py`. Those names are kept as *logical names* (rewriting the hundreds of places that
cite them was rejected), and this module maps a logical name to the folder it lives in. It is the
one place that knows the layout.

    OspreyFlow_Core   the product
    OspreyFlow_Build  spec, tests, process, these tools and the Claude material
    OspreyFlow_Data   datasets; nothing here is committed
    (root)            .git, .github, Makefile, .claude and the CLAUDE.md pointer

`REPO` is a path to the repository root that maps the first segment of whatever is appended, so code
written as `REPO / "spec" / "x.md"` still finds the file. Everything below the first segment is an
ordinary path.
"""

from __future__ import annotations

from pathlib import Path, PurePath

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "OspreyFlow_Build"
DATA = ROOT / "OspreyFlow_Data"
#: The product folder.
CORE = ROOT / "OspreyFlow_Core"

#: First segments that live in the Build folder.
BUILD_NAMES = frozenset(
    {
        "spec",
        "tests",
        "process",
        "tools",
        "CLAUDE.md",
        ".graphifyignore",
        "graphify-out",
        ".graphify",
        ".impeccable",
        "Claude outputs",
        "dist",
        "pytest.ini",
    }
)
#: First segments that must stay at the root because a tool requires it.
ROOT_NAMES = frozenset({".git", ".gitignore", ".github", ".claude"})
#: The three folders themselves, when a name already carries one.
FOLDER_NAMES = frozenset({"OspreyFlow_Core", "OspreyFlow_Build", "OspreyFlow_Data"})


def home(logical: str | PurePath) -> Path:
    """The real path of a logical name."""
    parts = PurePath(logical).parts
    if not parts:
        return ROOT
    first = parts[0]
    if first in BUILD_NAMES:
        base = BUILD
    elif first in ROOT_NAMES or first in FOLDER_NAMES:
        base = ROOT
    else:
        base = CORE
    return base.joinpath(*parts)


def logical(path: Path) -> str:
    """The logical name of a real path (the reverse of `home`), for messages and allowlists."""
    resolved = path.resolve() if path.is_absolute() else path
    for base in (BUILD, DATA, CORE, ROOT):
        try:
            relative = resolved.relative_to(base)
        except ValueError:
            continue
        name = relative.as_posix()
        if base == DATA:
            return f"{DATA.name}/{name}"
        return name
    return resolved.as_posix()


class _LogicalRoot(type(Path())):  # type: ignore[misc]
    """The repository root, which maps the first segment appended to it."""

    def __truediv__(self, key: str | PurePath) -> Path:  # type: ignore[override]
        if PurePath(key).is_absolute():
            return Path(key)
        return home(key)

    def joinpath(self, *others: str | PurePath) -> Path:  # type: ignore[override]
        if not others:
            return Path(self)
        return home(others[0]).joinpath(*others[1:])


REPO: Path = _LogicalRoot(ROOT)


def at(root: Path, logical_name: str) -> Path:
    """`logical_name` under `root`: mapped when `root` is `REPO`, plain for any other root (the
    checks are also run against small throwaway repositories that have no three folders)."""
    return root / logical_name


def rel(path: Path, root: Path = REPO) -> str:
    """`path` as a logical name: mapped back when `root` is the repository, plain otherwise."""
    if isinstance(root, _LogicalRoot):
        return logical(path)
    return path.relative_to(root).as_posix()
