"""A maintainer's manifest of the product tree at a git ref (ADR-114 Amendment 51).

    python -m scripts.maintainer_manifest --ref <commit-or-tag> --out <folder>
        [--repo <folder>] [--rules <file>] [--maintained-under <file>] [--check-areas]

It writes two files into `--out`:

* `maintainer-manifest.csv`: one row per tracked file, with the columns `path`, `area`, `language`,
  `lines`, `bytes`,
  `is_test`, `is_generated`, `release_images`; and, only when `--maintained-under` names a second
  rules file, a last
  column `maintained_under`;
* `maintainer-manifest.md`: a short summary, one row per folder.

**What it reads.** The tracked files at the ref and nothing from the working tree: the object
database is read with dulwich (`iter_tree_contents` for the list, one blob at a time for the
bytes). It is dulwich, not `git ls-tree` and `git cat-file`, because the `api` image copies
`scripts/` and carries no `git` executable, and the manifest must be runnable from the tree alone
wherever it is checked out. No copy of the tree is written to disk, so an untracked, ignored or
edited file cannot get in, and a clone elsewhere gives the same answer. The one exception is the
isolation check (`scripts/no_react_check.mjs`), which reads the disk: it runs on an extracted copy
of the ref in a temporary folder, with the product's bundler found in the `node_modules` of the
checkout this script lives in. Its rules are `scripts/manifest_areas.toml` beside this file, unless
`--rules` names another.

**Layouts.** In the user repository the product tree is the root. In the developer repository it is
the
`OspreyFlow_Core/` folder, whose prefix is taken off and beside which nothing is read. The summary
says which it saw.

**Same input, same bytes.** Sorted by the bytes of the path (no locale), `\\n` line endings, fixed
CSV quoting, no
dates, no machine path, no user name; every list is sorted by `format_list`.

`--check-areas` runs only the areas check: every tracked file is in exactly one area, `other` names
its folders and
files and is never a pattern. It exits 1, with one line per problem, if not.

`release_images` is read from the release workflow's matrix, each Dockerfile, its build context and
its
`.dockerignore`, and says `not determined` rather than guess; the summary explains each value.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import functools
import hashlib
import io
import json
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

CORE_PREFIX = "OspreyFlow_Core/"
HERE = Path(__file__).resolve().parent
DEFAULT_RULES = HERE / "manifest_areas.toml"
RELEASE_WORKFLOW = ".github/workflows/release.yml"
CSV_NAME = "maintainer-manifest.csv"
MD_NAME = "maintainer-manifest.md"
COLUMNS = [
    "path",
    "area",
    "language",
    "lines",
    "bytes",
    "is_test",
    "is_generated",
    "release_images",
]
BINARY_PROBE = 8192
UNKNOWN = "unknown"
UNASSIGNED = "unassigned"
OTHER = "other"
YES, NO, NO_EVIDENCE = "yes", "no", "no evidence in this tree"
NOT_DETERMINED, BUILDER_ONLY = "not determined", "builder only"
NONE, NOT_RELEASED = "none", "none (not released)"
GLOB = re.compile(r"[*?\[]")
# What the two trees' isolation check is run for (ADR-152 I1), by the folder it names.
REACT_TREES = ("apps/pages", "packages/glass-shared")
ISOLATION_SCRIPT = "scripts/no_react_check.mjs"
CHECKED_FOLDERS = ("apps", "packages", "services")


class ManifestError(Exception):
    """A refusal in words: the ref, the rules or a release matrix could not be read."""


# --- the repository, read with dulwich (no process is run: the image carries no `git`) -----------


def open_repo(path: Path):  # type: ignore[no-untyped-def]
    try:
        from dulwich.errors import NotGitRepository
        from dulwich.repo import Repo
    except ImportError as error:  # pragma: no cover - dulwich is a dependency of the product
        raise ManifestError("dulwich is needed to read the repository") from error
    try:
        return Repo.discover(str(path))
    except NotGitRepository as error:
        raise ManifestError(f"{str(path)!r} is not inside a git repository") from error


def resolve_commit(repo: Path, ref: str) -> str:
    """The commit a ref names, as git reads it: a tag is followed to its commit; `HEAD`, branches
    and hashes work. A suffix `^N` is the commit's Nth parent (`^` is `^1`, and `^0` is the commit
    itself); `~N` is N steps back along first parents (`~` is `~1`). A parent a commit does not
    have is a refusal, never another commit."""
    from dulwich.objectspec import parse_commit

    match = re.fullmatch(r"(.+?)((?:[~^]\d*)*)", ref)
    base, steps = (match.group(1), match.group(2)) if match else (ref, "")
    with open_repo(repo) as opened:
        try:
            commit = parse_commit(opened, base.encode())
            for kind, count in re.findall(r"([~^])(\d*)", steps):
                if kind == "^":
                    nth = int(count) if count else 1
                    if nth:
                        commit = opened[commit.parents[nth - 1]]
                else:
                    for _ in range(int(count) if count else 1):
                        commit = opened[commit.parents[0]]
            return commit.id.decode()
        except (KeyError, ValueError, TypeError, IndexError) as error:
            raise ManifestError(
                f"{ref!r} is not a commit or a tag of a commit in this repository"
            ) from error


@dataclass(frozen=True)
class Entry:
    path: str  # relative to the product tree
    oid: str


def decode_path(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")


GITLINK = 0o160000


def list_tree(repo: Path, commit: str) -> tuple[list[Entry], str]:
    """The tracked files of `commit` and the layout seen: `user` (the product tree is the root) or
    `developer` (it is `OspreyFlow_Core/`, the prefix taken off, nothing outside it read)."""
    from dulwich.object_store import iter_tree_contents

    found: list[tuple[str, str]] = []
    with open_repo(repo) as opened:
        tree = opened[commit.encode()].tree
        for item in iter_tree_contents(opened.object_store, tree):
            if item.mode is not None and item.mode != GITLINK:  # a submodule has no bytes here
                found.append((decode_path(item.path), item.sha.decode()))
    prefixed = any(path.startswith(CORE_PREFIX) for path, _ in found)
    rooted = any(path.split("/", 1)[0] in CHECKED_FOLDERS and "/" in path for path, _ in found)
    layout = "developer" if prefixed and not rooted else "user"
    if layout == "developer":
        entries = [
            Entry(path[len(CORE_PREFIX) :], oid)
            for path, oid in found
            if path.startswith(CORE_PREFIX)
        ]
    else:
        entries = [Entry(path, oid) for path, oid in found]
    entries.sort(key=lambda entry: entry.path.encode("utf-8", "surrogateescape"))
    return entries, layout


def read_blobs(repo: Path, oids: Sequence[str]) -> Iterator[bytes]:
    """Each blob's bytes, in order, one object at a time."""
    with open_repo(repo) as opened:
        for oid in oids:
            try:
                yield opened.object_store[oid.encode()].data
            except KeyError as error:
                raise ManifestError(f"the repository has no object {oid}") from error


