"""PL4d3d's proof of what changed: the differing units of the build are exactly the declared ones.

This slice splits code (the cases client, `admin/needsYou/openings.ts`,
`ingest/runs/ExternalOrchestration.tsx`), and `dist_compare` compares code units: a unit that is split or newly
made is a change by construction, so the slice's own required work cannot make `verify --build` say SAME.
The owner's ruling of 21 November 2026: the proof for a slice that splits code is the
checked list of differing units, not an identical build.

* `OspreyFlow_Build/tests/fixtures/pl4d3d_declared_units.txt` is that list: one differing unit a line, with its
  chunk, its side, its hash, the source module it comes from, the reason (`split`, `new`, `moved`, or `knock-on`) and,
  for a knock-on row, its basis. It is generated, never typed:
  `python OspreyFlow_Build/tests/glass_trees/test_pl4d3d_declared_units.py write` runs `dist_compare.mjs units` (the
  script's own uncapped list) on the pre-PL4 build and a fresh build of this tree, and writes what it prints.
* `test_the_differing_units_are_exactly_the_declared_ones` builds `apps/workspace`, runs the same command and compares
  the list with the file. An undeclared difference fails it; so does a declared unit that does not differ.

Which test fails if the invariant is broken (rule 12; each planted in the shape the real command prints, rule 15):

* **an undeclared change to one unit**: `test_an_undeclared_change_to_one_unit_is_red` edits one string of one unit
  (outside the declared ones) in a copy of the real build, then runs the real command on it;
* **a declared unit left unchanged**: `test_a_declared_unit_left_unchanged_is_red` compares the baseline with itself
  (so nothing differs) and `test_one_declared_unit_that_does_not_differ_is_red` drops one real row;
* **an extra declared unit**: `test_an_extra_declared_unit_is_red`.

Where the comparison runs, and how it retires (the conductor's rounds 2 and 4):

* **It needs the raw pre-PL4 build, which is not in the repository.** The folder is `PL4_BASELINE_DIST` (default
  `~/dev/osprey-acceptance/PL4a-baseline/dist`, the builder's and the verifier's Mac). Where it is absent (GitHub, a clean
  merge tree) the comparison **skips with a stated reason and never errors**.
* **The proof belongs to one baseline.** The declaration's first line is `against: <sha-256 of that folder>` (names and
  bytes). The comparison runs only if the folder's hash is that value; otherwise it skips with "this proof belongs to an
  earlier baseline".
* **The retirement is a scripted step, run by the conductor at merge, from the merged commit** (this file does not run it,
  and nothing here says the folder already holds the new build). From `OspreyFlow_Core`:
  `node scripts/dist_compare.mjs rebaseline --declared ../OspreyFlow_Build/tests/fixtures/pl4d3d_declared_units.txt --conductor-merge`
  (`--conductor-merge` is the conductor's own flag: **without it the step refuses, in words and touching nothing, to run against the
  default folder, the Mac's one real baseline**; the folder was swapped by hand six times in round 4, so the guard exists;
  `test_the_rebaseline_step_refuses_the_default_folder_without_the_conductors_flag` plants it on a scratch `HOME`.
  **Nothing else may run it against the real folder: not `rebaseline`, not `mv`, not `cp`**; every test here passes `--baseline <a
  temporary copy>`. `--declared` is required: `dist_compare.mjs` is Core's and does not name Build; `--baseline`, `--dist`, `--tests` and
  `--out` are for a folder, a build, a test output or a record other than the defaults). It builds the workspace from the checked-out commit; prints the
  old-against-new listing of differing units; **exits non-zero, touching nothing, if any differing unit is neither
  declared nor knock-on, or if a declared unit does not differ** (`test_the_rebaseline_step_refuses_an_undeclared_difference`
  and `test_the_rebaseline_step_refuses_a_declared_unit_that_does_not_differ` plant each); otherwise runs the
  workspace's unit tests, **moves the old baseline folder aside** (never deleted: a dated sibling,
  `<name>-before-<date>`), puts the new build in its place and writes `apps/workspace/PL4_BASELINE.json`. After it
  runs, the folder's hash is no longer the declaration's `against:` value, so this proof skips as an earlier baseline
  and later slices (D3e, slice E, AD1b) compare with `dist_compare verify --build`, which reads the recorded hash.
  The real folder holds the pre-PL4 build until then, so this proof runs on the Mac (its hash is the declaration's `against:`
  value); the conductor's step is what retires it.
* Tests that need no build always run: the declaration's own form, the gate itself (`proof_gate`: planted a folder that
  does not exist, one that does, a declaration for an earlier baseline, and one with no `against` line), the knock-on
  rule, and the rebaseline step on small builds made in a scratch folder.

**A fourth reason, `knock-on`, under a rule this file enforces (the owner's ruling of 21 November 2026).** A unit is
knock-on only if one of these holds, and its row says which in the `basis` column (`(a)` or `(b)`; every other row has `-`):

* **(a)** its source file's diff against main is import lines only (read against the merge-base of this tree and `main`,
  so a later change on main does not count; where there is no `main` ref, as on GitHub's shallow checkout, the real rows
  are not checked and the test says so; and once the slice is on main, that is, once the merge-base already holds
  `caseNavigation.ts`, the test skips and says so, so a later slice's own change to one of these files is not held to this
  slice's rule: that retirement is `slice_is_on_main`, planted below);
* **(b)** it is a built file that is byte-identical to the baseline's once the hashed chunk names
  (`assets/<stem>-<hash>.<ext>`, and every reference to one) are normalised on both sides, so the only differences are a
  changed chunk name or a reference to one. `dist_compare` does not expose its normaliser per file, so this file does it,
  strictly: a name is replaced only if it is a file of that very build. It runs on the real pair where the baseline exists.

Anything else declared as knock-on fails. Planted (red first): a knock-on row for a file whose diff changes a non-import
line, a `(b)` pair that differs in a string that is not a chunk name, and a knock-on row with neither `(a)` nor `(b)`.

**No two builds share a tree (the merge gate's round 8).** `npm run build --workspace apps/workspace` begins with
`sync_govuk_assets.mjs`, which removes and refills `apps/workspace/public/assets/govuk`, a folder every build in one tree
shares: two builds at once (this file's fixture in two xdist workers, or `test_workspace_bundle.py`'s or `test_render.py`'s
beside it) died with `ENOTEMPTY`. So every build this file makes (`build_to`) is made in **a private copy of the tree**,
not under a lock: a lock would hold only for the files that took it, and the other two files' builds are not this slice's to
change; a copy shares nothing with any of them. The copy is the workspace's source (no `node_modules`, `dist` or generated
`govuk` folder) with `node_modules` and `packages` linked, and builds the same output as the real tree (no differing unit).
`test_two_builds_in_one_tree_collide_and_two_builds_of_build_to_do_not` plants the race: two builds at once in one copy fail,
two `build_to`s at once both pass; `test_a_build_runs_in_a_private_copy_of_the_tree_never_in_the_real_one` shows no build
of this file runs in the real tree.

It builds, so it takes a few seconds beyond `dist_compare`'s own (about ten in all on an idle Mac; each comparison is
about five). Under load a timeout is the machine's, not the slice's.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import NamedTuple

import pytest

BUILD = Path(__file__).resolve().parents[2]
CORE = BUILD.parent / "OspreyFlow_Core"
SCRIPT = CORE / "scripts" / "dist_compare.mjs"
DECLARED = BUILD / "tests" / "fixtures" / "pl4d3d_declared_units.txt"
# The raw copy of the build before PL4 moved anything (the baseline `PL4_BASELINE.json` records the hash of).
BASELINE_DIST = Path(os.environ.get("PL4_BASELINE_DIST", Path.home() / "dev/osprey-acceptance/PL4a-baseline/dist"))
# The plain half of the cases client, written in pieces (D3d's old-path walk reads this file).
CASES = "glass-shared/src/" + "investigation/" + "cases.ts"
REASONS = {"split", "new", "moved", "knock-on"}
BASES = {"(a)", "(b)"}
SRC = CORE / "apps" / "workspace" / "src"
# The "source module" of a whole-file knock-on row: the page and a lazy chunk name the index chunk, which changed.
VIA_INDEX = "via index.js"
TIMEOUT = 600


class Unit(NamedTuple):
    file: str
    side: str
    sha: str


class Row(NamedTuple):
    """One line of the declaration."""

    unit: Unit
    source: str
    reason: str
    basis: str  # "(a)" or "(b)" for a knock-on row, "-" for every other
    text: str


# What generated the declaration decided for each unit, by what the unit says (label-free where it can be): the unit's
# source module, and why it differs. Used by `write` only: the check compares chunk, side and hash.
RULES: list[tuple[str, str, str]] = [
    # A whole file that differs only because it names the index chunk (the page, a lazy chunk that imports from it).
    (r"^\(names a file that changed, or another file\)$", VIA_INDEX, "knock-on"),
    (r"^function \$\w+\(\{apiBaseUrl:\$0,bearerToken:\$1,lastCaseId", "investigation/CasePicker.tsx", "knock-on"),
    (r"^function \$\w+\(\$0\)\{let\{pipelines:", "ingest/runs/RunsTab.tsx", "knock-on"),
    (r"investigationId:\$3,datasetId:\$4,deployed:", "ingest/runs/ExternalOrchestration.tsx", "split"),
    (r"/owned-externally`|/quota`", "ingest/runs/externalOrchestrationApi.ts", "new"),
    (r"method:`DELETE`,headers:\{Authorization:`Bearer \$\{\$1\}`\}\}\);if\(\$3\.status===403",
     CASES, "split"),
    (r"`ospreyflow\.investigationId`\)===\$2", "investigation/caseNavigation.ts", "split"),
    (r"^(var \$\w+=\(\)=>null|function \$\w+\(\$0\)\{\$\w+=\$0,\$\w+=\$\w+\(\)\}|\$\w+\(\(\)=>sessionStorage\);)",
     "admin/needsYou/openings.ts", "new"),
    (r"sessionStorage|\.getItem\(|\.removeItem\(|\.setItem\(|^var \$\w+=\$\w+\(\)$|\$61bfe3",
     "admin/needsYou/openings.ts", "split"),
]


def folder_hash(folder: Path) -> str:
    """A sha-256 over every file's relative name and bytes, in name order: what `against:` records."""
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        digest.update(path.relative_to(folder).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def proof_gate(baseline: Path, declared_text: str) -> str | None:
    """Why the unit comparison must not run here (a stated reason), or None when it should."""
    if not baseline.is_dir():
        return (
            f"the declared-units proof runs where `PL4_BASELINE_DIST` exists (the builder's and the verifier's Mac); "
            f"there is no baseline build at {baseline}"
        )
    first = next((line for line in declared_text.splitlines() if line.strip()), "")
    match = re.fullmatch(r"against: ([0-9a-f]{64})", first)
    if not match:
        return "the declaration names no baseline (its first line must be `against: <sha-256 of the folder>`): the proof does not run"
    if folder_hash(baseline) != match.group(1):
        return (
            "this proof belongs to an earlier baseline: the baseline folder no longer holds the build the declaration "
            "was generated against (the conductor's rebaseline step replaced it), so later slices are not held to it"
        )
    return None


# ------------------------------------------------------------------------------------------ the knock-on rule
# (a) a source file whose diff against main is import lines only. An import statement is `import` then names, braces and
# commas (nothing a line of code could hold: no `(`, `=` or `;`), `from`, a quoted module and an optional `;`; a bare
# `import "x";` too. Blank lines are not a difference.
IMPORT = re.compile(r"^import\s+(?:[\w$*\s{},]*?\s*from\s*)?[\"'][^\"'\n]+[\"'];?[ \t]*$", re.MULTILINE)


def without_imports(text: str) -> list[str]:
    return [line for line in IMPORT.sub("", text).splitlines() if line.strip()]


def non_import_changes(before: str, after: str) -> list[str]:
    """The changed lines (with `-`/`+`) that are not import statements or blank lines; empty when only imports differ."""
    diff = difflib.unified_diff(without_imports(before), without_imports(after), lineterm="", n=0)
    return [line for line in diff if not line.startswith(("---", "+++", "@@"))]


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60, check=False)


