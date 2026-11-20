"""I23: the built `pages` image carries no React (ADR-152 Amendment 1; slice PL6).

`scripts/pages_image_react_scan.py` reads the CycloneDX SBOM that `trivy image --format cyclonedx` writes
and the image's exported file system (`docker create`, `docker export`), and fails on a package named
`react`, `react-dom` or `scheduler` (in the SBOM, and in the exported tree as a `node_modules` folder or a
package.json by that name, listed or not), on `react/jsx-runtime`, `react/jsx-dev-runtime` or React's element
markers in any file under `/app`, and unless the SBOM names `express` and `nunjucks`. This file drives its
pure functions over a synthetic SBOM and a synthetic exported tree, both in the shape `trivy` and
`docker export` really produce. No Docker, no network. Nothing here is, or looks like, a secret: the one
token a case needs is generated at run time.

Rule 12, which test fails if the run-time install loses its scope: `apps/pages/Dockerfile`'s `runtime-deps`
stage runs `npm ci --omit=dev --workspace apps/pages`; without the flag, `npm ci` installs every
workspace's run-time dependencies (measured: `react`, `react-dom` and `scheduler` appear, because
`apps/workspace` is copied into that stage for the lockfile's sake).
`test_the_runtime_install_losing_its_scope_is_refused` is the test that goes red: it plants that loss in
the real Dockerfile's own text and asserts `runtime_install_problems` (this file's check of that stage)
refuses it, and that the SBOM such an image would give is refused by the scan.

Rule 15, each plant is shown red at the call site the scan really has:
  * the Dockerfile text is the real one, with the real flag removed;
  * the bundle's lines are what esbuild emits for a JSX import and a React element;
  * the SBOM has the shape `trivy` writes (`bom-ref`, `purl`, `properties`, a container as the subject),
    and the empty and wrong SBOMs are the ones a failed or mis-aimed `trivy` run could write;
  * the docker fake refuses what the docker CLI refuses (an image that is not there, a container that was
    not created), so a call made in the wrong order or with the wrong name fails here;
  * the near misses (a package called `react-dom-like`, a file saying "reaction") must not fail: the scan
    matches names, not substrings.

This test reads `apps/pages/Dockerfile` by name and walks only its own `tmp_path`: no folder walk of the
repository, so it needs no row in the line's scan map.
"""

from __future__ import annotations

import io
import json
import secrets
import subprocess
import tarfile
from collections.abc import Callable
from pathlib import Path

import pytest
from scripts import pages_image_react_scan as scan
from tools.licence_check import _instructions

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
DOCKERFILE = (CORE / "apps" / "pages" / "Dockerfile").read_text(encoding="utf-8")

# --- the check of the Dockerfile's run-time stage (this file's own; the scan reads the built image) ----------


def runtime_install_problems(dockerfile: str) -> list[str]:
    """What is wrong with the `runtime-deps` stage's install: it must run `npm ci --omit=dev` for the pages
    workspace alone. Read with `make licence-check`'s parser (continued lines joined, comments left out)."""
    in_stage = False
    installs: list[str] = []
    for instruction in _instructions(dockerfile):
        word, _, rest = instruction.partition(" ")
        if word.upper() == "FROM":
            in_stage = rest.lower().split()[-2:] == ["as", "runtime-deps"]
        elif in_stage and word.upper() == "RUN":
            installs += [
                part.strip() for part in rest.split("&&") if part.strip().startswith("npm ci")
            ]
    if not installs:
        return ["the runtime-deps stage runs no `npm ci`"]
    problems = []
    for install in installs:
        words = install.replace("=", " ").split()
        scopes = [words[i + 1] for i, w in enumerate(words[:-1]) if w in ("--workspace", "-w")]
        omits = [words[i + 1] for i, w in enumerate(words[:-1]) if w == "--omit"]
        if "dev" not in omits:
            problems.append(f"`{install}` does not omit dev dependencies")
        if scopes != ["apps/pages"]:
            problems.append(
                f"`{install}` is scoped to {scopes or 'no workspace'}, not apps/pages alone"
            )
    return problems


# --- synthetic SBOM, in the shape `trivy image --format cyclonedx` writes --------------------------------------