# --- the rules ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AreaRule:
    name: str
    paths: tuple[str, ...]
    excepts: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedRule:
    paths: tuple[str, ...]
    generator: str
    command: str = ""


@dataclass
class Rules:
    languages: dict[str, str]
    language_files: dict[str, str]
    test_patterns: tuple[str, ...]
    generated: list[GeneratedRule]
    areas: list[AreaRule]
    other_folders: tuple[str, ...]
    other_files: tuple[str, ...]
    header_lines: int
    header_markers: tuple[str, ...]
    sha256: str
    name: str


def _strings(table: dict, key: str, where: str) -> tuple[str, ...]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ManifestError(f"the rules file: {where} {key!r} must be a list of strings")
    return tuple(value)


def load_rules(path: Path) -> Rules:
    try:
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ManifestError(f"the rules file {path.name} cannot be read: {error}") from error
    header = data.get("header", {})
    areas = [
        AreaRule(
            name=str(table.get("name", "")),
            paths=_strings(table, "paths", "an [[area]]"),
            excepts=_strings(table, "except", "an [[area]]"),
        )
        for table in data.get("area", [])
    ]
    if any(not area.name or area.name in {OTHER, UNASSIGNED} for area in areas):
        raise ManifestError(
            f"the rules file {path.name}: an [[area]] needs its own name ('other' is the named "
            "list)"
        )
    other = data.get("other", {})
    return Rules(
        languages={str(k).lower(): str(v) for k, v in data.get("languages", {}).items()},
        language_files={str(k): str(v) for k, v in data.get("language_files", {}).items()},
        test_patterns=_strings(data.get("tests", {}), "patterns", "[tests]"),
        generated=[
            GeneratedRule(
                paths=_strings(table, "paths", "a [[generated]]"),
                generator=str(table.get("generator", "")),
                command=str(table.get("command", "")),
            )
            for table in data.get("generated", [])
        ],
        areas=areas,
        other_folders=_strings(other, "folders", "[other]"),
        other_files=_strings(other, "files", "[other]"),
        header_lines=int(header.get("lines", 10)),
        header_markers=tuple(
            m.lower()
            for m in header.get("markers", ["AUTO-GENERATED", "@generated", "DO NOT EDIT"])
        ),
        sha256=hashlib.sha256(raw).hexdigest(),
        name=path.name,
    )


def prefix_match(pattern: str, path: str) -> bool:
    """`pattern` is a path prefix: it names a folder (and all in it) or one file; a `*` or `?`
    stays in its segment."""
    wanted = pattern.strip("/").split("/")
    got = path.split("/")
    return len(got) >= len(wanted) and all(
        fnmatch.fnmatchcase(g, w) for g, w in zip(got, wanted, strict=False)
    )


def test_pattern_match(pattern: str, path: str) -> bool:
    if pattern.endswith("/"):
        return any(fnmatch.fnmatchcase(part, pattern[:-1]) for part in path.split("/")[:-1])
    if "/" not in pattern:
        return fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern)
    return prefix_match(pattern, path)


def other_names(rules: Rules, path: str) -> bool:
    """`other` names exactly: a pattern in its list names nothing."""
    for folder in rules.other_folders:
        if not GLOB.search(folder) and (path == folder or path.startswith(folder.strip("/") + "/")):
            return True
    return any(not GLOB.search(name) and path == name for name in rules.other_files)


def areas_of(rules: Rules, path: str) -> list[str]:
    """Every area that holds `path`, in the order of the rules file, `other` last."""
    hits: list[str] = []
    for area in rules.areas:
        if any(prefix_match(p, path) for p in area.paths) and not any(
            prefix_match(e, path) for e in area.excepts
        ):
            if area.name not in hits:
                hits.append(area.name)
    if other_names(rules, path):
        hits.append(OTHER)
    return hits


def format_list(values: Iterable[str]) -> str:
    """The one way a list is written into a cell: sorted, no repeats, joined with `;`."""
    return ";".join(sorted(set(values)))


# --- the areas check ------------------------------------------------------------------------------


def areas_problems(rules: Rules, paths: Sequence[str]) -> list[str]:
    problems = []
    for name in (*rules.other_folders, *rules.other_files):
        if GLOB.search(name):
            problems.append(
                f'rules: "other" names folders and files, never patterns: '
                f"{name!r} is a pattern, not a name"
            )
    for path in paths:
        hits = areas_of(rules, path)
        if not hits:
            problems.append(f"{path} is in no area")
        elif len(hits) > 1:
            count = "two" if len(hits) == 2 else str(len(hits))
            problems.append(f"{path} is in {count} areas: {'; '.join(hits)}")
    return problems


# --- facts about one file -------------------------------------------------------------------------


@dataclass
class Facts:
    lines: int | None
    size: int
    header: bool


def facts_of(data: bytes, rules: Rules) -> Facts:
    binary = b"\0" in data[:BINARY_PROBE]
    if binary:
        return Facts(None, len(data), False)
    lines = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    top = (
        b"\n".join(data.split(b"\n", rules.header_lines)[: rules.header_lines])
        .decode("utf-8", "replace")
        .lower()
    )
    return Facts(lines, len(data), any(marker in top for marker in rules.header_markers))


