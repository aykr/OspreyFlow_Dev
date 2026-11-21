"""PL13b round 2: no input to the gateway image's install names the commercial package.

The gateway's Dockerfile installs LiteLLM with `uv pip install` and gives it requirement files:
`--constraint`, `--override`, and any `-r`. Round 1's pure guard (`tests/harness/
test_own_gateway_image.py`) read two of the three by a hand-written list. The third,
`publisher-resolution.txt`, is an `--override` file: one added line there
(`litellm-enterprise==0.1.65`) is a second override for the commercial package, and brings it back
into the install while every pure test stays green. Only the build-time licence gate in a real
`docker build` would have caught it.

**The invariant:** no file the install reads names `litellm-enterprise`, other than as the one
removal line (`litellm-enterprise ; python_version < "0"`), which an override takes as "never
install". **The test that fails if it is violated:**
`test_the_real_install_reads_no_input_that_names_the_commercial_package` (the real Dockerfile,
every file it names), and the plants below, each of which is red for the reason it claims.

**The list of files is derived, not written.** `install_inputs` reads the Dockerfile's own
`uv pip install` instructions (`--constraint`/`-c`, `--override`, `-r`/`--requirement`,
`--build-constraint`, in both `--flag value` and `--flag=value` forms, plus `UV_CONSTRAINT`,
`UV_BUILD_CONSTRAINT` and `UV_OVERRIDE` where the Dockerfile sets them), follows `-r`/`-c` lines
inside the files, and resolves each name through the Dockerfile's own `COPY` (a `COPY other.txt
./constraints.txt` makes the install read `other.txt`). A fourth file cannot be forgotten, a named
file that does not exist is a failure, and a file the install names but the Dockerfile never copies
in is a failure (the guard could not have read what the build reads).

**Folders it walks:** `OspreyFlow_Core/deploy/litellm/` only (the Dockerfile and what it names);
plants are made in a scratch copy of it under `tmp_path`.
"""

from __future__ import annotations

import re
import shlex
import shutil
from pathlib import Path

import pytest
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from tools.layout import CORE
from tools.licence_check import _instructions

FOLDER = CORE / "deploy" / "litellm"
PACKAGE = "litellm-enterprise"
#: The one thing an override may say about the package: never install it.
REMOVAL = 'python_version < "0"'
#: The options of `uv pip install` that take a requirements-shaped file, and the variables that
#: take the same.
FILE_OPTIONS = {
    "--constraint": "constraint", "--constraints": "constraint", "-c": "constraint",
    "--override": "override", "--overrides": "override",
    "--requirement": "requirement", "-r": "requirement",
    "--build-constraint": "constraint", "--build-constraints": "constraint", "-b": "constraint",
}  # fmt: skip
ENV_VARIABLES = re.compile(
    r"\bUV_(?:BUILD_)?(?:CONSTRAINT|OVERRIDE)\s*=\s*(\"[^\"]*\"|'[^']*'|\S+)"
)
#: What uv reads from the working directory with no flag at all.
IMPLICIT_FILES = {"uv.toml", "pyproject.toml", ".python-version"}


def _install_arguments(text: str) -> list[list[str]]:
    """The arguments of each `pip install` in the Dockerfile's `RUN`s, one list per install."""
    found = []
    for instruction in _instructions(text):
        if instruction.split(None, 1)[0].upper() != "RUN":
            continue
        for segment in re.split(r"&&|\|\||;", instruction):
            if not re.search(r"\bpip\s+install\b", segment):
                continue
            try:
                found.append(shlex.split(segment))
            except ValueError:
                found.append(segment.split())
    return found


def _named_in_install(arguments: list[str]) -> list[str]:
    names = []
    iterator = iter(arguments)
    for word in iterator:
        flag, equals, value = word.partition("=")
        if flag in FILE_OPTIONS:
            names.append(value if equals else next(iterator, ""))
    return [n for n in names if n]


