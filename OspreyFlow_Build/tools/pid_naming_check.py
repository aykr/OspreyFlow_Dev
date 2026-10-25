"""The Prison Intelligence Dataset's naming gate (Brief 1, stage 6).

    cd OspreyFlow_Core
    PYTHONPATH=.:packages:../OspreyFlow_Build .venv/bin/python -m tools.pid_naming_check

Fails (exit 1, every hit printed) if either of the two names Brief 1 bans (the existing prison
fixture's, and the film-district word its originator carries) appears, in any case, anywhere in the
PID: in a file name, a file's
contents, a registered id, a generated id or string, or a generated file. Exit 0 when nothing does.
Exit 2 when it cannot find the PID at all, since a check over nothing proves nothing.

**What it scans, each computed rather than listed by hand:**

(a) *The PID's files.* Every file under `OspreyFlow_Core` and `OspreyFlow_Build` that has `pid` or
    `prison_intelligence` as a word in its name or in the name of a directory above it
    (`pid_plan.py`, `test_pid_files.py`, `write_pid_files.py`, a Brief 2 recipe
    `pid_*_recipe.yaml`, but not `RapidMovementParams.ts`). Path and contents. A file that is not
    text is skipped for its contents (a picture's bytes could spell the word by chance) and still
    has its name scanned.
(b) *The generated output.* The demo plan from its default seed is built in memory and every string
    in it is scanned, then every node and link it writes (ids, types, properties, provenance,
    handling originators and units, datasets), then the picture names, then each file the generator
    writes to a temporary folder (names and, for text files, every line).
(c) *What the PID registers.* Each seed dataset whose id starts `prison-intelligence` or whose
    source starts `pid-` (id, name, source, case name, domains), and every string of each PID
    recipe, which carries the recipe id, label and the originator and unit it stamps.

**A bare substring counts, case-insensitively.** The brief says "matches", the client reads file
names and job lists, and an innocent word that happens to contain the letters would still show them
in a list. If a real PID file ever hits one innocently, the answer is to say so, not to loosen this.

The words are built from pieces here, so that this file, which is itself a PID-named file the check
scans, does not contain them.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import sys
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from tools.layout import ROOT

#: Built from pieces on purpose (see the module docstring).
WORDS = ("h" + "mp", "holly" + "wood")
PATTERN = re.compile("|".join(re.escape(w) for w in WORDS), re.IGNORECASE)

TREES = ("OspreyFlow_Core", "OspreyFlow_Build")
SKIP_DIRECTORIES = frozenset(
    {"node_modules", ".venv", "dist", "__pycache__", ".git", ".mypy_cache", ".ruff_cache"}
)
#: `pid` or `prison_intelligence` as a word of a path part: `pid_plan.py`, `test_pid_files.py`,
#: `pid-explorer`, `prison_intelligence_demo`; not `rapid`, `stupid`, `pidgin`.
_PID_WORD = re.compile(r"(?:^|[_.\-])(?:pid|prison_intelligence)(?:[_.\-]|$)", re.IGNORECASE)
_TEXT_SUFFIXES = frozenset({".csv", ".json", ".txt", ".md", ".yaml", ".yml"})


@dataclass(frozen=True)
class Hit:
    where: str
    text: str

    def __str__(self) -> str:
        return f"{self.where}: {self.text.strip()[:160]}"


def repository_root() -> Path:
    return ROOT


def _scan(where: str, text: str) -> list[Hit]:
    """A hit for each line of `text` that holds a word, `where:LINE` for a multi-line text."""
    if not PATTERN.search(text):
        return []
    lines = text.splitlines() or [text]
    if len(lines) == 1:
        return [Hit(where, lines[0])]
    return [Hit(f"{where}:{n}", line) for n, line in enumerate(lines, 1) if PATTERN.search(line)]


# --- (a) the PID's files ------------------------------------------------------------------------


def pid_files(root: Path) -> list[Path]:
    """The PID's files, found by name under the two trees."""
    found: list[Path] = []
    for tree in TREES:
        top = root / tree
        if not top.is_dir():
            continue
        for current, directories, names in os.walk(top):
            directories[:] = sorted(d for d in directories if d not in SKIP_DIRECTORIES)
            for name in sorted(names):
                path = Path(current) / name
                relative = path.relative_to(root)
                if any(_PID_WORD.search(part) for part in relative.parts[1:]):
                    found.append(path)
    return found


def scan_files(root: Path, paths: Iterable[Path]) -> list[Hit]:
    hits: list[Hit] = []
    for path in paths:
        relative = str(path.relative_to(root))
        hits += _scan(f"file name {relative}", relative)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits += _scan(relative, text)
    return hits


# --- (b) the generated output -------------------------------------------------------------------