def _component(name: str, version: str, group: str | None = None) -> dict[str, object]:
    full = f"{group}/{name}" if group else name
    purl = "pkg:npm/" + (f"{group.replace('@', '%40')}/" if group else "") + f"{name}@{version}"
    component: dict[str, object] = {
        "bom-ref": purl,
        "type": "library",
        "name": name,
        "version": version,
        "licenses": [{"license": {"name": "MIT"}}],
        "purl": purl,
        "properties": [
            {"name": "aquasecurity:trivy:PkgID", "value": f"{full}@{version}"},
            {"name": "aquasecurity:trivy:PkgType", "value": "node-pkg"},
        ],
    }
    if group:
        component["group"] = group
    return component


def make_sbom(
    *npm: tuple[str, str], extra: list[dict[str, object]] | None = None
) -> dict[str, object]:
    os_package = {
        "bom-ref": "pkg:deb/debian/bash@5.2.15-2?distro=debian-12.8",
        "type": "library",
        "name": "bash",
        "version": "5.2.15-2",
        "purl": "pkg:deb/debian/bash@5.2.15-2?distro=debian-12.8",
        "properties": [{"name": "aquasecurity:trivy:PkgType", "value": "debian"}],
    }
    components = [os_package, *(_component(n, v) for n, v in npm), *(extra or [])]
    return {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:3e671687-395b-41f5-a30f-a58921a69b79",
        "version": 1,
        "metadata": {
            "timestamp": "2026-11-20T09:00:00+00:00",
            "tools": {
                "components": [{"type": "application", "group": "aquasecurity", "name": "trivy"}]
            },
            # the subject is the image itself: a container named by its tag, never a library
            "component": {
                "bom-ref": "pkg:oci/pages",
                "type": "container",
                "name": "ospreyflow/pages:ci",
            },
        },
        "components": components,
        "dependencies": [{"ref": c.get("bom-ref", "none"), "dependsOn": []} for c in components],
        "vulnerabilities": [],
    }


CLEAN = (
    ("express", "4.21.2"),
    ("nunjucks", "3.2.4"),
    ("helmet", "8.0.0"),
    ("express-session", "1.18.1"),
)
# What `npm ci --omit=dev` without `--workspace` brings in (evidence: all three appear).
UNSCOPED = (*CLEAN, ("react", "19.1.0"), ("react-dom", "19.1.0"), ("scheduler", "0.26.0"))


# --- synthetic exported file system, in the shape `docker export` gives --------------------------------------


def make_tree(root: Path, files: dict[str, str] | None = None) -> Path:
    """`root` as the exported file system: the service under /app, the run-time install's symlink for the
    workspace (relative, inside /app), and a system area outside /app."""
    base = {
        "app/package.json": '{"name": "ospreyflow-workspaces", "private": true}\n',
        "app/apps/pages/package.json": '{"name": "@ospreyflow/pages", "private": true}\n',
        "app/apps/pages/dist/server/main.js": '"use strict";\nconst express = require("express");\n',
        "app/node_modules/express/package.json": '{"name": "express", "version": "4.21.2"}\n',
        "app/node_modules/nunjucks/package.json": '{"name": "nunjucks", "version": "3.2.4"}\n',
        "usr/share/doc/readme": "nothing to see\n",
    }
    for name, text in {**base, **(files or {})}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    link = root / "app/node_modules/@ospreyflow/pages"
    if not link.is_symlink():
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to("../../apps/pages")
    return root


def kinds(findings: list[scan.Finding]) -> set[str]:
    return {f.kind for f in findings}


# --- the clean case, and what it must not trip on ----------------------------------------------------------


def test_the_clean_sbom_and_tree_pass(tmp_path: Path) -> None:
    sbom = make_sbom(*CLEAN)
    assert {"express", "nunjucks"} <= scan.sbom_package_names(
        sbom
    )  # the control: the positives are present
    assert scan.scan(sbom, make_tree(tmp_path / "fs")) == []