def language_of(path: str, rules: Rules) -> str:
    name = path.rsplit("/", 1)[-1]
    if name in rules.language_files:
        return rules.language_files[name]
    dot = name.rfind(".")
    ext = name[dot:].lower() if dot > 0 else ""
    return rules.languages.get(ext, UNKNOWN)


def generated_value(path: str, header: bool, rules: Rules, tree: frozenset[str]) -> str:
    """From the repository's own evidence: a header in the file, or a rule naming it with a
    generator that is in the tree.
    Never from a folder's name."""
    if header:
        return YES
    claimed = False
    for rule in rules.generated:
        if any(prefix_match(p, path) for p in rule.paths):
            claimed = True
            if rule.generator and rule.generator in tree:
                return YES
    return NO_EVIDENCE if claimed else NO


# --- the "maintained under" rules (the owner keeps this file outside the repository) --------------


def load_labels(path: Path) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ManifestError(f"the second rules file cannot be read: {error}") from error
    return [
        (_strings(t, "paths", "a [[rule]]"), _strings(t, "labels", "a [[rule]]"))
        for t in data.get("rule", [])
    ]


# --- .dockerignore, as Docker reads it ------------------------------------------------------------


def _compile_ignore(pattern: str) -> re.Pattern[str]:
    """A cleaned pattern as a regular expression: Go's `filepath.Match` (`*` and `?` stay in a
    segment, `[...]` is a
    class, a backslash escapes) plus Docker's `**` (any number of folders, none included)."""
    out = ["^"]
    i, n = 0, len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            if pattern[i + 1 : i + 2] == "*":
                i += 1
                if pattern[i + 1 : i + 2] == "/":
                    i += 1
                out.append(".*" if i + 1 >= n else "(.*/)?")
            else:
                out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        elif ch == "[":
            end = pattern.find("]", i + 2)
            if end == -1:
                out.append(r"\[")
            else:
                body = pattern[i + 1 : end].replace("\\", "\\\\")
                if body.startswith("^"):
                    body = "^" + body[1:]
                out.append(f"[{body}]")
                i = end
        elif ch == "\\" and i + 1 < n:
            i += 1
            out.append(re.escape(pattern[i]))
        else:
            out.append(re.escape(ch))
        i += 1
    out.append("$")
    return re.compile("".join(out))


@functools.lru_cache(maxsize=64)
def _ignore_patterns(lines: tuple[str, ...]) -> tuple[tuple[bool, re.Pattern[str]], ...]:
    compiled = []
    for number, raw in enumerate(lines):
        text = raw.lstrip("﻿") if number == 0 else raw
        pattern = text.strip()
        if not pattern or pattern.startswith("#"):
            continue
        negated = pattern.startswith("!")
        if negated:
            pattern = pattern[1:].strip()
        if not pattern:
            continue
        pattern = posixpath.normpath(pattern)
        if len(pattern) > 1 and pattern.startswith("/"):
            pattern = pattern.lstrip("/")
        compiled.append((negated, _compile_ignore(pattern)))
    return tuple(compiled)


def dockerignore_excludes(lines: Sequence[str], path: str) -> bool:
    """Whether the build context leaves `path` out. Docker's rule: the lines are read in order and
    the last that matches
    the path, or one of its parent folders, decides; a pattern is relative to the context's root,
    so a name with no slash
    matches only at the root (`**/name` is the way to say any depth)."""
    matched = False
    parents = path.split("/")[:-1]
    parent_paths = ["/".join(parents[: i + 1]) for i in range(len(parents))]
    for negated, regex in _ignore_patterns(tuple(lines)):
        if negated != matched:
            continue
        if regex.match(path) or any(regex.match(parent) for parent in parent_paths):
            matched = not negated
    return matched


# --- Dockerfiles ----------------------------------------------------------------------------------


@dataclass
class Instruction:
    op: str
    args: str


HEREDOC = re.compile(r"<<-?\s*([\"']?)([A-Za-z_][A-Za-z0-9_]*)\1")


def parse_dockerfile(text: str) -> list[Instruction]:
    """The instructions: comment lines dropped, a trailing backslash joining the next line, heredoc
    bodies skipped."""
    lines = text.replace("\r\n", "\n").split("\n")
    instructions: list[Instruction] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        joined = line.rstrip()
        while joined.endswith("\\") and i < len(lines):
            joined = joined[:-1].rstrip() + " "
            while i < len(lines) and lines[i].lstrip().startswith("#"):
                i += 1
            if i >= len(lines):
                break
            joined += lines[i].strip()
            i += 1
            joined = joined.rstrip()
        op, _, args = joined.strip().partition(" ")
        op = op.upper()
        if op in {"COPY", "ADD", "RUN"}:
            for match in HEREDOC.finditer(args):
                word = match.group(2)
                while i < len(lines) and lines[i].strip() != word:
                    i += 1
                i += 1
        instructions.append(Instruction(op, args.strip()))
    return instructions


@dataclass
class Stage:
    index: int
    name: str
    base: str
    base_stage: int | None  # the earlier stage this one stands on
    base_unresolved: bool
    body: list[Instruction] = field(default_factory=list)


def _expand(text: str, variables: dict[str, str]) -> str | None:
    """`$X`, `${X}` and `${X:-d}` from `variables`; None when a name is not known."""
    failed = False

    def one(match: re.Match[str]) -> str:
        nonlocal failed
        name, default = match.group(1) or match.group(3), match.group(2)
        if name in variables:
            return variables[name]
        if default is not None:
            return default
        failed = True
        return ""

    out = re.sub(
        r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}|([A-Za-z_][A-Za-z0-9_]*))", one, text
    )
    return None if failed else out


def split_stages(instructions: list[Instruction], overridden: frozenset[str]) -> list[Stage]:
    globals_: dict[str, str] = {}
    stages: list[Stage] = []
    for ins in instructions:
        if ins.op == "ARG" and not stages:
            name, eq, default = ins.args.partition("=")
            name = name.strip()
            if name and eq and name not in overridden:
                globals_[name] = default.strip().strip("\"'")
        elif ins.op == "FROM":
            tokens = [t for t in ins.args.split() if not t.startswith("--")]
            name = tokens[2].lower() if len(tokens) >= 3 and tokens[1].upper() == "AS" else ""
            base_raw = tokens[0] if tokens else ""
            base = _expand(base_raw, globals_)
            by_name = {s.name: s.index for s in stages if s.name}
            if base is None:
                stages.append(Stage(len(stages), name, base_raw, None, True))
            else:
                stages.append(Stage(len(stages), name, base, by_name.get(base.lower()), False))
        elif stages:
            stages[-1].body.append(ins)
    return stages


