"""PL4d3e's proof of what changed: the differing units of the build are exactly the declared ones.

This slice splits code (`home/guides.ts` into the package's plain half and the workspace's `home/guideDownloads.ts`;
`canvas/entityPictures.ts` into the package's store and client and the workspace's binding of the thumbnail step), and moves
`alertRuleGroup` out of a React file. `dist_compare` compares code units: a unit that is split or newly made is a change by
construction, so the slice's own required work cannot make `verify --build` say SAME. The owner's ruling of 21 November 2026
(the same as PL4d3d's, `slices/PL4d3d.md`): the proof for a slice that splits code is the checked list of differing units, not
an identical build. The whole-file moves (`help/roles.ts`, `shell/placesByRole.json`, `admin/api.ts`, `home/homeData.ts`) are not
splits and compare SAME: none of them is in the list, and the move of `alertRuleGroup` leaves no unit different either (the
function's text is the same wherever its file is).

This file reads the same machinery as `test_pl4d3d_declared_units.py` (the unit listing, the private-copy build, the gate, the
knock-on rule), which it imports, and adds this slice's own declaration:

* `OspreyFlow_Build/tests/fixtures/pl4d3e_declared_units.txt` is the list: one differing unit a line, with its chunk, its side,
  its hash, the source module it comes from, the reason (`split`, `new`, `moved`, or `knock-on`) and, for a knock-on row, its
  basis. It is generated, never typed: `python OspreyFlow_Build/tests/glass_trees/test_pl4d3e_declared_units.py write` runs
  `dist_compare.mjs units` (the script's own uncapped list) on the baseline PL4d3d recorded and a fresh build of this tree, and
  writes what it prints.
* `test_the_differing_units_are_exactly_the_declared_ones` builds `apps/workspace`, runs the same command and compares the list
  with the file. An undeclared difference fails it; so does a declared unit that does not differ.

Which test fails if the invariant is broken (rule 12; each planted in the shape the real command prints, rule 15):

* **an undeclared change to one unit**: `test_an_undeclared_change_to_one_unit_is_red` edits one string of one unit (outside the
  declared ones) in a copy of the real build, then runs the real command on it;
* **a declared unit left unchanged**: `test_a_declared_unit_left_unchanged_is_red` compares the baseline with itself (so nothing
  differs) and `test_one_declared_unit_that_does_not_differ_is_red` drops one real row;
* **an extra declared unit**: `test_an_extra_declared_unit_is_red`.

Where the comparison runs, and how it retires (the conductor's rounds 2 and 4 of PL4d3d, which bind this slice):

* **It needs the raw baseline build, which is not in the repository.** The folder is `PL4_BASELINE_DIST` (default
  `~/dev/osprey-acceptance/PL4a-baseline/dist`, the builder's and the verifier's Mac), and holds the build PL4d3d recorded. Where
  it is absent (GitHub, a clean merge tree) the comparison **skips with a stated reason and never errors**.
* **The proof belongs to one baseline.** The declaration's first line is `against: <sha-256 of that folder>` (names and bytes).
  The comparison runs only if the folder's hash is that value; otherwise it skips with "this proof belongs to an earlier baseline".
* **The retirement is the same scripted step PL4d3d built, run by the conductor at merge, from the merged commit** (this file does
  not run it against the real folder, and nothing here says the folder already holds the new build; no second step was built).
  From `OspreyFlow_Core`:
  `node scripts/dist_compare.mjs rebaseline --declared ../OspreyFlow_Build/tests/fixtures/pl4d3e_declared_units.txt --conductor-merge`
  (`--conductor-merge` is the conductor's own flag: without it the step refuses, in words and touching nothing, to run against the
  default folder, the Mac's one real baseline. **Nothing else may run it against the real folder: not `rebaseline`, not `mv`, not
  `cp`**; every test here passes `--baseline <a temporary copy>`). It builds the workspace from the checked-out commit; prints the
  old-against-new listing of differing units; **exits non-zero**, touching nothing, if any differing unit is neither declared nor
  knock-on, or if a declared unit does not differ; otherwise runs the workspace's unit tests, moves the old baseline folder aside
  (a dated sibling, never deleted), puts the new build in its place and writes `apps/workspace/PL4_BASELINE.json`.
  `test_the_rebaseline_step_refuses_an_undeclared_difference_in_this_slices_declaration` plants the refusal on this slice's own
  declaration, and `test_the_rebaseline_step_accepts_this_slices_declaration_on_a_copy_of_the_baseline` runs the real path on a copy.
  After it runs, the declaration's `against:` hash no longer matches, so this proof skips as an earlier baseline and later slices
  (slice E, AD1b) compare with `dist_compare verify --build`, which reads the recorded hash.
* Tests that need no build always run: the declaration's own form, the gate itself, the knock-on rule, and the step's refusal.

**The knock-on rule (the owner's ruling of 21 November 2026, enforced here as in PL4d3d).** A unit is knock-on only if (a) its source
file's diff against main is import lines only, or (b) it is a built file byte-identical to the baseline's once the hashed chunk names
are normalised. This slice's eight rows: `index.html` and `sigma-export-image.esm.js` both sides, each (b); the `App` component and
the start screen both sides, each (a): their source files changed in import lines only (`App.tsx`, `shell/startScreen.tsx`).

It builds, so it takes a few seconds beyond `dist_compare`'s own (about ten in all on an idle Mac). Under load a timeout is the
machine's, not the slice's.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.glass_trees import test_pl4d3d_declared_units as d3d

BUILD = d3d.BUILD
CORE = d3d.CORE
SCRIPT = d3d.SCRIPT
DECLARED = BUILD / "tests" / "fixtures" / "pl4d3e_declared_units.txt"
# The raw copy of the build the baseline records: the one PL4d3d's merge left (never written by this file).
BASELINE_DIST = d3d.BASELINE_DIST
SRC = d3d.SRC
Unit, Row = d3d.Unit, d3d.Row
VIA_INDEX = d3d.VIA_INDEX
BASES = d3d.BASES
TIMEOUT = d3d.TIMEOUT
#: A file only this slice makes: once it is on main the slice has merged and rule (a) retires.
SLICE_MARKER = "OspreyFlow_Core/apps/workspace/src/home/guideDownloads.ts"

# What the generator decided for each unit, by what the unit says: its source module and why it differs. `write` only: the check
# compares chunk, side and hash.
RULES: list[tuple[str, str, str]] = [
    # A whole file that differs only because it names the index chunk (the page, a lazy chunk that imports from it).
    (r"^\(names a file that changed, or another file\)$", VIA_INDEX, "knock-on"),
    # The `App` component and the start screen: their sources changed in import lines only (the guide's browser half).
    (r"^function \$\w+\(\)\{let \$0=\(0,\$\w+\.useRef\)\(\$\w+\(\)\),\$1=\$\w+\(\$0\.current\.store,\$2=>\$2\.withheld\)", "App.tsx", "knock-on"),
    (r"^function \$\w+\(\$0\)\{let\{rights:\$1,investigationId:\$2,startChoice:\$3,setStartChoice:\$4\}=\$0;", "shell/startScreen.tsx", "knock-on"),
    # The guides: the package's `openGuide` (its two browser calls are required now), the workspace's blank tab and wrapper.
    (r"showsPdf\?\?navigator\.pdfViewerEnabled", "home/guides.ts", "split"),
    (r"window\.open\(", "home/guideDownloads.ts", "new"),
    (r"\{\.\.\.\$1,openTab:\$1\.openTab\?\?", "home/guideDownloads.ts", "new"),
    # The pictures: the thumbnail step is held and handed in; the client's two functions that call it differ with it.
    (r"^var \$\w+=null$|^function \$\w+\(\$0\)\{\$\w+=\$0\}$|^\$\w+\(\$\w+\);$", "canvas/entityPictures.ts", "new"),
    (r"no thumbnail step is bound|picture \$\{\$2\.status\}|`/pictures`", "canvas/entityPictures.ts", "split"),
]


def declaration(rows: list[tuple[Unit, str]]) -> str:
    head = [
        f"against: {d3d.folder_hash(BASELINE_DIST)}",
        "# PL4d3e: the units of the build that differ from the build PL4d3d recorded (ADR-152 R2), and why.",
        "# Generated by `python OspreyFlow_Build/tests/glass_trees/test_pl4d3e_declared_units.py write` from",
        "# `node scripts/dist_compare.mjs units <PL4d3d's baseline dist> <this build>`; not typed by hand.",
        "# chunk <TAB> side <TAB> sha-256 of the unit, first 12 <TAB> source module <TAB> reason <TAB> basis <TAB> the unit.",
        "# reasons: split (a unit cut in two), new (a unit that did not exist), moved, knock-on. A knock-on row says its",
        "# basis (the owner's rule of 21 November 2026): (a) its source file's diff against main is import lines only;",
        "# (b) it is a built file byte-identical to the baseline's once hashed chunk names are normalised. Other rows: -.",
        "# The test enforces both; a knock-on row that meets neither fails the slice.",
    ]
    body = []
    for unit, text in rows:
        for pattern, source, reason in RULES:
            if re.search(pattern, text):
                basis = "-" if reason != "knock-on" else ("(b)" if source == VIA_INDEX else "(a)")
                body.append(f"{unit.file}\t{unit.side}\t{unit.sha}\t{source}\t{reason}\t{basis}\t{text}")
                break
        else:
            raise AssertionError(f"no rule says where this unit comes from: {text[:160]}")
    return "\n".join([*head, *sorted(body)]) + "\n"


# ------------------------------------------------------------------------------------------------------ the builds
@pytest.fixture(scope="module")
def baseline() -> Path:
    """The raw baseline build, or a skip with the reason: no test here errors on a missing or later baseline."""
    reason = d3d.proof_gate(BASELINE_DIST, DECLARED.read_text(encoding="utf-8") if DECLARED.is_file() else "")
    if reason:
        pytest.skip(reason)
    return BASELINE_DIST


@pytest.fixture(scope="module")
def built(baseline: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return d3d.build_to(tmp_path_factory.mktemp("pl4d3e") / "dist")


@pytest.fixture(scope="module")
def actual(built: Path) -> list[tuple[Unit, str]]:
    return d3d.read_units(BASELINE_DIST, built)


@pytest.fixture(scope="module")
def declared() -> list[Row]:
    assert DECLARED.is_file(), f"{DECLARED.relative_to(BUILD.parent)} is not there: generate it (see this file's head)"
    return d3d.parse_declared(DECLARED.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------------ the proof
def test_the_differing_units_are_exactly_the_declared_ones(
    actual: list[tuple[Unit, str]], declared: list[Row]
) -> None:
    assert actual, "no unit differs: the build was not compared with the recorded one"
    assert d3d.problems(actual, declared) == []


def test_each_whole_file_knock_on_row_differs_only_in_chunk_names(built: Path, declared: list[Row]) -> None:
    """(b), on the real pair: the recorded build and this build, file by file, once chunk names are normalised."""
    files = sorted({row.unit.file for row in declared if row.reason == "knock-on" and row.basis == "(b)"})
    assert files == ["index.html", "sigma-export-image.esm.js"]
    for file in files:
        changed = d3d.chunk_name_difference(BASELINE_DIST, built, file)
        assert changed == [], f"{file} is not knock-on: it differs in more than chunk names:\n" + "\n".join(changed)


def test_the_declaration_names_each_split_the_brief_declares(declared: list[Row]) -> None:
    sources = {row.source for row in declared}
    assert {
        "home/guides.ts",
        "home/guideDownloads.ts",
        "canvas/entityPictures.ts",
    } <= sources
    # The units are in the index chunk; the page and one lazy chunk differ as whole files only because they name it.
    assert {row.unit.file for row in declared} == {"index.js", "index.html", "sigma-export-image.esm.js"}
    # The whole-file moves and the rule group's move leave no unit different: none of them is a source of a row.
    assert not {"help/roles.ts", "admin/api.ts", "home/homeData.ts", "reports/ruleGroup.ts"} & sources


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
    now = d3d.read_units(BASELINE_DIST, planted)
    found = d3d.problems(now, declared)
    assert d3d.problems(actual, declared) == []
    # A unit others call is named by its content: its callers differ with it, so more than one pair is red.
    assert len(now) >= len(actual) + 2
    assert len([p for p in found if p.startswith("undeclared difference")]) >= len(now) - len(actual)
    known = {unit for unit, _text in actual}
    new_rows = [unit for unit, _text in now if unit not in known]
    assert not [unit for unit in new_rows if unit in {row.unit for row in declared}]
    assert any(unit.file == "index.js" for unit in new_rows)


def test_a_declared_unit_left_unchanged_is_red(baseline: Path, declared: list[Row]) -> None:
    assert d3d.read_units(baseline, baseline) == []
    found = d3d.problems([], declared)
    assert len(found) == len(declared)
    assert all(p.startswith("declared but not differing") for p in found)


def test_one_declared_unit_that_does_not_differ_is_red(actual: list[tuple[Unit, str]], declared: list[Row]) -> None:
    found = d3d.problems(actual[1:], declared)
    assert found == [f"declared but not differing: {actual[0][0].file} {actual[0][0].side} {actual[0][0].sha}"]


def test_an_extra_declared_unit_is_red(actual: list[tuple[Unit, str]], declared: list[Row]) -> None:
    extra = Row(Unit("index.js", "only after", "0" * 12), "home/guides.ts", "split", "-", "function x(){}")
    assert d3d.problems(actual, [*declared, extra]) == ["declared but not differing: index.js only after " + "0" * 12]


def test_a_unit_declared_twice_is_not_one_difference(actual: list[tuple[Unit, str]], declared: list[Row]) -> None:
    found = d3d.problems(actual, [*declared, declared[0]])
    assert len(found) == 1 and found[0].startswith("declared but not differing")


def test_the_listing_has_a_row_for_every_finding_of_compare(built: Path) -> None:
    """`compare` and `units` agree on whether the builds differ: no finding is dropped from the listing."""
    done = subprocess.run(
        [d3d.node(), str(SCRIPT), "compare", str(BASELINE_DIST), str(built)],
        cwd=CORE, capture_output=True, text=True, timeout=TIMEOUT, check=False,
    )
    assert done.returncode == 1 and done.stdout.startswith("DIFFERENT")
    assert d3d.read_units(BASELINE_DIST, built)


# ------------------------------------------------------------------------------- where the proof runs (no build)
GOOD_ROW = d3d.GOOD_ROW


def test_the_declaration_says_which_baseline_it_belongs_to() -> None:
    assert DECLARED.is_file(), f"{DECLARED.name} is not there: generate it (see this file's head)"
    first = DECLARED.read_text(encoding="utf-8").splitlines()[0]
    assert re.fullmatch(r"against: [0-9a-f]{64}", first), f"the first line must be `against: <sha-256 of the folder>`: {first!r}"


def test_the_declaration_is_well_formed_and_names_its_eight_knock_on_rows() -> None:
    rows = d3d.parse_declared(DECLARED.read_text(encoding="utf-8"))
    assert rows, "the declaration has no rows"
    knock_on = [row for row in rows if row.reason == "knock-on"]
    assert len(knock_on) == 8, "index.html and the sigma chunk both sides, the App component and the start screen both sides"
    assert {row.basis for row in knock_on} == BASES
    assert {row.source for row in knock_on if row.basis == "(a)"} == {"App.tsx", "shell/startScreen.tsx"}
    for row in knock_on:
        if row.basis == "(a)":
            assert (SRC / row.source).is_file(), f"{row.source} is not a workspace source file"


def test_a_missing_baseline_skips_and_a_later_one_retires_this_proof(tmp_path: Path) -> None:
    """The gate on this slice's own declaration: no folder skips with the reason (and never errors); a folder whose hash is not
    the declaration's is an earlier or a later baseline and skips too; the declaration's own is the only one that runs."""
    text = DECLARED.read_text(encoding="utf-8")
    reason = d3d.proof_gate(tmp_path / "not-there", text)
    assert reason is not None and "runs where `PL4_BASELINE_DIST` exists (the builder's and the verifier's Mac)" in reason
    (tmp_path / "index.js").write_text("a", encoding="utf-8")
    later = d3d.proof_gate(tmp_path, text)
    assert later is not None and "belongs to an earlier baseline" in later
    assert d3d.proof_gate(tmp_path, f"against: {d3d.folder_hash(tmp_path)}\n" + GOOD_ROW) is None
    none = d3d.proof_gate(tmp_path, GOOD_ROW)
    assert none is not None and "against" in none


# ---------------------------------------------------------------------------------------------- the knock-on rule
def test_a_knock_on_source_row_has_only_import_lines_in_its_diff_against_main() -> None:
    """(a), on the real rows: the diff of each source file against where this tree left `main`."""
    declared = d3d.parse_declared(DECLARED.read_text(encoding="utf-8"))
    repo = d3d.repo_root()
    base = d3d.merge_base(repo)
    if base is None:
        pytest.skip("no `main` ref here (GitHub's shallow checkout): rule (a) is checked where main exists, and was by the builder")
    if d3d.slice_is_on_main(repo, base, SLICE_MARKER):
        pytest.skip("this slice is already on main: rule (a) was checked at its merge, and a later change is not this slice's")
    for source in sorted({row.source for row in declared if row.reason == "knock-on" and row.basis == "(a)"}):
        changed = d3d.source_difference(repo, base, (SRC / source).relative_to(repo).as_posix())
        assert changed == [], f"{source} is not knock-on: its diff against main changes more than import lines:\n" + "\n".join(changed)


def test_the_source_rule_is_red_for_a_non_import_change_to_a_real_source_shape(tmp_path: Path) -> None:
    """Planted in a real git repository, in the shape of these rows' own change (`App.tsx` repointing its guide import)."""
    d3d.git(tmp_path, "init", "-q")
    file = tmp_path / "App.tsx"
    original = 'import { guideUrl, openGuide } from "./home/guides";\nimport { x } from "./x";\n\nexport const open = () => openGuide("user", {});\n'
    file.write_text(original, encoding="utf-8")
    d3d.git(tmp_path, "add", "App.tsx")
    d3d.git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "base")
    base = d3d.git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    # Only the imports change (split, repointed): not a difference.
    file.write_text(
        'import { guideUrl } from "@ospreyflow/glass-shared";\nimport { openGuide } from "./home/guideDownloads";\nimport { x } from "./x";\n\n'
        'export const open = () => openGuide("user", {});\n',
        encoding="utf-8",
    )
    assert d3d.source_difference(tmp_path, base, "App.tsx") == []
    # A line of code changes with them: red, and it names the line.
    file.write_text(file.read_text(encoding="utf-8").replace('openGuide("user", {})', 'openGuide("admin", {})'), encoding="utf-8")
    assert d3d.source_difference(tmp_path, base, "App.tsx") == [
        '-export const open = () => openGuide("user", {});',
        '+export const open = () => openGuide("admin", {});',
    ]


