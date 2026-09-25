"""`harness/Dockerfile`'s own exit test: the image builds, and `docker run ... preflight --gate`
from it reaches the same result as the host CLI.

**Opt-in via `OSPREY_TEST_HARNESS_IMAGE=1`** — builds a real Docker image and needs Docker, the
same reasoning `tests/harness/test_bundle_exit_test.py` already uses for its own opt-in gate.

**"The same result", with one named, measured exception.** Preflight's own `memory` check reads
`os.sysconf("SC_PHYS_PAGES")` — physical RAM, as the OS answers it. Run natively on a Docker-Desktop
host (macOS, Windows), that is the host's own real RAM; run inside this image, on the identical
host, it is the Docker Desktop VM's own — smaller — allocated budget, because the daemon (and every
container it runs, this one included) lives inside that VM, not on the host directly. Measured
directly building this test: 36.0GiB natively, 9.7GiB inside this same image, against the identical
16GiB `local-lite` floor — both readings are correct for what they measure, and the VM's own figure
is arguably the more relevant one, since it is what the deployment's own containers are actually
constrained by. Not a defect in this image to paper over by lying about either number; excluded
from the comparison below, named rather than silently dropped. A native Linux host has no such VM
layer and would not show this discrepancy at all — the exclusion is Docker-Desktop-specific, not a
general admission that the check disagrees with itself.

Every other check `harness.preflight`'s own `check_all` runs — `disk`, `gpu`, `ports`,
`container-runtime`, `cluster-connectivity`, `interpreter`, `bind-address`, `basemap`,
`duckdb-lock`, `oidc-audience` — matched in outcome (not necessarily in cosmetic detail: `gpu`'s
own skip reason differs by platform, `interpreter`'s own path is `/app/.venv` inside the image and
this checkout's own `.venv` on the host) the first time this test was run for real, which is what
this test asserts stays true.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("OSPREY_TEST_HARNESS_IMAGE") != "1",
    reason="builds a real Docker image; opt in with OSPREY_TEST_HARNESS_IMAGE=1",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE_TAG = "osprey/harness:test"

_PLATFORM_DEPENDENT_CHECKS = frozenset({"memory"})
_STATUS_LINE = re.compile(r"^(PASS|FAIL|WARN|SKIP)\s+(\S+)\s*\(", re.MULTILINE)


def _statuses(output: str) -> dict[str, str]:
    return dict((name, status) for status, name in _STATUS_LINE.findall(output))


@pytest.fixture(scope="module")
def built_image() -> str:
    result = subprocess.run(
        ["docker", "build", "-f", "harness/Dockerfile", "-t", IMAGE_TAG, "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return IMAGE_TAG


@pytest.fixture(scope="module")
def rendered_out_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Rendered once, on the host, and read by both the host CLI and the containerized one below
    — the comparison is only meaningful against the identical rendered compose file."""
    out_root = tmp_path_factory.mktemp("harness-image-test")
    result = subprocess.run(
        [sys.executable, "-m", "harness.render", "--out-root", str(out_root)],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "packages"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return out_root


def test_the_image_builds(built_image: str) -> None:
    assert built_image == IMAGE_TAG


def test_containerized_preflight_reaches_the_same_result_as_the_host_cli(
    built_image: str, rendered_out_root: Path
) -> None:
    host = subprocess.run(
        [sys.executable, "-m", "harness.preflight", "--out-root", str(rendered_out_root)],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "packages"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    host_statuses = _statuses(host.stdout + host.stderr)
    assert host_statuses, "could not parse any check status from the host CLI's own output"

    container = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "root",
            "-v",
            f"{REPO_ROOT}:/workspace",
            "-v",
            f"{rendered_out_root}:/workspace-out",
            "-v",
            "/var/run/docker.sock:/var/run/docker.sock",
            built_image,
            "preflight",
            "--config",
            "/workspace/osprey.yaml",
            "--out-root",
            "/workspace-out",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    container_statuses = _statuses(container.stdout + container.stderr)
    assert container_statuses, (
        "could not parse any check status from the containerized CLI's own output: "
        + container.stdout
        + container.stderr
    )

    assert set(host_statuses) == set(container_statuses), (
        f"the two runs checked a different set of checks: host={sorted(host_statuses)}, "
        f"container={sorted(container_statuses)}"
    )
    mismatched = {
        name: (host_statuses[name], container_statuses[name])
        for name in host_statuses
        if name not in _PLATFORM_DEPENDENT_CHECKS
        and host_statuses[name] != container_statuses[name]
    }
    assert not mismatched, f"host vs container check status disagreed: {mismatched}"