def _strings(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Every string in a plan: through dataclasses, mappings and sequences, with where it is."""
    if isinstance(value, str):
        yield path, value
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            yield from _strings(getattr(value, field.name), f"{path}.{field.name}")
    elif isinstance(value, Mapping):
        for key, inner in value.items():
            yield from _strings(key, f"{path}{{key}}")
            yield from _strings(inner, f"{path}[{key!r}]")
    elif isinstance(value, list | tuple | set | frozenset):
        for index, inner in enumerate(value):
            yield from _strings(inner, f"{path}[{index}]")


def scan_plan(plan: Any) -> list[Hit]:
    return [
        Hit(f"generated plan{where}", text)
        for where, text in _strings(plan)
        if PATTERN.search(text)
    ]


def scan_writes(plan: Any) -> list[Hit]:
    """Every node and link the plan writes by the end of the demo, as the writer would send it."""
    from demo_fixtures import pid_writes
    from demo_fixtures.datasets import PID

    nodes, links = pid_writes.writes(
        plan, "chapter9", dataset=PID.id, created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    hits: list[Hit] = []
    for kind, items in (("node", nodes), ("link", links)):
        for item in items:
            hits += _scan(f"generated {kind} {item.id}", item.model_dump_json())
    for node_id, name, _png in pid_writes.picture_writes(plan):
        hits += _scan(f"generated picture {node_id}", f"{node_id} {name}")
    return hits


def scan_generated_files(out: Path) -> list[Hit]:
    hits: list[Hit] = []
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        relative = str(path.relative_to(out))
        hits += _scan(f"generated file name {relative}", relative)
        if path.suffix.lower() in _TEXT_SUFFIXES:
            hits += _scan(f"generated file {relative}", path.read_text(encoding="utf-8"))
    return hits


def scan_generated(plan: Any | None = None, *, with_files: bool = True) -> list[Hit]:
    from demo_fixtures import pid_files as files
    from demo_fixtures import pid_plan

    plan = plan if plan is not None else pid_plan.build_plan("demo")
    hits = scan_plan(plan) + scan_writes(plan)
    if with_files:
        with tempfile.TemporaryDirectory() as folder:
            files.write_files(plan, Path(folder))
            hits += scan_generated_files(Path(folder))
    return hits


# --- (c) what the PID registers -----------------------------------------------------------------


def pid_datasets() -> list[Any]:
    from demo_fixtures.datasets import SEED_DATASETS

    return [
        d
        for d in SEED_DATASETS
        if d.id.startswith("prison-intelligence") or d.source.startswith("pid-")
    ]


def scan_registry(datasets: Iterable[Any] | None = None) -> list[Hit]:
    hits: list[Hit] = []
    for dataset in pid_datasets() if datasets is None else datasets:
        for field in dataclasses.fields(dataset):
            for _where, text in _strings(getattr(dataset, field.name)):
                if PATTERN.search(text):
                    hits.append(Hit(f"registered dataset {dataset.id}.{field.name}", text))
    return hits


def scan_recipes(paths: Iterable[Path]) -> list[Hit]:
    """Every string of each PID recipe (its id, label, and the originator and unit it stamps)."""
    hits: list[Hit] = []
    for path in paths:
        if path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        label = loaded.get("id", path.name) if isinstance(loaded, dict) else path.name
        for where, text in _strings(loaded):
            if PATTERN.search(text):
                hits.append(Hit(f"recipe {label}{where}", text))
    return hits


# --- the check ----------------------------------------------------------------------------------


class NothingToCheck(Exception):
    """The PID could not be found: a check over nothing proves nothing."""


def check(
    root: Path | None = None, *, generated: bool = True, plan: Any | None = None
) -> list[Hit]:
    root = root or repository_root()
    paths = pid_files(root)
    if not paths:
        raise NothingToCheck(f"no PID file found under {', '.join(TREES)} in {root}")
    datasets = pid_datasets()
    if not datasets:
        raise NothingToCheck("no PID dataset is registered in demo_fixtures/datasets.py")
    hits = scan_files(root, paths) + scan_registry(datasets) + scan_recipes(paths)
    if generated:
        hits += scan_generated(plan)
    return hits


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        prog="python -m tools.pid_naming_check", description=__doc__.split("\n\n")[0]
    ).parse_args(argv)
    sys.path[:0] = [str(repository_root() / "OspreyFlow_Core" / "packages")]
    try:
        hits = check()
    except NothingToCheck as error:
        print(f"pid-naming-check: {error}", file=sys.stderr)
        return 2
    for hit in hits:
        print(hit)
    if hits:
        print(f"pid-naming-check: {len(hits)} hit(s).", file=sys.stderr)
        return 1
    print(
        f"pid-naming-check: {len(pid_files(repository_root()))} PID file(s), "
        f"{len(pid_datasets())} registered dataset(s) and the generated demo output: no hit."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
