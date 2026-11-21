"""Slice IS5a0, the page foundation, the half that is Python (ADR-152 decisions 6, 7 and 12 and Amendments 1 and 2).

`OspreyFlow_Core/apps/pages/test/server/foundation.test.ts` holds items 1, 3 and 4 (the static route, the layout and
the route-module convention, the client-script bundle). This file holds the rest, and is pure: it runs `node` over the
asset build and reads files, with no network, no container and no store.

**Item 2, the stylesheet and the fonts.** The build makes one hashed stylesheet from `packages/design`'s own files and
copies none of their rules into the pages tree (`test_the_stylesheet_is_made_from_the_design_files_and_copies_none`).
It serves exactly the faces `fonts.json` names for the Default tree, which is every entry that carries no condition of
its own (`test_the_default_build_serves_exactly_the_faces_the_list_names`). GDS Transport is the GOV.UK tree's, with two
conditions (Amendment 2): the Default build never carries it, and each way it could arrive is planted in the shape the
real scan reads (`test_gds_transport_in_the_default_build_is_flagged_in_each_shape`).

**Item 5, the image.** The builder stage copies the sources the bundle and the stylesheet need and no others
(`test_the_builder_stage_copies_what_the_bundle_needs_and_no_more`), every COPY source exists
(`test_every_copy_source_exists`), and the stage that is left, the runtime, copies the build and the manifest alone.
The build is run in a folder holding only what the builder stage's COPY lines put there, with a module that imports the
shared package: it passes with the real lines and fails, naming the missing path, when `packages/design` or
`packages/glass-shared/src` is taken out (`test_the_build_runs_in_the_builder_stages_own_files_and_fails_without_each_copy`).
Nothing builds the image in CI yet, so this is the only thing that would notice a COPY line that was left out.

**Item 6, the gates read `apps/pages`.** Each of `ui_words_check`, `design_check`, `colour_drift_check` and
`no_branches_check` is given a planted violation under a copy of the pages roots, in each of the three roots, and flags
it; the same copy without it is clean. `client_name_check` reads every tracked file and so reads the pages already: that
is shown with a planted name in each root. The copy walker of `test_copy_says_no_client.py` reads the three roots. A
`.njk` template is read by `ui_words_check`, `colour_drift_check` and `no_branches_check` as text (their suffix lists
now name it); `design_check` runs `impeccable`, which reads HTML and not `.njk`, so the gate hands it each template as a
copy named `.html` and puts the template's own path back on what it finds (`test_a_template_is_read_by_the_design_detector`
plants an inline side stripe in a template and shows it flagged; without the reader it is not).

**The folders this test walks** (the conductor's scan-map row): under `OspreyFlow_Core`, `apps/pages/dist` (the build it
makes itself, in a temporary folder, never the real one), `apps/pages/tree-default`, `apps/pages/modules` and
`apps/pages/server/views` (copied into temporary folders, to plant in), `packages/design` and the files of the image's
builder stage (copied); and `apps/pages/Dockerfile`, `.dockerignore`. It never writes into the repository.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest
from tools import (
    client_name_check,
    colour_drift_check,
    design_check,
    layout,
    no_branches_check,
    ui_words_check,
)
from tools.layout import CORE
from tools.licence_check import _instructions

from tests.glass_trees import test_fonts_list as fonts
from tests.test_client_name_check import SYNTHETIC_CLIENT, _list, _repo
from tests.test_copy_says_no_client import pages_copy_hits

PAGES = CORE / "apps" / "pages"
DESIGN = CORE / "packages" / "design"
DOCKERFILE = (PAGES / "Dockerfile").read_text(encoding="utf-8")
ASSETS_SCRIPT = PAGES / "scripts" / "assets.mjs"
PAGES_ROOTS = ("apps/pages/tree-default", "apps/pages/modules", "apps/pages/server/views")
NODE = shutil.which("node")


def _run_node(*args: str | Path, cwd: Path = CORE) -> subprocess.CompletedProcess[str]:
    assert NODE, "node is needed to run the asset build"
    return subprocess.run(  # noqa: S603
        [NODE, *map(str, args)], cwd=cwd, capture_output=True, text=True, timeout=180, check=False
    )


def _build(out: Path, *extra: str | Path) -> dict[str, str]:
    done = _run_node(ASSETS_SCRIPT, "--out", out, *extra)
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


class Built(NamedTuple):
    out: Path
    manifest: dict[str, str]

    @property
    def css(self) -> str:
        return (self.out / self.manifest["pages.css"]).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Built:
    """The Default build, made once, in a folder shaped like the checkout so the fonts scan can read it as it reads `apps/pages/dist`."""
    out = tmp_path_factory.mktemp("core") / "apps" / "pages" / "dist" / "assets"
    return Built(out, _build(out))


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


# ------------------------------------------------------------------------------------------------ item 2: the stylesheet


def test_the_stylesheet_is_made_from_the_design_files_and_copies_none(built: Built) -> None:
    css = _squash(built.css)
    assert re.fullmatch(r"pages-[A-Z0-9]{8}\.css", built.manifest["pages.css"])
    # One distinctive rule from each of the four files the workspace composes, which only a build of them can have.
    assert "--brass:" in css  # tokens.css
    assert ":where(h1){font-size:var(--fs-23)" in css  # scale.css
    assert (
        ":where(.drawer,.canvas-menu-panel,.menu-panel,.view-lens-banner,.save-view){font-size:var(--fs-13)"
        in css
    )  # panelType.css
    assert ".btn{" in css  # primitives.css
    # The pages tree holds no stylesheet of its own: nothing was copied there.
    own = [p for root in (*PAGES_ROOTS, "apps/pages/server") for p in (CORE / root).rglob("*.css")]
    assert own == []
    # The GOV.UK identity is the other tree's: none of its rules are in the Default stylesheet.
    assert 'data-brand="govuk"' not in css
    assert "govuk" not in css.lower()
    assert "GDS Transport" not in css


def _default_faces(data: dict) -> dict[str, tuple[str, set[int]]]:
    """Every entry that carries no condition of its own: the faces the Default tree serves. `{package: (family, weights)}`."""
    return {
        e["source"].removeprefix("@fontsource/"): (e["family"], set(e["weights"]))
        for e in fonts.entries(data)
        if not (fonts.CONDITION_KEYS & set(e)) and e["source"].startswith("@fontsource/")
    }


def test_the_default_build_serves_exactly_the_faces_the_list_names(built: Built) -> None:
    data = fonts.load_list()
    wanted = _default_faces(data)
    assert set(wanted) == {
        "atkinson-hyperlegible-next",
        "ibm-plex-mono",
    }  # the list's two OFL faces, and not GDS Transport
    out = built.out
    # The faces the stylesheet declares: each listed family at each listed weight, and nothing else.
    declared: dict[str, set[int]] = {}
    for block in fonts.FONT_FACE.findall(built.css):
        family = re.search(r"font-family\s*:\s*([^;}]+)", block)
        weight = re.search(r"font-weight\s*:\s*([^;}]+)", block)
        assert family and weight, block
        declared.setdefault(family.group(1).strip().strip("'\""), set()).add(
            int(weight.group(1).strip())
        )
    assert declared == {family: weights for family, weights in wanted.values()}
    # The files served: every one is a listed package at a listed weight and the normal style, and every listed weight has one.
    files = sorted(p for p in out.rglob("*") if p.suffix in fonts.FONT_SUFFIXES)
    assert files, "the build made no font file: the faces would be drawn from the visitor's own"
    seen: dict[str, set[int]] = {}
    for path in files:
        rel = path.relative_to(out).as_posix()
        assert fonts._font_file_fault(rel, data) is None, rel
        package = next(p for p in wanted if p in path.name)
        seen.setdefault(package, set()).add(int(re.search(r"-(\d{3})-normal", path.name).group(1)))  # type: ignore[union-attr]
    assert seen == {package: weights for package, (_, weights) in wanted.items()}
    # A font file is named for its content too: it sits in a folder named by its hash, the file name itself unchanged.
    assert all(
        re.search(r"/[A-Z0-9]{8}/[^/]+$", "/" + p.relative_to(out).as_posix()) for p in files
    )


def _plant_real_core(tmp: Path, built: Built) -> Path:
    """A folder shaped like the checkout: the build above, and the real templates the scan also reads."""
    core = tmp / "core"
    shutil.copytree(built.out, core / "apps" / "pages" / "dist" / "assets")
    shutil.copytree(PAGES / "tree-default", core / "apps" / "pages" / "tree-default")
    shutil.copy(PAGES / "package.json", core / "apps" / "pages" / "package.json")
    return core


def _govuk_face() -> str:
    """The rule govuk-frontend writes its own bold face in (the real shape), else the same written by hand."""
    installed = fonts.INSTALLED_GOVUK_CSS
    if installed.is_file():
        for block in fonts.FONT_FACE.findall(installed.read_text(encoding="utf-8")):
            if "GDS Transport" in block and "bold" in block:
                # The package writes `/assets/fonts/`; this repository self-hosts the files under `/assets/govuk/fonts/`.
                return "@font-face{" + block.replace("/assets/fonts/", "/assets/govuk/fonts/") + "}"
    return '@font-face{font-family:"GDS Transport";font-style:normal;font-weight:700;src:url("/assets/govuk/fonts/bold-b542beb274-v2.woff2") format("woff2")}'


def test_gds_transport_in_the_default_build_is_flagged_in_each_shape(
    built: Built, tmp_path: Path
) -> None:
    data = fonts.load_list()
    clean_core = _plant_real_core(tmp_path / "clean", built)
    clean = fonts.scan(clean_core, data, fonts.PAGES_WALK, fonts.PAGES_SKIPPED, no_gds=True)
    assert clean.violations == []
    # The scan looked at the build: the stylesheet and the font files are among what it read.
    assert any(r.endswith(".css") and "/dist/assets/" in r for r in clean.read)
    assert any(r.endswith(".woff2") for r in clean.read)

    def planted(name: str, write: Callable[[Path], None]) -> list[str]:
        core = _plant_real_core(tmp_path / name, built)
        write(core / "apps" / "pages")
        return fonts.scan(core, data, fonts.PAGES_WALK, fonts.PAGES_SKIPPED, no_gds=True).violations

    def stylesheet(pages: Path) -> None:
        name = Path(built.manifest["pages.css"])
        target = pages / "dist" / "assets" / name
        target.write_text(target.read_text(encoding="utf-8") + _govuk_face(), encoding="utf-8")

    def font_file(pages: Path) -> None:
        folder = pages / "dist" / "assets" / "govuk" / "fonts"
        folder.mkdir(parents=True)
        (folder / "bold-b542beb274-v2.woff2").write_bytes(b"wOF2")

    def template(pages: Path) -> None:
        layout_path = pages / "tree-default" / "layout.njk"
        text = layout_path.read_text(encoding="utf-8")
        link = '<link rel="stylesheet" href="/assets/govuk/govuk-frontend.min.css">\n</head>'
        assert "</head>" in text
        layout_path.write_text(text.replace("</head>", link, 1), encoding="utf-8")

    for name, write in (
        ("stylesheet", stylesheet),
        ("font file", font_file),
        ("template", template),
    ):
        found = planted(name.replace(" ", "_"), write)
        assert len(found) == 1, (name, found)
        assert re.search(r"GDS Transport|assets/govuk", found[0]), (name, found)


# --------------------------------------------------------------------------------------------------- item 5: the image


def _stage_copies(dockerfile: str, stage: str) -> list[tuple[list[str], str, bool]]:
    """`(sources, destination, from_another_stage)` for each COPY in the named stage, read as `make licence-check` reads a Dockerfile."""
    current = ""
    out: list[tuple[list[str], str, bool]] = []
    for instruction in _instructions(dockerfile):
        word, _, rest = instruction.partition(" ")
        if word.upper() == "FROM":
            match = re.search(r"\bAS\s+(\S+)\s*$", rest, re.I)
            current = match.group(1) if match else f"stage{len(out)}"
            continue
        if word.upper() != "COPY" or current != stage:
            continue
        parts = rest.split()
        flags = [p for p in parts if p.startswith("--")]
        args = [p for p in parts if not p.startswith("--")]
        out.append((args[:-1], args[-1], any(f.startswith("--from=") for f in flags)))
    return out


def _local_sources(dockerfile: str, stage: str) -> list[str]:
    return [
        s for sources, _, other in _stage_copies(dockerfile, stage) if not other for s in sources
    ]


#: What the bundle and the stylesheet need in the builder stage, beyond the manifests `npm ci` checks the lockfile against:
#: the design package (the stylesheet and the font list), the shared package's source (modules import it) and the
#: generated schema types (the shared package's clients import them), and the service's own folder.
BUILDER_SOURCES = [
    "package.json",
    "package-lock.json",
    "apps/workspace/package.json",
    "apps/harness/package.json",
    "apps/pages/package.json",
    "packages/glass-shared/package.json",
    "packages/design",
    "packages/glass-shared/src",
    "packages/schemas/generated",
    "apps/pages",
]


def test_the_builder_stage_copies_what_the_bundle_needs_and_no_more() -> None:
    sources = _local_sources(DOCKERFILE, "builder")
    assert sorted(sources) == sorted(BUILDER_SOURCES), sorted(set(sources) ^ set(BUILDER_SOURCES))
    # Nothing broad, and nothing of the workspace's source or the Conduit's: the image is built from what it needs.
    for source in sources:
        assert source not in {".", "./", "apps", "packages", "apps/workspace", "services"}, source
        assert not source.startswith(("apps/workspace/src", "services", "harness")), source
    # The sources come after the manifests, so `npm ci` still caches across a source-only change.
    install = DOCKERFILE.index("RUN npm ci --workspace apps/pages")
    for late in (
        "packages/design",
        "packages/glass-shared/src",
        "packages/schemas/generated",
        "COPY apps/pages ./apps/pages",
    ):
        assert DOCKERFILE.index(late, install) > install, late
    # The runtime stage carries the build and the manifest, never a source folder.
    final = DOCKERFILE.rsplit("FROM node:22-slim", 1)[1]
    copied = [line.split() for line in final.splitlines() if line.startswith("COPY")]
    assert [c[-2:] for c in copied] == [
        ["/app/node_modules", "./node_modules"],
        ["/app/apps/pages/dist", "./apps/pages/dist"],
        ["apps/pages/package.json", "./apps/pages/package.json"],
    ]
    assert "packages/" not in final.replace("packages/glass-shared", "")


def test_every_copy_source_exists() -> None:
    """Nothing builds the image in CI, so a COPY of a path that is not there would be found by the first person to build it."""
    for stage in ("builder", "runtime-deps"):
        for source in _local_sources(DOCKERFILE, stage):
            assert (CORE / source).exists(), (
                f"{stage}: COPY {source}: no such path in the product folder"
            )
    # The check can fail: the same Dockerfile with a path that is not there.
    broken = DOCKERFILE.replace(
        "COPY packages/glass-shared/package.json ", "COPY packages/glass-shared/packag.json ", 1
    )
    missing = [s for s in _local_sources(broken, "builder") if not (CORE / s).exists()]
    assert missing == ["packages/glass-shared/packag.json"]


def test_the_dockerignore_keeps_none_of_the_copied_sources_out_of_the_context() -> None:
    """`.dockerignore` names `process`, `data` and the like: a COPY source under one of those names would be refused in the build."""
    ignored = [
        line.strip().rstrip("/")
        for line in (CORE / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith(("#", "!"))
    ]
    for source in _local_sources(DOCKERFILE, "builder"):
        parts = source.split("/")
        for pattern in ignored:
            assert pattern.lstrip("/") not in {
                "/".join(parts[: i + 1]) for i in range(len(parts))
            }, (source, pattern)


def _materialise(ctx: Path, copies: list[tuple[list[str], str, bool]]) -> None:
    """The files the builder stage has in `/app` after its COPY lines, and a `node_modules` that the stage's `npm ci` would make."""
    skip = shutil.ignore_patterns("node_modules", "dist", "__pycache__", "coverage")
    for sources, destination, other in copies:
        if other:
            continue
        for source in sources:
            origin = CORE / source
            target = ctx / destination.removeprefix("./")
            if origin.is_dir():
                shutil.copytree(origin, target, ignore=skip, dirs_exist_ok=True)
            else:
                target = (
                    target / origin.name if destination.endswith("/") or target.is_dir() else target
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(origin, target)
    # `npm ci` in the stage links every workspace into `node_modules/@ospreyflow` and installs the dependencies: here each
    # dependency is a link to the checkout's, and the workspaces are linked to the folders the stage copied, so that a
    # package left out of the COPY lines is not found through the checkout.
    modules = ctx / "node_modules"
    modules.mkdir()
    for entry in (CORE / "node_modules").iterdir():
        if entry.name not in {"@ospreyflow", ".bin", ".package-lock.json"}:
            (modules / entry.name).symlink_to(entry)
    own = modules / "@ospreyflow"
    own.mkdir()
    for name, folder in (("glass-shared", "packages/glass-shared"), ("pages", "apps/pages")):
        if (ctx / folder).is_dir():
            (own / name).symlink_to(ctx / folder)


PROBE = 'import { PRODUCT_STATEMENT } from "@ospreyflow/glass-shared";\ndocument.title = PRODUCT_STATEMENT;\n'


def _builder_context_build(tmp: Path, dockerfile: str) -> subprocess.CompletedProcess[str]:
    ctx = tmp / "app"
    ctx.mkdir(parents=True)
    _materialise(ctx, _stage_copies(dockerfile, "builder"))
    modules = ctx / "apps" / "pages" / "modules"
    modules.mkdir(parents=True, exist_ok=True)
    (modules / "probe.ts").write_text(PROBE, encoding="utf-8")
    return _run_node(
        ctx / "apps" / "pages" / "scripts" / "assets.mjs",
        "--out",
        ctx / "apps" / "pages" / "dist" / "assets",
        cwd=ctx,
    )


def test_the_build_runs_in_the_builder_stages_own_files_and_fails_without_each_copy(
    tmp_path: Path,
) -> None:
    real = _builder_context_build(tmp_path / "real", DOCKERFILE)
    assert real.returncode == 0, real.stdout + real.stderr
    out = tmp_path / "real" / "app" / "apps" / "pages" / "dist" / "assets"
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert "modules/probe.ts" in manifest and "pages.css" in manifest
    # Each COPY the bundle depends on, taken out of the stage's own text: the build fails, and says what it could not find.
    for source, words in (
        ("packages/design", r"packages/design|tokens\.css"),
        ("packages/glass-shared/src", r"glass-shared"),
    ):
        lines = DOCKERFILE.splitlines()
        kept = [line for line in lines if not re.match(rf"COPY {re.escape(source)}\b", line)]
        assert len(kept) == len(lines) - 1, f"no COPY line for {source} in the Dockerfile"
        broken = _builder_context_build(tmp_path / source.replace("/", "_"), "\n".join(kept))
        assert broken.returncode != 0, f"the build passed without COPY {source}"
        assert re.search(words, broken.stdout + broken.stderr), broken.stdout + broken.stderr


# ----------------------------------------------------------------------------------------------- item 6: the gates read


def _core_with(tmp: Path, files: dict[str, str]) -> Path:
    core = tmp / "OspreyFlow_Core"
    for root in PAGES_ROOTS:
        (core / root).mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (core / name).write_text(text, encoding="utf-8")
    return core


def test_the_pages_roots_are_the_ones_the_layout_names() -> None:
    assert tuple(layout.PAGES_COPY_ROOTS) == PAGES_ROOTS
    assert (PAGES / "tree-default" / "layout.njk").is_file()


#: Each root, the file a violation would be written in, and the copy a template or a module writes it in.
PLANTS = {
    "ui_words": {
        "apps/pages/tree-default/x.njk": "{% block content %}\n<h1>Review the target model</h1>\n{% endblock %}\n",
        "apps/pages/modules/x.ts": 'export const label = "Target model";\n',
        "apps/pages/server/views/x.njk": "<p>Edit the\n   target model here.</p>\n",
    },
    "colour_drift": {
        "apps/pages/tree-default/x.njk": '<svg><path fill="#ff00aa" d="M0 0"/></svg>\n',
        "apps/pages/modules/x.ts": 'export const stripe = "rgba(12, 34, 56, 0.5)";\n',
        "apps/pages/server/views/x.njk": '<rect fill="#12ab34"/>\n',
    },
    "no_branches": {
        "apps/pages/tree-default/x.njk": '<a href="/v1/investigations/{{ id }}/branch-by-filter">Branch</a>\n',
        "apps/pages/modules/x.ts": "export const branchNodes = () => [];\n",
        "apps/pages/server/views/x.njk": "<li>Branch of {{ name }}</li>\n",
    },
}


def _words_found(
    core: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> tuple[int, str]:
    none = core / "none"
    monkeypatch.setattr(ui_words_check, "PAGES_ROOTS", tuple(core / r for r in PAGES_ROOTS))
    for name in ("GLASS_SRC", "DESIGN_PACKAGE", "SHARED_SRC"):
        monkeypatch.setattr(ui_words_check, name, none)
    code = ui_words_check.main()
    return code, capsys.readouterr().out


@pytest.mark.parametrize("path", sorted(PLANTS["ui_words"]))
def test_the_ui_words_check_reads_the_pages_roots(
    path: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    clean = _core_with(tmp_path / "clean", {})
    assert _words_found(clean, capsys, monkeypatch)[0] == 0
    core = _core_with(tmp_path / "planted", {})
    target = core / path
    target.write_text(PLANTS["ui_words"][path], encoding="utf-8")
    code, out = _words_found(core, capsys, monkeypatch)
    assert code == 1, out
    assert f"{path}:" in out, out
    assert out.count("on screen") == 1, out


@pytest.mark.parametrize("path", sorted(PLANTS["colour_drift"]))
def test_the_colour_drift_check_reads_the_pages_roots(
    path: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(core: Path) -> tuple[int, str]:
        roots = tuple((core / r, frozenset()) for r in PAGES_ROOTS)
        monkeypatch.setattr(colour_drift_check, "SCANNED", roots)
        monkeypatch.setattr(colour_drift_check, "CORE", core)
        monkeypatch.setattr(colour_drift_check, "PAGES_ROOTS", tuple(core / r for r in PAGES_ROOTS))
        code = colour_drift_check.main()
        captured = capsys.readouterr()
        return code, captured.out + captured.err

    assert run(_core_with(tmp_path / "clean", {}))[0] == 0
    core = _core_with(tmp_path / "planted", {})
    (core / path).write_text(PLANTS["colour_drift"][path], encoding="utf-8")
    code, out = run(core)
    assert code == 1, out
    assert f"{path.rsplit('/', 1)[0]}/{Path(path).name}:1:" in out, out


def test_the_colour_drift_check_names_the_pages_roots_itself() -> None:
    """The real gate's own list, not a patched one: the three roots are in it, each with nothing exempt."""
    listed = {
        root.relative_to(CORE).as_posix(): exempt for root, exempt in colour_drift_check.SCANNED
    }
    for name in PAGES_ROOTS:
        assert listed.get(name) == frozenset(), name


@pytest.mark.parametrize("path", sorted(PLANTS["no_branches"]))
def test_the_no_branches_check_reads_the_pages_roots(path: str, tmp_path: Path) -> None:
    clean = _core_with(tmp_path / "clean", {})
    assert (
        no_branches_check.findings(no_branches_check.tree_files(clean, no_branches_check.SCANNED))
        == []
    )
    core = _core_with(tmp_path / "planted", {})
    (core / path).write_text(PLANTS["no_branches"][path], encoding="utf-8")
    found = no_branches_check.findings(
        no_branches_check.tree_files(core, no_branches_check.SCANNED)
    )
    assert [f[0] for f in found] == [path], found


SIDE_STRIPE = (
    '<div class="card" style="border-left: 4px solid red; border-radius: 8px; padding: 8px 12px; '
    'background: var(--surface-raised)">A status</div>\n'
)


@pytest.mark.parametrize("path", ["apps/pages/tree-default/x.njk", "apps/pages/server/views/x.njk"])
def test_a_template_is_read_by_the_design_detector(
    path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean = _core_with(tmp_path / "clean", {})
    roots = [clean / r for r in PAGES_ROOTS]
    assert design_check.unexcused(design_check.detect(roots)) == []
    core = _core_with(tmp_path / "planted", {})
    (core / path).write_text(
        '{% extends "layout.njk" %}\n{% block content %}\n' + SIDE_STRIPE + "{% endblock %}\n",
        encoding="utf-8",
    )
    found = design_check.unexcused(design_check.detect([core / r for r in PAGES_ROOTS]))
    assert [(Path(f["file"]), f["antipattern"]) for f in found] == [(core / path, "side-tab")], (
        found
    )


def test_the_design_check_names_the_pages_roots_itself() -> None:
    scanned = {Path(p).relative_to(CORE).as_posix() for p in design_check.SCANNED}
    assert set(PAGES_ROOTS) <= scanned


def test_the_design_detector_reads_a_module_and_a_template_through_main(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` over the pages roots alone: clean passes, the planted template fails and names its own path."""
    core = _core_with(tmp_path, {})
    monkeypatch.setattr(design_check, "SCANNED", [core / r for r in PAGES_ROOTS])
    monkeypatch.setattr(design_check, "CORE", core)
    monkeypatch.setattr(design_check, "copy_drift", lambda *_a, **_k: False)
    (core / "DESIGN.md").write_text("x", encoding="utf-8")
    assert design_check.main() == 0
    (core / "apps/pages/tree-default/x.njk").write_text(SIDE_STRIPE, encoding="utf-8")
    assert design_check.main() == 1
    assert "apps/pages/tree-default/x.njk" in capsys.readouterr().out


CLIENT_PLANTS = {
    "apps/pages/tree-default/x.njk": f"<p>Prepared for {SYNTHETIC_CLIENT}.</p>\n",
    "apps/pages/modules/x.ts": f'export const label = "{SYNTHETIC_CLIENT}";\n',
    "apps/pages/server/views/x.njk": f"<p>{SYNTHETIC_CLIENT}</p>\n",
}


@pytest.mark.parametrize("path", sorted(CLIENT_PLANTS))
def test_the_client_name_check_reads_the_pages_roots(
    path: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rel = f"OspreyFlow_Core/{path}"
    for name in ("clean", "planted"):
        (tmp_path / name).mkdir()  # `_repo` makes `<folder>/repo` and expects the folder there
    clean = _repo(tmp_path / "clean", {rel: "<p>Nothing here.</p>\n"})
    assert (
        client_name_check.main(["--root", str(clean), "--hashes", str(_list(tmp_path / "clean"))])
        == 0
    )
    capsys.readouterr()
    root = _repo(tmp_path / "planted", {rel: CLIENT_PLANTS[path]})
    code = client_name_check.main(
        ["--root", str(root), "--hashes", str(_list(tmp_path / "planted"))]
    )
    out = capsys.readouterr()
    assert code == 1, out.out + out.err
    assert f"{rel}:1:" in out.out + out.err


COPY_PLANTS = {
    "apps/pages/tree-default/x.njk": "<p>The client's connection strength is to be confirmed.</p>\n",
    "apps/pages/modules/x.ts": 'export const note = "TBC with the owner";\n',
    "apps/pages/server/views/x.njk": "<p>Not confirmed.</p>\n",
}


@pytest.mark.parametrize("path", sorted(COPY_PLANTS))
def test_the_copy_walker_reads_the_pages_roots(path: str, tmp_path: Path) -> None:
    clean = _core_with(tmp_path / "clean", {})
    assert pages_copy_hits(clean) == []
    core = _core_with(tmp_path / "planted", {})
    (core / path).write_text(COPY_PLANTS[path], encoding="utf-8")
    assert [h.split(":")[0] for h in pages_copy_hits(core)] == [path]


def test_the_real_pages_roots_are_clean_of_every_word_rule() -> None:
    """The real tree, against the rules the planted cases above show can fail."""
    assert pages_copy_hits(CORE) == []
    roots = tuple(CORE / r for r in PAGES_ROOTS)
    assert [f for r in roots for f in ui_words_check.find_banned(r)] == []
    files = no_branches_check.tree_files(CORE, PAGES_ROOTS)
    assert files, "the pages roots hold no file the no-branches check reads"
    assert no_branches_check.findings(files) == []
    palette = colour_drift_check.palette_from(
        colour_drift_check.DESIGN_PATH.read_text(encoding="utf-8")
    )
    assert [
        d for r in roots for d in colour_drift_check.find_drift(r, palette, mirrors=frozenset())
    ] == []
    assert design_check.unexcused(design_check.detect([r for r in roots if r.exists()])) == []