@dataclass
class ImageResult:
    name: str
    dockerfile: str
    context: str
    exact: set[str] = field(default_factory=set)  # context-relative origins in the final image
    maybe: set[str] = field(default_factory=set)  # inputs of built output the final image carries
    builder: set[str] = field(
        default_factory=set
    )  # copied into a stage the image is built from, and not carried
    context_files: set[str] = field(default_factory=set)
    unresolved: list[str] = field(
        default_factory=list
    )  # a COPY or FROM that cannot be read statically
    built_from: list[str] = field(
        default_factory=list
    )  # stages whose built output the final image copies


COPY_FLAGS_UNRESOLVED = ("--parents", "--exclude")
ARCHIVE = re.compile(r"\.(tar|tgz|tar\.gz|tar\.bz2|tar\.xz|txz)$")


class _Fs:
    """A stage's files: the container path of each tracked file copied in, and what it came from."""

    def __init__(self) -> None:
        self.entries: dict[str, str] = {}
        self.workdir = "/"
        self.ctx_copied: set[str] = (
            set()
        )  # copied from the context into this stage or the stages it stands on
        self.contrib: set[str] = set()  # every tracked file that flowed into the stage, however
        self.built_from: list[str] = []
        self.unresolved: list[str] = []

    def copy(self) -> _Fs:
        other = _Fs()
        other.entries = dict(self.entries)
        other.workdir = self.workdir
        other.ctx_copied = set(self.ctx_copied)
        other.contrib = set(self.contrib)
        other.built_from = list(self.built_from)
        other.unresolved = list(self.unresolved)
        return other

    def is_dir(self, path: str) -> bool:
        return (
            path == "/"
            or path == self.workdir
            or any(e.startswith(path.rstrip("/") + "/") for e in self.entries)
        )


def _abs(path: str, workdir: str) -> str:
    return posixpath.normpath(path if path.startswith("/") else posixpath.join(workdir, path))


def _below(parts: list[str], depth: int) -> str:
    """Where a file lands under the destination when a wildcard matched its first `depth` segments:
    a matched file by its
    name, a matched folder by what is in it (Docker copies a folder's contents, not the folder)."""
    return parts[depth - 1] if len(parts) == depth else "/".join(parts[depth:])


def _glob_paths(pattern: str, files: Iterable[str]) -> list[str]:
    """The files a context wildcard names: each segment matched on its own, a folder taking
    everything in it."""
    wanted = pattern.split("/")
    found = []
    for file in files:
        got = file.split("/")
        if len(got) >= len(wanted) and all(
            fnmatch.fnmatchcase(g, w) for g, w in zip(got, wanted, strict=False)
        ):
            found.append(file)
    return found


def _context_sources(source: str, files: list[str]) -> tuple[list[tuple[str, str]], bool] | None:
    """The (file, path below the source) pairs a COPY source names in the context, and whether the
    source is a single
    file (so it may be renamed by its destination). None: it cannot be read statically."""
    clean = posixpath.normpath(source.lstrip("/")) if source.strip("/") else "."
    if "**" in clean or "$" in clean:
        return None
    if clean == ".":
        return [(f, f) for f in files], False
    if GLOB.search(clean):
        depth = len(clean.split("/"))
        return [(f, _below(f.split("/"), depth)) for f in _glob_paths(clean, files)], False
    if clean in files:
        return [(clean, posixpath.basename(clean))], True
    return [(f, f[len(clean) + 1 :]) for f in files if f.startswith(clean + "/")], False


def _dest_for(fs: _Fs, dest: str, single_file: bool, count: int) -> tuple[str, bool]:
    """The destination's absolute path, and whether it is a folder the sources go into."""
    absolute = _abs(dest, fs.workdir)
    folder = (
        dest.endswith("/")
        or dest in {".", ".."}
        or count > 1
        or not single_file
        or fs.is_dir(absolute)
    )
    return absolute, folder


