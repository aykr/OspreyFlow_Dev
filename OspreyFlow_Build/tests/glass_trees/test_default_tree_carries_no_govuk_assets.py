"""Slice PL7c, item 4: invariant I9, its asset half (ADR-152 decision 14 and Amendment 2). The default tree (`apps/pages`'
`tree-default`, built by `scripts/assets.mjs`) never shows the crown, the GOV.UK logotype or the GOV.UK typeface: not in
the stylesheet it builds, not in a file it serves, not in a template it renders.

This is the asset half of the proof; `test_default_build_holds_no_gds_transport.py` is the React workspace's build (its
`public/` folder), and `test_fonts_list.py` already walks `apps/pages` for GDS Transport as source. This file reads what the
build *writes*: it makes the Default build into a scratch folder, once, and reads every file in it, and the templates the
Default tree renders from.

**What fails the tree.** In any file of the built assets or the tree's templates (and the module sources it serves):
  * the face: a file whose content hash is one of the four faces of the installed `govuk-frontend`, however it is named or
    where it sits (the build puts a font in a folder named by its hash); a font file named in the package's own
    `<stem>-<hash>-v2` shape; the family name `GDS Transport`; a path under `/assets/govuk/`;
  * the crown: the package's `govuk-crest` image, by name or reference, or the crown's own drawing, whose first path is
    the one every copy of it starts with in `GovukHeader.tsx`, `GovukFooter.tsx` and the package's SVG;
  * the logotype: the header's class `govuk-header__logotype`, the header or footer `govuk-footer__crown`, or an
    `aria-label="GOV.UK"` mark.
Each shape is also planted, at the shape the build writes (the real stylesheet with a real `@font-face` rule from the
installed package appended; a real face file in a hashed folder, and again under another name; a real template with the
header's markup put into it), and each is found, by its own reason, and nothing else is: the clean tree reports nothing.

**The folders this test walks** (the conductor's scan-map row): under `OspreyFlow_Core`, `apps/pages/` (`tree-default`,
`modules` and `server/views` are copied into a scratch folder to plant in; the build is made in a scratch folder, never
`dist/`), `packages/design/` (the stylesheet's source, read by the build), and the installed
`node_modules/govuk-frontend` faces and crest. It never writes into the repository.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from tools.layout import CORE

PAGES = CORE / "apps" / "pages"
GOVUK_ASSETS = CORE / "node_modules" / "govuk-frontend" / "dist" / "govuk" / "assets"
ASSETS_SCRIPT = PAGES / "scripts" / "assets.mjs"
NODE = shutil.which("node")
TEXT_SUFFIXES = {".css", ".js", ".mjs", ".ts", ".html", ".njk", ".json", ".svg", ".map", ".txt"}
FONT_SUFFIXES = {".woff", ".woff2", ".ttf", ".otf", ".eot"}
FACE_NAME = re.compile(r"^(bold|light)-[0-9a-f]{10}-v\d+\.(woff2?|ttf|otf|eot)$")
#: How a copy of the crown's drawing starts: the first dot of the crown's circles, the same in the package's SVG, the header
#: and the footer (the Glass's own GOV.UK components draw it inline).
CROWN_DRAWING = '<circle cx="20" cy="17.6" r="3.7"'

#: `(reason, pattern)`; the reason is what a finding says, and what each planted case asserts.
TEXT_SHAPES: list[tuple[str, re.Pattern[str]]] = [
    ("names GDS Transport", re.compile(r"GDS[ -]?Transport", re.I)),
    ("refers to a path under /assets/govuk/", re.compile(r"/assets/govuk/")),
    ("names the crown image", re.compile(r"govuk-crest")),
    ("draws the crown", re.compile(re.escape(CROWN_DRAWING))),
    ("carries the GOV.UK logotype class", re.compile(r"govuk-header__logotype")),
    ("carries the GOV.UK crown class", re.compile(r"govuk-footer__crown")),
    ("carries the GOV.UK mark", re.compile(r'aria-label="GOV\.UK"')),
]


def real_face_hashes() -> dict[str, str]:
    folder = GOVUK_ASSETS / "fonts"
    assert folder.is_dir(), "govuk-frontend is not installed: run `npm ci`"
    found = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}
    assert len(found) == 4, found
    return found


def tree_problems(root: Path, faces: dict[str, str], *, skip: tuple[str, ...] = ()) -> list[str]:
    """Every way a file under `root` shows the crown, the GOV.UK logotype or the GOV.UK typeface: `<path>: <reason>`."""
    hashes = set(faces.values())
    out: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(s) for s in skip):
            continue
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() in hashes:
            out.append(f"{rel}: is a GDS Transport face (by content hash)")
        elif path.suffix in FONT_SUFFIXES and FACE_NAME.match(path.name):
            out.append(f"{rel}: is named as a GDS Transport face")
        if path.name == "govuk-crest.svg":
            out.append(f"{rel}: is the crown image")
        if path.suffix in TEXT_SUFFIXES:
            text = data.decode("utf-8", "replace")
            out += [f"{rel}: {reason}" for reason, pattern in TEXT_SHAPES if pattern.search(text)]
    return out


# ---------------------------------------------------------------------------------------- the real Default tree


def _build(out: Path) -> dict[str, str]:
    assert NODE, "node is needed to run the asset build"
    done = subprocess.run(  # noqa: S603
        [NODE, str(ASSETS_SCRIPT), "--out", str(out)], cwd=CORE, capture_output=True, text=True, timeout=180, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads((out / "manifest.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def faces() -> dict[str, str]:
    return real_face_hashes()


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    out = tmp_path_factory.mktemp("default") / "assets"
    return out, _build(out)


def _tree_copy(tmp: Path) -> Path:
    """A folder shaped like `apps/pages`: the tree's templates, the modules it serves and the server's views."""
    pages = tmp / "pages"
    for folder in ("tree-default", "modules", "server/views"):
        if (PAGES / folder).is_dir():
            shutil.copytree(PAGES / folder, pages / folder)
    return pages


def test_the_default_tree_shows_no_crown_logotype_or_typeface(
    built: tuple[Path, dict[str, str]], faces: dict[str, str], tmp_path: Path
) -> None:
    out, manifest = built
    assert (out / manifest["pages.css"]).stat().st_size > 1000, "the build made no stylesheet: nothing was read"
    built_files = [p for p in out.rglob("*") if p.is_file()]
    assert any(p.suffix == ".css" for p in built_files) and any(p.suffix in FONT_SUFFIXES for p in built_files)
    assert tree_problems(out, faces) == []
    pages = _tree_copy(tmp_path)
    assert any((pages / "tree-default").rglob("*.njk")), "the tree's templates were not read"
    assert tree_problems(pages, faces) == []


def test_the_default_stylesheet_names_no_govuk_brand_block(built: tuple[Path, dict[str, str]]) -> None:
    out, manifest = built
    css = (out / manifest["pages.css"]).read_text("utf-8")
    assert 'data-brand="govuk"' not in re.sub(r"\s+", "", css).replace("'", '"')
    assert "govuk" not in css.lower()


# ------------------------------------------------------------------- rule 15: each shape, planted as the build writes it


def _real_face_rule() -> str:
    """The `@font-face` rule govuk-frontend writes for its bold face, as the package writes it."""
    css = (CORE / "node_modules/govuk-frontend/dist/govuk/govuk-frontend.min.css").read_text("utf-8")
    match = re.search(r"@font-face\{font-family:GDS Transport;[^}]*font-weight:700[^}]*\}", css)
    assert match, "the installed govuk-frontend writes no bold GDS Transport rule: update this test"
    return match.group(0)


def _copy_build(built: tuple[Path, dict[str, str]], tmp: Path) -> tuple[Path, str]:
    out, manifest = built
    copy = tmp / "assets"
    shutil.copytree(out, copy)
    return copy, manifest["pages.css"]


def _append(path: Path, text: str) -> None:
    path.write_text(path.read_text("utf-8") + text, "utf-8")


def _stylesheet_with_the_rule(root: Path, css: str) -> None:
    _append(root / css, _real_face_rule())


def _stylesheet_with_the_self_hosted_rule(root: Path, css: str) -> None:
    """The rule as the workspace's sync step writes it: the package's `/assets/fonts/` moved under `/assets/govuk/`."""
    _append(root / css, _real_face_rule().replace("/assets/fonts/", "/assets/govuk/fonts/"))


def _face_in_a_hashed_folder(root: Path, css: str) -> None:
    name = "bold-b542beb274-v2.woff2"
    folder = root / "ABCD1234"
    folder.mkdir()
    shutil.copy(GOVUK_ASSETS / "fonts" / name, folder / name)


def _face_renamed(root: Path, css: str) -> None:
    folder = root / "WXYZ9876"
    folder.mkdir()
    shutil.copy(GOVUK_ASSETS / "fonts" / "light-94a07e06a1-v2.woff2", folder / "ibm-plex-mono-latin-400-normal.woff2")


def _crest_image(root: Path, css: str) -> None:
    shutil.copy(GOVUK_ASSETS / "images" / "govuk-crest.svg", root / "govuk-crest.svg")


def _crest_in_the_stylesheet(root: Path, css: str) -> None:
    _append(root / css, ".footer{background-image:url(/assets/govuk/images/govuk-crest.svg)}")


@pytest.mark.parametrize(
    ("case", "plant", "reasons"),
    [
        ("the real @font-face rule in the stylesheet", _stylesheet_with_the_rule, ["names GDS Transport"]),
        ("the rule as the workspace self-hosts it", _stylesheet_with_the_self_hosted_rule, ["names GDS Transport", "refers to a path under /assets/govuk/"]),
        ("a real face in a hashed folder", _face_in_a_hashed_folder, ["is a GDS Transport face (by content hash)"]),
        ("a real face under another name", _face_renamed, ["is a GDS Transport face (by content hash)"]),
        ("the crest image file", _crest_image, ["is the crown image"]),
        ("the crest named in the stylesheet", _crest_in_the_stylesheet, ["names the crown image", "refers to a path under /assets/govuk/"]),
    ],
)
def test_the_assets_check_is_red_for_each_planted_shape(
    built: tuple[Path, dict[str, str]],
    faces: dict[str, str],
    tmp_path: Path,
    case: str,
    plant: Callable[[Path, str], None],
    reasons: list[str],
) -> None:
    root, css = _copy_build(built, tmp_path)
    assert tree_problems(root, faces) == [], "the copy is not clean before the plant"
    plant(root, css)
    found = tree_problems(root, faces)
    assert found, case
    for reason in reasons:
        assert any(f.endswith(reason) for f in found), (case, reason, found)


def _template_planted(pages: Path, text: str) -> None:
    layout = pages / "tree-default" / "layout.njk"
    body = layout.read_text("utf-8")
    assert "</body>" in body
    layout.write_text(body.replace("</body>", text + "\n</body>", 1), "utf-8")


def _header_markup() -> str:
    """The header's logo as `GovukHeader.tsx` writes it (the class, the label, and the first crown circle)."""
    source = (CORE / "apps/workspace/src/brand/govuk/GovukHeader.tsx").read_text("utf-8")
    assert 'className="govuk-header__logotype"' in source and 'cx="20" cy="17.6" r="3.7"' in source
    return f'<svg class="govuk-header__logotype" aria-label="GOV.UK"><g>{CROWN_DRAWING} /></g></svg>'


