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

**Round 3 (the install steps).** Reading the files was not enough: a second install of LiteLLM
(`uv pip install "litellm[proxy]"`, no version, no override) reads no new file and brings the
package back through the `proxy` extra. So every package-installing step (INSTALL_COMMAND: `pip`,
`pip3`, `python -m pip`, `uv pip install`/`sync`, `uv sync`/`add`, `uv tool install`, in shell or
exec form) must take an override file that carries the removal line (by `--override`,
`UV_OVERRIDE=` in front of it, or its own stage's `ENV UV_OVERRIDE`), a `uv pip sync` names its
files positionally (read like `-r`), and LiteLLM is installed in one step. **The tests that
fail:** the
`test_a_second_install_*`, `test_a_file_an_install_of_any_spelling_*` and
`test_an_install_whose_override_*` cases; shown red by disabling `_install_step_problems` (19 red)
and by narrowing INSTALL_COMMAND back to `pip install` (8 red).

**Folders it walks:** `OspreyFlow_Core/deploy/litellm/` only (the Dockerfile and what it names);
plants are made in a scratch copy of it under `tmp_path`.
"""

from __future__ import annotations

import json
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
    r"\b(UV_(?:BUILD_)?(?:CONSTRAINT|OVERRIDE))\s*=\s*(\"[^\"]*\"|'[^']*'|\S+)"
)
#: The tools whose subcommands put packages in, in every spelling the guard knows: `pip install`,
#: `pip3 install`, `python -m pip install`, `uv pip install`, `uv pip sync`, `uv sync`, `uv add`,
#: `uv tool install`, `pipx install`, `poetry install`. A shape missing here is a shape no guard
#: reads, so the list is wide and a step it names without a file the guard can read is refused.
INSTALL_COMMAND = re.compile(
    r"\b(?:pip3?|pipx|poetry)\s+(?:install|add)\b"
    r"|\buv\s+(?:pip\s+(?:install|sync)|sync|add|tool\s+install)\b"
    r"|\bpip3?\s+sync\b"
)
#: The options of an install that take a value which is not a file, so `uv pip sync` can tell its
#: positional requirements files from an option's value.
VALUE_OPTIONS = {
    "--python", "-p", "--target", "--prefix", "--index-url", "-i", "--extra-index-url", "--index",
    "--default-index", "-f", "--find-links", "--python-version", "--python-platform",
    "--index-strategy", "--keyring-provider", "--config-file", "--exclude-newer", "--cache-dir",
    "--link-mode", "--reinstall-package", "-P", "--upgrade-package", "--no-binary",
    "--only-binary", "--resolution", "--prerelease", "-C", "--config-setting", "--extra",
    "--group", "--color", "--directory", "--project", "--allow-insecure-host",
}  # fmt: skip
#: A requirement that asks for LiteLLM itself, with or without extras and a version (searched in the
#: step's whole text, so `litellm [proxy] >= 1` is found); a path or a longer name is not.
LITELLM_WORD = re.compile(r"(?<![\w./-])litellm(?![\w-])", re.I)
#: What uv reads from the working directory with no flag at all.
IMPLICIT_FILES = {"uv.toml", "pyproject.toml", ".python-version"}


def _instruction_body(instruction: str) -> str | None:
    """The command of a `RUN`, in shell form or in exec form (`RUN ["uv", "pip", "install"]`)."""
    word, _, rest = instruction.partition(" ")
    if word.upper() != "RUN":
        return None
    rest = rest.strip()
    if rest.startswith("["):
        try:
            parts = json.loads(rest)
        except ValueError:
            return rest
        if isinstance(parts, list):
            return " ".join(str(part) for part in parts)
    return rest


def _installs(text: str) -> list[tuple[list[str], list[str]]]:
    """Each package-installing step of the Dockerfile's `RUN`s: `(its arguments, the override files
    its stage's own `ENV UV_OVERRIDE=` names before it)`. Not only `pip install`: `pip3 install`,
    `uv pip sync`, `uv sync` and the others of INSTALL_COMMAND."""
    found = []
    env_overrides: list[str] = []
    for instruction in _instructions(text):
        word = instruction.split(None, 1)[0].upper()
        if word == "FROM":
            env_overrides = []
        elif word == "ENV":
            env_overrides += [
                m.group(2).strip("\"'")
                for m in ENV_VARIABLES.finditer(instruction)
                if m.group(1).endswith("OVERRIDE")
            ]
        body = _instruction_body(instruction)
        if body is None:
            continue
        for segment in re.split(r"&&|\|\||;|\n", body):
            if not INSTALL_COMMAND.search(segment):
                continue
            try:
                arguments = shlex.split(segment)
            except ValueError:
                arguments = segment.split()
            found.append((arguments, list(env_overrides)))
    return found


def _install_arguments(text: str) -> list[list[str]]:
    """The arguments of each package-installing step in the Dockerfile's `RUN`s."""
    return [arguments for arguments, _ in _installs(text)]


def _sync_files(arguments: list[str]) -> list[str]:
    """`uv pip sync a.txt b.txt`: the positional words after `sync` are requirements files."""
    if "sync" not in arguments:
        return []
    names = []
    iterator = iter(arguments[arguments.index("sync") + 1 :])
    for word in iterator:
        if word in VALUE_OPTIONS or word in FILE_OPTIONS:
            next(iterator, None)
        elif not word.startswith("-") and "=" not in word:
            names.append(word)
    return names


def _named_in_install(arguments: list[str], kind: str | None = None) -> list[str]:
    """The files one install names, of one kind (`override`, `constraint`, `requirement`) or all.
    Every spelling: `--flag file`, `--flag=file`, `-rfile`, `UV_OVERRIDE=file uv pip install` and a
    sync's positional files (which are requirements)."""
    names = []
    iterator = iter(arguments)
    for word in iterator:
        flag, equals, value = word.partition("=")
        if flag in FILE_OPTIONS:
            name = value if equals else next(iterator, "")
            if kind in (None, FILE_OPTIONS[flag]):
                names.append(name)
        elif re.fullmatch(r"-[rcb].+", word) and not word.startswith("--"):
            if kind in (None, FILE_OPTIONS[word[:2]]):
                names.append(word[2:])
        else:
            match = ENV_VARIABLES.fullmatch(word)
            if match and kind in (
                None,
                "override" if match.group(1).endswith("OVERRIDE") else "constraint",
            ):
                names.append(match.group(2).strip("\"'"))
    if kind in (None, "requirement"):
        names += _sync_files(arguments)
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
    names += [m.group(2).strip("\"'") for m in ENV_VARIABLES.finditer(text)]
    names = list(dict.fromkeys(names))
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


def _resolve(name: str, text: str, folder: Path) -> Path | None:
    mapping, whole = _copy_map(text)
    source = mapping.get(Path(name).name)
    if source is None and not whole:
        return None
    path = folder / (source if source is not None else name)
    return path if path.is_file() else None


def _carries_removal(path: Path) -> bool:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"(^|\s)#.*$", "", raw).strip()
        if re.search(r"enterprise", line, re.I) and _line_problem(line) is None:
            return True
    return False


