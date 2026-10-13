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
        self.info: dict[str, object] | None = {"MemTotal": 34_000_000_000}
        self.compose: str | None = "Docker Compose version v5.5.1"
        self.disk_gb = 500.0
        self.busy_ports: set[int] = set()
        self.ours_ports: set[int] = set()

    def which(self, tool: str) -> str | None:
        return None if tool in self.missing else f"/usr/bin/{tool}"

    def docker_info(self) -> dict[str, object] | None:
        return self.info

    def compose_version(self) -> str | None:
        return self.compose

    def free_disk_gb(self, path: Path) -> float:
        return self.disk_gb

    def port_free(self, port: int) -> bool:
        return port not in self.busy_ports

    def ours(self, port: int) -> bool:
        return port in self.ours_ports


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
        return self.replies.pop(0) if self.replies else default

    def __call__(self, *argv: str) -> int:
        return main(
            list(argv),
            runner=None if self.use_real_runner else self.runner,
            probes=self.probes,
            home_env={"OSPREYFLOW_HOME": str(self.product), **self.env},
            recorded_home=lambda: None,
            capture=self.capture,
            ask=self.ask,
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
    """The demo data root is pinned under `tmp_path`, so no test can reach the real home folder."""
    return Rig(product, env={"OSPREYFLOW_DEMO_DATA": str(tmp_path / "demo-data")})


def make_python_stub(product: Path, script: str) -> None:
    """Replace the product's interpreter with a shell script, so the real runner is exercised."""
    python = product / ".venv" / "bin" / "python"
    python.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)