def repo_root() -> Path:
    return Path(git(BUILD, "rev-parse", "--show-toplevel").stdout.strip())


def merge_base(repo: Path, main: str = "main") -> str | None:
    """Where this tree left `main`, or None when there is no such ref (GitHub's shallow checkout)."""
    done = git(repo, "merge-base", "HEAD", main)
    return done.stdout.strip() if done.returncode == 0 else None


SLICE_MARKER = "OspreyFlow_Core/apps/workspace/src/investigation/caseNavigation.ts"  # a file only this slice makes


def slice_is_on_main(repo: Path, base: str, marker: str = SLICE_MARKER) -> bool:
    """True when the merge-base already holds the slice's own new file: the slice has merged, and rule (a) retires."""
    return git(repo, "cat-file", "-e", f"{base}:{marker}").returncode == 0


def source_difference(repo: Path, base: str, relative: str) -> list[str]:
    """The non-import changes of one file between `base` and the working tree (the file's `git diff`, read as (a) says)."""
    shown = git(repo, "show", f"{base}:{relative}")
    before = shown.stdout if shown.returncode == 0 else ""  # a file that was not there: all of it is a change
    return non_import_changes(before, (repo / relative).read_text(encoding="utf-8"))


# (b) a built file identical to the baseline's once chunk names are normalised. A hashed name is `assets/<stem>-<8
# characters>.<ext>` (dist_compare's own pattern); it is replaced, wherever the file's text names it, by `<stem><ext>`,
# and only when it is a file of that very build, so a string that merely looks like one is left and shows as a difference.
HASHED = re.compile(r"^assets/([^/]+)-([A-Za-z0-9_-]{8})(\.[A-Za-z0-9.]+)$")


def hashed_names(dist: Path) -> dict[str, str]:
    """`<stem>-<hash><ext>` of each hashed file under `assets/`, with the name it normalises to."""
    names = {}
    for path in (dist / "assets").iterdir() if (dist / "assets").is_dir() else []:
        match = HASHED.fullmatch(f"assets/{path.name}")
        if match and path.is_file():
            names[path.name] = f"<{match.group(1)}{match.group(3)}>"
    return names


def find_built(dist: Path, file: str) -> Path:
    """A row's file in a build: the page itself, or the one hashed file with that stem and extension."""
    if (dist / file).is_file():
        return dist / file
    found = [
        path for path in (dist / "assets").iterdir()
        if (m := HASHED.fullmatch(f"assets/{path.name}")) and f"{m.group(1)}{m.group(3)}" == file
    ]
    assert len(found) == 1, f"{file}: {len(found)} files of that name in {dist}"
    return found[0]


