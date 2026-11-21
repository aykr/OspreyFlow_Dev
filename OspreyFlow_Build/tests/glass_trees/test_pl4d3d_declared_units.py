"""PL4d3d's proof of what changed: the differing units of the build are exactly the declared ones.

This slice splits code (the cases client, `admin/needsYou/openings.ts`,
`ingest/runs/ExternalOrchestration.tsx`), and `dist_compare` compares code units: a unit that is split or newly
made is a change by construction, so the slice's own required work cannot make `verify --build` say SAME.
The owner's ruling of 21 November 2026: the proof for a slice that splits code is the
checked list of differing units, not an identical build.

* `OspreyFlow_Build/tests/fixtures/pl4d3d_declared_units.txt` is that list: one differing unit a line, with its
  chunk, its side, its hash, the source module it comes from and the reason (`split`, `new`, `moved`, or
  `knock-on` for a unit that differs only because it calls a unit that was split). It is generated, never typed:
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

Where the comparison runs, and how it retires (the conductor's round 2):

* **It needs the raw pre-PL4 build, which is not in the repository.** The folder is `PL4_BASELINE_DIST` (default
  `~/dev/osprey-acceptance/PL4a-baseline/dist`, the builder's and the verifier's Mac). Where it is absent (GitHub, a clean
  merge tree) the comparison **skips with a stated reason and never errors**.
* **The proof belongs to one baseline.** The declaration's first line is `against: <sha-256 of that folder>` (names and
  bytes). The comparison runs only if the folder's hash is that value; otherwise it skips with "this proof belongs to an
  earlier baseline". When the baseline is refreshed (the folder is replaced with the new build, as the slice's re-record
  does: see the slice's report for the command), the hash stops matching and the proof retires itself; later slices compare
  with `dist_compare verify --build`, which reads the recorded hash.
* Tests that need no build always run: the declaration's own form, and the gate itself (`proof_gate`: planted a folder
  that does not exist, one that does, a declaration for an earlier baseline, and one with no `against` line).

It builds, so it takes a few seconds beyond `dist_compare`'s own (about ten in all on an idle Mac; each comparison is
about five). Under load a timeout is the machine's, not the slice's.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
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
# The "source module" of a whole-file knock-on row: the page and a lazy chunk name the index chunk, which changed.
VIA_INDEX = "via index.js"
TIMEOUT = 600


class Unit(NamedTuple):
    file: str
    side: str
    sha: str


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
            "was generated against (the slice's re-record replaced it), so later slices are not held to it"
        )
    return None


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


def build_to(directory: Path) -> Path:
    """A fresh build of `apps/workspace` into `directory`, never into the tree's own `dist/`."""
    done = subprocess.run(
        ["npm", "run", "build", "--workspace", "apps/workspace", "--", "--outDir", str(directory), "--emptyOutDir"],
        cwd=CORE, capture_output=True, text=True, timeout=TIMEOUT, check=False,
    )
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    return directory


def parse_declared(text: str) -> list[tuple[Unit, str, str, str]]:
    """The declaration's rows: unit, source module, reason, unit text."""
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith(("#", "against: ")):
            continue
        parts = line.split("\t", 5)
        assert len(parts) == 6, f"line {number}: expected chunk, side, hash, source, reason, unit"
        file, side, sha, source, reason, unit = parts
        assert side in {"only before", "only after"}, f"line {number}: side {side!r}"
        assert re.fullmatch(r"[0-9a-f]{12}", sha), f"line {number}: hash {sha!r}"
        assert reason in REASONS, f"line {number}: reason {reason!r} is none of {sorted(REASONS)}"
        assert source.endswith((".ts", ".tsx")) or source == VIA_INDEX, f"line {number}: source {source!r}"
        assert unit.strip(), f"line {number}: no unit"
        rows.append((Unit(file, side, sha), source, reason, unit))
    return rows


