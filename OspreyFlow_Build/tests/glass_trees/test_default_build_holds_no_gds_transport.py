"""Slice PL7c, item 3 and item 5: a default build of the workspace holds no GDS Transport file, and the register's
claim that it ships "only when appearance.govuk_identity is on" holds (ADR-152 decision 14, invariant I9; the owner's
ruling of 21 November 2026: the face's files leave the default build and are added only for a deployment with the
GOV.UK identity switched on; not a sovereignty gap).

**What is read, and why it is not a full `vite build`.** The workspace's `dev` and `build` scripts run
`scripts/sync_govuk_assets.mjs` first; it writes the GOV.UK Frontend fonts, images and stylesheet into
`apps/workspace/public/assets/govuk/`, and Vite copies everything under `public/` into `dist/` byte for byte, keeping the
path (`scripts/dist_compare.mjs` says the same about `assets/govuk/`). Nothing else in the workspace's build writes a file
under that folder (`test_nothing_else_in_the_build_writes_govuk_files` reads `vite.config.ts` and the manifest for it). So
the build's declared output for this face is exactly what the sync step leaves in `public/`: this test runs that step, with
`node`, in a scratch copy of the workspace folder, once with the switch off (nothing set: the default) and once with it
on, and reads every file it wrote. That is the same bytes a `dist/` would hold, in seconds and with no browser bundle in
the way. (A real `vite build` was run by hand for the report's before-and-after lists.)

**What fails a default build.** Any file whose content hash is one of the four faces in the installed `govuk-frontend`
(so a renamed copy is found), any file under `assets/govuk/fonts/`, any font-file name in the package's `<stem>-<hash>-v2`
shape, any text file that names the family `GDS Transport`, declares an `@font-face`, or refers to `govuk-crest` (the
crown image). With the switch on the same reading must find all four faces, the `@font-face` rules and the crest, so the
check cannot pass by the build producing nothing; and the default's stylesheet must still hold the GOV.UK Frontend rules
(`.govuk-header`), balanced, so a default build is a working fallback and not an empty file.

**Rule 15, the planted faults, at the shape the build writes.** `test_sync_made_unconditional_is_red`: the real
`sync_govuk_assets.mjs` with its `identityOn` made to return `true` (the script as it was before this slice, in effect:
it ran for every build), run with the switch off: the faces appear and the check names them. `test_a_renamed_face_is_found_by_its_hash`,
`test_the_build_script_forcing_the_switch_is_refused`, `test_a_dockerfile_defaulting_the_switch_on_is_refused` and
`test_a_renderer_passing_the_argument_when_the_switch_is_off_is_refused` plant the other ways it could come back, each in the
real file's own text or the renderer's own output.

**The folders this test walks** (the conductor's scan-map row, kept): under `OspreyFlow_Core`, `apps/workspace/`
(`package.json`, `Dockerfile`, `vite.config.ts` and `scripts/sync_govuk_assets.mjs` by name; the scratch copy it makes
holds only the script), `packages/design/fonts.json`, `harness/render.py` (called, not walked) and the installed
`node_modules/govuk-frontend` faces. It never writes into the repository. Under `OspreyFlow_Build`: `spec/LICENCE_REGISTER.yaml`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from schemas.deployment import OspreyConfig
from tools.layout import CORE
from tools.licence_check import _instructions

from harness.render import compose_services, service_images

APP = CORE / "apps" / "workspace"
SCRIPT = APP / "scripts" / "sync_govuk_assets.mjs"
PACKAGE_JSON = APP / "package.json"
DOCKERFILE = APP / "Dockerfile"
VITE_CONFIG = APP / "vite.config.ts"
FONTS_LIST = CORE / "packages" / "design" / "fonts.json"
GOVUK_FRONTEND = CORE / "node_modules" / "govuk-frontend" / "dist" / "govuk" / "assets"
NODE = shutil.which("node")
SWITCH = "OSPREY_GOVUK_IDENTITY"

#: The package's own file names for the faces: `bold-b542beb274-v2.woff2`, `light-94a07e06a1-v2.woff`.
FACE_NAME = re.compile(r"^(bold|light)-[0-9a-f]{10}-v\d+\.(woff2?|ttf|otf|eot)$")
TEXT_SUFFIXES = {".css", ".js", ".mjs", ".html", ".json", ".svg", ".txt", ".map"}


# ------------------------------------------------------------------------------------- the reference: the real faces


def real_faces() -> dict[str, str]:
    """`{file name: sha256}` for the faces in the installed `govuk-frontend` (the content the check matches by)."""
    folder = GOVUK_FRONTEND / "fonts"
    assert folder.is_dir(), "govuk-frontend is not installed: run `npm ci`"
    found = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}
    assert len(found) == 4, found  # bold and light, each woff and woff2 (6.6.0)
    return found


# --------------------------------------------------------------- the check a default build's output must pass


def default_build_problems(files: dict[str, bytes], faces: dict[str, str]) -> list[str]:
    """What is wrong with the output of a default build: `files` is `{path under public/: bytes}`. Empty when it holds no
    GDS Transport face, no rule that declares or names it, and no crown image."""
    hashes = set(faces.values())
    out: list[str] = []
    for rel, data in sorted(files.items()):
        base = rel.rsplit("/", 1)[-1]
        if hashlib.sha256(data).hexdigest() in hashes:
            out.append(f"{rel}: its content is a GDS Transport face (by hash)")
        elif FACE_NAME.match(base) or "govuk/fonts/" in "/" + rel:
            out.append(f"{rel}: a GDS Transport face file (by name or folder)")
        if Path(rel).suffix in TEXT_SUFFIXES:
            text = data.decode("utf-8", "replace")
            if "GDS Transport" in text:
                out.append(f"{rel}: names the family GDS Transport")
            if "@font-face" in text:
                out.append(f"{rel}: declares an @font-face")
            if "govuk-crest" in text or base == "govuk-crest.svg":
                out.append(f"{rel}: names the crown image")
        elif base == "govuk-crest.svg":
            out.append(f"{rel}: the crown image")
    return out


# --------------------------------------------------------------------------------- running the build's sync step


def run_sync(
    scratch: Path, *, switch: str | None = None, script: str | None = None, stale: bool = False
) -> dict[str, bytes]:
    """Runs the workspace's sync step in a scratch copy of its folder (only the script, and `node_modules` linked so the
    package resolves as it does in the checkout) with the switch as given (`None`: not set, the default), and returns every
    file it wrote under `public/`, `{path relative to public/: bytes}`."""
    assert NODE, "node is needed to run the sync step"
    app = scratch / "apps" / "workspace"
    (app / "scripts").mkdir(parents=True)
    (app / "scripts" / SCRIPT.name).write_text(script if script is not None else SCRIPT.read_text("utf-8"), "utf-8")
    (scratch / "node_modules").symlink_to(CORE / "node_modules")
    if stale:  # what an earlier build with the switch on would have left behind
        old = app / "public" / "assets" / "govuk" / "fonts"
        old.mkdir(parents=True)
        (old / "bold-b542beb274-v2.woff2").write_bytes(b"wOF2 an earlier build")
    env = {k: v for k, v in os.environ.items() if k != SWITCH}
    if switch is not None:
        env[SWITCH] = switch
    done = subprocess.run(  # noqa: S603
        [NODE, str(Path("scripts") / SCRIPT.name)], cwd=app, env=env, capture_output=True, text=True, timeout=120, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr
    public = app / "public"
    return {p.relative_to(public).as_posix(): p.read_bytes() for p in sorted(public.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def faces() -> dict[str, str]:
    return real_faces()


@pytest.fixture(scope="module")
def default_output(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    return run_sync(tmp_path_factory.mktemp("default"))


@pytest.fixture(scope="module")
def identity_output(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    return run_sync(tmp_path_factory.mktemp("identity"), switch="1")


# --------------------------------------------------------------------------------------- item 3: the default build


def test_a_default_build_holds_no_gds_transport_file(default_output: dict[str, bytes], faces: dict[str, str]) -> None:
    assert default_build_problems(default_output, faces) == []


def test_a_default_build_still_holds_the_fallback_stylesheet(default_output: dict[str, bytes]) -> None:
    """The GOV.UK look with the switch off is a fallback, not a broken request: the stylesheet is there, whole, with the
    face's rules taken out (the page then draws in the fallback stack: ADR-152 decision 14)."""
    css = default_output["assets/govuk/govuk-frontend.css"].decode("utf-8")
    assert ".govuk-header" in css and ".govuk-footer" in css and ".govuk-phase-banner" in css
    assert css.count("{") == css.count("}")
    # No request for a file the build does not hold: every url() the stylesheet carries points at a file in the output.
    for ref in re.findall(r"url\(([^)]+)\)", css):
        assert ref.strip("\"'").lstrip("/") in default_output, ref


