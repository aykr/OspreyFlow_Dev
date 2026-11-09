"""The Conduit image's Java runtime is the one its Dockerfile declares, pinned at its tag's current
digest.

ADR-147 Amendment 2 (the owner's ruling 1): the Conduit's image carries a jlinked Temurin 21,
pinned by digest (`OspreyFlow_Core/services/api/Dockerfile`). `trivy image` does not see a runtime
unpacked from a tarball and derived by `jlink`: no distribution package and no jar names it, so a
Temurin with known CVEs scans clean (shown on the test server, `process/lanes/platform/gates/`).
This check stands in that gap. The Dockerfile declares the runtime's version in a label,
`org.ospreyflow.runtime.java.version`, beside its licence label; and:

- the built image must run that version (`--image`): `/opt/java/release`'s `JAVA_VERSION` (all
  `jlink` writes there besides `MODULES`) must be the label's version, and `java -version`'s
  build the label whole, so the label cannot drift from the digest it describes;
- the Java stage's pinned digest must be the one its tag (`eclipse-temurin:21-jdk`) resolves to
  on Docker Hub now (`--current`), so an update not taken fails as a CVE would. The orchestrator's
  call: Docker Hub's tag, not Adoptium's release list, because the tag moves only once there is an
  image to repin to. So CI is never red for days with nothing to take, and an old commit re-run
  is red only if its pin is no longer the tag's.

`--image` runs in GitHub CI's `trivy-image-api` job, after the build (`P5_ci.diff`, the owner's
file), and in Build's `make ci` after `core-check` (`JAVA_RUNTIME_CI.diff`), with `--current`.
Never in Core's Makefile, which stands alone (ADR-114 Amendment 2). Without either flag it checks
only that the label is there and well formed. Anything it cannot read (the image, the Dockerfile's
pinned tag, or Docker Hub's answer) is a refusal in words, never a pass.
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

from tools.licence_check import _instructions, label_pairs

DOCKERFILE = (
    Path(__file__).resolve().parents[2] / "OspreyFlow_Core" / "services" / "api" / "Dockerfile"
)
LABEL = "org.ospreyflow.runtime.java.version"
RELEASE_LINE = re.compile(r"""^JAVA_VERSION\s*=\s*["']?([^"'\s]+)["']?\s*$""", re.M)
#: `java -version`'s second line, as
#: `OpenJDK Runtime Environment Temurin-21.0.13+9 (build 21.0.13+9-LTS)`.
BUILD_LINE = re.compile(r"^.*Runtime Environment.*\(build ([^)\s]+)\)\s*$", re.M)
VERSION = re.compile(r"^(\d+(?:\.\d+)*)\+(\d+)(?:-LTS)?$")
#: The Java stage, as the api Dockerfile writes it: an official image's tag pinned by digest.
JAVA_STAGE = re.compile(
    r"^FROM\s+(?:docker\.io/)?(?:library/)?(?P<repo>[a-z0-9._-]+):(?P<tag>[\w.-]+)"
    r"@(?P<digest>sha256:[0-9a-f]{64})\s+AS\s+java\s*$",
    re.I,
)
#: Docker Hub's answer for an official image's tag: its `digest` is the multi-architecture index's.
HUB_TAG = "https://hub.docker.com/v2/repositories/library/{repo}/tags/{tag}"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


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


def java_stage(dockerfile: str) -> tuple[str, str, str] | None:
    """The Java stage's (repository, tag, digest), read from the Dockerfile's instructions."""
    found = [
        m.group("repo", "tag", "digest")
        for m in map(JAVA_STAGE.match, _instructions(dockerfile))
        if m
    ]
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


def problems(dockerfile: str, runtime: Runtime | None, current: str | None) -> list[str]:
    """Every reason the image's runtime fails, in words; none when it passes."""
    declared = declared_version(dockerfile)
    if declared is None:
        return ["the api Dockerfile declares no single org.ospreyflow.runtime.java.version label"]
    try:
        version_key(declared)  # the label of Temurin's shape, or refused
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
    if current is not None:
        stage = java_stage(dockerfile)
        if stage is None:
            found.append("the api Dockerfile has no single Java stage pinned by digest")
        elif not DIGEST.match(current):
            found.append(f"Docker Hub named no digest for {stage[0]}:{stage[1]}: {current!r}")
        elif current != stage[2]:
            found.append(
                f"{stage[0]}:{stage[1]} now resolves to {current} and the image pins {stage[2]}: "
                "repin the api Dockerfile's java stage by digest and its label"
            )
    return found


def _image_runtime(image: str) -> Runtime:
    def run(*argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", argv[0], image, *argv[1:]],
            check=True, capture_output=True, text=True,
        )  # fmt: skip

    return run("cat", "/opt/java/release").stdout, run("java", "-version").stderr


def _current(dockerfile: str) -> str:
    """The digest the Dockerfile's Java tag resolves to on Docker Hub now. An answer of any other
    shape raises, and `main` refuses it; with no pinned Java stage there is nothing to ask."""
    stage = java_stage(dockerfile)
    if stage is None:
        return ""
    url = HUB_TAG.format(repo=stage[0], tag=stage[1])
    request = urllib.request.Request(url, headers={"User-Agent": "ospreyflow-java-runtime-check"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (a fixed https URL)
        digest = json.load(response)["digest"]
    if not isinstance(digest, str):
        raise ValueError(f"digest is {type(digest).__name__}, not a string")
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.java_runtime_check")
    parser.add_argument("--dockerfile", type=Path, default=DOCKERFILE)
    parser.add_argument("--image", help="a built api image whose runtime is read")
    parser.add_argument(
        "--current", action="store_true", help="compare the pin with its tag's digest now"
    )
    args = parser.parse_args(argv)
    # Whatever stops a read (no daemon, no such image, a network failure, a truncated or reshaped
    # answer) is said in words and fails the check: an unread runtime or answer never passes.
    try:
        release = _image_runtime(args.image) if args.image else None
    except Exception as exc:  # noqa: BLE001 (every failure is a refusal)
        print(f"java-runtime-check: the image's runtime could not be read: {exc}", file=sys.stderr)
        return 1
    dockerfile = args.dockerfile.read_text()
    try:
        current = _current(dockerfile) if args.current else None
    except Exception as exc:  # noqa: BLE001 (every failure is a refusal)
        print(f"java-runtime-check: Docker Hub could not be read: {exc!r}", file=sys.stderr)
        return 1
    found = problems(dockerfile, release, current)
    for line in found:
        print(f"java-runtime-check: {line}", file=sys.stderr)
    if not found:
        said = [f"Java {declared_version(dockerfile)} declared"]
        said += ["the image runs it"] * (release is not None)
        said += ["pinned at its tag's current digest"] * (current is not None)
        print("java-runtime-check: " + ", ".join(said))
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