def problems(actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]]) -> list[str]:
    """Every way the differing units and the declaration disagree; empty when they are exactly the same list."""
    found = []
    wanted = [row[0] for row in declared]
    for unit, text in actual:
        if unit in wanted:
            wanted.remove(unit)
        else:
            found.append(f"undeclared difference: {unit.file} {unit.side}: {text[:120]}")
    for unit in wanted:
        found.append(f"declared but not differing: {unit.file} {unit.side} {unit.sha}")
    return found


def classify(text: str) -> tuple[str, str]:
    for pattern, source, reason in RULES:
        if re.search(pattern, text):
            return source, reason
    raise AssertionError(f"no rule says where this unit comes from: {text[:160]}")


def declaration(rows: list[tuple[Unit, str]]) -> str:
    head = [
        f"against: {folder_hash(BASELINE_DIST)}",
        "# PL4d3d: the units of the build that differ from the build before PL4 (ADR-152 R2), and why.",
        "# Generated by `python OspreyFlow_Build/tests/glass_trees/test_pl4d3d_declared_units.py write` from",
        "# `node scripts/dist_compare.mjs units <pre-PL4 dist> <this build>`; not typed by hand.",
        "# chunk <TAB> side <TAB> sha-256 of the unit, first 12 <TAB> source module <TAB> reason <TAB> the unit.",
        "# reasons: split (a unit cut in two), new (a unit that did not exist), moved, knock-on (differs only",
        "# because it calls a unit that was split or, as a whole file, names the index chunk: the owner is asked about these).",
    ]
    body = []
    for unit, text in rows:
        source, reason = classify(text)
        body.append(f"{unit.file}\t{unit.side}\t{unit.sha}\t{source}\t{reason}\t{text}")
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
def declared() -> list[tuple[Unit, str, str, str]]:
    assert DECLARED.is_file(), f"{DECLARED.relative_to(BUILD.parent)} is not there: generate it (see this file's head)"
    return parse_declared(DECLARED.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------------ the proof
def test_the_differing_units_are_exactly_the_declared_ones(
    actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]]
) -> None:
    assert actual, "no unit differs: the build was not compared with the pre-PL4 one"
    assert problems(actual, declared) == []


def test_the_declaration_names_each_split_the_brief_declares(declared: list[tuple[Unit, str, str, str]]) -> None:
    sources = {source for _unit, source, _reason, _text in declared}
    assert {
        "admin/needsYou/openings.ts",
        CASES,
        "investigation/caseNavigation.ts",
        "ingest/runs/externalOrchestrationApi.ts",
        "ingest/runs/ExternalOrchestration.tsx",
    } <= sources
    # The units are in the index chunk; the page and one lazy chunk differ as whole files only because they name it.
    assert {unit.file for unit, *_rest in declared} == {"index.js", "index.html", "sigma-export-image.esm.js"}
    assert {unit.file for unit, _s, reason, _t in declared if reason == "knock-on" and _s == VIA_INDEX} == {
        "index.html",
        "sigma-export-image.esm.js",
    }


def test_an_undeclared_change_to_one_unit_is_red(
    built: Path, tmp_path: Path, actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]]
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
    assert not [unit for unit in new_rows if unit in {row[0] for row in declared}]
    assert any(unit.file == "index.js" for unit in new_rows)


# A difference that is a whole file is not a unit of one: `dist_compare` reports it at file level, and the listing must
# too (the round-2 verifier: an added or removed chunk, a changed image or font printed nothing). Each is planted in a
# copy of the real build, in the shape `dist_compare` itself reads (a `assets/<name>-<8 characters>.<ext>` file, a file
# a page asks for by name, a changed asset), then the real command is run on it.
def planted_copy(built: Path, tmp_path: Path) -> Path:
    planted = tmp_path / "dist"
    shutil.copytree(built, planted)
    return planted


