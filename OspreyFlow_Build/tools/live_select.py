"""The live test files a change can reach (admin's T1 part 3, 10 November 2026).

    ../OspreyFlow_Core/.venv/bin/python -m tools.live_select [--base main] [--all] [--why]   (from OspreyFlow_Build)

prints one live test path per line, relative to OspreyFlow_Build, for the lane's change against `--base`
(`git diff --name-only --no-renames <merge-base>`, so a rename is its old path and its new one, plus untracked files).
`stack_lease.sh live <lane>` runs them.

- **The live set** is the Makefile's `test` target's `--ignore` list, read by `test_file_coverage_check`'s own parser:
  the files `make test` leaves out because they need a store. When T1 part 2's `pytest.mark.store` replaces that
  list, `Repo.live_set` reads the marks instead.
- **Each changed path** is decided by the first of:
  1. a rule in `tools/live_map.tsv` (a glob, then `none`, `all` or test paths), for the paths imports cannot see:
     documents, the Glass, configuration;
  2. for a Python file on disk, every live test file whose run imports it: its own imports, its package's
     `__init__` files, its conftest files', and theirs in turn, including imports inside functions and modules named
     in a string (the worker's job registry and the harness's sub-commands load modules so; an f-string's constant
     package prefix stands for every module under it);
  3. otherwise **the full set**: a path no rule covers is never taken to need nothing, and nor is a removed Python file.

  A rule whose selection starts with `+` **adds** to what the other two give, rather than deciding the path: for a
  live test that reads other Python files as text or loads them by glob, which imports cannot see. Every matching `+`
  rule adds.
- `tests/services/api/test_route_rights.py` is selected for every change (the lanes' rule), so the selection is never
  empty. A rule naming tests no live file matches is refused, so a typo cannot select nothing.

`--all` prints the full set, the nightly run on main. `--why` prints to stderr what each changed path chose.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from tools.test_file_coverage_check import makefile_test_ignored

ALWAYS = "tests/services/api/test_route_rights.py"
SKIP = frozenset({".venv", "node_modules", "__pycache__", ".git", ".pytest_cache"})
_DOTTED = re.compile(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)+")


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern[str]
    glob: str
    kind: str  # none, all, list, or add
    tests: tuple[str, ...]


class Repo:
    """One checkout: its modules, their imports, the live set and the map. A synthetic one for the tests."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path(__file__).resolve().parents[2]).resolve()
        self.core = self.root / "OspreyFlow_Core"
        self.build = self.root / "OspreyFlow_Build"
        # pytest.ini's pythonpath: the roots a module name is read against.
        self.roots = (self.core, self.core / "packages", self.core / "cli", self.build)
        self._imports: dict[Path, frozenset[Path]] = {}

    # --- the live set and the map ---------------------------------------------------------------------------

    @cached_property
    def live(self) -> list[str]:
        out: set[str] = set()
        for entry in makefile_test_ignored((self.build / "Makefile").read_text(encoding="utf-8")):
            target = self.build / entry
            if target.is_dir():
                out |= {str(p.relative_to(self.build)) for p in target.rglob("test_*.py") if not SKIP & set(p.parts)}
            else:
                out.add(entry)
        if ALWAYS not in out:
            raise SystemExit(f"{ALWAYS} is not in the Makefile's live set: the selection's floor is gone.")
        return sorted(out)

    def live_set(self) -> list[str]:
        """Every live test file, relative to OspreyFlow_Build."""
        return list(self.live)

    def matching(self, word: str) -> set[str]:
        """The live files a rule's word names: the file, or every one under the folder."""
        return {t for t in self.live if t == word or t.startswith(word.rstrip("/") + "/")}

    @cached_property
    def rules(self) -> list[Rule]:
        path = self.build / "tools" / "live_map.tsv"
        out = []
        for n, line in enumerate(path.read_text().splitlines() if path.exists() else [], 1):
            if not line.strip() or line.startswith("#"):
                continue
            glob, selects, *_ = line.split("\t")
            words = selects.split()
            if words[0] in ("none", "all"):
                rule = Rule(_glob(glob), glob, words[0], ())
            else:
                kind = "add" if words[0].startswith("+") else "list"
                tests = tuple(w.lstrip("+") for w in words)
                for t in tests:
                    if not self.matching(t):
                        raise SystemExit(f"live_map.tsv line {n}: {t!r} names no live test file, so it would select nothing.")
                rule = Rule(_glob(glob), glob, kind, tests)
            out.append(rule)
        return out

    # --- modules and imports --------------------------------------------------------------------------------

    def modules_of(self, path: Path) -> list[str]:
        names = []
        for root in self.roots:
            try:
                parts = list(path.relative_to(root).with_suffix("").parts)
            except ValueError:
                continue
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            if parts and all(p.isidentifier() for p in parts):
                names.append(".".join(parts))
        return names

    @cached_property
    def index(self) -> dict[str, Path]:
        index: dict[str, Path] = {}
        for top in (self.core, self.build):
            for p in top.rglob("*.py"):
                if SKIP & set(p.relative_to(self.root).parts):
                    continue
                for name in self.modules_of(p):
                    index.setdefault(name, p.resolve())
        return index

    def _named(self, dotted: str) -> set[Path]:
        """The files `import <dotted>` loads: the module and each package above it."""
        parts, out = dotted.split("."), set()
        for i in range(1, len(parts) + 1):
            f = self.index.get(".".join(parts[:i]))
            if f is not None:
                out.add(f)
        return out

    def _under(self, prefix: str) -> set[Path]:
        """Every module under a package prefix (`import_module(f"services.api.{name}")`)."""
        return {f for name, f in self.index.items() if name.startswith(prefix)} | self._named(prefix.rstrip("."))

    def _string(self, value: str) -> set[Path]:
        """A module a string names: `pkg.mod`, `pkg.mod:attr` or `pkg.mod.attr`."""
        dotted = value.partition(":")[0]
        if not _DOTTED.fullmatch(dotted):
            return set()
        if dotted in self.index:
            return self._named(dotted)
        base = dotted.rpartition(".")[0]
        return self._named(base) if base in self.index and "." in base else set()

    def imports(self, path: Path) -> frozenset[Path]:
        if path in self._imports:
            return self._imports[path]
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            tree = ast.Module(body=[], type_ignores=[])
        own = self.modules_of(path)
        package = (own[0] if path.name == "__init__.py" else own[0].rpartition(".")[0]) if own else ""
        out: set[Path] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    out |= self._named(alias.name)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    up = package.split(".") if package else []
                    up = up[: len(up) - (node.level - 1)] if node.level > 1 else up
                    base = ".".join([*up, base]) if base else ".".join(up)
                out |= self._named(base)
                for alias in node.names:
                    out |= self._named(f"{base}.{alias.name}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "." in node.value:
                out |= self._string(node.value)
            elif isinstance(node, ast.JoinedStr) and node.values and isinstance(node.values[0], ast.Constant):
                head = node.values[0].value
                if isinstance(head, str) and head.endswith(".") and _DOTTED.fullmatch(head.rstrip(".") + ".x"):
                    out |= self._under(head)
        out.discard(path)
        self._imports[path] = frozenset(out)
        return self._imports[path]

    def conftests(self, test: Path) -> list[Path]:
        out, d = [], test.parent
        while True:
            if (d / "conftest.py").exists():
                out.append((d / "conftest.py").resolve())
            if d == self.build or d == d.parent:
                return out
            d = d.parent

    def reach(self, test: str) -> set[Path]:
        """Every file a live test file's run loads: its imports, its package's `__init__` files (pytest imports
        them for a test beneath them), its conftest files and theirs, in turn."""
        start = (self.build / test).resolve()
        seen: set[Path] = set()
        todo = [start, *self.conftests(start)]
        for f in list(todo):
            for name in self.modules_of(f):
                todo.extend(self._named(name))
        while todo:
            f = todo.pop()
            if f not in seen:
                seen.add(f)
                todo.extend(self.imports(f))
        return seen


def _glob(pattern: str) -> re.Pattern[str]:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def select(changed: Iterable[str], repo: Repo | None = None, *, why: list[str] | None = None) -> list[str]:
    """The live test files the changed paths (relative to the repository root) can reach; never empty."""
    repo = repo or Repo()
    live = repo.live_set()
    chosen: set[str] = {ALWAYS}
    reaches: dict[str, set[Path]] | None = None
    note = why.append if why is not None else (lambda _: None)
    for c in changed:
        for rule in (r for r in repo.rules if r.kind == "add" and r.pattern.match(c)):
            for t in rule.tests:
                chosen |= repo.matching(t)
            note(f"{c}: live_map.tsv adds {' '.join(rule.tests)}")
        rule = next((r for r in repo.rules if r.kind != "add" and r.pattern.match(c)), None)
        if rule is not None:
            if rule.kind == "all":
                chosen |= set(live)
            elif rule.kind == "list":
                for t in rule.tests:
                    chosen |= repo.matching(t)
            note(f"{c}: live_map.tsv says {rule.kind if rule.kind != 'list' else ' '.join(rule.tests)}")
            continue
        p = (repo.root / c).resolve()
        if c.endswith(".py") and p.is_file():
            if reaches is None:
                reaches = {t: repo.reach(t) for t in live if (repo.build / t).is_file()}
            hit = {t for t, r in reaches.items() if p in r}
            chosen |= hit
            note(f"{c}: imported by {len(hit)} live test files")
            continue
        chosen |= set(live)
        note(f"{c}: no rule covers it{' (a removed Python file)' if c.endswith('.py') else ''}, so the full set")
    return sorted(chosen)


def changed_paths(repo: Repo, base: str) -> list[str]:
    """The lane's change against `base`: every path its diff names (a rename as both its paths), and untracked files."""
    git = ["git", "-C", str(repo.root)]
    merge_base = subprocess.run([*git, "merge-base", base, "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    tracked = subprocess.run(
        [*git, "diff", "--name-only", "--no-renames", merge_base], capture_output=True, text=True, check=True
    ).stdout
    untracked = subprocess.run([*git, "ls-files", "-o", "--exclude-standard"], capture_output=True, text=True, check=True).stdout
    return sorted((set(tracked.splitlines()) | set(untracked.splitlines())) - {""})


def main(argv: list[str] | None = None, repo: Repo | None = None) -> int:
    parser = argparse.ArgumentParser(description="The live test files a change can reach.")
    parser.add_argument("--base", default="main")
    parser.add_argument("--all", action="store_true", help="the full live set (the nightly run)")
    parser.add_argument("--why", action="store_true", help="say on stderr what each changed path chose")
    args = parser.parse_args(argv)
    repo = repo or Repo()
    why: list[str] = []
    picked = repo.live_set() if args.all else select(changed_paths(repo, args.base), repo, why=why)
    if args.why:
        for w in why:
            print(w, file=sys.stderr)
        print(f"{len(picked)} of {len(repo.live_set())} live test files.", file=sys.stderr)
    print("\n".join(picked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
