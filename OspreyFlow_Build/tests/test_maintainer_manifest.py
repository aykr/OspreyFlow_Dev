"""Slice RL1: a maintainer's manifest of the product tree, generated from the tracked files at a ref
(`OspreyFlow_Core/scripts/maintainer_manifest.py`, its rules in `scripts/manifest_areas.toml`).

The owner will be asked for a map of the tree and an exact list of the code files someone else would maintain. It
has to come from the tag, the same way each release, so it is exact and cannot drift. These cases are the reasons it
can be believed (rule 12: the sentence, then the test that fails if it is untrue):

* **it reads the ref, never the working tree**: `test_the_manifest_is_of_the_ref_and_not_of_the_working_tree`;
* **same input, same bytes**: `test_two_runs_at_one_ref_are_byte_equal`, `..._from_another_clone_and_folder_...`,
  `..._whatever_the_hash_seed`, with the planted set iteration shown red in `test_a_planted_set_iteration_is_caught`;
* **every file under `apps`, `packages` and `services` is in exactly one area, and a new folder no rule covers
  fails**: the `test_areas_check_*` plants, each red and then green, in temporary git repositories with a real tree;
* **`is_generated` is decided from the repository's own evidence, never from a folder name**:
  `test_a_generated_folder_name_is_not_evidence` and the header and generator cases;
* **`release_images` is read from the Dockerfiles, the context and `.dockerignore`, and the release's matrix, and says
  `not determined` where it cannot be exact**: the `test_images_*` cases, and `test_dockerignore_*` against Docker's own
  documented cases;
* **no `maintained_under` column in what a release produces**: `test_the_default_output_has_exactly_the_eight_columns`
  and `test_the_repositorys_rules_file_has_no_maintained_under_mapping`.

**What it walks (the scan row).** Every case but the real-tree ones builds its own git repositories in `tmp_path`.
The real-tree cases (`test_the_real_tree_*`) read the whole of `OspreyFlow_Core` at `HEAD` of this repository through
`git ls-tree` and `git cat-file` (read-only, nothing from the working tree), once, and run the script's no-React
step on an extracted archive of it in a temporary folder; they also read `OspreyFlow_Core/scripts/manifest_areas.toml`
and the release workflow at `HEAD`. One case (`copy_reduced_core`) walks the working tree's `OspreyFlow_Core/apps/pages`
and `OspreyFlow_Core/packages/glass-shared` with `rglob`, reading them into a temporary repository for the planted React
import. Prefixes for the scan map: `OspreyFlow_Core/`.
"""

from __future__ import annotations

import csv
import getpass
import io
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from tools.layout import BUILD, CORE, ROOT

SCRIPT = CORE / "scripts" / "maintainer_manifest.py"
RULES = CORE / "scripts" / "manifest_areas.toml"
EIGHT = ["path", "area", "language", "lines", "bytes", "is_test", "is_generated", "release_images"]
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


# --- scaffolding -------------------------------------------------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        env={**os.environ, **GIT_ENV},
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def write_tree(repo: Path, files: dict[str, str | bytes]) -> None:
    for name, content in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())


def commit(repo: Path, message: str = "x") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def make_repo(root: Path, name: str, files: dict[str, str | bytes], *, prefix: str = "") -> Path:
    """A real git repository holding `files` (each under `prefix`) in one commit on `main`."""
    repo = root / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    write_tree(repo, {f"{prefix}{path}": content for path, content in files.items()})
    commit(repo, "tree")
    return repo