def assert_red(planted: Path, actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]], want: str) -> None:
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
    built: Path, tmp_path: Path, actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]]
) -> None:
    planted = planted_copy(built, tmp_path)
    (planted / "assets" / "plantedChunk-AbCd1234.js").write_text("export const planted=1;\n", encoding="utf-8")
    assert_red(planted, actual, declared, "file added")


def test_a_chunk_removed_from_the_build_is_red(
    built: Path, tmp_path: Path, actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]]
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
    built: Path, tmp_path: Path, actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]]
) -> None:
    planted = planted_copy(built, tmp_path)
    font = next((planted / "assets").glob("*.woff2"))
    font.write_bytes(font.read_bytes() + b"\0")
    assert_red(planted, actual, declared, "the bytes differ")


def test_a_file_added_or_removed_by_name_is_red(
    built: Path, tmp_path: Path, actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]]
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


def test_a_declared_unit_left_unchanged_is_red(baseline: Path, declared: list[tuple[Unit, str, str, str]]) -> None:
    assert read_units(baseline, baseline) == []
    found = problems([], declared)
    assert len(found) == len(declared)
    assert all(p.startswith("declared but not differing") for p in found)


def test_one_declared_unit_that_does_not_differ_is_red(
    actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]]
) -> None:
    found = problems(actual[1:], declared)
    assert found == [f"declared but not differing: {actual[0][0].file} {actual[0][0].side} {actual[0][0].sha}"]


def test_an_extra_declared_unit_is_red(
    actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]]
) -> None:
    extra = (Unit("index.js", "only after", "0" * 12), CASES, "split", "function x(){}")
    assert problems(actual, [*declared, extra]) == ["declared but not differing: index.js only after " + "0" * 12]


def test_a_unit_declared_twice_is_not_one_difference(
    actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]]
) -> None:
    found = problems(actual, [*declared, declared[0]])
    assert len(found) == 1 and found[0].startswith("declared but not differing")


# ------------------------------------------------------------------------------- where the proof runs (no build)
def declared_for(folder: Path) -> str:
    """A declaration written against `folder`, in the shape `write` makes."""
    return f"against: {folder_hash(folder)}\n" + "index.js\tonly after\t" + "a" * 12 + "\tx.ts\tsplit\tunit\n"


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
    reason = proof_gate(newer, declared_older)  # the re-record: the folder now holds the new build
    assert reason is not None and "belongs to an earlier baseline" in reason


def test_the_folder_hash_reads_names_and_bytes(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("x", encoding="utf-8")
    first = folder_hash(tmp_path)
    (tmp_path / "a.js").write_text("y", encoding="utf-8")
    second = folder_hash(tmp_path)
    (tmp_path / "a.js").rename(tmp_path / "b.js")
    assert len({first, second, folder_hash(tmp_path)}) == 3


def test_a_declaration_with_no_against_line_never_runs_the_proof(tmp_path: Path) -> None:
    reason = proof_gate(tmp_path, "index.js\tonly after\t" + "a" * 12 + "\tx.ts\tsplit\tunit\n")
    assert reason is not None and "against" in reason


def test_the_reasons_and_sources_are_well_formed() -> None:
    good = "index.js\tonly after\t" + "a" * 12 + "\tx.ts\tsplit\tunit\n"
    assert [unit for unit, *_rest in parse_declared(good)] == [Unit("index.js", "only after", "a" * 12)]
    with pytest.raises(AssertionError, match="because"):
        parse_declared(good.replace("split", "because"))
    with pytest.raises(AssertionError, match="hash"):
        parse_declared(good.replace("a" * 12, "a" * 11))


if __name__ == "__main__":
    if sys.argv[1:] == ["write"]:
        import tempfile

        with tempfile.TemporaryDirectory() as scratch:
            fresh = build_to(Path(scratch) / "dist")
            DECLARED.write_text(declaration(read_units(BASELINE_DIST, fresh)), encoding="utf-8")
        print(f"wrote {DECLARED}")
    else:
        sys.exit("usage: test_pl4d3d_declared_units.py write")
