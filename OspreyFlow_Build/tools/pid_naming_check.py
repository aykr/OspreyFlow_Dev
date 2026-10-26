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

(d) *The seed and its registration* (ADR-127 Amendment 23). `scripts/seed_pid.py` is a PID file, so
    (a) reads it. What it prints is built at run time from the recipes' ids and the files' names, so
    its printed lines (the run's, the checks', the pictures', the brief's, the reset's and the
    mid-demo commands')
    are produced from real inputs and scanned; so are the folder, the worker and the other names it
    holds. The registration is read too: the pack's manifest, its description, the seed's entry in
    `seed_internal` and the command's pack key, and the lines of `DEMO_GUIDE.md` that name the
    dataset.

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


# --- (d) the seed and its registration ----------------------------------------------------------


def seed_lines() -> list[str]:
    """What `scripts.seed_pid` prints, produced from real inputs: every stage of the load order with
    the recipe id its committed file declares, the run's summary (a standing load's included),
    R5's measurements, the checks, the pictures', the demo numbers (each one failing, over an empty
    store, so the lines are built from the plan's own keys and values), the reset's (refused by a
    revert, with and without `--show-ids`, and carried out, with a file to remove) and the release
    of batch 2."""
    import asyncio
    import tempfile
    from types import SimpleNamespace

    from scripts import seed_pid
    from services.ingest.load_revert import Refusal, RevertRefused

    from demo_fixtures import pid_files as files
    from demo_fixtures import pid_plan
    from schemas.domain import Subgraph
    from schemas.ingest import LoadRecord, LoadReport

    root = Path("/ingest")
    stages = [seed_pid.resolve(stage, root) for stage in files.SEED_ORDER]
    results = [
        seed_pid.StageResult(
            stage,
            skipped=index % 3 == 0 and stage.stage.file != files.CALLS,
            report=None
            if index % 3 == 0 and stage.stage.file != files.CALLS
            else LoadReport(
                load_id="l", recipe_id=stage.recipe_id, recipe_version=stage.version,
                rows_read=7, nodes_created=2, edges_created=1,
            ),
            seconds=1.5,
            standing=seed_pid.StandingRun(rows_read=7, rejected=1, held=0)
            if index % 3 == 0 and stage.stage.file != files.CALLS and index % 2 == 0
            else None,
        )
        for index, stage in enumerate(stages)
    ]  # fmt: skip
    lines = seed_pid.summary_lines(results)
    lines += seed_pid.measurement_lines(results, peak_before_mb=100.0, peak_after_mb=200.0)
    lines += seed_pid.check_lines(results, {s.stage.file: 7 for s in stages})[0]
    lines += seed_pid.picture_lines(
        seed_pid.PictureSummary(attached=5, skipped=2, missing=["principal"],
                                refused=[("brother", "UploadRefusedError: refused")]), 8,
    )  # fmt: skip
    # ADR-128: the brief step's lines (written, left alone, failed) and the refusal of a persona who
    # is not the case's Author, each from the real function, and the brief's own texts.
    for summary in (
        seed_pid.BriefSummary(written=True, requirements=4, ok=True),
        seed_pid.BriefSummary(written=False, requirements=4, ok=True),
        seed_pid.BriefSummary(written=False, requirements=0, ok=False),
    ):
        lines += seed_pid.brief_lines(summary, seed_pid.ENGINEER_USERNAME)

    class NotTheAuthor:
        async def get_authorized(self, *args: Any, **kwargs: Any) -> None:
            from services.api.investigations import InvestigationNotFoundError

            raise InvestigationNotFoundError("c")

    try:
        asyncio.run(seed_pid.require_author(NotTheAuthor(), "c", seed_pid.engineer()))
    except seed_pid.SeedRefusal as refusal:
        lines.append(str(refusal))
    lines += [seed_pid.BRIEF_PRIORITY, *seed_pid.BRIEF_REQUIREMENTS]

    class Empty:
        """A store that holds nothing: every demo number fails and says what it could not find."""

        async def find_node(self, *args: Any) -> None:
            return None

        async def search_nodes(self, *args: Any, **kwargs: Any) -> list[Any]:
            return []

        async def expand(self, *args: Any) -> Subgraph:
            return Subgraph(nodes=[], edges=[])

        async def match(self, *args: Any) -> Subgraph:
            return Subgraph(nodes=[], edges=[])

        async def match_count(self, *args: Any, **kwargs: Any) -> int:
            return 0

    plan = pid_plan.build_plan("demo")
    for moment in ("seed", "chapter4"):
        numbers = asyncio.run(
            seed_pid.run_demo_checks(Empty(), seed_pid.engineer(), plan, moment)  # type: ignore[arg-type]
        )
        lines += seed_pid.demo_check_lines(numbers)[0]

    def record(load_id: str, recipe: str, source: str) -> LoadRecord:
        return LoadRecord(
            load_id=load_id, recipe_id=recipe, recipe_version=1, source=source,
            started_at=datetime(2026, 10, 26, tzinfo=UTC), created_by="w", created_node_ids=["n"],
        )  # fmt: skip

    class World:
        def __init__(self, resting: set[str]) -> None:
            self.resting = resting

        async def unreverted_loads(self, case: str, recipe_ids: Any) -> list[LoadRecord]:
            return [
                record("02", seed_pid.incidents_recipe_id(), seed_pid.source_of(root, files.REPORT_INCIDENTS)),
                record("01", seed_pid.reports_recipe_id(), seed_pid.source_of(root, files.REPORTS)),
            ]  # fmt: skip

        async def load_record(self, load_id: str) -> LoadRecord | None:
            return record(load_id, seed_pid.reports_recipe_id(), "x")

        async def live_edges_touching(self, node_ids: Any) -> set[str]:
            return set(self.resting)

        async def get_edges(self, ids: Any, principal: Any) -> list[Any]:
            return [SimpleNamespace(id=i, type="SAME_AS") for i in sorted(ids)]

        async def revert(self, load_id: str, **kwargs: Any) -> None:
            return None

        async def refuse(self, load_id: str, **kwargs: Any) -> None:
            raise RevertRefused([Refusal(load_id, "rests_on_by_live_links", 1)])

    async def nothing() -> None:
        return None

    async def not_at_its_start() -> bool:
        return False

    with tempfile.TemporaryDirectory() as folder:
        scratch = Path(folder)
        listed = seed_pid.listed_folder(scratch)
        (listed / seed_pid.INCOMING).mkdir(parents=True)
        (listed / "a_corrected_upload.csv").write_text("x", encoding="utf-8")
        (listed / files.BATCH_2).write_text("x", encoding="utf-8")
        (listed / seed_pid.INCOMING / files.BATCH_2).write_text("x", encoding="utf-8")
        for resting, refusing, show in (
            ({"same-as-1"}, True, False), ({"same-as-1"}, True, True), (set(), False, False),
        ):  # fmt: skip
            world = World(resting)
            asyncio.run(
                seed_pid.reset_live(
                    case_id="c", root=scratch, ledger=world, graph=world,
                    worker=seed_pid.engineer(),
                    revert=world.refuse if refusing else world.revert, deps=None,
                    now=datetime(2026, 10, 26, tzinfo=UTC), restore_draft=nothing,
                    draft_is_starting=not_at_its_start, rewrite_reports=lambda: None,
                    say=lines.append, show_ids=show,
                )  # fmt: skip
            )
        lines.append(seed_pid.release_batch_2(scratch).replace(str(scratch), "<root>"))
        lines.append(seed_pid.release_batch_2(scratch).replace(str(scratch), "<root>"))
    return lines


def scan_seed() -> list[Hit]:
    """The seed's own names (the folder, the loader, the unit, the legal basis and the two
    sentences it prints whole) and every line it prints, from `seed_lines`."""
    from scripts import seed_pid

    hits: list[Hit] = []
    for name in (
        "FOLDER", "INCOMING", "ENGINEER_USERNAME", "WORKER_UNIT", "LEGAL_BASIS", "BACKUP_COMMAND",
        "RESTORE_COMMAND", "FALLBACK_SKIPS", "BRIEF_PRIORITY", "BRIEF_REQUIREMENTS",
    ):  # fmt: skip
        hits += _scan(f"seed constant {name}", str(getattr(seed_pid, name)))
    for line in seed_lines():
        hits += _scan("seed printed line", line)
    return hits


def scan_registration(guide: Path | None = None) -> list[Hit]:
    """The pack's registration: its manifest, its description, the seed's entry in `seed_internal`,
    the command's pack key, and the lines of the demo guide that name the dataset."""
    from ospreyflow import demo as command
    from scripts import demo_packs, demo_registry, seed_internal

    pack_id = "prison-intelligence"
    hits: list[Hit] = []
    manifest = next(m for m in demo_registry.REGISTRY if m.id == pack_id)
    for field in dataclasses.fields(manifest):
        for _where, text in _strings(getattr(manifest, field.name)):
            hits += _scan(f"registered manifest {pack_id}.{field.name}", text)
    description = demo_packs._DESCRIPTIONS[pack_id]
    for field in dataclasses.fields(description):
        for _where, text in _strings(getattr(description, field.name)):
            hits += _scan(f"registered pack {pack_id}.{field.name}", text)
    seed = seed_internal.DATASETS[pack_id]
    for field in dataclasses.fields(seed):
        for _where, text in _strings(getattr(seed, field.name)):
            hits += _scan(f"registered seed {pack_id}.{field.name}", text)
    hits += _scan(f"registered pack key {pack_id}", command.PACK_KEYS[pack_id])
    path = guide or (repository_root() / "OspreyFlow_Core" / "DEMO_GUIDE.md")
    if path.is_file():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "Prison Intelligence Dataset" in line and PATTERN.search(line):
                hits.append(Hit(f"demo guide:{number}", line))
    return hits


def check(
    root: Path | None = None,
    *,
    generated: bool = True,
    plan: Any | None = None,
    seed: bool = True,
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
    if seed:
        hits += scan_seed() + scan_registration()
    return hits


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        prog="python -m tools.pid_naming_check", description=__doc__.split("\n\n")[0]
    ).parse_args(argv)
    core = repository_root() / "OspreyFlow_Core"
    sys.path[:0] = [str(core / "packages"), str(core / "cli"), str(core)]
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
        f"{len(pid_datasets())} registered dataset(s), the seed's names and printed lines, its "
        "registration and the generated demo output: no hit."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