def analyse_image(
    name: str,
    dockerfile: str,
    context: str,
    target: str,
    files: dict[str, bytes],
    tree: Sequence[str],
    overridden: frozenset[str],
) -> ImageResult:
    result = ImageResult(name, dockerfile, context)
    if dockerfile not in files:
        raise ManifestError(
            f"the release matrix names {dockerfile} for the image {name!r}, and it is not in "
            "this tree"
        )
    base_dir = "" if context in {"", "."} else context.strip("/") + "/"
    own = posixpath.join(
        posixpath.dirname(dockerfile), posixpath.basename(dockerfile) + ".dockerignore"
    )
    ignore_path = own if own in files else base_dir + ".dockerignore"
    ignore_lines = (
        files[ignore_path].decode("utf-8", "replace").splitlines() if ignore_path in files else []
    )
    in_context = [p[len(base_dir) :] for p in tree if p.startswith(base_dir)]
    context_files = [p for p in in_context if not dockerignore_excludes(ignore_lines, p)]
    result.context_files = {base_dir + p for p in context_files}
    stages = split_stages(
        parse_dockerfile(files[dockerfile].decode("utf-8", "replace")), overridden
    )
    if not stages:
        raise ManifestError(f"{dockerfile} has no FROM")
    final = len(stages) - 1
    if target:
        named = [s.index for s in stages if s.name == target.lower()]
        if not named:
            raise ManifestError(
                f"the release matrix names the target {target!r} and {dockerfile} has no such stage"
            )
        final = named[0]

    states: dict[int, _Fs] = {}
    reachable: set[int] = set()

    def build(index: int) -> _Fs:
        if index in states:
            return states[index]
        stage = stages[index]
        reachable.add(index)
        if stage.base_stage is not None:
            fs = build(stage.base_stage).copy()
        else:
            fs = _Fs()
        if stage.base_unresolved:
            fs.unresolved.append(
                f"the base image {stage.base!r} cannot be resolved from the build arguments"
            )
        for ins in stage.body:
            apply(stage, fs, ins)
        states[index] = fs
        return fs

    def apply(stage: Stage, fs: _Fs, ins: Instruction) -> None:
        if ins.op == "WORKDIR":
            expanded = _expand(ins.args, {})
            if expanded is None:
                fs.unresolved.append(f"WORKDIR {ins.args}")
            else:
                fs.workdir = _abs(expanded, fs.workdir)
        elif ins.op == "RUN":
            if (
                "--mount=" in ins.args
                and re.search(r"type=bind", ins.args)
                and "from=" not in ins.args
            ):
                fs.unresolved.append("a RUN that binds files from the context")
        elif ins.op in {"COPY", "ADD"}:
            copy_instruction(stage, fs, ins)

    def copy_instruction(stage: Stage, fs: _Fs, ins: Instruction) -> None:
        args = ins.args
        if "<<" in args:
            fs.unresolved.append(f"{ins.op} {args.split()[0] if args.split() else ''} (a heredoc)")
            return
        flags: dict[str, str] = {}
        rest = args
        while rest.startswith("--"):
            flag, _, rest = rest.partition(" ")
            key, _, value = flag.partition("=")
            flags[key] = value
            rest = rest.lstrip()
        if any(key in flags for key in COPY_FLAGS_UNRESOLVED):
            fs.unresolved.append(f"{ins.op} with {', '.join(sorted(flags))}")
            return
        if rest.startswith("["):
            try:
                words = [str(w) for w in json.loads(rest)]
            except json.JSONDecodeError:
                fs.unresolved.append(f"{ins.op} {rest}")
                return
        else:
            words = rest.split()
        if len(words) < 2:
            fs.unresolved.append(f"{ins.op} {rest}")
            return
        *sources, dest = words
        if "$" in dest:
            fs.unresolved.append(f"{ins.op} {' '.join(words)}")
            return
        if "--from" in flags:
            copy_from(fs, flags["--from"], sources, dest, stage.index)
        else:
            copy_context(fs, ins.op, sources, dest)

    def copy_context(fs: _Fs, op: str, sources: list[str], dest: str) -> None:
        for source in sources:
            if re.match(r"^[a-z][a-z0-9+.-]*://", source) or source.startswith("git@"):
                continue  # fetched, not tracked
            if op == "ADD" and ARCHIVE.search(source):
                fs.unresolved.append(f"ADD {source} (a local archive is unpacked)")
                continue
            got = _context_sources(source, context_files)
            if got is None:
                fs.unresolved.append(f"COPY {source}")
                continue
            pairs, single = got
            absolute, folder = _dest_for(fs, dest, single and len(sources) == 1, len(sources))
            for file, below in pairs:
                target = posixpath.join(absolute, below) if folder or not single else absolute
                fs.entries[target] = base_dir + file
                fs.ctx_copied.add(base_dir + file)
                fs.contrib.add(base_dir + file)

    def stage_index(ref: str, current: int) -> int | None:
        if ref.isdigit() and int(ref) < current:
            return int(ref)
        for s in stages[:current]:
            if s.name and s.name == ref.lower():
                return s.index
        return None

    def copy_from(fs: _Fs, ref: str, sources: list[str], dest: str, current: int) -> None:
        origin = stage_index(ref, current)
        if origin is None:
            return  # another image's files: nothing tracked
        theirs = build(origin)
        for source in sources:
            src = _abs(source, "/")
            if "**" in src or "$" in src:
                fs.unresolved.append(f"COPY --from={ref} {source}")
                continue
            if GLOB.search(src):
                pattern = src.strip("/").split("/")
                hits = {
                    p: o
                    for p, o in theirs.entries.items()
                    if len(p.strip("/").split("/")) >= len(pattern)
                    and all(
                        fnmatch.fnmatchcase(g, w)
                        for g, w in zip(p.strip("/").split("/"), pattern, strict=False)
                    )
                }
                single = False
                below = {p: _below(p.strip("/").split("/"), len(pattern)) for p in hits}
            elif src in theirs.entries:
                hits = {src: theirs.entries[src]}
                single = True
                below = {src: posixpath.basename(src)}
            else:
                hits = {
                    p: o for p, o in theirs.entries.items() if p.startswith(src.rstrip("/") + "/")
                }
                single = False
                below = {p: p[len(src.rstrip("/")) + 1 :] for p in hits}
            if not hits:
                # Nothing tracked is there: built output (or content fetched or installed), which
                # came from the stage.
                if (
                    theirs.contrib
                ):  # a stage that took no tracked file in has nothing to make undetermined
                    fs.built_from.append(stages[origin].name or str(origin))
                fs.contrib |= theirs.contrib
                continue
            absolute, folder = _dest_for(fs, dest, single and len(sources) == 1, len(sources))
            for path, file in hits.items():
                target = posixpath.join(absolute, below[path]) if folder or not single else absolute
                fs.entries[target] = file
                fs.contrib.add(file)

    end = build(final)

    def walk(index: int, seen: set[int]) -> None:
        # every stage the final image is built from (a base stage, or one a COPY --from reads)
        if index in seen:
            return
        seen.add(index)
        stage = stages[index]
        if stage.base_stage is not None:
            walk(stage.base_stage, seen)
        for ins in stage.body:
            match = re.search(r"--from=(\S+)", ins.args) if ins.op in {"COPY", "ADD"} else None
            if match:
                found = stage_index(match.group(1), index)
                if found is not None:
                    # A COPY that could not be read statically never built the stage it names;
                    # build it now so what it leaves undetermined is counted.
                    build(found)
                    walk(found, seen)

    used: set[int] = set()
    walk(final, used)
    result.exact = set(end.entries.values())
    result.unresolved = [
        f"{stages[i].name or i}: {why}" for i in sorted(used) for why in states[i].unresolved
    ]
    result.unresolved = sorted(set(result.unresolved))
    result.built_from = sorted(set(end.built_from))
    if end.built_from:
        result.maybe = set(end.contrib) - result.exact
    result.builder = (
        set().union(*(states[i].ctx_copied for i in used)) - result.exact - result.maybe
    )
    return result


