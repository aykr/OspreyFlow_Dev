"""`06_DECISIONS.md` ADR-049 Stage 2 §5b's exit test #3, automated — not a placeholder for it.

`make bundle`'s own echo has cited this file since before it existed (`CLAUDE.md` rule 12: "A
citation to a test that does not exist is worse than no citation, because it reads as a
guarantee"). This is that file, built after the citation, not before it.

**Opt-in via `OSPREY_TEST_DIST_BUNDLE=1`** — it needs Docker, builds and archives every owned
image the rendered stack runs (several gigabytes), and brings up the real `local-lite` stack,
which takes minutes rather than seconds. Not part of the fast unit tier; a real, slow,
`make ci`-adjacent proof, the same reasoning `tests/harness/test_restore_exit_test.py` and
`tests/harness/test_workspace_bundle.py` already use for their own opt-in gates.

**What this proves, and why "for real" matters.** Builds the bundle with `--images`, unpacks the
tarball into a directory with no relationship to this checkout at all, `docker load`s every
archive, and runs `harness.apply --no-build` pointed at nothing but the bundle's own
`osprey.yaml.example` and the images just loaded. `06_DECISIONS.md`'s own words: "if apply cannot
run from the bundle alone, that is a finding to fix, not to note." It was: a real run against a
real `--out-root` outside this repository's own `deploy/generated/<profile>/` convention failed
with `IsADirectoryError: ... 'osprey.yaml'`, because the rendered `compose.yaml` mounted
`../../../osprey.yaml` — a path assuming the rendered output always sits exactly three directories
below wherever `osprey.yaml` lives, true of this repository's own layout and false of an arbitrary
install directory. `harness/render.py`'s `./osprey.yaml` mount plus `write_config_copy` (see
`tests/harness/test_render.py`'s own two named cases) is the fix this test would have caught
missing, and does catch missing: reverting either half reproduces the same `IsADirectoryError`
here, not merely in a fixture shaped like it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tools.layout import CORE

pytestmark = pytest.mark.skipif(
    os.environ.get("OSPREY_TEST_DIST_BUNDLE") != "1",
    reason="needs Docker and takes minutes (docker save/load of every image); opt in with "
    "OSPREY_TEST_DIST_BUNDLE=1",
)



def _run(args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=CORE,
        env={**os.environ, "PYTHONPATH": "packages"},
        capture_output=True,
        text=True,
        timeout=timeout,
    )


#: Every owned image `--images` archives, with the Dockerfile that builds it — `harness/render.py`'s
#: own `service_images` for the three services, plus `tools/osprey_bundle.py`'s `HARNESS_IMAGE`,
#: which is not a compose service and so appears in no render.
_OWNED_IMAGES: tuple[tuple[str, str], ...] = (
    ("osprey/api:local", "services/api/Dockerfile"),
    ("osprey/ingest:local", "services/ingest/Dockerfile"),
    ("osprey/workspace:local", "apps/workspace/Dockerfile"),
    ("osprey/harness:local", "harness/Dockerfile"),
)


def _build_the_owned_images() -> None:
    """**Built here, because nothing else builds all four** — found running this test from a fresh
    clone on 27 September 2026, following `05_DEPLOYMENT.md` §3 exactly. `harness.apply --build`
    builds the services a running `local-lite` actually starts, which excludes `ingest` (a
    `batch`-profile service) and the harness image (not a compose service at all). So two of the
    four had never been built, and `tools/osprey_bundle.py`'s own stated precondition —
    "already built and tagged locally before this command runs" — was unmet with nothing enforcing
    it: the failure was a bare `CalledProcessError` naming a `docker tag` invocation. That command
    now raises `MissingLocalImageError` naming the image and the build command; this test stops
    depending on the precondition at all. Docker's layer cache makes the repeat cost small.
    """
    for tag, dockerfile in _OWNED_IMAGES:
        built = _run(["docker", "build", "-f", dockerfile, "-t", tag, "."], timeout=1800)
        assert built.returncode == 0, f"could not build {tag}: {built.stdout + built.stderr}"


def test_the_real_bundle_installs_and_deploys_from_itself_alone(tmp_path: Path) -> None:
    _build_the_owned_images()
    dist_dir = tmp_path / "dist"
    build = _run(
        [
            sys.executable,
            "-m",
            "tools.osprey_bundle",
            "--profile",
            "local-lite",
            "--out",
            str(dist_dir),
            "--images",
        ],
        timeout=1800,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    tarball = dist_dir / "osprey-bundle-local-lite.tar"
    assert tarball.is_file()

    # No relationship to REPO_ROOT whatsoever — the shape a bundle recipient's own machine is in.
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    with tarfile.open(tarball) as tar:
        tar.extractall(install_dir, filter="data")

    image_archives = sorted((install_dir / "images").glob("*.tar"))
    assert len(image_archives) >= 10, "the bundle's own manifest names 11 image archives"
    for archive in image_archives:
        loaded = subprocess.run(
            ["docker", "load", "-i", str(archive)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert loaded.returncode == 0, loaded.stderr

    out_root = install_dir / "deployed"
    compose_file = out_root / "local-lite" / "compose.yaml"
    env_file = out_root / "local-lite" / "deployment.env"
    try:
        applied = _run(
            [
                sys.executable,
                "-m",
                "harness.apply",
                "--config",
                str(install_dir / "osprey.yaml.example"),
                "--out-root",
                str(out_root),
                "--no-build",
            ],
            timeout=900,
        )
        assert applied.returncode == 0, applied.stdout + applied.stderr
        assert "service(s) healthy" in applied.stdout, applied.stdout
        assert "verify" in applied.stdout and "green" in applied.stdout, applied.stdout
        assert (out_root / "local-lite" / "osprey.yaml").is_file(), (
            "write_config_copy did not place a real osprey.yaml beside the rendered compose.yaml "
            "— the exact regression this test exists to catch"
        )
    finally:
        if compose_file.is_file():
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    str(env_file),
                    "-f",
                    str(compose_file),
                    "down",
                    "-v",
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