def _copy_map(text: str) -> tuple[dict[str, str], bool]:
    """What each file the build context puts into the image is called there and where it came
    from: `({name in the image: name in the context}, the whole context was copied)`."""
    mapping: dict[str, str] = {}
    whole = False
    for instruction in _instructions(text):
        if instruction.split(None, 1)[0].upper() != "COPY":
            continue
        words = [w for w in instruction.split()[1:] if not w.startswith("--")]
        if any(w.startswith("--from=") for w in instruction.split()) or len(words) < 2:
            continue
        sources, destination = words[:-1], words[-1]
        if any(s.rstrip("/") in (".", "") for s in sources):
            whole = True
        if destination.endswith("/") or destination in (".", ".."):
            mapping.update({Path(s).name: s for s in sources})
        elif len(sources) == 1:
            mapping[Path(destination).name] = sources[0]
    return mapping, whole


def install_inputs(text: str, folder: Path) -> tuple[list[Path], list[str]]:
    """`(the files the install reads, why it could not say)`: every file the Dockerfile's install
    names, resolved through its `COPY`s, and the files those name in turn with `-r`/`-c`."""
    problems: list[str] = []
    installs = _install_arguments(text)
    if not installs:
        return [], ["the Dockerfile has no `pip install` step the guard can read"]
    names = [n for arguments in installs for n in _named_in_install(arguments)]
    names += [m.group(1).strip("\"'") for m in ENV_VARIABLES.finditer(text)]
    mapping, whole = _copy_map(text)
    for implicit in sorted(IMPLICIT_FILES & {Path(s).name for s in mapping.values()}):
        problems.append(f"copies {implicit} into the install's working folder, which uv reads")
    files: list[Path] = []
    queue = list(names)
    while queue:
        name = queue.pop(0)
        source = mapping.get(Path(name).name)
        if source is None and not whole:
            problems.append(f"the install names {name}, which the Dockerfile never copies in")
            continue
        path = folder / (source if source is not None else name)
        if not path.is_file():
            problems.append(f"the install names {name}, which does not exist ({path.name})")
            continue
        if path in files:
            continue
        files.append(path)
        for line in path.read_text(encoding="utf-8").splitlines():
            line = re.sub(r"(^|\s)#.*$", "", line).strip()
            match = re.match(r"(?:-r|--requirement|-c|--constraints?)(?:\s+|=)(\S+)", line)
            if match:
                queue.append(match.group(1))
    return files, problems


def _line_problem(line: str) -> str | None:
    """Why one requirement line brings the package, or None."""
    if not re.search(r"enterprise", line, re.I):
        return None
    try:
        requirement = Requirement(line)
    except InvalidRequirement:
        return "names the commercial package or its archive in a form that is not a requirement"
    removal = (
        canonicalize_name(requirement.name) == PACKAGE
        and not requirement.specifier
        and not requirement.extras
        and not requirement.url
        and requirement.marker is not None
        and str(requirement.marker) == REMOVAL
    )
    return None if removal else "asks for the commercial package, not for its removal"


def install_problems(text: str, folder: Path) -> list[str]:
    """Why an install could bring the commercial package in through a file it reads; empty when
    no file it reads names the package other than as an override's removal line, and an override
    does carry that line."""
    files, problems = install_inputs(text, folder)
    removals = 0
    for path in files:
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = re.sub(r"(^|\s)#.*$", "", raw).strip()
            if not line:
                continue
            problem = _line_problem(line)
            if problem:
                problems.append(f"{path.name}:{number} {problem}: {line!r}")
            elif re.search(r"enterprise", line, re.I):
                removals += 1
    if files and not removals:
        problems.append("no file the install reads carries the removal line")
    return problems


def _scratch(tmp_path: Path) -> Path:
    scratch = tmp_path / "litellm"
    shutil.copytree(FOLDER, scratch, ignore=shutil.ignore_patterns("__pycache__"))
    return scratch


def _real_dockerfile() -> str:
    return (FOLDER / "Dockerfile").read_text(encoding="utf-8")


REAL_FILES = [p.name for p in install_inputs(_real_dockerfile(), FOLDER)[0]]


def test_the_real_install_reads_no_input_that_names_the_commercial_package() -> None:
    assert install_problems(_real_dockerfile(), FOLDER) == []