# --- the release workflow -------------------------------------------------------------------------


@dataclass
class Release:
    present: bool
    images: list[tuple[str, str, str, str]]  # name, dockerfile, context, target
    text: str


def read_release(files: dict[str, bytes]) -> Release:
    if RELEASE_WORKFLOW not in files:
        return Release(False, [], "")
    text = files[RELEASE_WORKFLOW].decode("utf-8", "replace")
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - PyYAML is a dependency of the product
        raise ManifestError("PyYAML is needed to read the release workflow's matrix") from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ManifestError(f"{RELEASE_WORKFLOW} cannot be read: {error}") from error
    images: list[tuple[str, str, str, str]] = []
    for job in (document or {}).get("jobs", {}).values():
        matrix = ((job or {}).get("strategy") or {}).get("matrix") or {}
        for entry in matrix.get("include", []) if isinstance(matrix, dict) else []:
            if isinstance(entry, dict) and "service" in entry and "dockerfile" in entry:
                images.append(
                    (
                        str(entry["service"]),
                        str(entry["dockerfile"]),
                        str(entry.get("context") or "."),
                        str(entry.get("target") or ""),
                    )
                )
    names = [i[0] for i in images]
    if len(set(names)) != len(names):
        raise ManifestError(f"{RELEASE_WORKFLOW} names an image twice")
    return Release(True, images, text)


# --- no_react_check -------------------------------------------------------------------------------


def _scrub(text: str, *private: str) -> str:
    for item in private:
        if item:
            text = text.replace(item, "<path>")
    return re.sub(r"(?<![\w.@-])/(?:[\w.@+-]+/)+[\w.@+-]*", "<path>", text)