def test_a_knock_on_row_with_no_basis_or_the_wrong_one_is_refused() -> None:
    knock = "index.js\tonly after\t" + "a" * 12 + "\tApp.tsx\tknock-on\t(a)\tunit\n"
    assert [row.basis for row in d3d.parse_declared(knock)] == ["(a)"]
    with pytest.raises(AssertionError, match="needs its basis"):
        d3d.parse_declared(knock.replace("(a)", "-"))  # neither (a) nor (b)
    with pytest.raises(AssertionError, match=r"\(b\) is for a built file"):
        d3d.parse_declared(knock.replace("(a)", "(b)"))  # a source file claiming the built-file rule


def test_the_built_file_rule_is_red_for_a_string_that_is_not_a_chunk_name(tmp_path: Path) -> None:
    """(b), in the shape Vite writes: only a chunk name differs, green; any other string differs too, red."""
    before = d3d.synthetic_dist(tmp_path / "before", index_hash="AAAAAAAA", lazy_hash="11111111")
    renamed = d3d.synthetic_dist(tmp_path / "renamed", index_hash="BBBBBBBB", lazy_hash="22222222")
    for file in ("index.html", "lazy.js"):
        assert d3d.chunk_name_difference(before, renamed, file) == []
    other = d3d.synthetic_dist(tmp_path / "other", index_hash="BBBBBBBB", lazy_hash="22222222", lazy_body="a+2")
    changed = d3d.chunk_name_difference(before, other, "lazy.js")
    assert changed and any("a+2" in line for line in changed)