def test_the_files_are_derived_from_the_dockerfile_and_there_are_three() -> None:
    """The three files round 1's hand-written list did not cover together: the derivation sees the
    override file that the guard missed."""
    assert sorted(REAL_FILES) == ["constraints.txt", "overrides.txt", "publisher-resolution.txt"]


#: The shapes the package can arrive in through a requirements file: a `pip freeze` line of the
#: pinned image's venv, a specifier, a bare name, the venv's direct URL (scout row 3), the archive
#: beside the folder, an override that asks for it with a marker that is true, and the removal
#: marker with a version added.
PLANTS = [
    "litellm-enterprise==0.1.65",
    "litellm-enterprise>=0.1",
    "litellm-enterprise",
    "litellm_enterprise==0.1.65",
    "litellm-enterprise @ file:///app/enterprise",
    "litellm_enterprise-0.1.65-py3-none-any.whl",
    'litellm-enterprise ; python_version >= "0"',
    'litellm-enterprise==0.1.65 ; python_version < "0"',
]
PLANT_IDS = ["freeze", "specifier", "bare", "underscore", "direct-url", "archive",
             "true-marker", "removal-with-version"]  # fmt: skip


@pytest.mark.parametrize("plant", PLANTS, ids=PLANT_IDS)
@pytest.mark.parametrize("name", REAL_FILES)
def test_the_package_planted_into_each_file_the_install_reads_is_refused(
    tmp_path: Path, name: str, plant: str
) -> None:
    folder = _scratch(tmp_path)
    assert install_problems(_real_dockerfile(), folder) == []
    with (folder / name).open("a", encoding="utf-8") as handle:
        handle.write(plant + "\n")
    problems = install_problems(_real_dockerfile(), folder)
    assert any(f"{name}:" in p for p in problems), problems


def test_the_removal_line_alone_is_not_a_fault(tmp_path: Path) -> None:
    """The plants are red for the package, not for an override file holding the removal line: the
    same line in the second override file is accepted."""
    folder = _scratch(tmp_path)
    with (folder / "publisher-resolution.txt").open("a", encoding="utf-8") as handle:
        handle.write('litellm-enterprise ; python_version < "0"\n')
    assert install_problems(_real_dockerfile(), folder) == []


def test_the_removal_line_taken_out_is_refused(tmp_path: Path) -> None:
    folder = _scratch(tmp_path)
    (folder / "overrides.txt").write_text("# nothing\n", encoding="utf-8")
    assert any("removal line" in p for p in install_problems(_real_dockerfile(), folder))


def test_a_comment_naming_the_package_is_not_a_fault(tmp_path: Path) -> None:
    folder = _scratch(tmp_path)
    with (folder / "constraints.txt").open("a", encoding="utf-8") as handle:
        handle.write("# litellm-enterprise is removed by overrides.txt\n")
    assert install_problems(_real_dockerfile(), folder) == []


def _with_install_input(text: str, flag: str, name: str) -> str:
    """The real Dockerfile with one more file named by its real `uv pip install` and copied in by
    its real `COPY`: the shape a fourth file would have."""
    planted = text.replace("--override overrides.txt", f"--override overrides.txt {flag} {name}")
    planted = planted.replace(
        "COPY constraints.txt overrides.txt publisher-resolution.txt ./",
        f"COPY constraints.txt overrides.txt publisher-resolution.txt {name} ./",
    )
    assert planted != text
    return planted


@pytest.mark.parametrize(
    "flag", ["--constraint", "-c", "--override", "-r", "--requirement", "--constraint="]
)
def test_a_fourth_file_the_dockerfile_newly_names_is_read(tmp_path: Path, flag: str) -> None:
    folder = _scratch(tmp_path)
    text = _with_install_input(_real_dockerfile(), flag, "extra.txt")
    if flag.endswith("="):
        text = text.replace("--constraint= extra.txt", "--constraint=extra.txt")
    (folder / "extra.txt").write_text("fastapi>=0.1\n", encoding="utf-8")
    assert install_problems(text, folder) == []  # it is read, and clean: the plumbing works
    (folder / "extra.txt").write_text("litellm-enterprise==0.1.65\n", encoding="utf-8")
    problems = install_problems(text, folder)
    assert any("extra.txt:1" in p for p in problems), problems


