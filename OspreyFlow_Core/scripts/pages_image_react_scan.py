"""The built `pages` image carries no React (ADR-152 Amendment 1, invariant I23; slice PL6).

`python -m scripts.pages_image_react_scan --image <tag> --sbom <file>` reads two things about the
image `apps/pages/Dockerfile` makes: the CycloneDX SBOM that `trivy image --format cyclonedx` wrote
to `<file>`, and the image's own file system (`docker create`, `docker export`; the part under
`/app` is extracted to a temporary folder that is removed). It exits 1, naming each finding, when:

  * the SBOM names a component `react`, `react-dom` or `scheduler`;
  * a file under `/app` holds `react/jsx-runtime`, `react/jsx-dev-runtime` or one of React's element
    markers (the `react.element` and `react.transitional.element` symbols, or `Symbol.for("react.`);
  * the SBOM does not name both `express` and `nunjucks`: an empty SBOM, one for the wrong image or
    one that was never read is a failure, not a pass (rule 15);
  * the image's file system has no `/app`, a file under it cannot be read, or the image cannot be
    read.

A finding names its kind and where (a package, or a path in the image); it never prints a line of a
file, so a secret that shares a line with a marker is not echoed.

The pure functions (`sbom_findings`, `tree_findings`, `scan`, `extract_app`) take a parsed SBOM and
a folder and touch no Docker; the test drives those. `export_image` and `main` are the thin part
that calls `docker`. Names are matched, not substrings: a package called `react-dom-like` or a file
that says "reaction" is not React. The owner wires the scan into `make ci` (`trivy-image-pages`).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

REACT_PACKAGES = ("react", "react-dom", "scheduler")
REQUIRED_PACKAGES = ("express", "nunjucks")
APP = "app"  # the image's /app, as `docker export` names it (no leading slash)

# What React leaves in code that uses it. A name must not be glued to a longer one, so
# `preact/jsx-runtime` and `react.elements` are not matches.
_MARKERS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("react/jsx-runtime", re.compile(rb"(?<![\w-])react/jsx-runtime(?![\w-])")),
    ("react/jsx-dev-runtime", re.compile(rb"(?<![\w-])react/jsx-dev-runtime(?![\w-])")),
    ("react.element", re.compile(rb"(?<![\w-])react\.element(?![\w-])")),
    (
        "react.transitional.element",
        re.compile(rb"(?<![\w-])react\.transitional\.element(?![\w-])"),
    ),
    ('Symbol.for("react.', re.compile(rb"Symbol\.for\(\s*[\"'`]react\.")),
)


class ScanError(Exception):
    """The image or its export could not be read: nothing can be said about it (a failure)."""


@dataclass(frozen=True)
class Finding:
    kind: str  # react-package, react-marker, missing-package, bad-sbom, no-app, unreadable
    where: str  # a package name, or a path inside the image
    detail: str

    def render(self) -> str:
        return f"{self.kind}: {self.where}: {self.detail}"


# --- the SBOM --------------------------------------------------------------------------------


def _walk(components: object) -> Iterator[dict[str, object]]:
    if not isinstance(components, list):
        return
    for component in components:
        if isinstance(component, dict):
            yield component
            yield from _walk(component.get("components"))


def _npm_name_from_purl(purl: object) -> str | None:
    if not isinstance(purl, str) or not purl.lower().startswith("pkg:npm/"):
        return None
    rest = unquote(re.split(r"[?#]", purl[len("pkg:npm/") :], maxsplit=1)[0])
    at = rest.rfind("@")  # the version's; a scope's `@` is the first character
    return (rest[:at] if at > 0 else rest).lower() or None


def _names_of(component: dict[str, object]) -> set[str]:
    names: set[str] = set()
    name, group = component.get("name"), component.get("group")
    if isinstance(name, str) and name.strip():
        full = f"{group}/{name}" if isinstance(group, str) and group.strip() else name
        names.add(full.strip().lower())
    purl_name = _npm_name_from_purl(component.get("purl"))
    if purl_name:
        names.add(purl_name)
    return names


def _components(sbom: object) -> list[object] | None:
    components = sbom.get("components") if isinstance(sbom, dict) else None
    return components if isinstance(components, list) and components else None


def sbom_package_names(sbom: object) -> set[str]:
    """Every component's name (scope included: `@types/react`), lower case, nested ones too."""
    names: set[str] = set()
    for component in _walk(_components(sbom)):
        names |= _names_of(component)
    return names


def sbom_findings(sbom: object) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(sbom, dict):
        findings.append(Finding("bad-sbom", "sbom", "the SBOM is not a JSON object"))
    elif _components(sbom) is None:
        findings.append(
            Finding(
                "bad-sbom", "sbom", "the SBOM lists no components (empty, or not trivy's output)"
            )
        )
    names = sbom_package_names(sbom)
    findings += [
        Finding("react-package", name, "the SBOM names a React package")
        for name in REACT_PACKAGES
        if name in names
    ]
    findings += [
        Finding(
            "missing-package",
            name,
            "the SBOM does not name it, so it is not the pages image's SBOM",
        )
        for name in REQUIRED_PACKAGES
        if name not in names
    ]
    return findings