def run_script(
    *args: str, cwd: Path, hash_seed: str = "0", extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """The script as the release runs it: `python -m scripts.maintainer_manifest`, from a folder of its own."""
    env = {**os.environ, "PYTHONPATH": str(CORE), "PYTHONHASHSEED": hash_seed, **(extra_env or {})}
    return subprocess.run(
        [sys.executable, "-m", "scripts.maintainer_manifest", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


class Made:
    def __init__(self, done: subprocess.CompletedProcess[str], out: Path) -> None:
        self.done = done
        self.out = out

    @property
    def csv_bytes(self) -> bytes:
        return (self.out / "maintainer-manifest.csv").read_bytes()

    @property
    def md(self) -> str:
        return (self.out / "maintainer-manifest.md").read_text(encoding="utf-8")

    @property
    def table(self) -> list[dict[str, str]]:
        return list(csv.DictReader(io.StringIO(self.csv_bytes.decode("utf-8"), newline="")))

    def by_path(self) -> dict[str, dict[str, str]]:
        return {row["path"]: row for row in self.table}


def generate(
    repo: Path,
    tmp: Path,
    *extra: str,
    ref: str = "HEAD",
    rules: Path | None = None,
    tag: str = "out",
    **kw: object,
) -> Made:
    out = tmp / f"{tag}-{len(list(tmp.glob(tag + '-*')))}"
    args = ["--repo", str(repo), "--ref", ref, "--out", str(out), *extra]
    if rules is not None:
        args += ["--rules", str(rules)]
    done = run_script(*args, cwd=tmp, **kw)  # type: ignore[arg-type]
    assert done.returncode == 0, done.stdout + done.stderr
    return Made(done, out)


def check_areas(
    repo: Path, tmp: Path, rules: Path, ref: str = "HEAD"
) -> subprocess.CompletedProcess[str]:
    return run_script(
        "--repo", str(repo), "--ref", ref, "--check-areas", "--rules", str(rules), cwd=tmp
    )


def write_rules(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


#: A small rules file of the test's own, in the file's real shape, so a plant does not depend on today's product tree.
SMALL_RULES = """
version = 1
[languages]
".py" = "Python"
".ts" = "TypeScript"
".tsx" = "TypeScript"
".md" = "Markdown"
".txt" = "Text"
[language_files]
"Dockerfile" = "Dockerfile"
[tests]
patterns = ["*.test.ts", "*.test.tsx", "*.spec.ts", "test/", "tests/", "keyboard/", "a11y/"]
[[area]]
name = "libraries"
paths = ["packages/libs"]
[[area]]
name = "web"
paths = ["apps/web"]
[[area]]
name = "services"
paths = ["services/one", "services/two"]
[other]
folders = ["docs"]
files = ["README.md"]
"""

BASE = {
    "packages/libs/a.py": "x = 1\n",
    "apps/web/b.ts": "export {};\n",
    "services/one/c.py": "y = 2\n",
    "docs/guide.md": "# Guide\n",
    "README.md": "# Read me\n",
}


# --- the columns ---------------------------------------------------------------------------------------------------


def test_the_default_output_has_exactly_the_eight_columns(tmp_path: Path) -> None:
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    made = generate(make_repo(tmp_path, "r", BASE), tmp_path, rules=rules)
    header = next(csv.reader(io.StringIO(made.csv_bytes.decode("utf-8"))))
    assert header == EIGHT
    assert all(len(row) == 8 for row in csv.reader(io.StringIO(made.csv_bytes.decode("utf-8"))))
    assert "maintained_under" not in made.md


def test_the_repositorys_rules_file_has_no_maintained_under_mapping() -> None:
    text = RULES.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    assert set(parsed) <= {
        "version",
        "languages",
        "language_files",
        "tests",
        "generated",
        "area",
        "other",
        "header",
    }, (
        "the repository's rules file holds only the areas, languages, tests and generators: the owner keeps the "
        "second file, with a label for each file, outside the repository"
    )
    assert "maintained" not in text.lower()
    assert "label" not in text.lower()


def test_maintained_under_adds_one_last_column_only_when_the_file_is_given(tmp_path: Path) -> None:
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    second = write_rules(
        tmp_path / "second.toml",
        '[[rule]]\npaths = ["packages/libs"]\nlabels = ["B", "A"]\n'
        '[[rule]]\npaths = ["packages/libs/a.py"]\nlabels = ["C"]\n'
        '[[rule]]\npaths = ["apps"]\nlabels = ["B"]\n',
    )
    repo = make_repo(tmp_path, "r", {**BASE, "packages/libs/z.py": "z = 0\n"})
    plain = generate(repo, tmp_path, rules=rules)
    with_column = generate(repo, tmp_path, "--maintained-under", str(second), rules=rules)
    rows = with_column.by_path()
    assert list(with_column.table[0]) == [*EIGHT, "maintained_under"]
    assert rows["packages/libs/a.py"]["maintained_under"] == "A;B;C", (
        "a file in several: sorted, joined with ;"
    )
    assert rows["packages/libs/z.py"]["maintained_under"] == "A;B"
    assert rows["apps/web/b.ts"]["maintained_under"] == "B"
    assert rows["README.md"]["maintained_under"] == ""
    assert [
        {k: v for k, v in r.items() if k != "maintained_under"} for r in with_column.table
    ] == plain.table
    assert "maintained_under" not in plain.md and "A;B;C" not in plain.md


# --- the facts about one file ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "lines", "size"),
    [
        (b"a\nb", "2", 3),  # a last line without a newline counts
        (b"a\nb\n", "2", 4),
        (b"", "0", 0),
        (b"\n", "1", 1),
        (b"one", "1", 3),
        (b"a\r\nb\r\n", "2", 6),  # \n is what is counted
        (b"ab\x00cd\n", "", 6),  # a NUL byte in the first 8 KB: binary, so no line count
        (b"a" * 8191 + b"\x00\n", "", 8193),  # the last byte of the first 8 KB
        (b"a" * 8192 + b"\x00tail\n", "1", 8192 + 6),  # the first byte after it: text
    ],
)
def test_lines_bytes_and_binary(tmp_path: Path, content: bytes, lines: str, size: int) -> None:
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    made = generate(
        make_repo(tmp_path, "r", {"packages/libs/f.txt": content}), tmp_path, rules=rules
    )
    row = made.by_path()["packages/libs/f.txt"]
    assert (row["lines"], row["bytes"]) == (lines, str(size))


def test_language_comes_from_the_rules_and_an_unknown_one_is_the_word_unknown_and_counted(
    tmp_path: Path,
) -> None:
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    files = {
        "packages/libs/a.py": "",
        "packages/libs/B.PY": "",
        "apps/web/c.test.ts": "",
        "apps/web/Dockerfile": "FROM x\n",
        "apps/web/d.weird": "",
        "apps/web/noextension": "",
    }
    made = generate(make_repo(tmp_path, "r", files), tmp_path, rules=rules)
    languages = {p: r["language"] for p, r in made.by_path().items()}
    assert languages == {
        "packages/libs/a.py": "Python",
        "packages/libs/B.PY": "Python",
        "apps/web/c.test.ts": "TypeScript",
        "apps/web/Dockerfile": "Dockerfile",
        "apps/web/d.weird": "unknown",
        "apps/web/noextension": "unknown",
    }
    assert re.search(r"unknown language[^\n]*: 2\b", made.md), made.md


IS_TEST = {
    "a.test.ts": True,
    "x/b.test.tsx": True,
    "x/c.spec.ts": True,
    "test/d.py": True,
    "src/tests/e.py": True,
    "apps/w/keyboard/f.ts": True,
    "apps/w/a11y/g.ts": True,
    "src/latest/h.py": False,
    "contest.ts": False,
    "attest.py": False,
    "src/a.ts": False,
    "notkeyboard/x.ts": False,
    "src/testing.py": False,
}


@pytest.mark.parametrize("which", ["small", "real"])
def test_is_test_is_by_path_pattern(tmp_path: Path, which: str) -> None:
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES) if which == "small" else RULES
    made = generate(make_repo(tmp_path, "r", {p: "" for p in IS_TEST}), tmp_path, rules=rules)
    got = {p: r["is_test"] == "yes" for p, r in made.by_path().items()}
    assert got == IS_TEST
    assert {r["is_test"] for r in made.table} == {"yes", "no"}


# --- is_generated: the repository's own evidence ---------------------------------------------------------------------


GENERATED_RULES = (
    SMALL_RULES
    + """
[[generated]]
paths = ["packages/libs/out"]
generator = "packages/libs/make.py"
command = "python packages/libs/make.py"
[[generated]]
paths = ["docs/pdf"]
generator = "tools/not_in_this_tree.py"
command = "the document build"
[[generated]]
paths = ["apps/web/untraced.json"]
generator = ""
note = "written by a test the developer repository keeps"
"""
)


@pytest.mark.parametrize(
    "marker", ["AUTO-GENERATED", "@generated", "DO NOT EDIT", "auto-generated", "Do not edit"]
)
def test_a_header_in_the_first_lines_is_evidence(tmp_path: Path, marker: str) -> None:
    files = {"packages/libs/h.ts": f"// {marker} by something\nexport {{}};\n"}
    made = generate(
        make_repo(tmp_path, "r", files),
        tmp_path,
        rules=write_rules(tmp_path / "r.toml", SMALL_RULES),
    )
    assert made.by_path()["packages/libs/h.ts"]["is_generated"] == "yes"


def test_a_marker_far_from_the_top_is_prose_and_not_evidence(tmp_path: Path) -> None:
    # The shape the real tree has: a generator's own source says the words it writes into its output (far from the top).
    body = "x = 1\n" * 40 + '"# AUTO-GENERATED - do not edit by hand.\\n"\n'
    files = {"packages/libs/gen.py": body}
    made = generate(
        make_repo(tmp_path, "r", files),
        tmp_path,
        rules=write_rules(tmp_path / "r.toml", SMALL_RULES),
    )
    assert made.by_path()["packages/libs/gen.py"]["is_generated"] == "no"


def test_a_generated_folder_name_is_not_evidence(tmp_path: Path) -> None:
    files = {
        "packages/libs/generated/a.ts": "export {};\n",
        "packages/libs/dist/b.ts": "export {};\n",
    }
    made = generate(
        make_repo(tmp_path, "r", files),
        tmp_path,
        rules=write_rules(tmp_path / "r.toml", SMALL_RULES),
    )
    assert {r["is_generated"] for r in made.table} == {"no"}


def test_a_rule_is_evidence_only_where_its_generator_is_in_the_tree(tmp_path: Path) -> None:
    files = {
        "packages/libs/make.py": "print('writes out/')\n",
        "packages/libs/out/a.ts": "export {};\n",
        "packages/libs/outside.ts": "export {};\n",
        "docs/pdf/guide.pdf": b"%PDF-1.7\x00\x01",
        "apps/web/untraced.json": "{}\n",
        "apps/web/other.json": "{}\n",
    }
    made = generate(
        make_repo(tmp_path, "r", files),
        tmp_path,
        rules=write_rules(tmp_path / "r.toml", GENERATED_RULES),
    )
    got = {p: r["is_generated"] for p, r in made.by_path().items()}
    assert got["packages/libs/out/a.ts"] == "yes"
    assert got["packages/libs/outside.ts"] == "no", (
        "the rule names a folder; a file beside it is not covered"
    )
    assert got["docs/pdf/guide.pdf"] == "no evidence in this tree", (
        "the generator is not in the tree: not `yes`"
    )
    assert got["apps/web/untraced.json"] == "no evidence in this tree"
    assert got["apps/web/other.json"] == "no"
    assert re.search(r"no evidence in this tree[^\n]*: 2\b", made.md), made.md
    # the generator's own folder evidence is read at the ref: the same rule with the generator absent is not `yes`
    files.pop("packages/libs/make.py")
    again = generate(
        make_repo(tmp_path, "r2", files),
        tmp_path,
        rules=write_rules(tmp_path / "r2.toml", GENERATED_RULES),
    )
    assert again.by_path()["packages/libs/out/a.ts"]["is_generated"] == "no evidence in this tree"


def test_the_summary_explains_the_three_values(tmp_path: Path) -> None:
    made = generate(
        make_repo(tmp_path, "r", BASE),
        tmp_path,
        rules=write_rules(tmp_path / "r.toml", SMALL_RULES),
    )
    for words in (
        "`yes`",
        "`no`",
        "`no evidence in this tree`",
        "`not determined`",
        "`builder only`",
    ):
        assert words in made.md, words


# --- layouts and the ref -----------------------------------------------------------------------------------------------


def test_the_manifest_is_the_same_in_either_layout_and_says_which_it_saw(tmp_path: Path) -> None:
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    user = make_repo(tmp_path, "user", BASE)
    developer = make_repo(tmp_path, "dev", BASE, prefix="OspreyFlow_Core/")
    write_tree(
        developer,
        {
            "OspreyFlow_Build/tests/test_x.py": "def test(): ...\n",
            "OspreyFlow_Build/tools/t.py": "",
            "Makefile": "",
        },
    )
    commit(developer)
    a = generate(user, tmp_path, rules=rules)
    b = generate(developer, tmp_path, rules=rules)
    assert "Layout: user repository" in a.md
    assert "Layout: developer repository" in b.md
    assert b.table == a.table, "the same product content gives the same rows in either layout"
    assert a.csv_bytes == b.csv_bytes
    assert "OspreyFlow_Build" not in b.md and "OspreyFlow_Build" not in b.csv_bytes.decode()
    assert "Makefile" not in b.csv_bytes.decode(), (
        "a file beside the product folder is not the product's"
    )


def test_the_manifest_is_of_the_ref_and_not_of_the_working_tree(tmp_path: Path) -> None:
    rules = write_rules(tmp_path / "rules.toml", GENERATED_RULES)
    repo = make_repo(
        tmp_path,
        "r",
        {
            **BASE,
            "packages/libs/make.py": "",
            "packages/libs/out/a.ts": "one\n",
            "gone.txt": "bye\n",
        },
    )
    git(repo, "tag", "-a", "v1", "-m", "release")
    first = git(repo, "rev-parse", "v1^{commit}")
    (repo / "gone.txt").unlink()
    git(repo, "rm", "-q", "-f", "packages/libs/make.py")
    write_tree(
        repo, {"later.txt": "added after the tag\n", "packages/libs/out/a.ts": "one\ntwo\nthree\n"}
    )
    commit(repo, "after the tag")
    # now dirty the working tree further: an edit, an untracked file, an ignored file
    write_tree(
        repo, {"README.md": "edited\n" * 99, "untracked.txt": "u\n", ".gitignore": "ignored.txt\n"}
    )
    write_tree(repo, {"ignored.txt": "i\n"})
    made = generate(repo, tmp_path, ref="v1", rules=rules)
    rows = made.by_path()
    assert set(rows) == {*BASE, "packages/libs/make.py", "packages/libs/out/a.ts", "gone.txt"}
    assert rows["packages/libs/out/a.ts"]["lines"] == "1"
    assert rows["README.md"]["bytes"] == str(len(BASE["README.md"]))
    assert rows["packages/libs/out/a.ts"]["is_generated"] == "yes", (
        "the generator was in the tree at v1"
    )
    assert "Ref: v1" in made.md and f"Commit: {first}" in made.md, (
        "the annotated tag resolves to its commit"
    )
    head = generate(repo, tmp_path, rules=rules)
    assert "later.txt" in head.by_path() and "untracked.txt" not in head.by_path()
    assert "ignored.txt" not in head.by_path()
    assert head.by_path()["packages/libs/out/a.ts"]["is_generated"] == "no evidence in this tree"


def merge_repo(tmp: Path) -> Path:
    """A merge commit whose two parents differ: first parent has `main.txt`, second has `side.txt`."""
    repo = make_repo(tmp, "merged", {**BASE, "base.txt": "b\n"})
    git(repo, "checkout", "-q", "-b", "side")
    write_tree(repo, {"side.txt": "s\n"})
    commit(repo, "side")
    git(repo, "checkout", "-q", "main")
    write_tree(repo, {"main.txt": "m\n"})
    commit(repo, "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge", "side")
    return repo


@pytest.mark.parametrize(
    "ref",
    ["HEAD^", "HEAD^1", "HEAD^2", "HEAD^0", "HEAD~", "HEAD~1", "HEAD~2", "HEAD^2^", "HEAD~1^2"],
)
def test_a_ref_with_parent_and_ancestor_steps_names_the_commit_git_names(
    tmp_path: Path, ref: str
) -> None:
    # `^N` is the Nth parent of a merge (`^0` the commit itself), `~N` the Nth first-parent ancestor
    repo = merge_repo(tmp_path)
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    try:
        want = git(repo, "rev-parse", f"{ref}^{{commit}}")
    except subprocess.CalledProcessError:  # HEAD~1^2 is not a merge: git refuses, and so must we
        done = run_script(
            "--repo", str(repo), "--ref", ref, "--out", str(tmp_path / "o"), cwd=tmp_path
        )
        assert done.returncode != 0
        return
    made = generate(repo, tmp_path, ref=ref, rules=rules)
    assert f"Commit: {want}" in made.md and f"Ref: {ref}" in made.md
    assert set(made.by_path()) == set(git(repo, "ls-tree", "-r", "--name-only", want).splitlines())


def test_the_second_parent_of_a_merge_is_the_second_parent_and_not_the_first(
    tmp_path: Path,
) -> None:
    repo = merge_repo(tmp_path)
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    second = set(generate(repo, tmp_path, ref="HEAD^2", rules=rules).by_path())
    first = set(generate(repo, tmp_path, ref="HEAD^1", rules=rules).by_path())
    assert "side.txt" in second and "main.txt" not in second
    assert "main.txt" in first and "side.txt" not in first


@pytest.mark.parametrize("ref", ["HEAD^3", "HEAD^9", "HEAD~9", "HEAD^2^2"])
def test_a_ref_past_the_parents_there_are_is_refused_in_words(tmp_path: Path, ref: str) -> None:
    repo = merge_repo(tmp_path)
    done = run_script("--repo", str(repo), "--ref", ref, "--out", str(tmp_path / "o"), cwd=tmp_path)
    assert done.returncode != 0 and "not a commit" in done.stderr + done.stdout
    assert not (tmp_path / "o").exists()


# --- same input, same bytes ----------------------------------------------------------------------------------------------

DOCKER_FILES = {
    ".github/workflows/release.yml": "jobs:\n  images:\n    strategy:\n      matrix:\n        include:\n"
    "          - { service: worker, dockerfile: svc/worker/Dockerfile }\n"
    "          - { service: api, dockerfile: svc/api/Dockerfile }\n"
    "          - { service: report-sync, dockerfile: svc/rs/Dockerfile }\n"
    "          - { service: ingest, dockerfile: svc/ingest/Dockerfile }\n",
    **{
        f"svc/{name}/Dockerfile": "FROM python:3.12-slim AS builder\nWORKDIR /app\nCOPY pkgs ./pkgs\n"
        "FROM python:3.12-slim\nWORKDIR /app\nCOPY --from=builder /app/pkgs ./pkgs\n"
        for name in ("worker", "api", "rs", "ingest")
    },
    "pkgs/one.py": "1\n",
    "pkgs/two/three.py": "3\n",
    "Z.txt": "z\n",
    "a-b": "1\n",
    "a/b": "1\n",
    "a.b": "1\n",
    "b": "1\n",
    "é.txt": "e\n",
    'x,y"z.txt': "quoted\n",
}


def test_two_runs_at_one_ref_are_byte_equal(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "r", DOCKER_FILES)
    one = generate(repo, tmp_path, rules=RULES)
    two = generate(repo, tmp_path, rules=RULES)
    assert one.csv_bytes == two.csv_bytes and one.md.encode() == two.md.encode()


def test_two_runs_from_another_clone_and_folder_are_byte_equal(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "r", DOCKER_FILES)
    deep = tmp_path / "somewhere" / "else"
    deep.mkdir(parents=True)
    git(tmp_path, "clone", "-q", str(repo), str(deep / "clone"))
    one = generate(repo, tmp_path, rules=RULES)
    two = generate(deep / "clone", deep, rules=RULES)
    assert one.csv_bytes == two.csv_bytes and one.md.encode() == two.md.encode()
    # and run from a folder inside the repository, with no --repo, as a person at the root of a checkout would
    sub = repo / "pkgs"
    out = tmp_path / "from-sub"
    done = run_script("--ref", "HEAD", "--out", str(out), "--rules", str(RULES), cwd=sub)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (out / "maintainer-manifest.csv").read_bytes() == one.csv_bytes
    assert (out / "maintainer-manifest.md").read_bytes() == one.md.encode()


def test_the_output_does_not_depend_on_the_hash_seed(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "r", DOCKER_FILES)
    seen = {
        (made.csv_bytes, made.md)
        for seed in "01234567"
        for made in [generate(repo, tmp_path, rules=RULES, hash_seed=seed)]
    }
    assert len(seen) == 1


def test_a_planted_set_iteration_is_caught(tmp_path: Path) -> None:
    """Rule 15: the check above is shown red. The plant is the set iteration at the call site the code really has
    (the list of images a file is in, joined for its cell); four images, so some seed gives another order."""
    repo = make_repo(tmp_path, "r", DOCKER_FILES)
    program = (
        "import sys; import scripts.maintainer_manifest as m; "
        "m.format_list = lambda values: ';'.join(set(values)); sys.exit(m.main(sys.argv[1:]))"
    )
    outputs = set()
    for seed in "01234567":
        out = tmp_path / f"plant-{seed}"
        env = {**os.environ, "PYTHONPATH": str(CORE), "PYTHONHASHSEED": seed}
        done = subprocess.run(
            [sys.executable, "-c", program, "--repo", str(repo), "--ref", "HEAD", "--out", str(out),
             "--rules", str(RULES)],
            cwd=tmp_path, env=env, capture_output=True, text=True,
        )  # fmt: skip
        assert done.returncode == 0, done.stdout + done.stderr
        outputs.add((out / "maintainer-manifest.csv").read_bytes())
    assert len(outputs) > 1, (
        "set iteration must change the bytes under some hash seed, or the test above is blind"
    )


def test_the_output_is_sorted_by_bytes_with_unix_line_endings_and_fixed_quoting(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path, "r", {**DOCKER_FILES, "crlf.txt": "a\r\nb\r\n"})
    made = generate(repo, tmp_path, rules=RULES)
    paths = [r["path"] for r in made.table]
    assert paths == sorted(paths, key=lambda p: p.encode("utf-8"))
    assert (
        paths.index("Z.txt")
        < paths.index("a-b")
        < paths.index("a.b")
        < paths.index("a/b")
        < paths.index("b")
    )
    assert paths.index("b") < paths.index("é.txt"), "bytes, not a locale's order"
    assert b"\r" not in made.csv_bytes and b"\r" not in made.md.encode()
    assert made.csv_bytes.endswith(b"\n") and made.md.endswith("\n")
    assert made.by_path()['x,y"z.txt']["bytes"] == str(len("quoted\n"))
    assert b'\n"x,y""z.txt",' in made.csv_bytes, "minimal quoting, a quote doubled"


def test_the_summary_names_no_date_machine_path_or_user(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "r", DOCKER_FILES)
    made = generate(repo, tmp_path, rules=RULES)
    text = made.md + made.csv_bytes.decode()
    assert str(tmp_path) not in text and str(Path.home()) not in text
    user = getpass.getuser()
    assert user.lower() in {"user", "root", "runner", "docker"} or user not in text
    assert not re.search(r"\b(19|20)\d\d-\d\d-\d\d\b", text), "no date"
    assert not re.search(r"\b\d\d:\d\d:\d\d\b", text), "no time"
    assert made.md.count("Commit: ") == 1 and f"Commit: {git(repo, 'rev-parse', 'HEAD')}" in made.md


# --- the areas check ------------------------------------------------------------------------------------------------------


def test_areas_check_passes_a_tree_every_rule_covers(tmp_path: Path) -> None:
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    done = check_areas(make_repo(tmp_path, "r", BASE), tmp_path, rules)
    assert done.returncode == 0, done.stdout + done.stderr


def test_areas_check_fails_on_a_new_folder_under_packages_and_passes_once_a_rule_covers_it(
    tmp_path: Path,
) -> None:
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    repo = make_repo(
        tmp_path,
        "r",
        {**BASE, "packages/newthing/c.py": "z = 3\n", "packages/newthing/deep/d.py": ""},
    )
    red = check_areas(repo, tmp_path, rules)
    assert red.returncode == 1
    assert "packages/newthing/c.py" in red.stdout and "packages/newthing/deep/d.py" in red.stdout
    assert "no area" in red.stdout
    write_rules(
        rules,
        SMALL_RULES.replace(
            'paths = ["packages/libs"]', 'paths = ["packages/libs", "packages/newthing"]'
        ),
    )
    green = check_areas(repo, tmp_path, rules)
    assert green.returncode == 0, green.stdout + green.stderr


def test_areas_check_fails_on_a_new_service_and_a_new_app_folder_too(tmp_path: Path) -> None:
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    repo = make_repo(
        tmp_path,
        "r",
        {**BASE, "services/three/s.py": "", "apps/tool/t.ts": "", "packages/libs/new/x.py": ""},
    )
    red = check_areas(repo, tmp_path, rules)
    assert red.returncode == 1
    assert "services/three/s.py" in red.stdout and "apps/tool/t.ts" in red.stdout
    assert "packages/libs/new/x.py" not in red.stdout, "a folder inside a covered one is covered"


def test_areas_check_fails_on_a_file_two_rules_match_and_passes_when_the_overlap_is_taken_out(
    tmp_path: Path,
) -> None:
    both = SMALL_RULES + '[[area]]\nname = "shared"\npaths = ["packages/libs/a.py"]\n'
    rules = write_rules(tmp_path / "rules.toml", both)
    repo = make_repo(tmp_path, "r", BASE)
    red = check_areas(repo, tmp_path, rules)
    assert red.returncode == 1
    line = next(row for row in red.stdout.splitlines() if "packages/libs/a.py" in row)
    assert "libraries" in line and "shared" in line and "two areas" in line
    assert "packages/libs/z.py" not in red.stdout
    fixed = both.replace(
        'paths = ["packages/libs"]', 'paths = ["packages/libs"]\nexcept = ["packages/libs/a.py"]'
    )
    write_rules(rules, fixed)
    green = check_areas(repo, tmp_path, rules)
    assert green.returncode == 0, green.stdout + green.stderr
    assert generate(repo, tmp_path, rules=rules).by_path()["packages/libs/a.py"]["area"] == "shared"


def test_areas_check_fails_on_a_folder_in_other_that_the_rules_do_not_name(tmp_path: Path) -> None:
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    repo = make_repo(tmp_path, "r", {**BASE, "misc/z.txt": "z\n", "NEWS": "n\n"})
    red = check_areas(repo, tmp_path, rules)
    assert red.returncode == 1 and "misc/z.txt" in red.stdout and "NEWS" in red.stdout
    named = SMALL_RULES.replace('folders = ["docs"]', 'folders = ["docs", "misc"]').replace(
        'files = ["README.md"]', 'files = ["README.md", "NEWS"]'
    )
    write_rules(rules, named)
    green = check_areas(repo, tmp_path, rules)
    assert green.returncode == 0, green.stdout + green.stderr
    assert generate(repo, tmp_path, rules=rules).by_path()["misc/z.txt"]["area"] == "other"


@pytest.mark.parametrize("catch_all", ["*", "**", "mi*", "docs/*"])
def test_other_is_not_a_catch_all_it_names_folders_and_files(
    tmp_path: Path, catch_all: str
) -> None:
    body = SMALL_RULES.replace('folders = ["docs"]', f'folders = ["docs", "{catch_all}"]')
    rules = write_rules(tmp_path / "rules.toml", body)
    red = check_areas(make_repo(tmp_path, "r", {**BASE, "misc/z.txt": "z\n"}), tmp_path, rules)
    assert red.returncode == 1
    assert "other" in red.stdout and catch_all in red.stdout and "names" in red.stdout


#: A file in a folder no one has made a rule for, one for each place the check guards.
NEW_FOLDERS = [
    "packages/newthing/x.py",
    "services/newone/x.py",
    "apps/newapp/x.ts",
    "apps/pages/newtree/x.ts",
    "packages/themes/newtheme/x.css",
    "packages/loose_file.py",
]


@pytest.mark.parametrize("planted", NEW_FOLDERS)
def test_the_shipped_rules_fail_on_a_new_folder_no_rule_covers(
    tmp_path: Path, planted: str
) -> None:
    # the check exists to fail on a folder nobody has placed: so it is the repository's own rules file that is
    # run here, not a small one of this test's, and a wildcard that covered every new folder would turn this red
    repo = make_repo(tmp_path, "r", {"README.md": "r\n", planted: "z\n"})
    done = check_areas(repo, tmp_path, RULES)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"{planted} is in no area" in done.stdout


def test_a_wildcard_in_the_shipped_rules_would_turn_that_case_red(tmp_path: Path) -> None:
    # the planted fault at its real shape: the real rules with the per-service list swapped for `services/*`
    # (and likewise for packages and apps), so the new-folder cases above are shown able to fail
    text = RULES.read_text(encoding="utf-8")
    wild = text.replace('"services/compute",', '"services/*", "services/compute",')
    wild = wild.replace(
        'paths = ["packages/adapters"]', 'paths = ["packages/adapters", "packages/*"]'
    )
    wild = wild.replace('paths = ["apps/harness"]', 'paths = ["apps/harness", "apps/*"]')
    assert wild.count("/*") == 3, "the plant did not land in the real file's shape"
    rules = write_rules(tmp_path / "wild.toml", wild)
    for planted in ("services/newone/x.py", "packages/newthing/x.py", "apps/newapp/x.ts"):
        repo = make_repo(
            tmp_path, "r" + planted.replace("/", "_"), {"README.md": "r\n", planted: "z\n"}
        )
        hidden = check_areas(repo, tmp_path, rules)
        assert hidden.returncode == 0, "a wildcard hides a new folder from the check: " + planted


def test_no_area_in_the_shipped_rules_names_its_folders_by_pattern() -> None:
    # `other` is checked by the script itself; the areas are checked here: a folder under apps, packages or
    # services is placed by name, so a new one is a failure and a rule is added with it
    rules = tomllib.loads(RULES.read_text(encoding="utf-8"))
    for area in rules["area"]:
        for path in [*area["paths"], *area.get("except", [])]:
            assert not re.search(r"[*?\[]", path), (area["name"], path)


def test_areas_check_reads_the_ref_not_the_working_tree(tmp_path: Path) -> None:
    rules = write_rules(tmp_path / "rules.toml", SMALL_RULES)
    repo = make_repo(tmp_path, "r", BASE)
    write_tree(repo, {"packages/untracked/u.py": "u\n"})
    assert check_areas(repo, tmp_path, rules).returncode == 0, (
        "an untracked folder is not in the tree"
    )
    commit(repo)
    assert check_areas(repo, tmp_path, rules).returncode == 1
    assert check_areas(repo, tmp_path, rules, ref="HEAD~1").returncode == 0


def test_a_manifest_run_names_the_files_in_no_area_and_in_two_in_its_summary(
    tmp_path: Path,
) -> None:
    both = SMALL_RULES + '[[area]]\nname = "shared"\npaths = ["packages/libs/a.py"]\n'
    repo = make_repo(tmp_path, "r", {**BASE, "packages/newthing/c.py": ""})
    made = generate(repo, tmp_path, rules=write_rules(tmp_path / "rules.toml", both))
    assert re.search(r"in no area[^\n]*: 1\b", made.md) and re.search(
        r"in more than one area[^\n]*: 1\b", made.md
    )
    assert made.by_path()["packages/newthing/c.py"]["area"] == "unassigned"
    assert made.by_path()["packages/libs/a.py"]["area"] == "libraries", (
        "first match in the file's order"
    )


# --- release_images -------------------------------------------------------------------------------------------------------


def release_yml(*entries: str) -> str:
    return (
        "name: release\njobs:\n  images:\n    strategy:\n      matrix:\n        include:\n"
        + "".join(f"          - {{ {entry} }}\n" for entry in entries)
        + "  scan:\n    strategy:\n      matrix:\n        include:\n          - { os: linux }\n"
    )


def images(
    tmp: Path, files: dict[str, str | bytes], *matrix: str, name: str = "r"
) -> dict[str, str]:
    files = {".github/workflows/release.yml": release_yml(*matrix), **files}
    made = generate(
        make_repo(tmp, name, files), tmp, rules=write_rules(tmp / f"{name}.toml", SMALL_RULES)
    )
    return {p: r["release_images"] for p, r in made.by_path().items()}


def test_images_the_release_names_come_from_the_matrix_and_a_file_in_several_is_a_sorted_list(
    tmp_path: Path,
) -> None:
    files = {
        "svc/b/Dockerfile": "FROM x\nCOPY shared ./shared\n",
        "svc/a/Dockerfile": "FROM x\nCOPY shared ./shared\nCOPY svc/a/own.py ./\n",
        "svc/c/Dockerfile": "FROM x\nCOPY shared ./shared\nCOPY svc/c/own.py ./\n",
        "shared/lib.py": "",
        "svc/a/own.py": "",
        "svc/c/own.py": "",
        "svc/c/other.py": "",
    }
    got = images(
        tmp_path,
        files,
        "service: zeta, dockerfile: svc/b/Dockerfile",
        "service: alpha, dockerfile: svc/a/Dockerfile",
    )
    assert got["shared/lib.py"] == "alpha;zeta", "sorted by name, not by the matrix's order"
    assert got["svc/a/own.py"] == "alpha"
    assert got["svc/c/own.py"] == "none (not released)", (
        "svc/c holds a Dockerfile the release does not name"
    )
    assert got["svc/c/other.py"] == "none (not released)"
    assert got["svc/a/Dockerfile"] == "none", "a Dockerfile is not copied into its own image"
    renamed = images(tmp_path, files, "service: beta, dockerfile: svc/b/Dockerfile", name="r2")
    assert renamed["shared/lib.py"] == "beta", (
        "the names are read from the matrix, never fixed in the code"
    )


def test_images_without_a_release_workflow_are_not_determined(tmp_path: Path) -> None:
    made = generate(
        make_repo(tmp_path, "r", BASE),
        tmp_path,
        rules=write_rules(tmp_path / "r.toml", SMALL_RULES),
    )
    assert {r["release_images"] for r in made.table} == {"not determined"}
    assert "no release workflow" in made.md


def test_images_a_matrix_entry_whose_dockerfile_is_not_in_the_tree_fails_in_words(
    tmp_path: Path,
) -> None:
    files = {
        ".github/workflows/release.yml": release_yml(
            "service: ghost, dockerfile: svc/ghost/Dockerfile"
        ),
        "a.txt": "",
    }
    repo = make_repo(tmp_path, "r", files)
    done = run_script(
        "--repo", str(repo), "--ref", "HEAD", "--out", str(tmp_path / "o"), cwd=tmp_path
    )
    assert done.returncode != 0 and "svc/ghost/Dockerfile" in done.stdout + done.stderr


def test_images_the_root_dockerignore_applies_with_docker_s_rule_that_a_name_without_a_slash_is_the_root_only(
    tmp_path: Path,
) -> None:
    files = {
        "svc/Dockerfile": "FROM x\nCOPY . /app\n",
        ".dockerignore": "# not in the image\ntests\n**/cache\ndata\n!data/keep.txt\n*.log\n",
        "tests/x.py": "",  # the root `tests`: excluded
        "pkg/tests/y.py": "",  # `tests` has no slash: only the root's
        "pkg/cache/z.py": "",  # `**/cache`: at any depth
        "cache/w.py": "",
        "data/gone.txt": "",
        "data/keep.txt": "",  # re-included by `!`
        "run.log": "",
        "deep/run.log": "",  # `*.log` without a slash: only the root's
    }
    got = images(tmp_path, files, "service: app, dockerfile: svc/Dockerfile")
    assert (
        got["pkg/tests/y.py"] == "app"
        and got["data/keep.txt"] == "app"
        and got["deep/run.log"] == "app"
    )
    for excluded in ("tests/x.py", "pkg/cache/z.py", "cache/w.py", "data/gone.txt", "run.log"):
        assert got[excluded] == "none", excluded


def test_images_a_build_with_its_own_context_uses_that_folders_dockerignore_and_not_the_roots(
    tmp_path: Path,
) -> None:
    files = {
        ".dockerignore": "*.md\nsvc\n",  # the root's: not this build's
        "svc/own/Dockerfile": "FROM x\nCOPY . /srv\n",
        "svc/own/.dockerignore": "private\n",
        "svc/own/app.py": "",
        "svc/own/notes.md": "",
        "svc/own/private/key.txt": "",
        "svc/other.py": "",
        "root.py": "",
    }
    got = images(tmp_path, files, "service: own, dockerfile: svc/own/Dockerfile, context: svc/own")
    assert got["svc/own/app.py"] == "own" and got["svc/own/notes.md"] == "own"
    assert got["svc/own/private/key.txt"] == "none"
    assert got["svc/other.py"] == "none" and got["root.py"] == "none", "outside the context"


def test_images_only_a_final_stage_copy_counts_and_the_rest_is_builder_only(tmp_path: Path) -> None:
    files = {
        "svc/Dockerfile": (
            "FROM x AS builder\nWORKDIR /w\nCOPY helper.txt ./\nCOPY kept.txt ./\nCOPY dir ./dir\n"
            "FROM y\nCOPY --from=builder /w/kept.txt /kept.txt\nCOPY --from=builder /w/dir /dir\n"
        ),
        "helper.txt": "",
        "kept.txt": "",
        "dir/a.txt": "",
        "unused.txt": "",
    }
    got = images(tmp_path, files, "service: app, dockerfile: svc/Dockerfile")
    assert got["kept.txt"] == "app" and got["dir/a.txt"] == "app"
    assert got["helper.txt"] == "builder only"
    assert got["unused.txt"] == "none"


def test_images_built_output_makes_its_sources_not_determined_and_never_a_guess(
    tmp_path: Path,
) -> None:
    files = {
        "svc/Dockerfile": (
            "FROM node AS builder\nWORKDIR /app\nCOPY package.json ./\nCOPY src ./src\nRUN npm run build\n"
            "FROM nginx\nCOPY conf.template /etc/nginx/t.conf\nCOPY --from=builder /app/dist /usr/share/html\n"
        ),
        "package.json": "{}",
        "src/main.ts": "",
        "conf.template": "",
        "elsewhere.txt": "",
    }
    got = images(tmp_path, files, "service: web, dockerfile: svc/Dockerfile")
    assert got["package.json"] == "not determined" and got["src/main.ts"] == "not determined"
    assert got["conf.template"] == "web", "copied straight into the final stage: exact"
    assert got["elsewhere.txt"] == "none"


def test_images_a_source_that_cannot_be_resolved_statically_is_not_determined(
    tmp_path: Path,
) -> None:
    for number, line in enumerate(("COPY $WHAT ./", "COPY **/*.py ./", "COPY <<EOF /x\nbody\nEOF")):
        files = {
            "svc/Dockerfile": f"FROM x\n{line}\nCOPY known.txt ./\n",
            "known.txt": "",
            "x/y.py": "",
            "other.txt": "",
        }
        got = images(tmp_path, files, "service: app, dockerfile: svc/Dockerfile", name=f"u{number}")
        assert got["known.txt"] == "app", line
        assert got["other.txt"] == "not determined", line
        assert got["x/y.py"] == "not determined", line


def test_images_stages_chain_by_from_and_by_copy_from_and_the_base_stage_is_part_of_the_image(
    tmp_path: Path,
) -> None:
    files = {
        "svc/Dockerfile": (
            "ARG KIND=included\n"
            "FROM base AS runtime-included\nCOPY inc.txt /inc.txt\n"
            "FROM base AS runtime-omitted\nCOPY omit.txt /omit.txt\n"
            "FROM scratch AS first\nCOPY deep.txt /w/deep.txt\n"
            "FROM scratch AS Second\nCOPY --from=first /w /v\n"
            "FROM runtime-${KIND}\n"
            "COPY --from=second /v /final\n"
            "COPY --from=0 /nothing /x\n"
            "COPY --chown=1:1 --chmod=0444 a.txt \\\n     b.txt /two/\n"
            'COPY ["with space.txt", "/json/"]\n'
        ),
        "inc.txt": "", "omit.txt": "", "deep.txt": "", "a.txt": "", "b.txt": "", "with space.txt": "",
    }  # fmt: skip
    got = images(tmp_path, files, "service: app, dockerfile: svc/Dockerfile")
    assert got["inc.txt"] == "app", (
        "the base stage chosen by the ARG's default is part of the image"
    )
    assert got["omit.txt"] == "none", "a stage the final image does not stand on is not built"
    assert got["deep.txt"] == "app", "through two COPY --from hops"
    assert got["a.txt"] == got["b.txt"] == got["with space.txt"] == "app"


def test_images_a_build_argument_the_workflow_mentions_may_override_a_default_and_is_not_assumed(
    tmp_path: Path,
) -> None:
    dockerfile = (
        "ARG KIND=included\nFROM base AS runtime-included\nCOPY inc.txt /inc.txt\n"
        "FROM base AS runtime-omitted\nCOPY omit.txt /omit.txt\nFROM runtime-${KIND}\n"
    )
    files = {"svc/Dockerfile": dockerfile, "inc.txt": "", "omit.txt": ""}
    plain = images(tmp_path, files, "service: app, dockerfile: svc/Dockerfile")
    assert plain["inc.txt"] == "app" and plain["omit.txt"] == "none", (
        "the default, nothing overrides it"
    )
    passed = release_yml("service: app, dockerfile: svc/Dockerfile") + (
        "  other:\n    steps:\n      - run: docker build --build-arg KIND=omitted .\n"
    )
    got = images(tmp_path, {**files, ".github/workflows/release.yml": passed}, name="r2")
    assert got["inc.txt"] == got["omit.txt"] == "not determined", (
        "the workflow may pass another value"
    )


def test_images_a_wildcard_source_is_resolved_as_docker_does_a_star_stays_in_its_folder(
    tmp_path: Path,
) -> None:
    files = {
        "svc/Dockerfile": "FROM x\nCOPY src/*.py /dst/\nCOPY lib/[ab].txt /lib/\nCOPY sin?le.txt /one/\n",
        "src/a.py": "", "src/sub/b.py": "", "src/c.txt": "",
        "lib/a.txt": "", "lib/b.txt": "", "lib/c.txt": "",
        "single.txt": "",
    }  # fmt: skip
    got = images(tmp_path, files, "service: app, dockerfile: svc/Dockerfile")
    assert [got[p] for p in ("src/a.py", "lib/a.txt", "lib/b.txt", "single.txt")] == ["app"] * 4
    assert [got[p] for p in ("src/sub/b.py", "src/c.txt", "lib/c.txt")] == ["none"] * 3


def test_images_a_dockerfile_the_release_does_not_name_leaves_its_folder_not_released(
    tmp_path: Path,
) -> None:
    files = {
        "apps/pages/Dockerfile": "FROM x\nCOPY apps/pages ./\n",
        "apps/pages/server/app.ts": "",
        "svc/Dockerfile": "FROM x\nCOPY svc ./\n",
        "svc/a.txt": "",
    }
    got = images(tmp_path, files, "service: svc, dockerfile: svc/Dockerfile")
    assert got["apps/pages/server/app.ts"] == "none (not released)"
    assert got["svc/a.txt"] == "svc"


# --- Docker's own documented cases (the `.dockerignore` reference) -----------------------------------------------------


@pytest.fixture(scope="module")
def mm() -> Iterator[object]:
    sys.path.insert(0, str(CORE))
    try:
        import scripts.maintainer_manifest as module

        yield module
    finally:
        sys.path.remove(str(CORE))


DOCUMENTED = [
    # (the file's lines, path, excluded)
    (["# comment", "*/temp*"], "somedir/temporary.txt", True),
    (["*/temp*"], "somedir/temp", True),
    (["*/temp*"], "somedir/temp/inner.txt", True),  # an excluded directory excludes what is in it
    (["*/temp*"], "temporary.txt", False),  # one level only: not the root
    (["*/temp*"], "a/b/temporary.txt", False),
    (["*/*/temp*"], "somedir/subdir/temporary.txt", True),
    (["*/*/temp*"], "somedir/temporary.txt", False),
    (["temp?"], "tempa", True),
    (["temp?"], "tempb", True),
    (["temp?"], "temp", False),
    (["temp?"], "tempab", False),
    (["temp?"], "somedir/tempa", False),  # a name without a slash is the root's only
    (["**/*.go"], "main.go", True),  # `**` also matches no directory at all
    (["**/*.go"], "a/b/c/main.go", True),
    (["**/*.go"], "main.rs", False),
    (["*.md", "!README*.md"], "CHANGELOG.md", True),
    (["*.md", "!README*.md"], "README.md", False),
    (["*.md", "!README*.md"], "README-secret.md", False),
    (
        ["*.md", "!README*.md", "README-secret.md"],
        "README-secret.md",
        True,
    ),  # the last matching line wins
    (["*.md", "!README*.md", "README-secret.md"], "README.md", False),
    (
        ["*.md", "README-secret.md", "!README*.md"],
        "README-secret.md",
        False,
    ),  # ... wherever the others sit
    (["/foo"], "foo", True),  # a leading slash is the root, as without it
    (["foo/"], "foo", True),  # a trailing slash is dropped
    (["foo"], "bar/foo", False),
    (["foo"], "foo/bar", True),
    (["docs", "!docs/keep.md"], "docs/keep.md", False),
    (["docs", "!docs/keep.md"], "docs/other.md", True),
    (["**"], "any/where.txt", True),
    (["a/**/z"], "a/z", True),
    (["a/**/z"], "a/b/c/z", True),
    (["a/**/z"], "b/a/z", False),
    (["[ab]c"], "ac", True),
    (["[ab]c"], "cc", False),
    (["a.c"], "abc", False),  # a dot is a dot
    (["a+b"], "aab", False),  # and `+` is not a repeat
    ([""], "x", False),
]


@pytest.mark.parametrize(("lines", "path", "excluded"), DOCUMENTED, ids=lambda v: str(v))
def test_dockerignore_follows_docker_s_documented_cases(
    mm: object, lines: list[str], path: str, excluded: bool
) -> None:
    assert mm.dockerignore_excludes(lines, path) is excluded  # type: ignore[attr-defined]


def test_dockerignore_documented_case_would_fail_if_the_rule_were_wrong(mm: object) -> None:
    """Rule 15: a matcher that treated every pattern as matching at any depth (a gitignore reading) fails the case
    Docker's reference gives for a name without a slash, so the cases above are not satisfied by any matcher."""

    def gitignore_reading(lines: list[str], path: str) -> bool:
        names = [
            line.strip().strip("/")
            for line in lines
            if line.strip() and not line.startswith(("#", "!"))
        ]
        return any(part in names for part in path.split("/"))

    wrong = [c for c in DOCUMENTED if gitignore_reading(c[0], c[1]) is not c[2]]
    assert wrong, "a gitignore-style matcher must disagree with at least one documented case"
    assert all(mm.dockerignore_excludes(c[0], c[1]) is c[2] for c in wrong)  # type: ignore[attr-defined]


# --- the summary ----------------------------------------------------------------------------------------------------------


def test_the_summary_has_one_row_per_folder_and_the_sentence_about_the_python_tests(
    tmp_path: Path,
) -> None:
    files = {
        "packages/libs/a.py": "1\n2\n3\n",
        "packages/libs/b.py": "1\n",
        "packages/libs/img.bin": b"\x00\x01",
        "packages/libs/deep/c.py": "1\n2\n",
        "apps/web/d.ts": "x",
        "README.md": "# r\n",
    }
    made = generate(
        make_repo(tmp_path, "r", files),
        tmp_path,
        rules=write_rules(tmp_path / "r.toml", SMALL_RULES),
    )
    assert "| Folder | Area | Files | Lines | Binary files |" in made.md
    assert "| packages/libs | libraries | 3 | 4 | 1 |" in made.md
    assert "| packages/libs/deep | libraries | 1 | 2 | 0 |" in made.md
    assert "| apps/web | web | 1 | 1 | 0 |" in made.md
    assert "| . | other | 1 | 1 | 0 |" in made.md
    assert (
        "The Python tests are kept in the developer repository and are not part of this tree."
        in made.md
    )
    assert "Ref: HEAD" in made.md


def no_react_line(md: str) -> str:
    return next(line for line in md.splitlines() if line.startswith("no_react_check:"))


ISOLATION_TREE = {"apps/pages/a.ts": "export {};\n", "packages/glass-shared/b.ts": "export {};\n"}


def test_the_summary_says_not_run_when_the_bundler_is_not_installed_beside_the_script(
    tmp_path: Path,
) -> None:
    """The check bundles with the product's own bundler, found in the `node_modules` beside the script: a checkout
    that has not installed them cannot run it, and says so (it must not read the missing bundler as a pass)."""
    if shutil.which("node") is None:
        pytest.skip(
            "node is needed: the case is the one where node is there and the bundler is not"
        )
    checkout = tmp_path / "checkout"
    (checkout / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, checkout / "scripts" / SCRIPT.name)
    shutil.copy(RULES, checkout / "scripts" / RULES.name)
    repo = make_repo(
        tmp_path, "r", {**ISOLATION_TREE, "scripts/no_react_check.mjs": "// the check\n"}
    )
    made = generate(repo, tmp_path, extra_env={"PYTHONPATH": str(checkout)})
    line = no_react_line(made.md)
    assert "not run" in line and "node_modules" in line and "PASS" not in line, line


def test_the_summary_says_not_run_and_never_a_pass_when_the_ref_has_no_check(
    tmp_path: Path,
) -> None:
    made = generate(make_repo(tmp_path, "r", ISOLATION_TREE), tmp_path, rules=RULES)
    line = no_react_line(made.md)
    assert "not run" in line and "scripts/no_react_check.mjs" in line and "PASS" not in line


def test_the_summary_says_not_run_and_never_a_pass_when_node_is_not_available(
    tmp_path: Path,
) -> None:
    repo = make_repo(
        tmp_path, "r", {**ISOLATION_TREE, "scripts/no_react_check.mjs": "// the check\n"}
    )
    rules = write_rules(tmp_path / "r.toml", SMALL_RULES)
    bin_dir = tmp_path / "only-git"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(shutil.which("git") or "git")
    made = generate(repo, tmp_path, rules=rules, extra_env={"PATH": str(bin_dir)})
    line = no_react_line(made.md)
    assert "not run" in line and "PASS" not in line
    assert "| apps/pages | 1 | 1 |" in made.md and "| packages/glass-shared | 1 | 1 |" in made.md


def test_the_summary_records_a_failure_of_no_react_check_as_its_exit_status_and_last_line(
    tmp_path: Path,
) -> None:
    """Planted at the shape the check meets it: a tracked file of `apps/pages` that imports react, in an archive of a
    real (reduced) copy of the product's package files, with the product's bundler found from the checkout."""
    node = shutil.which("node")
    if node is None or not (CORE / "node_modules" / "rolldown").exists():
        pytest.skip(
            "node and the workspace's node_modules are needed to run scripts/no_react_check.mjs"
        )
    base = copy_reduced_core()
    clean = make_repo(tmp_path, "clean", base)
    bad = make_repo(
        tmp_path,
        "bad",
        {
            **base,
            "apps/pages/server/planted.ts": 'import { createElement } from "react";\nexport const x = createElement;\n',
        },
    )
    green = generate(clean, tmp_path, rules=RULES)
    red = generate(bad, tmp_path, rules=RULES)
    assert "exit status 0" in no_react_line(green.md) and "PASS" in no_react_line(green.md), (
        green.md
    )
    line = no_react_line(red.md)
    assert "exit status 1" in line and "planted.ts imports react" in line, line


def copy_reduced_core() -> dict[str, str | bytes]:
    names = [
        "package.json",
        "package-lock.json",
        "scripts/no_react_check.mjs",
        "scripts/lib/glass_trees.mjs",
        "apps/workspace/package.json",
        "apps/harness/package.json",
    ]
    names += [
        str(p.relative_to(CORE))
        for folder in ("apps/pages", "packages/glass-shared")
        for p in sorted((CORE / folder).rglob("*"))
        if p.is_file() and "node_modules" not in p.parts and "dist" not in p.parts
    ]
    return {name: (CORE / name).read_bytes() for name in names}


# --- the real tree ---------------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real(tmp_path_factory: pytest.TempPathFactory) -> Made:
    """The script at `HEAD` of this repository's `OspreyFlow_Core`, as the release would run it (read-only)."""
    tmp = tmp_path_factory.mktemp("real")
    out = tmp / "out"
    done = run_script("--repo", str(ROOT), "--ref", "HEAD", "--out", str(out), cwd=tmp)
    assert done.returncode == 0, done.stdout + done.stderr
    return Made(done, out)


def test_the_real_tree_is_manifested_from_the_tracked_files_and_every_one_is_in_one_area(
    real: Made,
) -> None:
    listed = git(ROOT, "ls-tree", "-r", "--name-only", "HEAD", "OspreyFlow_Core").splitlines()
    assert [r["path"] for r in real.table] == sorted(
        (p.removeprefix("OspreyFlow_Core/") for p in listed), key=lambda p: p.encode()
    )
    assert "Layout: developer repository" in real.md
    assert not any(r["path"].startswith("OspreyFlow_") for r in real.table)
    assert {r["area"] for r in real.table} <= {
        a["name"] for a in tomllib.loads(RULES.read_text())["area"]
    } | {"other"}
    assert "unassigned" not in {r["area"] for r in real.table}


def test_the_real_tree_passes_the_areas_check_with_its_own_rules(tmp_path: Path) -> None:
    done = run_script("--repo", str(ROOT), "--ref", "HEAD", "--check-areas", cwd=tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_real_tree_walk_of_apps_packages_and_services_leaves_no_file_unplaced(
    real: Made,
) -> None:
    for row in real.table:
        if row["path"].split("/")[0] in {"apps", "packages", "services"}:
            assert row["area"] not in {"unassigned", ""}, row["path"]
    top = {row["path"].split("/")[0] for row in real.table if "/" in row["path"]}
    assert {"apps", "packages", "services"} <= top


def test_the_real_tree_images_come_from_the_release_matrix_and_the_dockerfiles(real: Made) -> None:
    release = yaml.safe_load(
        git(ROOT, "show", "HEAD:OspreyFlow_Core/.github/workflows/release.yml")
    )
    names = {e["service"] for e in release["jobs"]["images"]["strategy"]["matrix"]["include"]}
    words = {"none", "none (not released)", "builder only", "not determined"}
    for row in real.table:
        value = row["release_images"]
        # a list of exact names, sorted, then `not determined` when another image may carry it too
        listed = value.split(";")
        undecided = len(listed) > 1 and listed[-1] == "not determined"
        named = listed[:-1] if undecided else listed
        assert value in words or set(named) <= names, (row["path"], value)
        assert value in words or named == sorted(named), (row["path"], value)
    by = real.by_path()
    assert by["deploy/superset/superset_config.py"]["release_images"] == "superset"
    assert by["services/laurium/app.py"]["release_images"] == "none (not released)", (
        "the optional engine's paths are shown"
    )
    assert by["apps/pages/server/app.ts"]["release_images"] == "none (not released)"
    assert by["services/api/app.py"]["release_images"] == "api;ingest;report-sync;worker", (
        "whole trees are copied"
    )
    assert "api" in by["docs/pdf/user-guide.pdf"]["release_images"].split(";")
    assert by["services/ner/app.py"]["release_images"] == "api;ingest;ner;report-sync;worker"


def test_the_real_tree_generated_evidence(real: Made) -> None:
    by = real.by_path()

    def named(name: str) -> dict[str, str]:
        """The one file of that name, wherever a move puts it: the case is about its evidence, not its folder."""
        found = [row for path, row in by.items() if path.rsplit("/", 1)[-1] == name]
        assert len(found) == 1, (name, [r["path"] for r in found])
        return found[0]

    assert named("release.schema.json")["is_generated"] == "yes", "generate_ts.py writes it"
    assert named("generate_ts.py")["is_generated"] == "no", "the generator is not itself generated"
    generated = [r for p, r in by.items() if p.startswith("packages/schemas/generated/")]
    assert len(generated) > 100 and {r["is_generated"] for r in generated} == {"yes"}
    assert named("user-guide.pdf")["is_generated"] == "no evidence in this tree"
    assert named("placesByRole.json")["is_generated"] == "no evidence in this tree"
    assert named("PL4_BASELINE.json")["is_generated"] == "yes"
    assert named("osprey_theme.json")["is_generated"] == "yes"


def test_the_real_summary_carries_the_counts_the_two_trees_and_the_no_react_result(
    real: Made,
) -> None:
    md = real.md
    for words in (
        "unknown language",
        "not determined",
        "no evidence in this tree",
        "in no area",
        "more than one area",
    ):
        assert words in md, words
    assert "| apps/pages |" in md and "| packages/glass-shared |" in md
    line = no_react_line(md)
    assert re.search(r"exit status \d+; last line: \S", line) or "not run" in line, line
    if shutil.which("node") and (CORE / "node_modules" / "rolldown").exists():
        assert "exit status 0; last line: PASS" in line, (
            "the real tree passes its own isolation check"
        )
    assert (
        "The Python tests are kept in the developer repository and are not part of this tree." in md
    )
    assert "OspreyFlow_Build" not in md and "OspreyFlow_Build" not in real.csv_bytes.decode()
    assert str(ROOT) not in md


def test_the_real_rules_file_and_output_name_no_client(real: Made) -> None:
    """The repository's client-name check over the rules file, the script and the real output (it hides names as
    hashes: this can only run it). Where the owner's local list is absent it says so and does not pass."""
    marketing = str(BUILD / "marketing_site")
    if marketing not in sys.path:
        sys.path.insert(0, marketing)
    import client_hashes
    from tools import client_name_check

    held = client_hashes.known()
    if held is None:
        pytest.skip(client_hashes.ABSENT)
    assert held, "client_names.local.sha256 holds no names"
    texts = {
        "rules": RULES.read_text(encoding="utf-8"),
        "script": SCRIPT.read_text(encoding="utf-8"),
        "csv": real.csv_bytes.decode("utf-8"),
        "summary": real.md,
    }
    for label, text in texts.items():
        assert client_name_check.client_lines(text, f"{label}.txt", held) == [], label
    for row in real.table:
        assert not client_name_check.path_names(row["path"], held), (
            "a path in the output names the client"
        )
