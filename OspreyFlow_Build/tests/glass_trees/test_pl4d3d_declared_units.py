"""PL4d3d's proof of what changed: the differing units of the build are exactly the declared ones.

This slice splits code (`investigation/cases.ts`, `admin/needsYou/openings.ts`,
`ingest/runs/ExternalOrchestration.tsx`), and `dist_compare` compares code units: a unit that is split or newly
made is a change by construction, so the slice's own required work cannot make `verify --build` say SAME. The owner's ruling of 21 November 2026: the proof for a slice that
splits code is the checked list of differing units, not an identical build.

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

It builds, so it takes a few seconds beyond `dist_compare`'s own (about ten in all on an idle Mac; each comparison is
about five). Under load a timeout is the machine's, not the slice's.
"""

from __future__ import annotations

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
REASONS = {"split", "new", "moved", "knock-on"}
TIMEOUT = 600


class Unit(NamedTuple):
    file: str
    side: str
    sha: str


# What generated the declaration decided for each unit, by what the unit says (label-free where it can be): the unit's
# source module, and why it differs. Used by `write` only: the check compares chunk, side and hash.
RULES: list[tuple[str, str, str]] = [
    (r"^function \$\w+\(\{apiBaseUrl:\$0,bearerToken:\$1,lastCaseId", "investigation/CasePicker.tsx", "knock-on"),
    (r"^function \$\w+\(\$0\)\{let\{pipelines:", "ingest/runs/RunsTab.tsx", "knock-on"),
    (r"investigationId:\$3,datasetId:\$4,deployed:", "ingest/runs/ExternalOrchestration.tsx", "split"),
    (r"/owned-externally`|/quota`", "ingest/runs/externalOrchestrationApi.ts", "new"),
    (r"method:`DELETE`,headers:\{Authorization:`Bearer \$\{\$1\}`\}\}\);if\(\$3\.status===403",
     "investigation/cases.ts", "split"),
    (r"`ospreyflow\.investigationId`\)===\$2", "investigation/caseNavigation.ts", "split"),
    (r"^(var \$\w+=\(\)=>null|function \$\w+\(\$0\)\{\$\w+=\$0,\$\w+=\$\w+\(\)\}|\$\w+\(\(\)=>sessionStorage\);)",
     "admin/needsYou/openings.ts", "new"),
    (r"sessionStorage|\.getItem\(|\.removeItem\(|\.setItem\(|^var \$\w+=\$\w+\(\)$|\$61bfe3",
     "admin/needsYou/openings.ts", "split"),
]


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
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t", 5)
        assert len(parts) == 6, f"line {number}: expected chunk, side, hash, source, reason, unit"
        file, side, sha, source, reason, unit = parts
        assert side in {"only before", "only after"}, f"line {number}: side {side!r}"
        assert re.fullmatch(r"[0-9a-f]{12}", sha), f"line {number}: hash {sha!r}"
        assert reason in REASONS, f"line {number}: reason {reason!r} is none of {sorted(REASONS)}"
        assert source.endswith((".ts", ".tsx")), f"line {number}: source {source!r}"
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
        "# PL4d3d: the units of the build that differ from the build before PL4 (ADR-152 R2), and why.",
        "# Generated by `python OspreyFlow_Build/tests/glass_trees/test_pl4d3d_declared_units.py write` from",
        "# `node scripts/dist_compare.mjs units <pre-PL4 dist> <this build>`; not typed by hand.",
        "# chunk <TAB> side <TAB> sha-256 of the unit, first 12 <TAB> source module <TAB> reason <TAB> the unit.",
        "# reasons: split (a unit cut in two), new (a unit that did not exist), moved, knock-on (differs only",
        "# because it calls a unit that was split: the owner is asked about these in the report).",
    ]
    body = []
    for unit, text in rows:
        source, reason = classify(text)
        body.append(f"{unit.file}\t{unit.side}\t{unit.sha}\t{source}\t{reason}\t{text}")
    return "\n".join([*head, *sorted(body)]) + "\n"


# ------------------------------------------------------------------------------------------------------ the builds
@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    assert BASELINE_DIST.is_dir(), f"the raw pre-PL4 build is not at {BASELINE_DIST} (set PL4_BASELINE_DIST)"
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
        "investigation/cases.ts",
        "investigation/caseNavigation.ts",
        "ingest/runs/externalOrchestrationApi.ts",
        "ingest/runs/ExternalOrchestration.tsx",
    } <= sources
    assert {unit.file for unit, *_rest in declared} == {"index.js"}


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
    assert len(now) == len(actual) + 2, "one unit changed: one row gone, one row new"
    assert len([p for p in found if p.startswith("undeclared difference")]) == 2
    assert any("Skip to the main content" in p for p in found)
    in_declared = any(literal in declared_text for *_unit, declared_text in declared)
    assert not in_declared, "the plant is outside the declared units"


def test_a_declared_unit_left_unchanged_is_red(declared: list[tuple[Unit, str, str, str]]) -> None:
    assert read_units(BASELINE_DIST, BASELINE_DIST) == []
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
    extra = (Unit("index.js", "only after", "0" * 12), "investigation/cases.ts", "split", "function x(){}")
    assert problems(actual, [*declared, extra]) == ["declared but not differing: index.js only after " + "0" * 12]


def test_a_unit_declared_twice_is_not_one_difference(
    actual: list[tuple[Unit, str]], declared: list[tuple[Unit, str, str, str]]
) -> None:
    found = problems(actual, [*declared, declared[0]])
    assert len(found) == 1 and found[0].startswith("declared but not differing")


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