def test_the_switch_on_holds_the_faces_so_the_check_cannot_pass_by_producing_nothing(
    identity_output: dict[str, bytes], faces: dict[str, str]
) -> None:
    held = {Path(rel).name: hashlib.sha256(data).hexdigest() for rel, data in identity_output.items() if "fonts/" in rel}
    assert held == faces
    problems = default_build_problems(identity_output, faces)
    assert len([p for p in problems if "(by hash)" in p]) == 4
    assert any("declares an @font-face" in p for p in problems)
    assert any("names the family GDS Transport" in p for p in problems)
    assert any("govuk-crest" in p or "crown image" in p for p in problems)
    # And with it on the stylesheet's own urls all resolve, the crest included.
    css = identity_output["assets/govuk/govuk-frontend.css"].decode("utf-8")
    for ref in re.findall(r"url\(([^)]+)\)", css):
        assert ref.strip("\"'").lstrip("/") in identity_output, ref


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", " "])
def test_only_a_yes_turns_the_switch_on(tmp_path: Path, faces: dict[str, str], value: str) -> None:
    assert default_build_problems(run_sync(tmp_path, switch=value), faces) == []


@pytest.mark.parametrize("value", ["1", "true", "TRUE"])
def test_the_switch_on_spellings(tmp_path: Path, faces: dict[str, str], value: str) -> None:
    assert default_build_problems(run_sync(tmp_path, switch=value), faces) != []