def run_isolation_check(repo: Path, entries: list[Entry], has_script: bool = True) -> str:
    """`exit status N; last line: ...` of scripts/no_react_check.mjs on an extracted archive of the
    ref, or `not run (why)`:
    never a pass the check did not give."""
    if not has_script:
        return f"not run (no {ISOLATION_SCRIPT} at this ref)"
    node = shutil.which("node")
    if node is None:
        return "not run (node is not available)"
    modules = HERE.parent / "node_modules"
    if not modules.is_dir():
        return (
            "not run (the product's node_modules are not installed beside this script, "
            "and the check bundles with them)"
        )
    with tempfile.TemporaryDirectory(prefix="manifest-archive-") as scratch_name:
        scratch = Path(scratch_name)
        root = scratch / "tree"
        root.mkdir()
        work = scratch / "cwd"
        work.mkdir()
        for entry, data in zip(entries, read_blobs(repo, [e.oid for e in entries]), strict=True):
            if entry.path.startswith(("/", "../")) or "/../" in entry.path:
                raise ManifestError(f"the tree holds an unsafe path: {entry.path!r}")
            target = root / entry.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        script = root / ISOLATION_SCRIPT
        if not script.is_file():
            return f"not run (no {ISOLATION_SCRIPT} at this ref)"
        (root / "node_modules").symlink_to(modules.resolve())
        try:
            done = subprocess.run(
                [node, str(script), str(root)],
                cwd=work,
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "not run (the check did not finish in 15 minutes)"
        output = (done.stdout.strip() or done.stderr.strip()).splitlines()
        last = (
            _scrub(output[-1].strip(), str(root), str(modules.resolve()), str(HERE.parent))
            if output
            else "(no output)"
        )
        return f"exit status {done.returncode}; last line: {last}"


# --- the manifest ---------------------------------------------------------------------------------


@dataclass
class Row:
    path: str
    area: str
    language: str
    lines: int | None
    size: int
    is_test: bool
    is_generated: str
    release_images: str
    maintained_under: str = ""
    areas: int = 1


@dataclass
class Manifest:
    csv_bytes: bytes
    md_bytes: bytes
    rows: list[Row]


def is_dockerfile_name(path: str) -> bool:
    """Docker's conventional names for a Dockerfile: `Dockerfile`, `Dockerfile.<x>` and
    `<x>.Dockerfile`, in any case. The release matrix may name another file; those are read too
    (see `build_manifest`)."""
    name = path.rsplit("/", 1)[-1].lower()
    return name == "dockerfile" or name.startswith("dockerfile.") or name.endswith(".dockerfile")


def needs_content(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        (is_dockerfile_name(path) and not name.endswith(".dockerignore"))
        or name.endswith(".dockerignore")
        or path == RELEASE_WORKFLOW
    )


def images_column(
    release: Release,
    files: dict[str, bytes],
    tree: Sequence[str],
) -> tuple[dict[str, str], list[ImageResult], dict[str, set[str]]]:
    """Each file's `release_images`, the analysis of each released image, and the files each image
    leaves undetermined."""
    paths = list(tree)
    if not release.present:
        return {p: NOT_DETERMINED for p in paths}, [], {}
    # A build argument the release workflow mentions may be overridden there: its default is then
    # not the value.
    named = {dockerfile for _, dockerfile, _, _ in release.images}
    overridden = frozenset(
        name for name in _all_args(files, named) if name and name in release.text
    )
    results = [
        analyse_image(name, dockerfile, context, target, files, paths, overridden)
        for name, dockerfile, context, target in release.images
    ]
    unreleased = sorted(
        posixpath.dirname(p)
        for p in paths
        if is_dockerfile_name(p) and not p.endswith(".dockerignore") and p not in named
    )
    unreleased = [folder for folder in unreleased if folder]
    values: dict[str, str] = {}
    undetermined: dict[str, set[str]] = {}
    for path in paths:
        exact = [r.name for r in results if path in r.exact]
        undecided = []
        for r in results:
            if path in r.exact or path not in r.context_files:
                continue
            if path in r.maybe or r.unresolved:
                undecided.append(r.name)
        for name in undecided:
            undetermined.setdefault(name, set()).add(path)
        if exact or undecided:
            value = format_list(exact)
            if undecided:
                value = f"{value};{NOT_DETERMINED}" if value else NOT_DETERMINED
        elif any(path in r.builder for r in results):
            value = BUILDER_ONLY
        elif any(path == f or path.startswith(f + "/") for f in unreleased):
            value = NOT_RELEASED
        else:
            value = NONE
        values[path] = value
    return values, results, undetermined


def _all_args(files: dict[str, bytes], named: set[str]) -> Iterator[str]:
    """The name of every build argument a Dockerfile in the tree declares with a default, before
    its first FROM. A Dockerfile is one by its conventional name or because the release matrix
    names it."""
    for path, data in files.items():
        if path not in named and not (
            is_dockerfile_name(path) and not path.endswith(".dockerignore")
        ):
            continue
        for ins in parse_dockerfile(data.decode("utf-8", "replace")):
            if ins.op == "FROM":
                break
            if ins.op == "ARG":
                yield ins.args.partition("=")[0].strip()


def build_manifest(
    repo: Path,
    ref: str,
    rules: Rules,
    labels: list[tuple[tuple[str, ...], tuple[str, ...]]] | None = None,
    isolation: str | None = None,
) -> Manifest:
    commit = resolve_commit(repo, ref)
    entries, layout = list_tree(repo, commit)
    paths = [e.path for e in entries]
    tree = frozenset(paths)
    facts: dict[str, Facts] = {}
    kept: dict[str, bytes] = {}
    for entry, data in zip(entries, read_blobs(repo, [e.oid for e in entries]), strict=True):
        facts[entry.path] = facts_of(data, rules)
        if needs_content(entry.path):
            kept[entry.path] = data
    release = read_release(kept)
    # The release matrix may name a Dockerfile whatever it is called: read what it names.
    by_path = {e.path: e for e in entries}
    wanted = sorted(d for _, d, _, _ in release.images if d in by_path and d not in kept)
    for path, data in zip(wanted, read_blobs(repo, [by_path[p].oid for p in wanted]), strict=True):
        kept[path] = data
    images, results, undetermined = images_column(release, kept, paths)
    rows: list[Row] = []
    for path in paths:
        hits = areas_of(rules, path)
        fact = facts[path]
        row = Row(
            path=path,
            area=hits[0] if hits else UNASSIGNED,
            language=language_of(path, rules),
            lines=fact.lines,
            size=fact.size,
            is_test=any(test_pattern_match(p, path) for p in rules.test_patterns),
            is_generated=generated_value(path, fact.header, rules, tree),
            release_images=images[path],
            areas=len(hits),
        )
        if labels is not None:
            row.maintained_under = format_list(
                label
                for prefixes, names in labels
                if any(prefix_match(p, path) for p in prefixes)
                for label in names
            )
        rows.append(row)
    columns = COLUMNS + (["maintained_under"] if labels is not None else [])
    sink = io.StringIO(newline="")
    writer = csv.writer(sink, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        cells = [
            row.path,
            row.area,
            row.language,
            "" if row.lines is None else str(row.lines),
            str(row.size),
            YES if row.is_test else NO,
            row.is_generated,
            row.release_images,
        ]
        writer.writerow(cells + ([row.maintained_under] if labels is not None else []))
    if isolation is None:
        isolation = run_isolation_check(repo, entries, ISOLATION_SCRIPT in tree)
    summary = render_summary(
        ref, commit, layout, rules, rows, release, results, undetermined, isolation
    )
    return Manifest(
        sink.getvalue().encode("utf-8", "surrogateescape"),
        summary.encode("utf-8", "surrogateescape"),
        rows,
    )


# --- the summary ----------------------------------------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def render_summary(
    ref: str,
    commit: str,
    layout: str,
    rules: Rules,
    rows: list[Row],
    release: Release,
    results: list[ImageResult],
    undetermined: dict[str, set[str]],
    isolation: str,
) -> str:
    out: list[str] = []
    add = out.append
    add("# Maintainer's manifest of the product tree")
    add("")
    add(f"Ref: {ref}")
    add(f"Commit: {commit}")
    if layout == "developer":
        add(
            "Layout: developer repository (the product tree is the `OspreyFlow_Core` folder, "
            "whose prefix is taken off; nothing"
        )
        add("beside it is read)")
    else:
        add("Layout: user repository (the product tree is the repository root)")
    add(f"Rules: `{rules.name}`, sha256 {rules.sha256}")
    add("")
    add(
        "Generated from the tracked files at that commit and nothing from a working tree, by "
        "`scripts/maintainer_manifest.py`."
    )
    add("The same commit gives the same bytes. `maintainer-manifest.csv` has one row per file.")
    add("")
    add("The Python tests are kept in the developer repository and are not part of this tree.")
    add("")
    text_rows = [r for r in rows if r.lines is not None]
    unknown = sum(1 for r in rows if r.language == UNKNOWN)
    not_determined = sum(1 for r in rows if NOT_DETERMINED in r.release_images.split(";"))
    no_evidence = sum(1 for r in rows if r.is_generated == NO_EVIDENCE)
    unassigned = sum(1 for r in rows if r.area == UNASSIGNED)
    add("## Counts")
    add("")
    add(f"- Files: {len(rows)}")
    add(f"- Lines (text files; a binary file has none): {sum(r.lines or 0 for r in text_rows)}")
    add(f"- Binary files: {len(rows) - len(text_rows)}")
    add(f"- Files with an unknown language (`{UNKNOWN}`): {unknown}")
    add(f"- Files whose `release_images` has `{NOT_DETERMINED}`: {not_determined}")
    add(f"- Files whose `is_generated` is `{NO_EVIDENCE}`: {no_evidence}")
    add(f"- Files in no area (`{UNASSIGNED}`): {unassigned}")
    multi = sum(1 for r in rows if r.areas > 1)
    add(
        f"- Files in more than one area: {multi} (the areas check fails on each; the first area "
        "in the rules' order is used)"
    )
    add("")
    add("## Areas")
    add("")
    add("| Area | Files | Lines |")
    add("| --- | --- | --- |")
    by_area: dict[str, list[Row]] = {}
    for r in rows:
        by_area.setdefault(r.area, []).append(r)
    for area in sorted(by_area, key=lambda a: a.encode()):
        group = by_area[area]
        add(f"| {_cell(area)} | {len(group)} | {sum(r.lines or 0 for r in group)} |")
    add("")
    add("## Folders")
    add("")
    add(
        "One row for each folder that holds files of its own (a folder's own files, not those of "
        "folders inside it)."
    )
    add("")
    add("| Folder | Area | Files | Lines | Binary files |")
    add("| --- | --- | --- | --- | --- |")
    by_folder: dict[tuple[str, str], list[Row]] = {}
    for r in rows:
        folder = posixpath.dirname(r.path) or "."
        by_folder.setdefault((folder, r.area), []).append(r)
    for (folder, area), group in sorted(
        by_folder.items(), key=lambda kv: (kv[0][0].encode(), kv[0][1].encode())
    ):
        binary = sum(1 for r in group if r.lines is None)
        add(
            f"| {_cell(folder)} | {_cell(area)} | {len(group)} | "
            f"{sum(r.lines or 0 for r in group)} | {binary} |"
        )
    add("")
    add("## The page service and the shared TypeScript")
    add("")
    add(
        "The two trees that import no React (ADR-152 invariant I1). `scripts/no_react_check.mjs` "
        "is run on an extracted archive"
    )
    add(
        "of this commit; if `node` or the product's bundler is not there it says `not run`, "
        "never a pass."
    )
    add("")
    add("| Tree | Files | Lines | no_react_check |")
    add("| --- | --- | --- | --- |")
    shown = "not run" if isolation.startswith("not run") else isolation.split(";")[0]
    for tree in REACT_TREES:
        group = [r for r in rows if r.path.startswith(tree + "/")]
        add(f"| {tree} | {len(group)} | {sum(r.lines or 0 for r in group)} | {shown} |")
    add("")
    add(f"no_react_check: {isolation}")
    add("")
    add("## What the columns say")
    add("")
    add(
        "- `area`: where the file lives, by the rules file's folders in its order; a test stays "
        "in the area of its folder."
    )
    add("- `is_test`: `yes` for the rules file's test names and folders, else `no`.")
    add(
        "- `is_generated`: from the repository's own evidence, never a folder's name. `yes`: a "
        "header in the file's first lines"
    )
    add(
        "  (`AUTO-GENERATED`, `@generated`, `DO NOT EDIT`), or a rule naming the file and a "
        "generator script that is in this tree."
    )
    add(
        f"  `{NO}`: no such evidence. `{NO_EVIDENCE}`: a rule says the file is generated and the "
        "script that makes it is"
    )
    add(
        "  not in this tree (it is kept in the developer repository, or none writes it): that is "
        "not `yes`."
    )
    add(
        "- `release_images`: the released images (read from the release workflow's matrix) whose "
        "final stage carries the file,"
    )
    add(
        "  read from each Dockerfile's COPY lines, its build context and the `.dockerignore` "
        "that applies to it. A file is in"
    )
    add(
        "  several images when whole folders are copied, and then the cell is a list, sorted, "
        "joined with `;`. Other values:"
    )
    add(f"  `{BUILDER_ONLY}` (copied into a build stage and not carried to the final image),")
    add(
        f"  `{NOT_DETERMINED}` (the file is an input of built output the final image carries, or "
        "a COPY could not be read"
    )
    add('  statically; alone or after a list, it means "and possibly more"),')
    add(
        f"  `{NOT_RELEASED}` (it lives in the folder of a Dockerfile the release does not build, "
        "and no released image carries it),"
    )
    add(
        f"  `{NONE}` (no released image carries it). Files fetched or installed during a build "
        "are not tracked and have no row."
    )
    add("")
    add("## Released images")
    add("")
    if not release.present:
        add(
            f"There is no release workflow in this tree (`{RELEASE_WORKFLOW}`), so every "
            f"`release_images` is `{NOT_DETERMINED}`."
        )
    else:
        add("| Image | Dockerfile | Context | Files carried exactly | Files not determined | Why |")
        add("| --- | --- | --- | --- | --- | --- |")
        for r in sorted(results, key=lambda x: x.name.encode()):
            why = []
            if r.built_from:
                why.append(
                    "the final image copies built output from the stage "
                    + ", ".join(f'"{s}"' for s in r.built_from)
                )
            why += [f"cannot be read statically: {w}" for w in r.unresolved]
            add(
                f"| {_cell(r.name)} | {_cell(r.dockerfile)} | {_cell(r.context)} | {len(r.exact)} "
                f"| {len(undetermined.get(r.name, ()))} | {_cell('; '.join(why)) or '-'} |"
            )
    add("")
    return "\n".join(out) + "\n"


# --- the command ----------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path("."),
        help="the repository (default: the current folder's)",
    )
    parser.add_argument("--ref", required=True, help="a commit or a tag")
    parser.add_argument("--out", type=Path, help="the folder to write the two files into")
    parser.add_argument(
        "--rules",
        type=Path,
        default=DEFAULT_RULES,
        help="the areas, languages and generators rules",
    )
    parser.add_argument(
        "--maintained-under", type=Path, help="a second rules file: adds the last column"
    )
    parser.add_argument(
        "--check-areas", action="store_true", help="only check every file is in exactly one area"
    )
    args = parser.parse_args(argv)
    try:
        rules = load_rules(args.rules)
        if args.check_areas:
            commit = resolve_commit(args.repo, args.ref)
            entries, _ = list_tree(args.repo, commit)
            problems = areas_problems(rules, [e.path for e in entries])
            for problem in problems:
                print(f"FAIL {problem}")
            if problems:
                print(f"areas check: {len(problems)} problem(s) in {len(entries)} tracked files")
                return 1
            print(f"areas check: all {len(entries)} tracked files are in exactly one area")
            if args.out is None:
                return 0
        if args.out is None:
            parser.error("--out is needed to write the manifest")
        labels = load_labels(args.maintained_under) if args.maintained_under else None
        manifest = build_manifest(args.repo, args.ref, rules, labels)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / CSV_NAME).write_bytes(manifest.csv_bytes)
        (args.out / MD_NAME).write_bytes(manifest.md_bytes)
    except ManifestError as error:
        print(f"maintainer_manifest: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