def test_names_are_matched_not_substrings(tmp_path: Path) -> None:
    sbom = make_sbom(
        *CLEAN, ("react-dom-like", "1.0.0"), ("reactive-store", "2.0.0"), ("preact", "10.0.0"),
        ("scheduler-lite", "1.0.0"),
    )  # fmt: skip
    # a scoped type package is not React; the run-time install (`--omit=dev`) would not carry it anyway
    sbom["components"].append(_component("react", "19.0.0", group="@types"))  # type: ignore[attr-defined]
    tree = make_tree(
        tmp_path / "fs",
        {
            "app/notes.txt": "The reaction of the reactor; a reactionary react-dom-like thing.\n",
            "app/apps/pages/dist/server/preact.js": 'var j = require("preact/jsx-runtime");\n',
            "app/apps/pages/dist/server/prose.js": "// a word like react. element or reactelement is no marker\n",
        },
    )
    assert scan.scan(sbom, tree) == []


# --- plant 1: the run-time install without its scope ---------------------------------------------------------


def test_the_real_runtime_install_is_scoped() -> None:
    assert runtime_install_problems(DOCKERFILE) == []


def test_the_runtime_install_losing_its_scope_is_refused() -> None:
    planted = DOCKERFILE.replace(
        "RUN npm ci --omit=dev --workspace apps/pages && npm cache clean --force",
        "RUN npm ci --omit=dev && npm cache clean --force",
    )
    assert planted != DOCKERFILE  # the plant took: the real line is where we think it is
    assert runtime_install_problems(planted) != []
    # the other half of the plant: the SBOM that image gives, with all three packages, is refused by name
    findings = scan.sbom_findings(make_sbom(*UNSCOPED))
    assert kinds(findings) == {"react-package"}
    assert {f.where for f in findings} == {"react", "react-dom", "scheduler"}


@pytest.mark.parametrize(
    "plant",
    [
        lambda t: t.replace("--workspace apps/pages && npm cache", "&& npm cache"),
        lambda t: t.replace("--workspace apps/pages", "--workspace apps/workspace"),
        lambda t: t.replace(
            "--workspace apps/pages", "--workspace apps/pages --workspace apps/workspace"
        ),
        lambda t: t.replace("--workspace apps/pages", "-w apps/workspace"),
        lambda t: t.replace("--omit=dev ", ""),
        lambda t: t.replace("npm ci --omit=dev --workspace apps/pages", "npm install --omit=dev"),
        lambda t: t.replace("AS runtime-deps", "AS something-else"),
    ],
    ids=[
        "unscoped",
        "wrong-workspace",
        "extra-workspace",
        "short-flag-wrong",
        "with-dev",
        "not-ci",
        "no-stage",
    ],
)
def test_other_ways_the_runtime_install_can_lose_its_scope_are_refused(
    plant: Callable[[str], str],
) -> None:
    planted = plant(DOCKERFILE)
    assert planted != DOCKERFILE
    assert runtime_install_problems(planted) != []


def test_the_builders_own_install_is_not_the_runtime_stage() -> None:
    # the builder stage's `npm ci --workspace apps/pages` must not satisfy the check for the other stage
    planted = DOCKERFILE.replace("RUN npm ci --omit=dev --workspace apps/pages", "RUN true")
    assert "npm ci --workspace apps/pages" in planted
    assert runtime_install_problems(planted) == ["the runtime-deps stage runs no `npm ci`"]


# --- plant 2: React's markers in a file under /app -----------------------------------------------------------

BUNDLE_LINES = {
    "jsx-runtime": 'var import_jsx_runtime = require("react/jsx-runtime");',
    "jsx-dev-runtime": 'import { jsxDEV } from "react/jsx-dev-runtime";',
    "element-symbol": 'var REACT_ELEMENT_TYPE = Symbol.for("react.element");',
    "transitional-element": "var t = Symbol.for('react.transitional.element');",
    "element-in-object": 'var el = { $$typeof: "react.element", type: "div", props: {} };',
    "other-symbol": 'var P = Symbol.for("react.portal");',
}


@pytest.mark.parametrize("line", BUNDLE_LINES.values(), ids=BUNDLE_LINES.keys())
def test_a_bundle_holding_a_react_marker_is_refused(tmp_path: Path, line: str) -> None:
    tree = make_tree(
        tmp_path / "fs",
        {"app/apps/pages/dist/public/bundle.js": f"(() => {{\n{line}\n}})();\n"},
    )
    findings = scan.tree_findings(tree)
    assert kinds(findings) == {"react-marker"}
    assert [f.where for f in findings] == ["app/apps/pages/dist/public/bundle.js"]


