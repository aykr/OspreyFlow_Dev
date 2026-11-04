"""Shared fakes for the `ospreyflow` command's tests (ADR-114 Amendment 3, stage B2b).

Every test drives `ospreyflow.main.main` with injected fakes — a runner that records what it was
asked to run, probes that report a healthy machine, a capture, a prompt and an opener — so nothing
here touches Docker, the network, the real home folder or a deployment.

Per `CLAUDE.md` rule 15 the fakes model refusals as well as grants: `FakeProbes` can be told to
refuse each prerequisite, and `FakeRunner` can be told which step exits non-zero.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml
from ospreyflow.main import main

PACKS_OUTPUT = "hmp\nfixture-corp\noperation-ledger\npaysim\n"

#: ADR-135 Amendment 1: `docker info`'s runtimes on a Linux server without the NVIDIA Container
#: Toolkit (Docker Engine 28; each also carries a `status` of runtime features, left out here) —
#: and with it, once `nvidia-ctk runtime configure --runtime=docker` has registered its runtime.
RUNTIMES_WITHOUT_TOOLKIT: dict[str, object] = {
    "io.containerd.runc.v2": {"path": "runc"},
    "runc": {"path": "runc"},
}
RUNTIMES_WITH_TOOLKIT: dict[str, object] = {
    **RUNTIMES_WITHOUT_TOOLKIT,
    "nvidia": {"path": "nvidia-container-runtime"},
}
#: What `nvidia-smi` prints, exit 9, where the driver is installed but not loaded (or not at all,
#: with its tools left behind).
NVIDIA_SMI_NO_DRIVER = (
    "NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver. Make sure that "
    "the latest NVIDIA driver is installed and running.\n"
)
#: The test server's own GPU (4 November 2026): name, memory.total in MiB, driver_version.
TEST_SERVER_GPU = ("NVIDIA GeForce RTX 5060 Ti", 16311, "595.99.02")
BASE_CONFIG = {
    "profile": "local-lite",
    "components": {"storage": {"data": "/var/lib/osprey/data"}},
    "models": {"local_only": True},
    "network": {"public_origin": "http://ospreyflow.localhost"},
}


@dataclass
class Call:
    argv: list[str]
    env: Mapping[str, str] | None
    cwd: Path | None


class FakeRunner:
    """Records each command. `fail` maps a word that appears in the argv to the exit code."""

    def __init__(self) -> None:
        self.calls: list[Call] = []
        self.fail: dict[str, int] = {}

    def __call__(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
    ) -> int:
        self.calls.append(Call(list(argv), env, cwd))
        for word, code in self.fail.items():
            if word in argv:
                return code
        return 0

    def argvs(self) -> list[list[str]]:
        return [c.argv for c in self.calls]

    def with_word(self, word: str) -> list[Call]:
        return [c for c in self.calls if word in c.argv]


class FakeProbes:
    """A machine that satisfies every prerequisite until a test removes one."""

    def __init__(self) -> None:
        self.missing: set[str] = set()
        self.info: dict[str, object] | None = {
            "MemTotal": 34_000_000_000,
            "Architecture": "x86_64",
            "DockerRootDir": "/var/lib/docker",
            "Runtimes": dict(RUNTIMES_WITH_TOOLKIT),
        }
        #: Free disk by folder, else `disk_gb` (a server's Docker root can be another disk).
        self.disk_by_path: dict[str, float] = {}
        #: Ports held on some interface, not necessarily loopback (ADR-114 Amendment 33): the
        #: loopback probe (`port_free`) does not see them, as the real one does not.
        self.held_elsewhere: set[int] = set()
        #: What a server's own probes say (Amendment 33 decision 8); None is "could not tell".
        self.clock: bool | None = True
        self.max_map: int | None = 262144
        self.docker_at_boot: bool | None = True
        self.python: tuple[int, int] | None = (3, 12)
        self.root = False
        self.unresolved: set[str] = set()
        #: `harness.tls_check`'s exit and output, as the doctor's step receives them.
        self.certificate_says: tuple[int, str] = (0, "ok: the certificate covers every name\n")
        #: Each server probe asked, in order, with its subject.
        self.asked: list[tuple[str, object]] = []
        self.compose: str | None = "Docker Compose version v5.5.1"
        self.disk_gb = 500.0
        self.busy_ports: set[int] = set()
        self.ours_ports: set[int] = set()
        #: The cluster `kubectl` reaches (its context), or None (ADR-114 Amendment 16).
        self.kube: str | None = "osprey-test-context"
        #: ADR-135 Amendment 1: a Linux server with the test server's GPU, its driver loaded and
        #: the toolkit's runtime registered. `nvidia-smi` in `missing` is no driver installed.
        self.system_name = "Linux"
        self.gpus: list[tuple[str, int, str]] = [TEST_SERVER_GPU]
        self.driver_loaded = True
        self.nvidia_asked: list[list[str]] = []

    def which(self, tool: str) -> str | None:
        return None if tool in self.missing else f"/usr/bin/{tool}"

    def docker_info(self) -> dict[str, object] | None:
        return self.info

    def compose_version(self) -> str | None:
        return self.compose

    def free_disk_gb(self, path: Path) -> float:
        self.asked.append(("disk", str(path)))
        return self.disk_by_path.get(str(path), self.disk_gb)

    def port_free(self, port: int) -> bool:
        return port not in self.busy_ports

    def port_free_everywhere(self, port: int) -> bool | None:
        self.asked.append(("port-everywhere", port))
        return port not in self.busy_ports and port not in self.held_elsewhere

    def clock_synchronised(self) -> bool | None:
        return self.clock

    def max_map_count(self) -> int | None:
        return self.max_map

    def docker_enabled_at_boot(self) -> bool | None:
        return self.docker_at_boot

    def python_version(self) -> tuple[int, int] | None:
        return self.python

    def running_as_root(self) -> bool:
        return self.root

    def resolves(self, name: str) -> bool:
        return name not in self.unresolved

    def certificate(
        self, product: Path, certificate: str, key: str, ca: str | None, names: Sequence[str]
    ) -> tuple[int, str]:
        self.asked.append(("certificate", certificate))
        return self.certificate_says

    def ours(self, port: int) -> bool:
        return port in self.ours_ports

    def kube_context(self) -> str | None:
        return self.kube

    def system(self) -> str:
        return self.system_name

    def nvidia_smi(self, arguments: Sequence[str]) -> tuple[int, str] | None:
        """As the real `nvidia-smi` answers: not there, the driver's refusal (exit 9), a field it
        does not know (exit 2), or one line per GPU, with units unless `nounits` is asked for."""
        self.nvidia_asked.append(list(arguments))
        if "nvidia-smi" in self.missing:
            return None
        if not self.driver_loaded:
            return 9, NVIDIA_SMI_NO_DRIVER
        query = next((a.split("=", 1)[1] for a in arguments if a.startswith("--query-gpu=")), "")
        form = next((a.split("=", 1)[1] for a in arguments if a.startswith("--format=")), "")
        known = {"name", "memory.total", "driver_version"}
        for name in query.split(","):
            if name not in known:
                return 2, f'Field "{name}" is not a valid field to query.\n'
        units = "nounits" not in form.split(",")
        lines = []
        for name, memory, driver in self.gpus:
            values = {"name": name, "memory.total": f"{memory} MiB" if units else str(memory),
                      "driver_version": driver}  # fmt: skip
            lines.append(", ".join(values[f] for f in query.split(",")))
        return 0, "".join(f"{line}\n" for line in lines)


@dataclass
class Rig:
    """The command with every outside dependency faked. Call it with the argv after `ospreyflow`."""

    product: Path
    runner: FakeRunner = field(default_factory=FakeRunner)
    probes: FakeProbes = field(default_factory=FakeProbes)
    opened: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    ps_output: str = ""
    ps_code: int = 0
    use_real_runner: bool = False
    env: dict[str, str] = field(default_factory=dict)
    capture_envs: list[Mapping[str, str] | None] = field(default_factory=list)
    #: What `git tag --points-at HEAD` says of the checkout (ADR-114 Amendment 8 point 10).
    tags_at_head: str = ""
    #: Answers for captured commands, by a word in their argv: each answer is used once, in turn,
    #: and the last stays (`tofu output`, the secret store asked until the code is there).
    responses: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    captured: list[list[str]] = field(default_factory=list)
    #: The hidden prompt (`getpass`) a key is asked at (ADR-135): what it asked, what it answers.
    secret_prompts: list[str] = field(default_factory=list)
    secret_replies: list[str] = field(default_factory=list)

    def capture(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
    ) -> tuple[int, str]:
        self.capture_envs.append(env)
        self.captured.append(list(argv))
        for word, queued in self.responses.items():
            if word in argv:
                return queued.pop(0) if len(queued) > 1 else queued[0]
        if "--ids" in argv:
            return 0, PACKS_OUTPUT
        if "--points-at" in argv:
            return 0, self.tags_at_head
        if "ps" in argv:
            return self.ps_code, self.ps_output
        return 0, ""

    def ask(self, prompt: str, default: str = "") -> str:
        self.questions.append(prompt)
        # As the real prompt (`ospreyflow.main._ask`): an empty reply takes the default.
        return (self.replies.pop(0) if self.replies else "") or default

    def ask_secret(self, prompt: str) -> str:
        self.secret_prompts.append(prompt)
        return self.secret_replies.pop(0) if self.secret_replies else ""

    def __call__(self, *argv: str) -> int:
        return main(
            list(argv),
            runner=None if self.use_real_runner else self.runner,
            probes=self.probes,
            home_env={"OSPREYFLOW_HOME": str(self.product), **self.env},
            recorded_home=lambda: None,
            capture=self.capture,
            ask=self.ask,
            ask_secret=self.ask_secret,
            open_url=self.opened.append,
        )

    @property
    def deployment(self) -> Path:
        return self.product / "deploy" / "generated" / "local-lite"

    def install_deployment(self) -> None:
        self.deployment.mkdir(parents=True, exist_ok=True)
        (self.deployment / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        (self.deployment / "deployment.env").write_text("X=1\n", encoding="utf-8")

    def config(self) -> dict[str, object]:
        loaded = yaml.safe_load((self.product / "osprey.yaml").read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        return loaded


@pytest.fixture
def product(tmp_path: Path) -> Path:
    """A product folder as a user's repository has it: the product IS the repository root."""
    root = tmp_path / "ospreyflow"
    (root / "harness").mkdir(parents=True)
    (root / "harness" / "__init__.py").write_text("", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "osprey.yaml").write_text(yaml.safe_dump(BASE_CONFIG), encoding="utf-8")
    python = root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return root


@pytest.fixture
def rig(product: Path, tmp_path: Path) -> Rig:
    """The demo data root and the home folder (`~/.ospreyflow/deployments`, ADR-138) are pinned
    under `tmp_path`, so no test can reach the real home folder."""
    return Rig(
        product,
        env={"OSPREYFLOW_DEMO_DATA": str(tmp_path / "demo-data"), "HOME": str(tmp_path / "home")},
    )


def make_python_stub(product: Path, script: str) -> None:
    """Replace the product's interpreter with a shell script, so the real runner is exercised."""
    python = product / ".venv" / "bin" / "python"
    python.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)