def test_a_switch_turned_off_clears_what_an_earlier_build_left(tmp_path: Path, faces: dict[str, str]) -> None:
    """A developer who built with the switch on and then without must not keep the faces in `public/`: the step removes
    the folder first, whichever way it runs."""
    assert default_build_problems(run_sync(tmp_path, stale=True), faces) == []


# ------------------------------------------------------------ rule 15: each way the face could come back, planted


def _unconditional(script: str) -> str:
    """The real script with `identityOn` made to answer yes whatever is set: the way it ran before this slice."""
    planted, n = re.subn(r"export function identityOn\([^)]*\) \{.*?\n\}\n", "export function identityOn() { return true; }\n", script, flags=re.S)
    assert n == 1, "the script has no `identityOn` function the plant can replace: update this test with the script"
    return planted


def test_sync_made_unconditional_is_red(tmp_path: Path, faces: dict[str, str]) -> None:
    files = run_sync(tmp_path, script=_unconditional(SCRIPT.read_text("utf-8")))  # the switch is NOT set
    problems = default_build_problems(files, faces)
    assert len([p for p in problems if "(by hash)" in p]) == 4, problems
    assert any("declares an @font-face" in p for p in problems)


def test_a_renamed_face_is_found_by_its_hash(faces: dict[str, str]) -> None:
    name, _ = next(iter(sorted(faces.items())))
    data = (GOVUK_FRONTEND / "fonts" / name).read_bytes()
    problems = default_build_problems({"assets/fonts/inter-latin-400-normal.woff2": data}, faces)
    assert problems == ["assets/fonts/inter-latin-400-normal.woff2: its content is a GDS Transport face (by hash)"]


def test_a_face_named_in_the_packages_shape_is_found_by_name_alone(faces: dict[str, str]) -> None:
    problems = default_build_problems({"assets/x/bold-b542beb274-v2.woff2": b"wOF2 not the face"}, faces)
    assert problems == ["assets/x/bold-b542beb274-v2.woff2: a GDS Transport face file (by name or folder)"]


def test_a_near_miss_is_not_a_fault(faces: dict[str, str]) -> None:
    """A different face, a different crest-less file and the word `govuk` alone are not GDS Transport."""
    files = {
        "assets/fonts/atkinson-hyperlegible-next-latin-400-normal.woff2": b"wOF2 an OFL face",
        "assets/govuk/govuk-frontend.css": b".govuk-header{font-family:arial,sans-serif}",
    }
    assert default_build_problems(files, faces) == []


def _package_scripts() -> dict[str, str]:
    return json.loads(PACKAGE_JSON.read_text("utf-8"))["scripts"]


