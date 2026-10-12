"""`ospreyflow doctor`: each prerequisite of ADR-114 decision 4 for the chosen mode, said in a
sentence with its fix. Nothing here installs anything; it reads the machine through `Probes`, which
the tests replace.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MIN_MEMORY_GB = 16.0
MIN_DISK_GB = 60.0
LITE_PORTS = (8080, 8081, 8088)
_CLOUD_CLI = {"aws": ("aws", "AWS"), "azure": ("az", "Azure")}
_STAGE = {"small": "B6", "enterprise": "B7"}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    says: str
    fix: str = ""


class Probes(Protocol):
    def which(self, tool: str) -> str | None: ...
    def docker_info(self) -> dict[str, object] | None: ...
    def compose_version(self) -> str | None: ...
    def free_disk_gb(self, path: Path) -> float: ...
    def port_free(self, port: int) -> bool: ...
    def ours(self, port: int) -> bool: ...


class SystemProbes:
    """The real machine. `deployment` (when known) is what `ours` asks about a port."""

    def __init__(self, compose_prefix: list[str] | None = None) -> None:
        self._compose = compose_prefix

    def which(self, tool: str) -> str | None:
        return shutil.which(tool)

    def _run(self, argv: list[str]) -> str | None:
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return done.stdout if done.returncode == 0 else None

    def docker_info(self) -> dict[str, object] | None:
        text = self._run(["docker", "info", "--format", "{{json .}}"])
        try:
            loaded = json.loads(text) if text else None
        except ValueError:
            return None
        return loaded if isinstance(loaded, dict) else None

    def compose_version(self) -> str | None:
        text = self._run(["docker", "compose", "version"])
        return text.strip() if text else None

    def free_disk_gb(self, path: Path) -> float:
        probe = path
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        return shutil.disk_usage(probe).free / 1e9

    def port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            return sock.connect_ex(("127.0.0.1", port)) != 0

    def ours(self, port: int) -> bool:
        """Whether this deployment's own containers publish `port`."""
        if not self._compose:
            return False
        text = self._run([*self._compose, "ps", "--format", "json"])
        for line in (text or "").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            for publisher in row.get("Publishers") or []:
                if publisher.get("PublishedPort") == port:
                    return True
        return False


def _compose_major(text: str) -> int | None:
    """The major version in text like "Docker Compose version v5.5.1" or "2.29.1"."""
    found = re.search(r"(\d+)\.\d+", text)
    return int(found.group(1)) if found else None


def _tool(probes: Probes, name: str, tool: str, label: str, fix: str, why: str = "") -> Check:
    found = probes.which(tool) is not None
    return Check(
        name,
        found,
        f"{label} is installed." if found else f"{label} is not installed{why}.",
        "" if found else fix,
    )


def _docker_checks(probes: Probes, product: Path) -> list[Check]:
    checks = [
        _tool(
            probes, "docker-installed", "docker", "Docker",
            "Install Docker Desktop (macOS, Windows) or Docker Engine with the Compose plugin "
            "(Linux) from https://docs.docker.com/get-docker/.",
        ),
    ]  # fmt: skip
    info = probes.docker_info()
    checks.append(
        Check("docker-running", True, "Docker is running.")
        if info is not None
        else Check(
            "docker-running",
            False,
            "Docker is not running.",
            "Start Docker (open Docker Desktop, or start the Docker service) and run this again.",
        )
    )
    version = probes.compose_version()
    major = _compose_major(version) if version else None
    compose_ok = major is not None and major >= 2
    if version is None:
        says = "Docker Compose is not available."
    elif compose_ok:
        says = f"Docker Compose version {major} is available (version 2 or later is needed)."
    else:
        says = f"Docker Compose is too old ({version}); version 2 or later is needed."
    checks.append(
        Check(
            "compose", compose_ok, says,
            "" if compose_ok else
            "Update Docker Desktop, or install the Docker Compose v2 plugin for Docker Engine.",
        )
    )  # fmt: skip
    if info is not None:
        total = info.get("MemTotal")
        gigabytes = float(total) / 1e9 if isinstance(total, int | float) else 0.0
        enough = gigabytes >= MIN_MEMORY_GB
        checks.append(
            Check(
                "memory",
                enough,
                f"Docker has {gigabytes:.1f} GB of memory; OspreyFlow needs at least "
                f"{MIN_MEMORY_GB:.0f} GB (32 GB is comfortable).",
                "" if enough else
                "Raise the memory in Docker Desktop's settings (Resources), then restart Docker.",
            )
        )  # fmt: skip
    free = probes.free_disk_gb(product)
    roomy = free >= MIN_DISK_GB
    checks.append(
        Check(
            "disk",
            roomy,
            f"{free:.0f} GB of disk is free here; OspreyFlow needs at least {MIN_DISK_GB:.0f} GB "
            "plus the demo packs you choose.",
            "" if roomy else "Free up disk space, or move the checkout to a larger drive.",
        )
    )
    return checks


def _port_check(probes: Probes, port: int) -> Check:
    name = f"port-{port}"
    if probes.port_free(port):
        return Check(name, True, f"Port {port} is free.")
    if probes.ours(port):
        return Check(name, True, f"Port {port} is already in use by this deployment.")
    return Check(
        name,
        False,
        f"Port {port} is already in use by something else.",
        f"Stop whatever is using port {port}, then run this again.",
    )


def run_doctor(
    mode: str, probes: Probes, *, product: Path = Path("."), cloud: str | None = None
) -> list[Check]:
    """Every check for `mode`, in the order a person should fix them."""
    git = _tool(probes, "git", "git", "Git", "Install Git from https://git-scm.com/downloads.")
    uv = _tool(
        probes, "uv", "uv", "uv",
        "Install uv: https://docs.astral.sh/uv/getting-started/installation/.",
    )  # fmt: skip
    if mode == "lite":
        return [
            *_docker_checks(probes, product),
            git,
            uv,
            *(_port_check(probes, port) for port in LITE_PORTS),
        ]
    stage = _STAGE.get(mode, "B6")
    tofu = _tool(
        probes, "tofu", "tofu", "OpenTofu",
        "Install OpenTofu from https://opentofu.org/docs/intro/install/.",
        f" (it is needed for the {mode} install, stage {stage})",
    )  # fmt: skip
    tofu = Check(
        tofu.name,
        tofu.ok,
        tofu.says if not tofu.ok else f"OpenTofu is installed (needed for stage {stage}).",
        tofu.fix,
    )
    clouds = [cloud] if cloud else list(_CLOUD_CLI)
    found = [(c, _CLOUD_CLI[c]) for c in clouds if probes.which(_CLOUD_CLI[c][0])]
    if found:
        cli = Check("cloud-cli", True, f"The {found[0][1][1]} command line is installed.")
    else:
        label = " or ".join(_CLOUD_CLI[c][1] for c in clouds)
        cli = Check(
            "cloud-cli",
            False,
            f"The {label} command line is not installed (it is needed for stage {stage}).",
            "Install it and sign in to your account.",
        )
    return [git, uv, tofu, cli]


def format_check(check: Check) -> str:
    return f"✔ {check.says}" if check.ok else f"✘ {check.says} — {check.fix}"
