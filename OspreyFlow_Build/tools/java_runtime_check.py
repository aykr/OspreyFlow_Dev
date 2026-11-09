"""The Conduit image's Java runtime is the one its Dockerfile declares, and Temurin 21's newest.

ADR-147 Amendment 2 (the owner's ruling 1): the Conduit's image carries a jlinked Temurin 21,
pinned by digest (`OspreyFlow_Core/services/api/Dockerfile`). `trivy image` does not see a runtime
unpacked from a tarball and derived by `jlink`: no distribution package and no jar names it, so a
Temurin with known CVEs scans clean (shown on the test server, `process/lanes/platform/gates/`).
This check stands in that gap. The Dockerfile declares the runtime's version in a label,
`org.ospreyflow.runtime.java.version`, beside its licence label; and:

- the built image must run that version (`--image`): `/opt/java/release`'s `JAVA_VERSION` (all
  `jlink` writes there besides `MODULES`) must be the label's version, and `java -version`'s
  build the label whole, so the label cannot drift from the digest it describes;
- that version must be Temurin 21's newest general-availability release (`--latest`, from
  Adoptium's API), so a quarterly update not taken fails the image's scan as a CVE would.

Run by `make ci`'s `java-runtime-check` (this folder's Makefile, never Core's: Core stands
alone, ADR-114 Amendment 2), after `core-check` has built the image, where Docker and the network
are. Without `--image` or `--latest` it checks only that the label is there and well formed.
Anything it cannot read (the image, or Adoptium's answer) is a refusal in words, never a pass.
Each refusal shown red in `tests/licence_check/test_java_runtime_check.py` (rule 15).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from tools.licence_check import label_pairs

DOCKERFILE = (
    Path(__file__).resolve().parents[2] / "OspreyFlow_Core" / "services" / "api" / "Dockerfile"
)
LABEL = "org.ospreyflow.runtime.java.version"
RELEASE_LINE = re.compile(r"""^JAVA_VERSION\s*=\s*["']?([^"'\s]+)["']?\s*$""", re.M)
#: `java -version`'s second line, as
#: `OpenJDK Runtime Environment Temurin-21.0.13+9 (build 21.0.13+9-LTS)`.
BUILD_LINE = re.compile(r"^.*Runtime Environment.*\(build ([^)\s]+)\)\s*$", re.M)
VERSION = re.compile(r"^(\d+(?:\.\d+)*)\+(\d+)(?:-LTS)?$")
#: Temurin 21's general-availability releases, newest first (the same query Adoptium's site makes).
ADOPTIUM = (
    "https://api.adoptium.net/v3/info/release_names?architecture=x64&heap_size=normal&image_type=jdk"
    "&os=linux&page=0&page_size=20&project=jdk&release_type=ga&semver=false&sort_method=DATE"
    "&sort_order=DESC&vendor=eclipse&version=%5B21%2C22%29"
)


def version_key(version: str) -> tuple[tuple[int, ...], int]:
    """`21.0.12.1+1` as `((21, 0, 12, 1), 1)`, ordered as Temurin numbers its releases; a release
    name's `jdk-` and a runtime's `-LTS` are dropped. A version of no such shape is refused."""
    match = VERSION.match(version.removeprefix("jdk-"))
    if match is None:
        raise ValueError(f"not a Temurin version: {version!r}")
    return tuple(int(part) for part in match.group(1).split(".")), int(match.group(2))


def declared_version(dockerfile: str) -> str | None:
    """The label's value, read as `licence-check` reads the licence labels (`label_pairs`)."""
    found = [value for key, value in label_pairs(dockerfile) if key == LABEL]
    return found[0] if len(found) == 1 else None


def release_version(release: str) -> str | None:
    """`/opt/java/release`'s `JAVA_VERSION`: the version without its build (`21.0.12.1`)."""
    found = RELEASE_LINE.findall(release)
    return found[0] if len(found) == 1 else None