def build_script_problems(scripts: dict[str, str]) -> list[str]:
    """`dev` and `build` must run the sync step and must not set the switch themselves: it comes from the deployment."""
    out = []
    for name in ("dev", "build"):
        line = scripts.get(name, "")
        if "sync_govuk_assets.mjs" not in line:
            out.append(f"`{name}` does not run the sync step, so a deployment with the switch on would get no stylesheet")
        if SWITCH in line:
            out.append(f"`{name}` sets {SWITCH} itself: the switch would be on for every build")
    return out


def test_the_build_scripts_leave_the_switch_to_the_deployment() -> None:
    assert build_script_problems(_package_scripts()) == []


def test_the_build_script_forcing_the_switch_is_refused() -> None:
    scripts = dict(_package_scripts())
    scripts["build"] = scripts["build"].replace("node scripts/", f"{SWITCH}=1 node scripts/", 1)
    assert any("sets OSPREY_GOVUK_IDENTITY itself" in p for p in build_script_problems(scripts))


def dockerfile_problems(dockerfile: str) -> list[str]:
    """The builder stage takes the switch as an `ARG` whose default is empty, and passes it to the build as an `ENV`."""
    stage = ""
    arg = env = False
    out: list[str] = []
    for instruction in _instructions(dockerfile):
        word, _, rest = instruction.partition(" ")
        if word.upper() == "FROM":
            stage = rest.lower().split()[-1]
        elif stage == "builder" and word.upper() == "ARG" and rest.split("=")[0].strip() == SWITCH:
            arg = True
            default = rest.partition("=")[2].strip().strip("\"'")
            if default != "":
                out.append(f"`ARG {SWITCH}` defaults to {default!r}: the default image would be a switch-on build")
        elif stage == "builder" and word.upper() == "ENV" and re.search(rf"{SWITCH}[= ]\$\{{?{SWITCH}\}}?", rest):
            env = True
        elif stage == "builder" and word.upper() == "RUN" and "npm run build" in rest and not (arg and env):
            out.append("the build runs before the switch is passed to it (an ARG and an ENV from it)")
    if not arg:
        out.append(f"the builder stage has no `ARG {SWITCH}`")
    # Nothing of GOV.UK Frontend is copied into the image by name: the build step is the only way it gets there.
    for instruction in _instructions(dockerfile):
        if instruction.upper().startswith("COPY") and "govuk" in instruction.lower():
            out.append(f"a COPY names GOV.UK files directly: {instruction}")
    return out


def test_the_image_takes_the_switch_as_a_build_argument_defaulting_to_off() -> None:
    assert dockerfile_problems(DOCKERFILE.read_text("utf-8")) == []


def test_a_dockerfile_defaulting_the_switch_on_is_refused() -> None:
    real = DOCKERFILE.read_text("utf-8")
    planted = real.replace(f"ARG {SWITCH}=\n", f"ARG {SWITCH}=1\n")
    assert planted != real, "the Dockerfile has no `ARG OSPREY_GOVUK_IDENTITY=` line to plant in"
    assert any("defaults to '1'" in p for p in dockerfile_problems(planted))


def test_a_dockerfile_that_never_passes_the_switch_on_is_refused() -> None:
    real = DOCKERFILE.read_text("utf-8")
    planted = re.sub(rf"^ENV {SWITCH}=.*\n", "", real, flags=re.M)
    assert planted != real
    assert any("before the switch is passed" in p for p in dockerfile_problems(planted))


# ---------------------------------------------------------------------- the renderer passes the argument on, when on