# One line per marker that no other marker's pattern matches, so each pattern is shown to be needed
# on its own: a minified bundle that aliases `Symbol.for` leaves React 19's element marker without the
# `Symbol.for(` prefix, which only its own pattern catches (rule 15: no broader rule may cover for it).
ISOLATED_MARKERS = {
    "react/jsx-runtime": 'var j = require("react/jsx-runtime");',
    "react/jsx-dev-runtime": 'var d = require("react/jsx-dev-runtime");',
    "react.element": 'var e = { $$typeof: "react.element" };',
    "react.transitional.element": 'var s = Symbol.for; var E = s("react.transitional.element");',
    'Symbol.for("react.': 'var P = Symbol.for("react.portal");',
}


def test_the_isolated_marker_lines_are_each_caught_by_one_pattern_alone() -> None:
    assert set(ISOLATED_MARKERS) == {label for label, _ in scan._MARKERS}
    for label, line in ISOLATED_MARKERS.items():
        matching = [lab for lab, pattern in scan._MARKERS if pattern.search(line.encode())]
        assert matching == [label], (label, matching)


@pytest.mark.parametrize("label", ISOLATED_MARKERS)
def test_each_marker_is_named_by_its_own_pattern(tmp_path: Path, label: str) -> None:
    tree = make_tree(
        tmp_path / "fs", {"app/apps/pages/dist/public/bundle.js": ISOLATED_MARKERS[label] + "\n"}
    )
    (finding,) = scan.tree_findings(tree)
    assert finding.kind == "react-marker"
    assert finding.detail == f"holds {label}"


def test_a_marker_in_a_dependency_or_a_binary_file_is_refused(tmp_path: Path) -> None:
    tree = make_tree(tmp_path / "fs")
    deep = tree / "app/node_modules/express/lib/deep/view.js"
    deep.parent.mkdir(parents=True)
    deep.write_bytes(b"\x00\x01binary" + b'require("react/jsx-runtime")' + b"\xff\xfe")
    assert [f.where for f in scan.tree_findings(tree)] == [
        "app/node_modules/express/lib/deep/view.js"
    ]


# a file with no React marker in it, as `scheduler`'s own files are
SCHEDULER_FILE = 'module.exports = require("./cjs/scheduler.production.js");\n'


@pytest.mark.parametrize("package", scan.REACT_PACKAGES)
def test_a_react_package_folder_in_the_tree_is_refused_without_any_marker(
    tmp_path: Path, package: str
) -> None:
    # I23 reads the file system for a package by name, not only for strings: `scheduler`'s files hold none
    tree = make_tree(
        tmp_path / "fs",
        {
            f"app/node_modules/{package}/package.json": f'{{"name": "{package}", "version": "1.0.0"}}\n',
            f"app/node_modules/{package}/index.js": SCHEDULER_FILE,
        },
    )
    findings = scan.tree_findings(tree)
    assert kinds(findings) == {"react-package"}
    assert {f.where.rsplit("/", 1)[-1] for f in findings} <= {package, "package.json"}
    assert any(package in f.where for f in findings)
    # and the whole scan, with an SBOM that does not list it, still fails on the tree alone
    assert scan.scan(make_sbom(*CLEAN), tree) != []


def test_a_react_package_nested_or_named_only_in_its_package_json_is_refused(
    tmp_path: Path,
) -> None:
    tree = make_tree(
        tmp_path / "fs",
        {
            # nested under another package's own node_modules
            "app/node_modules/express/node_modules/scheduler/package.json": '{"name": "scheduler"}\n',
            # the folder renamed, the package.json still says what it is
            "app/vendor/renamed/package.json": '{"name": "React-DOM", "version": "19.1.0"}\n',
        },
    )
    assert {f.where for f in scan.tree_findings(tree)} >= {
        "app/node_modules/express/node_modules/scheduler",
        "app/vendor/renamed/package.json",
    }
    assert kinds(scan.tree_findings(tree)) == {"react-package"}