def test_a_file_named_by_a_requirements_line_inside_another_is_read(tmp_path: Path) -> None:
    folder = _scratch(tmp_path)
    text = _real_dockerfile().replace(
        "COPY constraints.txt overrides.txt publisher-resolution.txt ./",
        "COPY constraints.txt overrides.txt publisher-resolution.txt more.txt ./",
    )
    assert text != _real_dockerfile()
    with (folder / "publisher-resolution.txt").open("a", encoding="utf-8") as handle:
        handle.write("-r more.txt\n")
    (folder / "more.txt").write_text("litellm-enterprise==0.1.65\n", encoding="utf-8")
    problems = install_problems(text, folder)
    assert any("more.txt:1" in p for p in problems), problems


def test_a_file_renamed_by_the_copy_is_read_under_its_source_name(tmp_path: Path) -> None:
    """`COPY other.txt ./constraints.txt`: the install reads what `other.txt` holds, and a guard
    that opened `constraints.txt` in the folder would read the innocent file."""
    folder = _scratch(tmp_path)
    text = _real_dockerfile().replace(
        "COPY constraints.txt overrides.txt publisher-resolution.txt ./",
        "COPY other.txt ./constraints.txt\nCOPY overrides.txt publisher-resolution.txt ./",
    )
    assert text != _real_dockerfile()
    shutil.copy(folder / "constraints.txt", folder / "other.txt")
    assert install_problems(text, folder) == []
    with (folder / "other.txt").open("a", encoding="utf-8") as handle:
        handle.write("litellm-enterprise==0.1.65\n")
    problems = install_problems(text, folder)
    assert any("other.txt:" in p for p in problems), problems


def test_a_file_named_by_an_environment_variable_is_read(tmp_path: Path) -> None:
    folder = _scratch(tmp_path)
    text = _real_dockerfile().replace(
        "ENV UV_LINK_MODE=copy", "ENV UV_OVERRIDE=more.txt UV_LINK_MODE=copy"
    )
    text = text.replace(
        "COPY constraints.txt overrides.txt publisher-resolution.txt ./",
        "COPY constraints.txt overrides.txt publisher-resolution.txt more.txt ./",
    )
    assert text != _real_dockerfile()
    (folder / "more.txt").write_text("litellm-enterprise==0.1.65\n", encoding="utf-8")
    assert any("more.txt:1" in p for p in install_problems(text, folder))


def test_a_file_the_dockerfile_names_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    folder = _scratch(tmp_path)
    text = _with_install_input(_real_dockerfile(), "--override", "ghost.txt")
    problems = install_problems(text, folder)
    assert any("ghost.txt" in p and "does not exist" in p for p in problems), problems


def test_a_file_the_install_names_but_the_dockerfile_never_copies_is_refused(
    tmp_path: Path,
) -> None:
    folder = _scratch(tmp_path)
    text = _real_dockerfile().replace(
        "--override overrides.txt", "--override overrides.txt --override loose.txt"
    )
    (folder / "loose.txt").write_text("litellm-enterprise==0.1.65\n", encoding="utf-8")
    problems = install_problems(text, folder)
    assert any("loose.txt" in p and "never copies" in p for p in problems), problems


@pytest.mark.parametrize("name", ["uv.toml", "pyproject.toml"])
def test_a_config_file_uv_reads_without_a_flag_is_refused(tmp_path: Path, name: str) -> None:
    folder = _scratch(tmp_path)
    text = _real_dockerfile().replace(
        "COPY constraints.txt overrides.txt publisher-resolution.txt ./",
        f"COPY constraints.txt overrides.txt publisher-resolution.txt {name} ./",
    )
    (folder / name).write_text('override-dependencies = ["litellm-enterprise"]\n', encoding="utf-8")
    assert any(name in p for p in install_problems(text, folder))


def test_a_dockerfile_with_no_install_is_refused(tmp_path: Path) -> None:
    text = re.sub(r"(?m)^RUN uv venv.*\n(?:\s+.*\n)+", "", _real_dockerfile())
    assert text != _real_dockerfile()
    assert any("no `pip install` step" in p for p in install_problems(text, _scratch(tmp_path)))