# ----------------------------------------------------------------------------- the rebaseline step (the one PL4d3d built)
def test_the_rebaseline_step_is_the_one_this_file_names() -> None:
    doc = __doc__ or ""
    assert "node scripts/dist_compare.mjs rebaseline --declared ../OspreyFlow_Build/tests/fixtures/pl4d3e_declared_units.txt --conductor-merge" in doc
    assert "exits non-zero" in doc.replace("**", "") and "run by the conductor at merge" in doc.replace("\n", " ")
    assert "nothing else may run it against the real folder" in " ".join(doc.replace("**", "").split()).lower()
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"rebaseline"' in text and "--conductor-merge" in text
    assert "OspreyFlow_Build" not in text, "Core's script must not name the Build folder"


def test_the_rebaseline_step_refuses_an_undeclared_difference_in_this_slices_declaration(tmp_path: Path) -> None:
    """Planted on this slice's own declaration (its rows, minus one that differs): a small pair of builds whose units are
    listed, a declaration made from all but one of them, and the step refusing, touching nothing."""
    old, new, tests, out = d3d.rebaseline_scene(tmp_path)
    listing = subprocess.run(
        [d3d.node(), str(SCRIPT), "units", str(old), str(new)], cwd=CORE, capture_output=True, text=True, check=True
    ).stdout
    lines = listing.splitlines()
    assert len(lines) >= 3
    declared_text = tmp_path / "declared.txt"
    declared_text.write_text(d3d.declaration_for("\n".join(lines[1:])), encoding="utf-8")
    before = d3d.folder_hash(old)
    done = d3d.run_rebaseline("--baseline", str(old), "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out))
    assert done.returncode != 0 and "UNDECLARED" in done.stdout and "REFUSED" in done.stdout, done.stdout
    assert d3d.folder_hash(old) == before and not out.exists()
    assert [p.name for p in old.parent.iterdir()] == ["dist"], "nothing is moved aside when it refuses"
    # The same step on the whole listing goes through, and keeps the old folder.
    declared_text.write_text(d3d.declaration_for(listing), encoding="utf-8")
    done = d3d.run_rebaseline("--baseline", str(old), "--declared", str(declared_text), "--dist", str(new), "--tests", str(tests), "--out", str(out))
    assert done.returncode == 0, done.stdout + done.stderr
    assert len([p for p in old.parent.iterdir() if p.name.startswith("dist-before-")]) == 1


def test_the_rebaseline_step_accepts_this_slices_declaration_on_a_copy_of_the_baseline(baseline: Path, tmp_path: Path) -> None:
    """The real path, on a copy of the baseline, with this slice's declaration and a build of this tree: what the conductor's
    step does at merge, except the step's own in-tree build (`--dist` is `build_to`'s private-copy build, so no other build in
    the sweep shares the tree). It exits 0, writes the record, keeps the old folder, and then this proof reads the copy as
    another baseline."""
    import json

    copy = tmp_path / "PL4a-baseline" / "dist"
    shutil.copytree(baseline, copy)
    tests = tmp_path / "tests.txt"
    tests.write_text(d3d.TESTS_OUTPUT, encoding="utf-8")
    out = tmp_path / "PL4_BASELINE.json"
    fresh = d3d.build_to(tmp_path / "fresh" / "dist")
    done = d3d.run_rebaseline("--baseline", str(copy), "--declared", str(DECLARED), "--dist", str(fresh), "--tests", str(tests), "--out", str(out))
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-2000:]
    assert '"normalised_hash"' in out.read_text(encoding="utf-8")
    assert json.loads(out.read_text(encoding="utf-8"))["normalised_hash"]
    reason = d3d.proof_gate(copy, DECLARED.read_text(encoding="utf-8"))
    assert reason is not None and "belongs to an earlier baseline" in reason
    assert [p.name for p in copy.parent.iterdir() if p.name.startswith("dist-before-")], "the old build is kept"


def test_the_rebaseline_step_still_refuses_the_real_folder_without_the_conductors_flag(tmp_path: Path) -> None:
    """The guard PL4d3d added holds with this slice's declaration: no `--baseline`, so the default folder (a scratch `HOME`'s),
    and no flag, so it refuses in words and touches nothing."""
    home, old, new, _declared_text, tests = d3d.default_scene(tmp_path)
    before = d3d.folder_hash(old)
    out = tmp_path / "PL4_BASELINE.json"
    done = d3d.run_rebaseline_at_default(home, "--declared", str(DECLARED), "--dist", str(new), "--tests", str(tests), "--out", str(out))
    assert done.returncode != 0 and "--conductor-merge" in done.stdout + done.stderr
    assert d3d.folder_hash(old) == before and not out.exists()


if __name__ == "__main__":
    if sys.argv[1:] == ["write"]:
        with tempfile.TemporaryDirectory() as scratch:
            fresh = d3d.build_to(Path(scratch) / "dist")
            DECLARED.write_text(declaration(d3d.read_units(BASELINE_DIST, fresh)), encoding="utf-8")
        print(f"wrote {DECLARED}")
    else:
        sys.exit("usage: test_pl4d3e_declared_units.py write")