def test_package_names_in_the_tree_are_matched_not_substrings(tmp_path: Path) -> None:
    tree = make_tree(
        tmp_path / "fs",
        {
            "app/node_modules/react-dom-like/package.json": '{"name": "react-dom-like"}\n',
            "app/node_modules/scheduler-lite/package.json": '{"name": "scheduler-lite"}\n',
            "app/node_modules/preact/package.json": '{"name": "preact"}\n',
            # the scoped type package is not React; `--omit=dev` would not carry it
            "app/node_modules/@types/react/package.json": '{"name": "@types/react"}\n',
            "app/apps/pages/react/notes.txt": "a folder called react that is not a package\n",
            "app/apps/pages/broken/package.json": "{not json",
        },
    )
    assert scan.tree_findings(tree) == []


def test_the_scan_stays_under_app_and_does_not_follow_links(tmp_path: Path) -> None:
    tree = make_tree(
        tmp_path / "fs", {"usr/lib/node_modules/react/index.js": 'Symbol.for("react.element")'}
    )
    assert (tree / "usr/lib/node_modules/react/index.js").is_file()
    (tree / "app/escape").symlink_to(
        "../usr/lib/node_modules/react"
    )  # a link out of /app is not followed
    assert scan.tree_findings(tree) == []


def test_a_finding_never_prints_the_line_it_came_from(tmp_path: Path) -> None:
    token = secrets.token_hex(16)  # generated now; nothing in the repository looks like a secret
    tree = make_tree(
        tmp_path / "fs",
        {
            "app/apps/pages/dist/server/config.js": f'const k = "{token}"; require("react/jsx-runtime");\n'
        },
    )
    (finding,) = scan.tree_findings(tree)
    assert token not in repr(finding) and token not in finding.render()


# --- plant 3: an empty or wrong SBOM, and a tree that is not the image -----------------------------------------