@pytest.mark.parametrize(
    ("case", "text", "reasons"),
    [
        ("the header's logotype", None, ["carries the GOV.UK logotype class", "carries the GOV.UK mark", "draws the crown"]),
        ("the footer's crown", '<svg class="govuk-footer__crown"></svg>', ["carries the GOV.UK crown class"]),
        ("a link to the package's stylesheet", '<link rel="stylesheet" href="/assets/govuk/govuk-frontend.min.css">', ["refers to a path under /assets/govuk/"]),
        ("the face in an inline style", '<p style="font-family:GDS Transport,arial">x</p>', ["names GDS Transport"]),
    ],
)
def test_the_template_check_is_red_for_each_planted_shape(
    faces: dict[str, str], tmp_path: Path, case: str, text: str | None, reasons: list[str]
) -> None:
    pages = _tree_copy(tmp_path)
    assert tree_problems(pages, faces) == []
    _template_planted(pages, text if text is not None else _header_markup())
    found = tree_problems(pages, faces)
    assert found, case
    for reason in reasons:
        assert any(f.endswith(reason) and "layout.njk" in f for f in found), (case, reason, found)


def test_a_near_miss_is_not_a_fault(faces: dict[str, str], tmp_path: Path) -> None:
    """The word `government` or a class `govuk-like` are not the crown, the logotype or the face; nor is a listed face."""
    pages = _tree_copy(tmp_path)
    _template_planted(pages, '<p class="govuk-like">A government page.</p>')
    (pages / "tree-default" / "face.woff2").write_bytes(b"wOF2 an OFL face")
    assert tree_problems(pages, faces) == []


def test_the_check_reads_the_hash_and_not_only_the_name(faces: dict[str, str], tmp_path: Path) -> None:
    (tmp_path / "x.woff2").write_bytes((GOVUK_ASSETS / "fonts" / "bold-b542beb274-v2.woff2").read_bytes())
    assert tree_problems(tmp_path, faces) == ["x.woff2: is a GDS Transport face (by content hash)"]