def _install_step_problems(text: str, folder: Path) -> list[str]:
    """The steps that could bring the commercial package in even with every file clean: any
    install that does not take an override file carrying the removal line (the `proxy` extra
    brings the package whenever the override is absent), and a second install of LiteLLM itself."""
    problems = []
    litellm_installs = 0
    for number, (arguments, env_overrides) in enumerate(_installs(text), 1):
        shown = " ".join(arguments)[:80]
        overrides = _named_in_install(arguments, "override") + env_overrides
        paths = [p for n in overrides if (p := _resolve(n, text, folder)) is not None]
        if not overrides:
            problems.append(f"install {number} ({shown!r}) takes no override file")
        elif not any(_carries_removal(p) for p in paths):
            problems.append(
                f"install {number} ({shown!r}) takes no override carrying the removal line"
            )
        if LITELLM_WORD.search(" ".join(arguments)):
            litellm_installs += 1
    if litellm_installs > 1:
        problems.append(f"installs litellm in {litellm_installs} steps, not one")
    return problems


def install_problems(text: str, folder: Path) -> list[str]:
    """Why an install could bring the commercial package in: through a file it reads (none may
    name the package other than as an override's removal line, and an override does carry that
    line), or through a step that takes no such override. Empty when it cannot."""
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
    return [*problems, *_install_step_problems(text, folder)]


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


# --- round 3: a second install step, and the spellings of an install the guard did not know ------

#: Where a plant goes: the builder stage, after the real install and before the entrypoint scripts.
ANCHOR = "COPY docker/ /app/docker/"
PY = "--python /app/.venv/bin/python"


def _with_step(text: str, *lines: str) -> str:
    planted = text.replace(ANCHOR, "\n".join([*lines, ANCHOR]), 1)
    assert planted != text
    return planted


@pytest.mark.parametrize(
    "step",
    [
        # The round-2 verifier's plant, in the shape the Dockerfile uses: the `proxy` extra with no
        # version, no override, no constraint.
        f'RUN uv pip install {PY} "litellm[proxy]"',
        f"RUN uv pip install {PY} litellm[proxy]==1.101.0",
        'RUN pip3 install "litellm[proxy]"',
        'RUN python -m pip install "litellm[proxy]"',
        f'RUN uv pip install {PY} "litellm [proxy] >= 1"',
        'RUN ["uv", "pip", "install", "litellm[proxy]"]',
        f'RUN echo ok && uv pip install {PY} "litellm[proxy]"',
        f'RUN uv pip install {PY} "litellm @ git+https://example.invalid/litellm.git"',
    ],
    ids=["no-version", "with-version", "pip3", "python-m-pip", "spaced-specifier", "exec-form",
         "after-and", "direct-url"],
)  # fmt: skip
def test_a_second_install_of_litellm_without_the_override_is_refused(
    tmp_path: Path, step: str
) -> None:
    folder = _scratch(tmp_path)
    assert install_problems(_real_dockerfile(), folder) == []
    problems = install_problems(_with_step(_real_dockerfile(), step), folder)
    assert any("takes no override file" in p for p in problems), problems
    assert any("installs litellm in 2 steps" in p for p in problems), problems