@pytest.mark.parametrize(
    "sbom",
    [
        {},
        {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": []},
        {"bomFormat": "CycloneDX", "specVersion": "1.6"},
        {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": None},
        make_sbom(),  # the OS packages only: trivy was pointed at a different image
        make_sbom(("express", "4.21.2")),  # no nunjucks
        make_sbom(("nunjucks", "3.2.4")),  # no express
        make_sbom(("express-session", "1.18.1"), ("nunjucks-like", "1.0.0")),  # near-names are not the names
        [],
        "components",
        None,
    ],
    ids=["empty-object", "no-components", "missing-components", "null-components", "os-only", "no-nunjucks",
         "no-express", "near-names", "a-list", "a-string", "null"],
)  # fmt: skip
def test_an_empty_or_wrong_sbom_is_refused_not_passed(tmp_path: Path, sbom: object) -> None:
    findings = scan.scan(
        sbom, make_tree(tmp_path / "fs")
    )  # a perfectly clean tree: the SBOM alone fails it
    assert findings != []
    assert kinds(findings) <= {"missing-package", "bad-sbom"}


@pytest.mark.parametrize(
    "sbom",
    [{}, {"components": []}, {"specVersion": "1.6"}, {"components": None}, [], "components", None],
    ids=[
        "empty-object",
        "no-components",
        "missing-components",
        "null-components",
        "a-list",
        "a-string",
        "null",
    ],
)
def test_an_sbom_with_no_component_list_is_named_as_such(sbom: object) -> None:
    # not left to the missing-package findings: an SBOM that is not a component list says so itself
    assert "bad-sbom" in kinds(scan.sbom_findings(sbom))


def test_the_missing_packages_are_named() -> None:
    findings = scan.sbom_findings(make_sbom(("express", "4.21.2")))
    assert [(f.kind, f.where) for f in findings] == [("missing-package", "nunjucks")]
    findings = scan.sbom_findings(make_sbom())
    assert {f.where for f in findings} == {"express", "nunjucks"}


@pytest.mark.parametrize(
    "component",
    [
        _component("react", "19.1.0"),
        _component("react-dom", "19.1.0"),
        _component("scheduler", "0.26.0"),
        # the name field blank, the purl still says what it is
        {"type": "library", "name": "", "purl": "pkg:npm/react-dom@19.1.0"},
        # the name in capitals
        {"type": "library", "name": "React", "purl": "pkg:npm/react@19.1.0"},
        # nested under another component
        {"type": "application", "name": "node-pkg", "components": [_component("react", "19.1.0")]},
    ],
    ids=["react", "react-dom", "scheduler", "purl-only", "capitalised", "nested"],
)
def test_each_react_package_in_the_sbom_is_refused(component: dict[str, object]) -> None:
    findings = scan.sbom_findings(make_sbom(*CLEAN, extra=[component]))
    assert kinds(findings) == {"react-package"}


def test_a_tree_without_app_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "fs"
    empty.mkdir()
    assert kinds(scan.tree_findings(empty)) == {"no-app"}
    (empty / "app").write_text("a file, not a folder", encoding="utf-8")
    assert kinds(scan.tree_findings(empty)) == {"no-app"}


# --- the exported tar, and the thin main --------------------------------------------------------------------


def _tar(entries: list[tarfile.TarInfo], data: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for info in entries:
            payload = (data or {}).get(info.name)
            if payload is not None:
                info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload) if payload is not None else None)
    return buffer.getvalue()


def _file(name: str) -> tarfile.TarInfo:
    return tarfile.TarInfo(name)


def _link(name: str, target: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE
    info.linkname = target
    return info


def test_extraction_keeps_only_app_and_survives_the_systems_own_links(tmp_path: Path) -> None:
    # `docker export` of a Debian image holds absolute links (`/bin/sh -> /usr/bin/dash`-like)
    tar = tmp_path / "fs.tar"
    tar.write_bytes(
        _tar(
            [
                _link("bin/sh", "/usr/bin/dash"),
                _file("etc/passwd"),
                _file("app/apps/pages/dist/server/main.js"),
                _link("app/node_modules/@ospreyflow/pages", "../../apps/pages"),
                _file("application/not-app.txt"),
            ],
            {
                "etc/passwd": b"root",
                "app/apps/pages/dist/server/main.js": b"x",
                "application/not-app.txt": b"y",
            },
        )
    )
    dest = tmp_path / "out"
    dest.mkdir()
    scan.extract_app(tar, dest)
    assert (dest / "app/apps/pages/dist/server/main.js").read_bytes() == b"x"
    assert (dest / "app/node_modules/@ospreyflow/pages").is_symlink()
    assert (
        not (dest / "etc").exists()
        and not (dest / "bin").exists()
        and not (dest / "application").exists()
    )


@pytest.mark.parametrize(
    "bad",
    [
        _link("app/out", "../../../escape"),
        _link("app/abs", "/etc/passwd"),
        _file("app/../../escape.txt"),
    ],
    ids=["link-out", "absolute-link", "dot-dot-name"],
)
def test_extraction_refuses_a_member_that_would_escape(
    tmp_path: Path, bad: tarfile.TarInfo
) -> None:
    tar = tmp_path / "fs.tar"
    tar.write_bytes(_tar([bad], {bad.name: b"z"} if bad.isfile() else None))
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(scan.ScanError):
        scan.extract_app(tar, dest)
    assert not (tmp_path / "escape.txt").exists() and not (tmp_path.parent / "escape.txt").exists()


def _export_of(files: dict[str, str] | None) -> Callable[[str, Path], None]:
    def export(image: str, dest: Path) -> None:
        assert image == "ospreyflow/pages:ci"
        make_tree(dest, files)

    return export


def _sbom_file(tmp_path: Path, sbom: object) -> Path:
    path = tmp_path / "pages.cdx.json"
    path.write_text(json.dumps(sbom), encoding="utf-8")
    return path


def test_main_passes_a_clean_image(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = scan.main(
        ["--image", "ospreyflow/pages:ci", "--sbom", str(_sbom_file(tmp_path, make_sbom(*CLEAN)))],
        export=_export_of(None),
    )
    assert code == 0
    assert "no react" in capsys.readouterr().out.lower()


def test_main_names_each_finding_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    token = secrets.token_hex(16)
    code = scan.main(
        [
            "--image",
            "ospreyflow/pages:ci",
            "--sbom",
            str(_sbom_file(tmp_path, make_sbom(*UNSCOPED))),
        ],
        export=_export_of(
            {"app/apps/pages/dist/public/bundle.js": f'{token}\nrequire("react/jsx-runtime")\n'}
        ),
    )
    out = capsys.readouterr()
    text = out.out + out.err
    assert code == 1
    for named in (
        "react-package",
        "react-dom",
        "scheduler",
        "react-marker",
        "app/apps/pages/dist/public/bundle.js",
    ):
        assert named in text
    assert token not in text


@pytest.mark.parametrize(
    "content", ["", "not json", "[]", "{}"], ids=["empty-file", "not-json", "list", "object"]
)
def test_main_fails_on_an_sbom_that_is_empty_or_unreadable(
    tmp_path: Path, content: str, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "pages.cdx.json"
    path.write_text(content, encoding="utf-8")
    assert (
        scan.main(["--image", "ospreyflow/pages:ci", "--sbom", str(path)], export=_export_of(None))
        == 1
    )
    out = capsys.readouterr()
    assert "sbom" in (out.out + out.err).lower()


def test_main_fails_when_the_sbom_file_is_missing(tmp_path: Path) -> None:
    missing = tmp_path / "absent.cdx.json"
    assert (
        scan.main(
            ["--image", "ospreyflow/pages:ci", "--sbom", str(missing)], export=_export_of(None)
        )
        == 1
    )


def test_main_refuses_an_image_that_is_an_option(tmp_path: Path) -> None:
    sbom = _sbom_file(tmp_path, make_sbom(*CLEAN))
    assert scan.main(["--image=--privileged", "--sbom", str(sbom)], export=_export_of(None)) != 0


def test_a_failed_export_fails_the_scan_it_does_not_pass_it(tmp_path: Path) -> None:
    def broken(image: str, dest: Path) -> None:
        raise scan.ScanError("docker export failed")

    sbom = _sbom_file(tmp_path, make_sbom(*CLEAN))
    assert scan.main(["--image", "ospreyflow/pages:ci", "--sbom", str(sbom)], export=broken) == 1


class FakeDocker:
    """`subprocess.run` as the docker CLI answers it, refusals included: `create` of an image that is not
    there fails; `export` and `rm` of a container that was not created (or is already removed) fail."""

    def __init__(self, *, export_fails: bool = False, known: str = "ospreyflow/pages:ci") -> None:
        self.calls: list[list[str]] = []
        self.containers: set[str] = set()
        self.export_fails = export_fails
        self.known = known

    def __call__(self, args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[0] == "docker" and kwargs.get("shell") is not True
        self.calls.append(args)
        verb = args[1]
        if verb == "create":
            if args[-1] != self.known:
                raise subprocess.CalledProcessError(1, args, stderr="Unable to find image")
            self.containers.add("c0ffee")
            return subprocess.CompletedProcess(args, 0, "c0ffee\n", "")
        if args[-1] not in self.containers:
            raise subprocess.CalledProcessError(1, args, stderr="No such container")
        if verb == "export":
            if self.export_fails:
                raise subprocess.CalledProcessError(1, args, stderr="export failed")
            out = Path(
                args[args.index("-o") + 1] if "-o" in args else args[args.index("--output") + 1]
            )
            out.write_bytes(
                _tar([_file("app/apps/pages/package.json")], {"app/apps/pages/package.json": b"{}"})
            )
        if verb == "rm":
            self.containers.discard(args[-1])
        return subprocess.CompletedProcess(args, 0, "", "")


def test_export_image_exports_the_app_and_removes_its_container(tmp_path: Path) -> None:
    docker = FakeDocker()
    scan.export_image("ospreyflow/pages:ci", tmp_path, run=docker)
    assert (tmp_path / "app/apps/pages/package.json").is_file()
    assert [c[1] for c in docker.calls] == ["create", "export", "rm"]
    assert docker.containers == set()


def test_export_image_removes_its_container_when_the_export_fails(tmp_path: Path) -> None:
    docker = FakeDocker(export_fails=True)
    with pytest.raises(scan.ScanError):
        scan.export_image("ospreyflow/pages:ci", tmp_path, run=docker)
    assert docker.containers == set()
    assert docker.calls[-1][1] == "rm"


def test_export_image_of_an_image_that_is_not_there_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(scan.ScanError):
        scan.export_image("ospreyflow/other:ci", tmp_path, run=FakeDocker())