# --- the exported file system ----------------------------------------------------------------


def tree_findings(root: Path) -> list[Finding]:
    """Files under `root/app` holding a React marker. Links are not followed; nothing outside
    /app is read."""
    app = root / APP
    if app.is_symlink() or not app.is_dir():
        return [Finding("no-app", f"/{APP}", "the image's file system has no /app to scan")]
    findings: list[Finding] = []
    for folder, subfolders, files in os.walk(app, followlinks=False):
        subfolders.sort()
        for name in sorted(files):
            path = Path(folder) / name
            if path.is_symlink() or not path.is_file():
                continue
            where = path.relative_to(root).as_posix()
            try:
                data = path.read_bytes()
            except OSError as error:
                findings.append(
                    Finding(
                        "unreadable", where, f"the file could not be read ({type(error).__name__})"
                    )
                )
                continue
            hits = [label for label, pattern in _MARKERS if pattern.search(data)]
            if hits:
                findings.append(Finding("react-marker", where, "holds " + ", ".join(hits)))
    return findings


def scan(sbom: object, root: Path) -> list[Finding]:
    return sbom_findings(sbom) + tree_findings(root)


# --- the image -------------------------------------------------------------------------------


def extract_app(tar_path: Path, dest: Path) -> None:
    """Extract only `app/...` from an exported file system into `dest`, with tarfile's `data`
    filter: a member that would land outside `dest`, or a link that points outside it, is a
    `ScanError`. The system's own absolute links (`bin/sh`) are never extracted, so they cannot
    trip the filter."""
    try:
        with tarfile.open(tar_path, mode="r:") as archive:
            for member in archive:
                name = member.name.removeprefix("./")
                if name == APP or name.startswith(APP + "/"):
                    archive.extract(member, dest, filter="data")
    except (tarfile.TarError, OSError) as error:
        raise ScanError(
            f"the image's export could not be extracted safely: {type(error).__name__}: {error}"
        ) from error


Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def _docker(run: Runner, *args: str) -> str:
    try:
        done = run(["docker", *args], check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise ScanError("docker is not installed or not on the path") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip().splitlines()
        raise ScanError(
            f"`docker {args[0]}` failed: {detail[-1] if detail else 'no message'}"
        ) from error
    return done.stdout or ""


def export_image(image: str, dest: Path, *, run: Runner = subprocess.run) -> None:
    """`docker create`, `docker export`, extract `/app` into `dest`; the container is always
    removed."""
    if not image or image.startswith("-"):
        raise ScanError(f"{image!r} is not an image name")
    container = _docker(run, "create", image).strip()
    if not re.fullmatch(r"[0-9a-f]+", container):
        raise ScanError("`docker create` did not give a container id")
    try:
        with tempfile.TemporaryDirectory(prefix="pages-scan-tar-") as scratch:
            tar_path = Path(scratch) / "fs.tar"
            _docker(run, "export", "-o", str(tar_path), container)
            extract_app(tar_path, dest)
    finally:
        try:
            _docker(run, "rm", container)
        except ScanError as error:
            print(
                f"pages image react scan: could not remove container {container}: {error}",
                file=sys.stderr,
            )


# --- the command -----------------------------------------------------------------------------


def _read_sbom(path: Path) -> tuple[object, list[Finding]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return None, [
            Finding(
                "bad-sbom", str(path), f"the SBOM file could not be read ({type(error).__name__})"
            )
        ]
    try:
        return json.loads(text), []
    except ValueError:
        return None, [Finding("bad-sbom", str(path), "the SBOM file is empty or not valid JSON")]


def main(
    argv: Sequence[str] | None = None, *, export: Callable[[str, Path], None] = export_image
) -> int:
    parser = argparse.ArgumentParser(
        prog="pages_image_react_scan", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--image", required=True, help="the built image's tag, e.g. ospreyflow/pages:ci"
    )
    parser.add_argument(
        "--sbom", required=True, type=Path, help="the CycloneDX file `trivy image` wrote"
    )
    args = parser.parse_args(argv)
    if args.image.startswith("-"):
        print(f"pages image react scan: {args.image!r} is not an image name", file=sys.stderr)
        return 2

    sbom, findings = _read_sbom(args.sbom)
    try:
        with tempfile.TemporaryDirectory(prefix="pages-scan-fs-") as scratch:
            root = Path(scratch)
            export(args.image, root)
            # a file that could not be read has its own finding; the generic one would repeat it
            findings += [f for f in sbom_findings(sbom) if not (findings and f.kind == "bad-sbom")]
            findings += tree_findings(root)
    except ScanError as error:
        print(
            f"pages image react scan: cannot read the image {args.image}: {error}", file=sys.stderr
        )
        return 1

    if findings:
        print(
            f"pages image react scan: FAILED, {len(findings)} finding(s) in {args.image}",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  - {finding.render()}", file=sys.stderr)
        return 1
    named = " and ".join(REQUIRED_PACKAGES)
    print(f"pages image react scan: no React in {args.image} (the SBOM names {named})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