def _workspace_build(appearance: dict[str, object]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """The workspace's compose `build` stanza and every service's, as the renderer writes them for this appearance."""
    config = OspreyConfig.model_validate({"components": {"source_path": "."}, "appearance": appearance})
    services = compose_services(config, service_images(config, build_context="../../.."))
    return services["workspace"]["build"], {n: s.get("build", {}) for n, s in services.items()}


def render_problems(workspace_build: dict[str, Any], every_build: dict[str, dict[str, Any]], *, on: bool) -> list[str]:
    out = []
    args = workspace_build.get("args")
    if on and args != {SWITCH: "1"}:
        out.append(f"the switch is on and the workspace's build arguments are {args!r}, not {{{SWITCH!r}: '1'}}")
    if not on and "args" in workspace_build:
        out.append(f"the switch is off and the workspace's build still carries arguments: {args!r}")
    for name, build in every_build.items():
        if name != "workspace" and SWITCH in build.get("args", {}):
            out.append(f"{name} is given the switch")
    return out


def test_the_renderer_passes_the_argument_only_when_the_switch_is_on() -> None:
    off, off_all = _workspace_build({"brand": "govuk"})
    assert render_problems(off, off_all, on=False) == []
    on, on_all = _workspace_build({"brand": "govuk", "govuk_identity": True})
    assert render_problems(on, on_all, on=True) == []


def test_a_renderer_passing_the_argument_when_the_switch_is_off_is_refused() -> None:
    off, off_all = _workspace_build({"brand": "govuk"})
    planted = {**off, "args": {SWITCH: "1"}}
    assert any("still carries arguments" in p for p in render_problems(planted, off_all, on=False))


def test_a_renderer_leaving_the_argument_out_when_the_switch_is_on_is_refused() -> None:
    on, on_all = _workspace_build({"brand": "govuk", "govuk_identity": True})
    planted = {k: v for k, v in on.items() if k != "args"}
    assert any("build arguments are None" in p for p in render_problems(planted, on_all, on=True))


# ------------------------------------------------------------------------------ nothing else writes the face's files


def test_nothing_else_in_the_build_writes_govuk_files() -> None:
    """The sync step is the one writer of `public/assets/govuk/`: the Vite config names no `publicDir` of its own and no
    copy plugin, and no other script in the workspace's `scripts/` writes under that folder."""
    config = VITE_CONFIG.read_text("utf-8")
    assert "publicDir" not in config and "govuk" not in config.lower()
    writers = [
        p.name for p in sorted((APP / "scripts").glob("*")) if p.is_file() and p != SCRIPT and "assets/govuk" in p.read_text("utf-8", "replace")
    ]
    assert writers == []


# ------------------------------------------------------------------------------- item 5: the register's claim holds


def _register() -> list[dict[str, object]]:
    import importlib

    return importlib.import_module("tools.licence_register").load_register()


def conditional_files(rows: list[dict[str, object]], fonts: dict) -> list[tuple[str, str, list[str]]]:
    """`(row id, folder, stems)` for each `conditional` font row: where its fonts.json entry says it is self-hosted, and the
    file-name stems it owns there. The folder also holds the fallback stylesheet, which is not the face."""
    by_family = {e["family"]: e for e in fonts["fonts"]}
    found = []
    for row in rows:
        if row["kind"] == "font" and row["status"] == "conditional":
            entry = by_family[row["name"]]
            found.append((str(row["id"]), str(entry["self_hosted_under"]), list(entry["file_stems"])))
    return found


def register_problems(rows: list[dict[str, object]], fonts: dict, files: dict[str, bytes]) -> list[str]:
    out = []
    for row_id, folder, stems in conditional_files(rows, fonts):
        for rel in sorted(files):
            base = rel.rsplit("/", 1)[-1]
            under = ("/" + rel).startswith(folder.rstrip("/") + "/")
            if under and any(base.startswith(stem + "-") for stem in stems):
                out.append(f"{row_id} is conditional and its file {rel} is in the default build")
    return out


def test_the_register_marks_gds_transport_conditional_and_says_the_build_no_longer_holds_it() -> None:
    rows = _register()
    row = next(r for r in rows if r["name"] == "GDS Transport")
    assert row["status"] == "conditional" and str(row["ships"]).startswith("only when appearance.govuk_identity is on")
    note = " ".join(str(row["note"]).split())
    assert "no longer" in note and "unconditionally" not in note.replace("no longer", ""), note
    assert "Today's build still holds" not in note


def test_no_file_the_register_marks_conditional_is_in_a_default_build(default_output: dict[str, bytes]) -> None:
    fonts = json.loads(FONTS_LIST.read_text("utf-8"))
    rows = _register()
    assert conditional_files(rows, fonts), "the register marks no font conditional: the check would pass on nothing"
    assert register_problems(rows, fonts, default_output) == []


def test_the_register_check_is_red_when_a_conditional_file_is_in_the_output(
    identity_output: dict[str, bytes],
) -> None:
    fonts = json.loads(FONTS_LIST.read_text("utf-8"))
    problems = register_problems(_register(), fonts, identity_output)
    assert len(problems) >= 4 and all(p.startswith("F3 is conditional") for p in problems), problems