def test_a_second_install_of_litellm_that_takes_the_override_is_still_a_second_install(
    tmp_path: Path,
) -> None:
    """The override keeps the package out, but the guard holds LiteLLM to the one step the
    Dockerfile's own checks are written for; the two reasons are separate."""
    folder = _scratch(tmp_path)
    step = f'RUN uv pip install {PY} --override overrides.txt "litellm[proxy]"'
    problems = install_problems(_with_step(_real_dockerfile(), step), folder)
    assert problems == ["installs litellm in 2 steps, not one"], problems


@pytest.mark.parametrize(
    ("step", "name"),
    [
        ("RUN pip3 install -r extra.txt", "extra.txt"),
        ("RUN pip3 install -rextra.txt", "extra.txt"),
        ("RUN pip install --requirement=extra.txt", "extra.txt"),
        ("RUN uv pip sync extra.txt", "extra.txt"),
        (f"RUN uv pip sync {PY} extra.txt", "extra.txt"),
        (f"RUN uv pip sync {PY} --constraint constraints.txt extra.txt", "extra.txt"),
        ('RUN ["uv", "pip", "sync", "extra.txt"]', "extra.txt"),
        ("RUN UV_CONSTRAINT=extra.txt uv pip install fastapi", "extra.txt"),
    ],
    ids=["pip3-r", "pip3-attached", "pip-equals", "sync", "sync-python", "sync-constraint",
         "sync-exec", "inline-env"],
)  # fmt: skip
def test_a_file_an_install_of_any_spelling_names_is_read(
    tmp_path: Path, step: str, name: str
) -> None:
    """A COPYed `extra.txt` naming the package, installed with a spelling the first guard's
    `pip install` pattern missed: both the file and the missing override are reported."""
    folder = _scratch(tmp_path)
    text = _with_step(_real_dockerfile(), "COPY extra.txt ./", step)
    (folder / "extra.txt").write_text("fastapi>=0.1\n", encoding="utf-8")
    clean = install_problems(text, folder)
    assert not any("extra.txt:" in p for p in clean), clean  # read, and clean
    (folder / "extra.txt").write_text("litellm-enterprise==0.1.65\n", encoding="utf-8")
    problems = install_problems(text, folder)
    assert any("extra.txt:1" in p for p in problems), problems
    assert any("takes no override file" in p for p in problems), problems


def test_a_sync_naming_a_file_the_dockerfile_never_copies_is_refused(tmp_path: Path) -> None:
    folder = _scratch(tmp_path)
    (folder / "extra.txt").write_text("litellm-enterprise==0.1.65\n", encoding="utf-8")
    problems = install_problems(_with_step(_real_dockerfile(), "RUN uv pip sync extra.txt"), folder)
    assert any("extra.txt" in p and "never copies" in p for p in problems), problems


def test_an_install_whose_override_file_lacks_the_removal_line_is_refused(tmp_path: Path) -> None:
    folder = _scratch(tmp_path)
    (folder / "inert.txt").write_text("fastapi==0.1\n", encoding="utf-8")
    text = _with_step(
        _real_dockerfile(),
        "COPY inert.txt ./",
        f"RUN uv pip install {PY} --override inert.txt fastapi",
    )
    problems = install_problems(text, folder)
    assert any("no override carrying the removal line" in p for p in problems), problems


def test_a_second_install_that_takes_the_override_and_asks_for_something_else_is_fine(
    tmp_path: Path,
) -> None:
    """The red cases above are for the reason they claim: a step that takes the override and does
    not install LiteLLM is accepted."""
    folder = _scratch(tmp_path)
    text = _with_step(
        _real_dockerfile(), f"RUN uv pip install {PY} --override overrides.txt fastapi==0.1"
    )
    assert install_problems(text, folder) == []


def test_an_override_named_by_the_stages_own_environment_covers_an_install_after_it(
    tmp_path: Path,
) -> None:
    folder = _scratch(tmp_path)
    text = _with_step(
        _real_dockerfile(), "ENV UV_OVERRIDE=overrides.txt", f"RUN uv pip install {PY} fastapi==0.1"
    )
    assert install_problems(text, folder) == []


def test_an_override_set_in_another_stage_does_not_cover_an_install_in_this_one(
    tmp_path: Path,
) -> None:
    """`ENV UV_OVERRIDE` in the builder is not in the final stage's environment."""
    folder = _scratch(tmp_path)
    text = _with_step(_real_dockerfile(), "ENV UV_OVERRIDE=overrides.txt")
    text += f'\nRUN uv pip install {PY} "litellm[proxy]"\n'
    problems = install_problems(text, folder)
    assert any("takes no override file" in p for p in problems), problems