def build_version(java_version: str) -> str | None:
    """`java -version`'s build, as the label writes it (`21.0.12.1+1`)."""
    found = BUILD_LINE.findall(java_version)
    return found[0].removesuffix("-LTS") if len(found) == 1 else None


Runtime = tuple[str, str]  # (/opt/java/release, java -version's output)


def problems(dockerfile: str, runtime: Runtime | None, latest: list[str] | None) -> list[str]:
    """Every reason the image's runtime fails, in words; none when it passes."""
    declared = declared_version(dockerfile)
    if declared is None:
        return ["the api Dockerfile declares no single org.ospreyflow.runtime.java.version label"]
    try:
        pinned = version_key(declared)
    except ValueError as exc:
        return [f"the api Dockerfile's java version label: {exc}"]
    found: list[str] = []
    if runtime is not None:
        release, java_version = runtime
        named = release_version(release)
        running = build_version(java_version)
        if named is None:
            found.append("the image's /opt/java/release names no single JAVA_VERSION")
        elif named != declared.split("+")[0]:
            found.append(f"the image's /opt/java/release names {named}, its Dockerfile {declared}")
        if running is None:
            found.append("the image's java -version names no single build")
        elif running != declared:
            found.append(f"the image runs Java {running}, its Dockerfile declares {declared}")
    if latest is not None:
        unshaped = [name for name in latest if not _is_version(name)]
        if not latest:
            found.append("Adoptium named no Temurin 21 release")
        elif unshaped:
            found.append(f"Adoptium named a release of no Temurin shape: {unshaped[0]!r}")
        else:
            newest = max(latest, key=version_key)
            if version_key(newest) > pinned:
                found.append(
                    f"Temurin {newest.removeprefix('jdk-')} is out and the image pins {declared}: "
                    "repin the api Dockerfile's java stage by digest and its label"
                )
    return found


def _is_version(name: object) -> bool:
    return isinstance(name, str) and VERSION.match(name.removeprefix("jdk-")) is not None


def _image_runtime(image: str) -> Runtime:
    def run(*argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", argv[0], image, *argv[1:]],
            check=True, capture_output=True, text=True,
        )  # fmt: skip

    return run("cat", "/opt/java/release").stdout, run("java", "-version").stderr


def _latest() -> list[str]:
    """Adoptium's release names. Its front refuses Python's own User-Agent (403), so a client name
    is sent. An answer of any other shape raises, and `main` refuses it."""
    request = urllib.request.Request(
        ADOPTIUM, headers={"User-Agent": "ospreyflow-java-runtime-check"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (a fixed https URL)
        releases = json.load(response)["releases"]
    if not isinstance(releases, list):
        raise ValueError(f"releases is {type(releases).__name__}, not a list")
    return releases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.java_runtime_check")
    parser.add_argument("--dockerfile", type=Path, default=DOCKERFILE)
    parser.add_argument("--image", help="a built api image whose runtime is read")
    parser.add_argument("--latest", action="store_true", help="compare with Adoptium's newest")
    args = parser.parse_args(argv)
    # Whatever stops a read (no daemon, no such image, a network failure, a truncated or reshaped
    # answer) is said in words and fails the check: an unread runtime or answer never passes.
    try:
        release = _image_runtime(args.image) if args.image else None
    except Exception as exc:  # noqa: BLE001 (every failure is a refusal)
        print(f"java-runtime-check: the image's runtime could not be read: {exc}", file=sys.stderr)
        return 1
    try:
        latest = _latest() if args.latest else None
    except Exception as exc:  # noqa: BLE001 (every failure is a refusal)
        print(f"java-runtime-check: Adoptium could not be read: {exc!r}", file=sys.stderr)
        return 1
    found = problems(args.dockerfile.read_text(), release, latest)
    for line in found:
        print(f"java-runtime-check: {line}", file=sys.stderr)
    if not found:
        print(f"java-runtime-check: Java {declared_version(args.dockerfile.read_text())} declared"
              + (", the image runs it" if release is not None else "")
              + (", Temurin 21's newest" if latest is not None else ""))  # fmt: skip
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