def normalised_text(dist: Path, file: str) -> str:
    text = find_built(dist, file).read_text(encoding="utf-8")
    for name, plain in sorted(hashed_names(dist).items(), key=lambda item: -len(item[0])):
        text = text.replace(name, plain)
    return text


def chunk_name_difference(before: Path, after: Path, file: str) -> list[str]:
    """What still differs between one file of two builds once chunk names are normalised; empty when byte-identical."""
    diff = difflib.unified_diff(
        normalised_text(before, file).splitlines(), normalised_text(after, file).splitlines(), lineterm="", n=0
    )
    return [line[:300] for line in diff if not line.startswith(("---", "+++", "@@"))]


def node() -> str:
    found = shutil.which("node")
    assert found, "node is needed"
    return found


def read_units(before: Path, after: Path) -> list[tuple[Unit, str]]:
    """`dist_compare.mjs units <before> <after>`: the script's own uncapped list of differing units."""
    done = subprocess.run(
        [node(), str(SCRIPT), "units", str(before), str(after)],
        cwd=CORE, capture_output=True, text=True, timeout=TIMEOUT, check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    rows = []
    for line in done.stdout.splitlines():
        file, side, sha, text = line.split("\t", 3)
        rows.append((Unit(file, side, sha), text))
    return rows


def scratch_tree(parent: Path) -> Path:
    """A private copy of `apps/workspace` (and links to what it reads) to build in; returns the copy's `apps/workspace`.

    The real tree's `public/assets/govuk` is written by every build in it, so two builds in one tree at once collide
    (`ENOTEMPTY`, the merge gate's round 8). Each build here gets its own tree: the source is copied (no `node_modules`,
    `dist` or generated `govuk` folder); `node_modules` and `packages` (the design CSS, the glass-shared package, which a
    build only reads) are links to the real ones. Its output is the same as the real tree's build, byte for byte."""
    app = parent / "apps" / "workspace"
    shutil.copytree(
        CORE / "apps" / "workspace", app, symlinks=True,
        ignore=lambda folder, names: [
            name for name in names
            if name in {"node_modules", "dist"} or (name == "govuk" and Path(folder).parts[-2:] == ("public", "assets"))
        ],
    )
    (parent / "node_modules").symlink_to(CORE / "node_modules")
    (parent / "packages").symlink_to(CORE / "packages")
    return app


def run_build(app: Path, directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["npm", "run", "build", "--", "--outDir", str(directory), "--emptyOutDir"],
        cwd=app, capture_output=True, text=True, timeout=TIMEOUT, check=False,
    )


def build_to(directory: Path) -> Path:
    """A fresh build of `apps/workspace` into `directory`: built in a private copy of the tree, never in the real one,
    so no other build in the sweep (this file's, `test_workspace_bundle.py`'s, `test_render.py`'s) can race it."""
    with tempfile.TemporaryDirectory(prefix="pl4d3d-tree-") as scratch:
        done = run_build(scratch_tree(Path(scratch)), directory)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    return directory


def parse_declared(text: str) -> list[Row]:
    """The declaration's rows. A knock-on row must say its basis, `(a)` or `(b)`; any other row has `-`."""
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith(("#", "against: ")):
            continue
        parts = line.split("\t", 6)
        assert len(parts) == 7, f"line {number}: expected chunk, side, hash, source, reason, basis, unit"
        file, side, sha, source, reason, basis, unit = parts
        assert side in {"only before", "only after"}, f"line {number}: side {side!r}"
        assert re.fullmatch(r"[0-9a-f]{12}", sha), f"line {number}: hash {sha!r}"
        assert reason in REASONS, f"line {number}: reason {reason!r} is none of {sorted(REASONS)}"
        assert source.endswith((".ts", ".tsx")) or source == VIA_INDEX, f"line {number}: source {source!r}"
        if reason == "knock-on":
            assert basis in BASES, f"line {number}: a knock-on row needs its basis, (a) or (b), not {basis!r}"
            assert (basis == "(b)") == (source == VIA_INDEX), (
                f"line {number}: (b) is for a built file ({VIA_INDEX!r}), (a) for a source file"
            )
        else:
            assert basis == "-", f"line {number}: only a knock-on row has a basis, not {basis!r}"
        assert unit.strip(), f"line {number}: no unit"
        rows.append(Row(Unit(file, side, sha), source, reason, basis, unit))
    return rows


def problems(actual: list[tuple[Unit, str]], declared: list[Row]) -> list[str]:
    """Every way the differing units and the declaration disagree; empty when they are exactly the same list."""
    found = []
    wanted = [row.unit for row in declared]
    for unit, text in actual:
        if unit in wanted:
            wanted.remove(unit)
        else:
            found.append(f"undeclared difference: {unit.file} {unit.side}: {text[:120]}")
    for unit in wanted:
        found.append(f"declared but not differing: {unit.file} {unit.side} {unit.sha}")
    return found


def classify(text: str) -> tuple[str, str, str]:
    for pattern, source, reason in RULES:
        if re.search(pattern, text):
            basis = "-" if reason != "knock-on" else ("(b)" if source == VIA_INDEX else "(a)")
            return source, reason, basis
    raise AssertionError(f"no rule says where this unit comes from: {text[:160]}")


def declaration(rows: list[tuple[Unit, str]]) -> str:
    head = [
        f"against: {folder_hash(BASELINE_DIST)}",
        "# PL4d3d: the units of the build that differ from the build before PL4 (ADR-152 R2), and why.",
        "# Generated by `python OspreyFlow_Build/tests/glass_trees/test_pl4d3d_declared_units.py write` from",
        "# `node scripts/dist_compare.mjs units <pre-PL4 dist> <this build>`; not typed by hand.",
        "# chunk <TAB> side <TAB> sha-256 of the unit, first 12 <TAB> source module <TAB> reason <TAB> basis <TAB> the unit.",
        "# reasons: split (a unit cut in two), new (a unit that did not exist), moved, knock-on. A knock-on row says its",
        "# basis (the owner's rule of 21 November 2026): (a) its source file's diff against main is import lines only;",
        "# (b) it is a built file byte-identical to the baseline's once hashed chunk names are normalised. Other rows: -.",
        "# The test enforces both; a knock-on row that meets neither fails the slice.",
    ]
    body = []
    for unit, text in rows:
        source, reason, basis = classify(text)
        body.append(f"{unit.file}\t{unit.side}\t{unit.sha}\t{source}\t{reason}\t{basis}\t{text}")
    return "\n".join([*head, *sorted(body)]) + "\n"


# ------------------------------------------------------------------------------------------------------ the builds
@pytest.fixture(scope="module")
def baseline() -> Path:
    """The raw pre-PL4 build, or a skip with the reason: no test here errors on a missing or later baseline."""
    reason = proof_gate(BASELINE_DIST, DECLARED.read_text(encoding="utf-8") if DECLARED.is_file() else "")
    if reason:
        pytest.skip(reason)
    return BASELINE_DIST


@pytest.fixture(scope="module")
def built(baseline: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_to(tmp_path_factory.mktemp("pl4d3d") / "dist")


@pytest.fixture(scope="module")
def actual(built: Path) -> list[tuple[Unit, str]]:
    return read_units(BASELINE_DIST, built)


@pytest.fixture(scope="module")
def declared() -> list[Row]:
    assert DECLARED.is_file(), f"{DECLARED.relative_to(BUILD.parent)} is not there: generate it (see this file's head)"
    return parse_declared(DECLARED.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------------ the proof
def test_the_differing_units_are_exactly_the_declared_ones(
    actual: list[tuple[Unit, str]], declared: list[Row]
) -> None:
    assert actual, "no unit differs: the build was not compared with the pre-PL4 one"
    assert problems(actual, declared) == []


def test_each_whole_file_knock_on_row_differs_only_in_chunk_names(
    built: Path, declared: list[Row]
) -> None:
    """(b), on the real pair: the pre-PL4 build and this build, file by file, once chunk names are normalised."""
    files = sorted({row.unit.file for row in declared if row.reason == "knock-on" and row.basis == "(b)"})
    assert files == ["index.html", "sigma-export-image.esm.js"]
    for file in files:
        changed = chunk_name_difference(BASELINE_DIST, built, file)
        assert changed == [], f"{file} is not knock-on: it differs in more than chunk names:\n" + "\n".join(changed)


def test_the_declaration_names_each_split_the_brief_declares(declared: list[Row]) -> None:
    sources = {row.source for row in declared}
    assert {
        "admin/needsYou/openings.ts",
        CASES,
        "investigation/caseNavigation.ts",
        "ingest/runs/externalOrchestrationApi.ts",
        "ingest/runs/ExternalOrchestration.tsx",
    } <= sources
    # The units are in the index chunk; the page and one lazy chunk differ as whole files only because they name it.
    assert {row.unit.file for row in declared} == {"index.js", "index.html", "sigma-export-image.esm.js"}
    assert {row.unit.file for row in declared if row.reason == "knock-on" and row.source == VIA_INDEX} == {
        "index.html",
        "sigma-export-image.esm.js",
    }


def test_an_undeclared_change_to_one_unit_is_red(
    built: Path, tmp_path: Path, actual: list[tuple[Unit, str]], declared: list[Row]
) -> None:
    planted = tmp_path / "dist"
    shutil.copytree(built, planted)
    chunk = next((planted / "assets").glob("index-*.js"))
    text = chunk.read_text(encoding="utf-8")
    literal = "Skip to main content"
    assert text.count(literal) == 1, "the plant needs one literal in one unit"
    chunk.write_text(text.replace(literal, "Skip to the main content"), encoding="utf-8")
    now = read_units(BASELINE_DIST, planted)
    found = problems(now, declared)
    assert problems(actual, declared) == []
    # A unit others call is named by its content: its callers differ with it, so more than one pair is red.
    assert len(now) >= len(actual) + 2
    # The page and the lazy chunk that name the index chunk differ with it: their declared rows change hash too.
    assert len([p for p in found if p.startswith("undeclared difference")]) >= len(now) - len(actual)
    # The units printed are cut at 220 characters, so the literal itself may not show: the rows that are new are
    # what the plant changed, and none of them is a declared unit.
    known = {unit for unit, _text in actual}
    new_rows = [unit for unit, _text in now if unit not in known]
    assert not [unit for unit in new_rows if unit in {row.unit for row in declared}]
    assert any(unit.file == "index.js" for unit in new_rows)


# A difference that is a whole file is not a unit of one: `dist_compare` reports it at file level, and the listing must
# too (the round-2 verifier: an added or removed chunk, a changed image or font printed nothing). Each is planted in a
# copy of the real build, in the shape `dist_compare` itself reads (a `assets/<name>-<8 characters>.<ext>` file, a file
# a page asks for by name, a changed asset), then the real command is run on it.
def planted_copy(built: Path, tmp_path: Path) -> Path:
    planted = tmp_path / "dist"
    shutil.copytree(built, planted)
    return planted


def assert_red(planted: Path, actual: list[tuple[Unit, str]], declared: list[Row], want: str) -> None:
    now = read_units(BASELINE_DIST, planted)
    known = {unit for unit, _text in actual}
    new_rows = [(unit, text) for unit, text in now if unit not in known]
    assert new_rows, "the plant is a difference the listing does not show"
    assert any(want in text for _unit, text in new_rows), [text for _unit, text in new_rows]
    found = problems(now, declared)
    # A page or chunk that names the changed file differs with it (its own declared row changes hash), so a declared
    # row may stop differing as well: red is that an undeclared row appears.
    assert [p for p in found if p.startswith("undeclared difference")]


def test_a_chunk_added_to_the_build_is_red(
    built: Path, tmp_path: Path, actual: list[tuple[Unit, str]], declared: list[Row]
) -> None:
    planted = planted_copy(built, tmp_path)
    (planted / "assets" / "plantedChunk-AbCd1234.js").write_text("export const planted=1;\n", encoding="utf-8")
    assert_red(planted, actual, declared, "file added")


def test_a_chunk_removed_from_the_build_is_red(
    built: Path, tmp_path: Path, actual: list[tuple[Unit, str]], declared: list[Row]
) -> None:
    planted = planted_copy(built, tmp_path)
    next((planted / "assets").glob("*.woff2")).unlink()
    assert_red(planted, actual, declared, "file removed")
    # A code chunk that goes is read against the nearest one that is left, so its units show as differing units.
    gone = tmp_path / "gone"
    shutil.copytree(built, gone)
    next((gone / "assets").glob("communityWorker-*.js")).unlink()
    assert_red(gone, actual, declared, "")


def test_a_changed_asset_is_red(
    built: Path, tmp_path: Path, actual: list[tuple[Unit, str]], declared: list[Row]
) -> None:
    planted = planted_copy(built, tmp_path)
    font = next((planted / "assets").glob("*.woff2"))
    font.write_bytes(font.read_bytes() + b"\0")
    assert_red(planted, actual, declared, "the bytes differ")


def test_a_file_added_or_removed_by_name_is_red(
    built: Path, tmp_path: Path, actual: list[tuple[Unit, str]], declared: list[Row]
) -> None:
    added = planted_copy(built, tmp_path)
    (added / "planted.txt").write_text("a page asks for me by name\n", encoding="utf-8")
    assert_red(added, actual, declared, "file added: a page asks for it by name")
    removed = tmp_path / "removed"
    shutil.copytree(built, removed)
    (removed / "cookies.html").unlink()
    assert_red(removed, actual, declared, "file removed: a page asks for it by name")


def test_the_listing_has_a_row_for_every_finding_of_compare(built: Path) -> None:
    """`compare` and `units` agree on whether the builds differ: no finding is dropped from the listing."""
    done = subprocess.run(
        [node(), str(SCRIPT), "compare", str(BASELINE_DIST), str(built)],
        cwd=CORE, capture_output=True, text=True, timeout=TIMEOUT, check=False,
    )
    assert done.returncode == 1 and done.stdout.startswith("DIFFERENT")
    assert read_units(BASELINE_DIST, built)


def test_a_declared_unit_left_unchanged_is_red(baseline: Path, declared: list[Row]) -> None:
    assert read_units(baseline, baseline) == []
    found = problems([], declared)
    assert len(found) == len(declared)
    assert all(p.startswith("declared but not differing") for p in found)


def test_one_declared_unit_that_does_not_differ_is_red(
    actual: list[tuple[Unit, str]], declared: list[Row]
) -> None:
    found = problems(actual[1:], declared)
    assert found == [f"declared but not differing: {actual[0][0].file} {actual[0][0].side} {actual[0][0].sha}"]


def test_an_extra_declared_unit_is_red(
    actual: list[tuple[Unit, str]], declared: list[Row]
) -> None:
    extra = Row(Unit("index.js", "only after", "0" * 12), CASES, "split", "-", "function x(){}")
    assert problems(actual, [*declared, extra]) == ["declared but not differing: index.js only after " + "0" * 12]


def test_a_unit_declared_twice_is_not_one_difference(
    actual: list[tuple[Unit, str]], declared: list[Row]
) -> None:
    found = problems(actual, [*declared, declared[0]])
    assert len(found) == 1 and found[0].startswith("declared but not differing")


# ------------------------------------------------------------------------------- where the proof runs (no build)
GOOD_ROW = "index.js\tonly after\t" + "a" * 12 + "\tx.ts\tsplit\t-\tunit\n"


def declared_for(folder: Path) -> str:
    """A declaration written against `folder`, in the shape `write` makes."""
    return f"against: {folder_hash(folder)}\n" + GOOD_ROW


def test_the_declaration_says_which_baseline_it_belongs_to() -> None:
    first = DECLARED.read_text(encoding="utf-8").splitlines()[0]
    assert re.fullmatch(r"against: [0-9a-f]{64}", first), f"the first line must be `against: <sha-256 of the folder>`: {first!r}"


def test_a_missing_baseline_folder_skips_with_the_reason_and_never_errors(tmp_path: Path) -> None:
    gone = tmp_path / "not-there"
    reason = proof_gate(gone, declared_for(tmp_path))
    assert reason is not None
    assert "runs where `PL4_BASELINE_DIST` exists (the builder's and the verifier's Mac)" in reason


def test_a_folder_that_exists_and_matches_does_not_skip(tmp_path: Path) -> None:
    (tmp_path / "index.js").write_text("a", encoding="utf-8")
    assert proof_gate(tmp_path, declared_for(tmp_path)) is None


def test_a_declaration_for_an_earlier_baseline_skips_and_retires_the_proof(tmp_path: Path) -> None:
    older, newer = tmp_path / "older", tmp_path / "newer"
    for folder, content in ((older, "a"), (newer, "b")):
        folder.mkdir()
        (folder / "index.js").write_text(content, encoding="utf-8")
    declared_older = declared_for(older)
    assert proof_gate(older, declared_older) is None
    reason = proof_gate(newer, declared_older)  # once the conductor's rebaseline has put the new build in the folder
    assert reason is not None and "belongs to an earlier baseline" in reason


def test_the_folder_hash_reads_names_and_bytes(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("x", encoding="utf-8")
    first = folder_hash(tmp_path)
    (tmp_path / "a.js").write_text("y", encoding="utf-8")
    second = folder_hash(tmp_path)
    (tmp_path / "a.js").rename(tmp_path / "b.js")
    assert len({first, second, folder_hash(tmp_path)}) == 3


def test_a_declaration_with_no_against_line_never_runs_the_proof(tmp_path: Path) -> None:
    reason = proof_gate(tmp_path, GOOD_ROW)
    assert reason is not None and "against" in reason


def test_the_reasons_and_sources_are_well_formed() -> None:
    good = GOOD_ROW
    assert [row.unit for row in parse_declared(good)] == [Unit("index.js", "only after", "a" * 12)]
    with pytest.raises(AssertionError, match="because"):
        parse_declared(good.replace("split", "because"))
    with pytest.raises(AssertionError, match="hash"):
        parse_declared(good.replace("a" * 12, "a" * 11))


# ---------------------------------------------------------------------------------------------- the knock-on rule
def test_a_knock_on_row_needs_its_basis_and_only_a_knock_on_row_has_one() -> None:
    knock = "index.js\tonly after\t" + "a" * 12 + "\tinvestigation/CasePicker.tsx\tknock-on\t(a)\tunit\n"
    assert [row.basis for row in parse_declared(knock)] == ["(a)"]
    with pytest.raises(AssertionError, match="needs its basis"):
        parse_declared(knock.replace("(a)", "-"))  # a knock-on row with neither (a) nor (b)
    with pytest.raises(AssertionError, match="needs its basis"):
        parse_declared(knock.replace("(a)", "(c)"))
    with pytest.raises(AssertionError, match="expected"):
        parse_declared(knock.replace("\t(a)", ""))  # the column is missing altogether
    with pytest.raises(AssertionError, match="only a knock-on row has a basis"):
        parse_declared(GOOD_ROW.replace("\t-\t", "\t(a)\t"))
    with pytest.raises(AssertionError, match=r"\(b\) is for a built file"):
        parse_declared(knock.replace("(a)", "(b)"))
    whole = "index.html\tonly after\t" + "a" * 12 + f"\t{VIA_INDEX}\tknock-on\t(b)\t(whole file)\n"
    assert [row.basis for row in parse_declared(whole)] == ["(b)"]
    with pytest.raises(AssertionError, match=r"\(a\) for a source file"):
        parse_declared(whole.replace("(b)", "(a)"))


def test_every_knock_on_row_of_the_declaration_names_a_basis(declared: list[Row]) -> None:
    knock_on = [row for row in declared if row.reason == "knock-on"]
    assert len(knock_on) == 8, "the owner's eight rows: index.html and the sigma chunk both sides, CasePicker, RunsTab"
    assert {row.basis for row in knock_on} == BASES
    for row in declared:
        if row.reason == "knock-on" and row.basis == "(a)":
            assert (SRC / row.source).is_file(), f"{row.source} is not a workspace source file"


def test_a_knock_on_source_row_has_only_import_lines_in_its_diff_against_main(declared: list[Row]) -> None:
    """(a), on the real rows: the diff of each source file against where this tree left `main`."""
    repo = repo_root()
    base = merge_base(repo)
    if base is None:
        pytest.skip("no `main` ref here (GitHub's shallow checkout): rule (a) is checked where main exists, and was by the builder")
    if slice_is_on_main(repo, base):
        pytest.skip("this slice is already on main: rule (a) was checked at its merge, and a later change is not this slice's")
    for source in sorted({row.source for row in declared if row.reason == "knock-on" and row.basis == "(a)"}):
        changed = source_difference(repo, base, (SRC / source).relative_to(repo).as_posix())
        assert changed == [], f"{source} is not knock-on: its diff against main changes more than import lines:\n" + "\n".join(changed)


def test_the_source_rule_is_red_for_a_changed_line_that_is_not_an_import(tmp_path: Path) -> None:
    """Planted in a real git repository, read the way the real rows are (`git show <base>:<file>` against the file)."""
    git(tmp_path, "init", "-q")
    file = tmp_path / "Picker.tsx"
    original = 'import { a } from "./a";\nimport {\n  b,\n  c,\n} from "./b";\n\nexport const x = a + b + c;\n'
    file.write_text(original, encoding="utf-8")
    git(tmp_path, "add", "Picker.tsx")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "base")
    base = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    assert merge_base(tmp_path, "no-such-ref") is None
    # Only imports change (one repointed, one multi-line import reshaped, a blank line gone): not a difference.
    file.write_text('import { a } from "@pkg/shared";\nimport { b, c } from "./b";\nexport const x = a + b + c;\n', encoding="utf-8")
    assert source_difference(tmp_path, base, "Picker.tsx") == []
    # A non-import line changes with the imports: red, and it names the line.
    file.write_text('import { a } from "@pkg/shared";\nimport { b, c } from "./b";\nexport const x = a + b + c + 1;\n', encoding="utf-8")
    changed = source_difference(tmp_path, base, "Picker.tsx")
    assert changed == ["-export const x = a + b + c;", "+export const x = a + b + c + 1;"]
    # A line that only looks like an import (it has code in it) is a change too.
    file.write_text(original.replace("\n\nexport", '\nimport "x"; run();\n\nexport'), encoding="utf-8")
    assert source_difference(tmp_path, base, "Picker.tsx") == ['+import "x"; run();']


def test_the_source_rule_retires_once_the_slice_is_on_main(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / "a.ts").write_text("export const a = 1;\n", encoding="utf-8")
    git(tmp_path, "add", "a.ts")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "before the slice")
    before = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    assert not slice_is_on_main(tmp_path, before, "marker.ts")
    (tmp_path / "marker.ts").write_text("export const m = 1;\n", encoding="utf-8")
    git(tmp_path, "add", "marker.ts")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "the slice merged")
    after = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    assert slice_is_on_main(tmp_path, after, "marker.ts")


def synthetic_dist(root: Path, *, index_hash: str, lazy_hash: str, answer: int = 1, lazy_body: str = "a+1") -> Path:
    """A small build in the shape Vite writes: a page, the index chunk, and a lazy chunk that imports from the index."""
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(f'<script type="module" src="/assets/index-{index_hash}.js"></script>\n', encoding="utf-8")
    (root / "assets" / f"index-{index_hash}.js").write_text(f"export const answer={answer};export const f=(n)=>n+1;\n", encoding="utf-8")
    (root / "assets" / f"lazy-{lazy_hash}.js").write_text(
        f'import{{answer as a}}from"./index-{index_hash}.js";export const g=()=>{lazy_body};\n', encoding="utf-8"
    )
    return root


def test_the_built_file_rule_is_green_for_a_chunk_name_alone_and_red_for_any_other_string(tmp_path: Path) -> None:
    """(b), in the shape Vite writes: the page and a lazy chunk name the index chunk by its hashed name."""
    before = synthetic_dist(tmp_path / "before", index_hash="AAAAAAAA", lazy_hash="11111111")
    renamed = synthetic_dist(tmp_path / "renamed", index_hash="BBBBBBBB", lazy_hash="22222222")
    for file in ("index.html", "lazy.js", "index.js"):
        assert chunk_name_difference(before, renamed, file) == []  # only a chunk name (and references to it) differ
    assert (before / "index.html").read_bytes() != (renamed / "index.html").read_bytes()  # the raw files do differ
    # A string that is not a chunk name changes as well: red, and the diff is shown.
    other = synthetic_dist(tmp_path / "other", index_hash="BBBBBBBB", lazy_hash="22222222", lazy_body="a+2")
    changed = chunk_name_difference(before, other, "lazy.js")
    assert changed and any("a+2" in line for line in changed)
    # A string that merely looks like a chunk name, but is none of the build's files, is a difference too.
    look = synthetic_dist(tmp_path / "look", index_hash="BBBBBBBB", lazy_hash="22222222")
    (look / "assets" / "lazy-22222222.js").write_text(
        'import{answer as a}from"./index-BBBBBBBB.js";export const g=()=>a+1;export const n="assets/other-ZZZZZZZZ.js";\n', encoding="utf-8"
    )
    assert chunk_name_difference(before, look, "lazy.js")
    # The index chunk's own content changed: its rows are not knock-on, and the rule shows it.
    edited = synthetic_dist(tmp_path / "edited", index_hash="BBBBBBBB", lazy_hash="22222222", answer=2)
    assert chunk_name_difference(before, edited, "index.js")


# ----------------------------------------------------------------------------- the rebaseline step (no real build)
def run_rebaseline(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([node(), str(SCRIPT), "rebaseline", *args], cwd=CORE, capture_output=True, text=True, timeout=TIMEOUT, check=False)


TESTS_OUTPUT = " Test Files  2 passed (2)\n      Tests  5 passed (5)\n"


def declaration_for(listing: str) -> str:
    """A declared file for a `units` listing, in the shape `write` makes (the script reads the first three columns)."""
    body = []
    for line in listing.splitlines():
        file, side, sha, text = line.split("\t", 3)
        body.append(f"{file}\t{side}\t{sha}\tx.ts\tsplit\t-\t{text}")
    return "against: " + "0" * 64 + "\n# test\n" + "\n".join(body) + "\n"


def rebaseline_scene(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    old = synthetic_dist(tmp_path / "baseline" / "dist", index_hash="AAAAAAAA", lazy_hash="11111111")
    new = synthetic_dist(tmp_path / "new", index_hash="BBBBBBBB", lazy_hash="22222222", answer=2)
    tests = tmp_path / "tests.txt"
    tests.write_text(TESTS_OUTPUT, encoding="utf-8")
    return old, new, tests, tmp_path / "PL4_BASELINE.json"


def test_the_rebaseline_step_refuses_an_undeclared_difference(tmp_path: Path) -> None:
    old, new, tests, out = rebaseline_scene(tmp_path)
    listing = subprocess.run([node(), str(SCRIPT), "units", str(old), str(new)], cwd=CORE, capture_output=True, text=True, check=True).stdout
    assert listing.count("\n") >= 3  # the index chunk's unit both sides, and the lazy chunk and the page as knock-ons
    lines = listing.splitlines()
    declared_text = tmp_path / "declared.txt"
    declared_text.write_text(declaration_for("\n".join(lines[1:])), encoding="utf-8")  # one differing unit left undeclared
    before = folder_hash(old)
    done = run_rebaseline("--baseline", str(old), "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out))
    assert done.returncode != 0, done.stdout
    assert "UNDECLARED" in done.stdout and "REFUSED" in done.stdout
    assert folder_hash(old) == before, "a refused rebaseline must leave the baseline folder as it was"
    assert not out.exists(), "a refused rebaseline must not write the record"
    assert [p.name for p in old.parent.iterdir()] == ["dist"], "nothing is moved aside when it refuses"


def test_the_rebaseline_step_replaces_the_folder_and_the_record_and_keeps_the_old_folder(tmp_path: Path) -> None:
    old, new, tests, out = rebaseline_scene(tmp_path)
    listing = subprocess.run([node(), str(SCRIPT), "units", str(old), str(new)], cwd=CORE, capture_output=True, text=True, check=True).stdout
    declared_text = tmp_path / "declared.txt"
    declared_text.write_text(declaration_for(listing), encoding="utf-8")
    old_hash, new_hash = folder_hash(old), folder_hash(new)
    assert old_hash != new_hash
    done = run_rebaseline("--baseline", str(old), "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "UNDECLARED" not in done.stdout and "declared" in done.stdout
    assert folder_hash(old) == new_hash, "the new build is in the baseline's place"
    kept = [p for p in old.parent.iterdir() if p.name.startswith("dist-before-")]
    assert len(kept) == 1 and folder_hash(kept[0]) == old_hash, "the old folder is kept, as a dated sibling, not deleted"
    assert out.is_file() and '"normalised_hash"' in out.read_text(encoding="utf-8")
    # The proof's own gate then reads the new folder as another baseline: this proof retires.
    reason = proof_gate(old, f"against: {old_hash}\n" + GOOD_ROW)
    assert reason is not None and "belongs to an earlier baseline" in reason


def test_the_rebaseline_step_is_the_one_this_file_names() -> None:
    doc = __doc__ or ""
    assert "node scripts/dist_compare.mjs rebaseline --declared ../OspreyFlow_Build/tests/fixtures/pl4d3d_declared_units.txt --conductor-merge" in doc
    assert "exits non-zero" in doc and "run by the conductor at merge" in doc
    assert '"rebaseline"' in SCRIPT.read_text(encoding="utf-8")
    assert "OspreyFlow_Build" not in SCRIPT.read_text(encoding="utf-8"), "Core's script must not name the Build folder"


def test_the_rebaseline_step_needs_the_declaration_named_and_touches_nothing_without_it(tmp_path: Path) -> None:
    old, new, tests, out = rebaseline_scene(tmp_path)
    before = folder_hash(old)
    done = run_rebaseline("--baseline", str(old), "--dist", str(new), "--tests", str(tests), "--out", str(out))
    assert done.returncode != 0 and "--declared" in done.stdout
    assert folder_hash(old) == before and not out.exists() and [p.name for p in old.parent.iterdir()] == ["dist"]


def test_the_rebaseline_step_refuses_a_declared_unit_that_does_not_differ(tmp_path: Path) -> None:
    old, new, tests, out = rebaseline_scene(tmp_path)
    listing = subprocess.run([node(), str(SCRIPT), "units", str(old), str(new)], cwd=CORE, capture_output=True, text=True, check=True).stdout
    declared_text = tmp_path / "declared.txt"
    declared_text.write_text(declaration_for(listing) + "index.js\tonly after\t" + "0" * 12 + "\tx.ts\tsplit\t-\tfunction z(){}\n", encoding="utf-8")
    before = folder_hash(old)
    done = run_rebaseline("--baseline", str(old), "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out))
    assert done.returncode != 0 and "declared but not differing" in done.stdout and "REFUSED" in done.stdout, done.stdout
    assert folder_hash(old) == before and not out.exists() and [p.name for p in old.parent.iterdir()] == ["dist"]


def test_the_rebaseline_step_takes_a_build_of_the_checked_out_tree_and_writes_the_recorded_hash(baseline: Path, tmp_path: Path) -> None:
    """The real path on a copy of the baseline, with the declaration the slice made, and a build of this tree.

    The build is `build_to`'s (a private copy of the tree, output identical to the real tree's) passed as `--dist`, not the
    script's own in-tree build: that one writes the real tree's `public/assets/govuk`, which no other build in the sweep may
    share (the merge gate's round 8). The script's own build is the conductor's at merge, where nothing else runs."""
    import json

    copy = tmp_path / "PL4a-baseline" / "dist"
    shutil.copytree(baseline, copy)
    tests = tmp_path / "tests.txt"
    tests.write_text(TESTS_OUTPUT, encoding="utf-8")
    out = tmp_path / "PL4_BASELINE.json"
    fresh = build_to(tmp_path / "fresh" / "dist")
    done = run_rebaseline("--baseline", str(copy), "--declared", str(DECLARED), "--dist", str(fresh), "--tests", str(tests), "--out", str(out))
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-2000:]
    recorded = json.loads((CORE / "apps" / "workspace" / "PL4_BASELINE.json").read_text(encoding="utf-8"))
    assert json.loads(out.read_text(encoding="utf-8"))["normalised_hash"] == recorded["normalised_hash"]
    reason = proof_gate(copy, DECLARED.read_text(encoding="utf-8"))
    assert reason is not None and "belongs to an earlier baseline" in reason
    assert [p.name for p in copy.parent.iterdir() if p.name.startswith("dist-before-")], "the old build is kept"


# ----------------------------------------------------------------------------- the guard: only the conductor's merge may replace the real folder
def run_rebaseline_at_default(home: Path, *args: str, baseline_dist: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run `rebaseline` with no `--baseline`, so the folder it means is the script's own default.

    The default is derived from `$HOME` (and `PL4_BASELINE_DIST` is removed unless `baseline_dist` sets it), so a scratch `HOME`
    makes the real default path a scratch folder: this plants the real default's shape without ever naming the Mac's real folder
    (which no test may touch).
    """
    env = {k: v for k, v in os.environ.items() if k != "PL4_BASELINE_DIST"} | {"HOME": str(home)}
    if baseline_dist is not None:
        env["PL4_BASELINE_DIST"] = str(baseline_dist)
    return subprocess.run([node(), str(SCRIPT), "rebaseline", *args], cwd=CORE, capture_output=True, text=True, timeout=TIMEOUT, check=False, env=env)


def default_scene(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    """A scratch HOME holding a baseline at the script's default path, a new build, a matching declaration and a test output."""
    home = tmp_path / "home"
    old = synthetic_dist(home / "dev" / "osprey-acceptance" / "PL4a-baseline" / "dist", index_hash="AAAAAAAA", lazy_hash="11111111")
    new = synthetic_dist(tmp_path / "new", index_hash="BBBBBBBB", lazy_hash="22222222", answer=2)
    listing = subprocess.run([node(), str(SCRIPT), "units", str(old), str(new)], cwd=CORE, capture_output=True, text=True, check=True).stdout
    declared_text = tmp_path / "declared.txt"
    declared_text.write_text(declaration_for(listing), encoding="utf-8")
    tests = tmp_path / "tests.txt"
    tests.write_text(TESTS_OUTPUT, encoding="utf-8")
    return home, old, new, declared_text, tests


def test_the_rebaseline_step_refuses_the_default_folder_without_the_conductors_flag(tmp_path: Path) -> None:
    """Planted: the call that replaced the Mac's real folder six times by hand (no `--baseline`, so the default)."""
    home, old, new, declared_text, tests = default_scene(tmp_path)
    before = folder_hash(old)
    out = tmp_path / "PL4_BASELINE.json"
    done = run_rebaseline_at_default(home, "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out))
    assert done.returncode != 0, "rebaseline replaced the default baseline folder without --conductor-merge:\n" + done.stdout
    assert "--conductor-merge" in done.stdout + done.stderr and "conductor" in (done.stdout + done.stderr), "it must say, in words, why it refused"
    assert folder_hash(old) == before and not out.exists(), "a refused rebaseline must touch nothing"
    assert [p.name for p in old.parent.iterdir()] == ["dist"], "nothing is moved aside when it refuses"


def test_the_rebaseline_step_refuses_an_explicit_baseline_that_is_the_default_folder_too(tmp_path: Path) -> None:
    """Naming the default path by hand with `--baseline` is the same call: the flag is what the conductor adds."""
    home, old, new, declared_text, tests = default_scene(tmp_path)
    before = folder_hash(old)
    out = tmp_path / "PL4_BASELINE.json"
    done = run_rebaseline_at_default(home, "--baseline", str(old), "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out))
    assert done.returncode != 0 and "--conductor-merge" in done.stdout + done.stderr, done.stdout
    assert folder_hash(old) == before and not out.exists()


def test_the_guard_still_protects_the_real_folder_when_pl4_baseline_dist_names_another(tmp_path: Path) -> None:
    """Planted (the round-7 finding): `PL4_BASELINE_DIST` points at a scratch folder, `--baseline` names the real path.

    The real folder is the fixed `~/dev/osprey-acceptance/PL4a-baseline/dist`; the environment variable may add a second
    protected folder but must never move the protection off the real one.
    """
    home, old, new, declared_text, tests = default_scene(tmp_path)
    elsewhere = synthetic_dist(tmp_path / "elsewhere" / "dist", index_hash="AAAAAAAA", lazy_hash="11111111")
    before = folder_hash(old)
    out = tmp_path / "PL4_BASELINE.json"
    done = run_rebaseline_at_default(home, "--baseline", str(old), "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out), baseline_dist=elsewhere)
    assert done.returncode != 0 and "--conductor-merge" in done.stdout + done.stderr, done.stdout
    assert folder_hash(old) == before and not out.exists(), "a refused rebaseline must touch nothing"
    assert [p.name for p in old.parent.iterdir()] == ["dist"], "nothing is moved aside when it refuses"


def test_the_guard_also_protects_the_folder_pl4_baseline_dist_names(tmp_path: Path) -> None:
    """The folder the variable names is the proof's baseline on that machine: it is guarded too, and passes with the flag."""
    home, _, new, declared_text, tests = default_scene(tmp_path)
    named = synthetic_dist(tmp_path / "named" / "dist", index_hash="AAAAAAAA", lazy_hash="11111111")
    before = folder_hash(named)
    out = tmp_path / "PL4_BASELINE.json"
    done = run_rebaseline_at_default(home, "--baseline", str(named), "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out), baseline_dist=named)
    assert done.returncode != 0 and "--conductor-merge" in done.stdout + done.stderr, done.stdout
    assert folder_hash(named) == before and not out.exists()
    done = run_rebaseline_at_default(home, "--conductor-merge", "--baseline", str(named), "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out), baseline_dist=named)
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_rebaseline_step_replaces_the_default_folder_with_the_conductors_flag(tmp_path: Path) -> None:
    """Green: with `--conductor-merge` the same call goes through (on a scratch default), and the old folder is kept."""
    home, old, new, declared_text, tests = default_scene(tmp_path)
    old_hash, new_hash = folder_hash(old), folder_hash(new)
    out = tmp_path / "PL4_BASELINE.json"
    done = run_rebaseline_at_default(home, "--conductor-merge", "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out))
    assert done.returncode == 0, done.stdout + done.stderr
    assert folder_hash(old) == new_hash
    kept = [p for p in old.parent.iterdir() if p.name.startswith("dist-before-")]
    assert len(kept) == 1 and folder_hash(kept[0]) == old_hash


def test_a_baseline_that_is_not_the_default_needs_no_flag(tmp_path: Path) -> None:
    """The tests' own shape (`--baseline <scratch>`) keeps working: the guard is for the default path only."""
    home, _, new, declared_text, tests = default_scene(tmp_path)
    other = synthetic_dist(tmp_path / "elsewhere" / "dist", index_hash="AAAAAAAA", lazy_hash="11111111")
    out = tmp_path / "PL4_BASELINE.json"
    done = run_rebaseline_at_default(home, "--baseline", str(other), "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out))
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_docstring_names_the_conductors_flag_and_says_nothing_else_may_run_the_step() -> None:
    doc = __doc__ or ""
    assert "--conductor-merge" in doc
    assert "nothing else may run it against the real folder" in " ".join(doc.split()).lower()
    assert "Until the conductor has run it, this proof stays live on the Mac." not in doc
    assert "--conductor-merge" in SCRIPT.read_text(encoding="utf-8")


# ---------------------------------------------------------------- no two builds share a tree (the merge gate's round 8)
def build_is_possible() -> bool:
    return (CORE / "node_modules" / "vite").is_dir() and (CORE / "apps" / "workspace" / "package.json").is_file()


def test_a_build_runs_in_a_private_copy_of_the_tree_never_in_the_real_one(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`build_to` is what every build of this file goes through, so it must not touch the real `apps/workspace`.

    The real tree's `public/assets/govuk` is shared by every build in it (`sync_govuk_assets.mjs` removes and refills it):
    two builds in one tree at once is the `ENOTEMPTY` the merge gate refused. Recorded: the working directory of the build
    command is a copy outside the real tree, and what it builds is not the real folder."""
    calls: list[tuple[list[str], Path]] = []
    real_run = subprocess.run

    def spy(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        calls.append((list(command), Path(kwargs["cwd"]).resolve()))
        return real_run(["true"], *args, **{**kwargs, "cwd": tmp_path})

    monkeypatch.setattr(subprocess, "run", spy)
    build_to(tmp_path / "dist")
    assert len(calls) == 1
    command, cwd = calls[0]
    assert "build" in command
    assert CORE.resolve() not in [cwd, *cwd.parents], f"the build ran in the real tree: {cwd}"
    assert "--workspace" not in command, "a workspace build runs from the real tree's root"


def race(builders: list) -> list[subprocess.CompletedProcess[str]]:
    """Every builder starts at the same moment (a barrier), so the builds overlap as two xdist workers' do."""
    done: list = [None] * len(builders)
    barrier = threading.Barrier(len(builders))

    def go(index: int) -> None:
        barrier.wait()
        done[index] = builders[index]()

    threads = [threading.Thread(target=go, args=(index,)) for index in range(len(builders))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return done


@pytest.mark.skipif(not build_is_possible(), reason="needs the workspace's node_modules")
def test_two_builds_in_one_tree_collide_and_two_builds_of_build_to_do_not(tmp_path: Path) -> None:
    """The race planted in the shape the gate met (rule 15): two `npm run build`s at once in one tree.

    Unlocked, in one copy of the tree (the real tree's shape, but a copy, so no other test's build is harmed):
    one of the two fails in `sync_govuk_assets.mjs`'s `rmSync`/`cpSync` of the shared `public/assets/govuk`, as at the merge
    (tried up to fifteen times, since a race is not certain: it was six in six on an idle Mac, and five tries were not
    enough once, on a loaded merge gate, 22 November 2026; a try that collides stops the loop, so the extra tries cost
    nothing when the race shows). Then two `build_to`s at once,
    each in its own copy: both succeed, every time. The two collide because they share a tree, and they do not once they
    share none; no lock is needed, and none is taken."""
    failures: list[str] = []
    for attempt in range(15):
        shared = scratch_tree(tmp_path / f"shared{attempt}")
        results = race([
            lambda out=tmp_path / f"s{attempt}a": run_build(shared, out),
            lambda out=tmp_path / f"s{attempt}b": run_build(shared, out),
        ])
        failures = [r.stdout + r.stderr for r in results if r.returncode != 0]
        if failures:
            break
    assert failures, "two builds in one tree never collided in fifteen tries: the plant does not show the race"
    assert re.search(r"ENOTEMPTY|ENOENT|EEXIST|sync_govuk_assets", failures[0]), failures[0][-1500:]

    outcomes: list[object] = []

    def private(name: str) -> object:
        try:
            return build_to(tmp_path / name / "dist")
        except AssertionError as error:  # pragma: no cover - the failure is the finding
            return error

    outcomes = race([lambda: private("p1"), lambda: private("p2")])
    assert all(isinstance(o, Path) for o in outcomes), outcomes
    assert all((o / "index.html").is_file() for o in outcomes)


if __name__ == "__main__":
    if sys.argv[1:] == ["write"]:
        import tempfile

        with tempfile.TemporaryDirectory() as scratch:
            fresh = build_to(Path(scratch) / "dist")
            DECLARED.write_text(declaration(read_units(BASELINE_DIST, fresh)), encoding="utf-8")
        print(f"wrote {DECLARED}")
    else:
        sys.exit("usage: test_pl4d3d_declared_units.py write")
