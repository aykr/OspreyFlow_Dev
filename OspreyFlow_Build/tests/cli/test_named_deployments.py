"""Several deployments side by side (ADR-138 decision 2): `--name`, `ospreyflow deployments`,
`ospreyflow switch <name>`.

Every case runs with a temporary home (`HOME` under `tmp_path`, `OSPREYFLOW_HOME` a temporary
product) and with the render and Compose layers stood in for by `FakeDocker`. **The stand-in refuses
what the real ones refuse** (rule 15): Compose names a project's containers and volumes after the
project, so a second folder started under a name another folder already has collides with that
project's containers (`test_the_stand_in_refuses_what_docker_refuses`); and Docker refuses to start
a container whose published port another container already holds ("port is already allocated").

What a mistake would do, and the case that catches it (rule 12):
- two deployments sharing a folder, project, volume or port —
  `test_two_named_deployments_share_no_volume_folder_project_or_port`;
- a verb that ignores `--name` (planted: `logs` reading the checkout's) —
  `test_name_on_every_verb_reaches_only_that_deployment`;
- a name another Compose project has taken over —
  `test_a_name_another_compose_project_has_is_refused_before_anything_is_written`;
- the checkout's own deployment changed by any of this —
  `test_the_checkout_deployment_works_unchanged_and_is_listed_as_default`.
"""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml
from ospreyflow import deployments as named
from ospreyflow.main import main

from .conftest import BASE_CONFIG, PACKS_OUTPUT, FakeProbes


@dataclass
class Project:
    compose_file: Path
    ports: set[int]
    running: bool = False


@dataclass
class FakeDocker:
    """Docker, Compose and the harness's render, as far as the command drives them.

    `harness.apply` writes what the real render writes that the command reads — `compose.yaml`
    naming its project and published ports, and `deployment.env` (600) — into `<out-root>/<name>`,
    then starts it as the real apply does. Compose `up` refuses a project name another folder holds
    and a port another running project publishes; `docker compose ls` lists every project."""

    projects: dict[str, Project] = field(default_factory=dict)
    calls: list[tuple[list[str], dict[str, str], Path | None]] = field(default_factory=list)
    captured: list[list[str]] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)

    # -- the runner -----------------------------------------------------------------------------
    def __call__(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
    ) -> int:
        argv = list(argv)
        self.calls.append((argv, dict(env or {}), cwd))
        if "harness.apply" in argv and "--reapply" not in argv:
            return self._render_and_up(argv)
        if argv[:2] == ["docker", "compose"] and "-f" in argv:
            compose_file = Path(argv[argv.index("-f") + 1])
            if "up" in argv:
                return self.up(compose_file)
            if "stop" in argv:
                project = self._project_of(compose_file)
                if project in self.projects:
                    self.projects[project].running = False
        return 0

    def capture(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
    ) -> tuple[int, str]:
        argv = list(argv)
        self.captured.append(argv)
        if "--ids" in argv:
            return 0, PACKS_OUTPUT
        if argv[:3] == ["docker", "compose", "ls"]:
            rows = [
                {"Name": name, "Status": "running(12)" if p.running else "exited(12)",
                 "ConfigFiles": str(p.compose_file)}
                for name, p in self.projects.items()
            ]  # fmt: skip
            return 0, json.dumps(rows)
        if "ps" in argv:
            return 0, json.dumps([{"Service": "proxy", "State": "running", "Health": ""}])
        return 0, ""

    # -- Compose ----------------------------------------------------------------------------------
    @staticmethod
    def _project_of(compose_file: Path) -> str:
        document = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
        return str(document.get("name") or compose_file.parent.name)

    @staticmethod
    def _ports_of(compose_file: Path) -> set[int]:
        document = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
        env = (compose_file.parent / "deployment.env").read_text(encoding="utf-8")
        values = dict(line.split("=", 1) for line in env.splitlines() if "=" in line)
        ports: set[int] = set()
        for service in (document.get("services") or {}).values():
            for mapping in service.get("ports", []):
                text = re.sub(r"\$\{(\w+):-(\d+)\}", lambda m: values.get(m[1], m[2]), mapping)
                ports.add(int(text.split(":")[-2]))
        return ports

    def up(self, compose_file: Path) -> int:
        name = self._project_of(compose_file)
        held = self.projects.get(name)
        if held is not None and held.compose_file.resolve() != compose_file.resolve():
            self.refusals.append(f"project {name} belongs to {held.compose_file}")
            return 1
        ports = self._ports_of(compose_file)
        for other, project in self.projects.items():
            if other != name and project.running and ports & project.ports:
                self.refusals.append(f"port is already allocated: {sorted(ports & project.ports)}")
                return 1
        self.projects[name] = Project(compose_file, ports, running=True)
        return 0

    # -- the render ---------------------------------------------------------------------------------
    def _render_and_up(self, argv: list[str]) -> int:
        from harness.render import write_private

        config_path = Path(argv[argv.index("--config") + 1])
        out_root = Path(argv[argv.index("--out-root") + 1])
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        name = config["deployment"]["name"]
        port = named._port_of(config["network"]["public_origin"])
        folder = out_root / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "compose.yaml").write_text(
            yaml.safe_dump({
                "name": name,
                "services": {"proxy": {"ports": [
                    f"{port}:80", "127.0.0.1:${OSPREY_ARCADEDB_PORT:-2480}:2480",
                ]}},
                "volumes": {"arcadedb-data": {}, "postgres-data": {}},
            }),
            encoding="utf-8",
        )  # fmt: skip
        graph = config["deployment"].get("graph_port") or 2480
        write_private(folder / "deployment.env", f"OSPREY_ARCADEDB_PORT={graph}\nX=1\n")
        return self.up(folder / "compose.yaml")

    def checkout_deployment(self, product: Path, name: str = "osprey-local-lite") -> Path:
        """A checkout-rooted deployment as one installed before ADR-138 is: rendered under the
        checkout's `deploy/generated/local-lite/`, its project `osprey-local-lite`, on port 80."""
        folder = product / "deploy" / "generated" / "local-lite"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "compose.yaml").write_text(
            yaml.safe_dump({"name": name, "services": {"proxy": {"ports": [
                "80:80", "127.0.0.1:${OSPREY_ARCADEDB_PORT:-2480}:2480"]}}}),
            encoding="utf-8",
        )  # fmt: skip
        (folder / "deployment.env").write_text("OSPREY_ARCADEDB_PORT=2480\n", encoding="utf-8")
        self.projects[name] = Project(folder / "compose.yaml", {80, 2480}, running=True)
        return folder


@dataclass
class Machine:
    product: Path
    home: Path
    docker: FakeDocker = field(default_factory=FakeDocker)
    probes: FakeProbes = field(default_factory=FakeProbes)
    opened: list[str] = field(default_factory=list)
    data: Path | None = None

    def __call__(self, *argv: str) -> int:
        return main(
            list(argv),
            runner=self.docker,
            probes=self.probes,
            home_env={
                "OSPREYFLOW_HOME": str(self.product),
                "HOME": str(self.home),
                "OSPREYFLOW_DEMO_DATA": str(self.data or self.home / "demo-data"),
            },
            recorded_home=lambda: None,
            capture=self.docker.capture,
            ask=lambda prompt, default="": default,
            ask_secret=lambda prompt: "",
            open_url=self.opened.append,
        )

    @property
    def root(self) -> Path:
        return self.home / ".ospreyflow" / "deployments"

    def install(self, name: str, *extra: str) -> int:
        return self("install", "--mode", "lite", "--yes", "--name", name, *extra)

    def config(self, name: str) -> dict[str, object]:
        loaded = yaml.safe_load((self.root / name / "osprey.yaml").read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        return loaded


@pytest.fixture
def machine(product: Path, tmp_path: Path) -> Machine:
    return Machine(product, tmp_path / "home")


def _compose_for(folder: Path) -> list[str]:
    return ["docker", "compose", "--env-file", str(folder / "deployment.env"),
            "-f", str(folder / "compose.yaml")]  # fmt: skip


def _uploads_for(machine: Machine, folder: Path) -> list[str]:
    """The step before every `up` (ADR-114 Amendment 33): the Conduit's upload folder its own."""
    python = str(machine.product / ".venv" / "bin" / "python")
    return [python, "-m", "harness.ingest_uploads", str(folder / "compose.yaml")]


def _stores_for(machine: Machine, folder: Path) -> list[str]:
    """The step after it (ADR-114 Amendment 35): the stores' data moved to named volumes, once."""
    python = str(machine.product / ".venv" / "bin" / "python")
    return [python, "-m", "harness.store_volumes", str(folder / "compose.yaml")]


# --- installing side by side ---------------------------------------------------------------------


def test_two_named_deployments_share_no_volume_folder_project_or_port(machine: Machine) -> None:
    machine.docker.checkout_deployment(machine.product)
    assert machine.install("alpha") == 0
    machine("stop", "--name", "alpha")
    assert machine.install("bravo") == 0
    folders = [machine.root / "alpha", machine.root / "bravo"]
    assert folders[0] != folders[1] and all((f / "compose.yaml").is_file() for f in folders)
    # Its own Compose project, which names its volumes (`<project>_arcadedb-data`).
    projects = {FakeDocker._project_of(f / "compose.yaml") for f in folders}
    assert projects == {"alpha", "bravo"}
    volumes = [
        {f"{p}_{v}" for v in (yaml.safe_load((f / "compose.yaml").read_text()) or {})["volumes"]}
        for p, f in zip(["alpha", "bravo"], folders, strict=True)
    ]
    assert not volumes[0] & volumes[1]
    # Its own address and graph-store port; none of them the checkout's or a reserved one.
    ports = [FakeDocker._ports_of(f / "compose.yaml") for f in folders]
    assert not ports[0] & ports[1]
    assert not (ports[0] | ports[1]) & named.RESERVED_PORTS
    assert machine.config("alpha")["network"]["public_origin"].startswith("http://alpha.localhost:")  # type: ignore[index]
    assert machine.config("alpha")["deployment"]["name"] == "alpha"  # type: ignore[index]
    assert machine.docker.refusals == []


def test_deployment_env_and_its_folder_are_private(machine: Machine) -> None:
    """ADR-138: `deployment.env` under `~/.ospreyflow/deployments/` is 600, and the folder that
    holds it 700. (The real render's own 600 is held by `tests/harness/test_named_render.py`.)"""
    assert machine.install("alpha") == 0
    folder = machine.root / "alpha"
    assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(folder / "deployment.env").st_mode) == 0o600


def test_the_install_is_rendered_into_its_own_folder_from_its_own_osprey_yaml(
    machine: Machine,
) -> None:
    assert machine.install("alpha", "--starter", "ospreyflow-blank") == 0
    apply = next(argv for argv, _e, _c in machine.docker.calls if "harness.apply" in argv)
    assert apply[apply.index("--config") + 1] == str(machine.root / "alpha" / "osprey.yaml")
    assert apply[apply.index("--out-root") + 1] == str(machine.root)
    # The checkout's own osprey.yaml is never written.
    assert yaml.safe_load((machine.product / "osprey.yaml").read_text()) == BASE_CONFIG
    text = (machine.root / "alpha" / "osprey.yaml").read_text(encoding="utf-8")
    assert text.startswith("# Starter: ospreyflow-blank")


def test_a_name_another_compose_project_has_is_refused_before_anything_is_written(
    machine: Machine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The owner's GOV.UK deployment runs from a worktree as the project `osprey-govuk`. A new one
    given that name would take its containers over; it is refused, with nothing written."""
    worktree = tmp_path / "ospreyflow-govuk" / "deploy" / "generated" / "osprey-govuk"
    worktree.mkdir(parents=True)
    (worktree / "compose.yaml").write_text("name: osprey-govuk\nservices: {}\n", encoding="utf-8")
    machine.docker.projects["osprey-govuk"] = Project(worktree / "compose.yaml", {8081}, True)
    assert machine.install("osprey-govuk") == 1
    assert "already has a Compose project called 'osprey-govuk'" in capsys.readouterr().err
    assert not (machine.root / "osprey-govuk").exists()
    assert not any("harness.apply" in argv for argv, _e, _c in machine.docker.calls)
    assert machine.docker.projects["osprey-govuk"].running


def test_the_stand_in_refuses_what_docker_refuses(machine: Machine, tmp_path: Path) -> None:
    """Rule 15: the stand-in is no more permissive than Docker. Started straight (as a command
    that skipped the name check would start it), a duplicate project and a bound port fail."""
    docker = machine.docker
    machine.docker.checkout_deployment(machine.product)
    stranger = tmp_path / "elsewhere"
    stranger.mkdir()
    (stranger / "compose.yaml").write_text(
        "name: osprey-local-lite\nservices: {proxy: {ports: ['9000:80']}}\n", encoding="utf-8"
    )
    (stranger / "deployment.env").write_text("X=1\n", encoding="utf-8")
    assert docker.up(stranger / "compose.yaml") == 1
    clash = tmp_path / "clash"
    clash.mkdir()
    (clash / "compose.yaml").write_text(
        "name: clash\nservices: {proxy: {ports: ['80:80']}}\n", encoding="utf-8"
    )
    (clash / "deployment.env").write_text("X=1\n", encoding="utf-8")
    assert docker.up(clash / "compose.yaml") == 1
    assert [r.split(":")[0] for r in docker.refusals] == [
        "project osprey-local-lite belongs to " + str(
            machine.product / "deploy" / "generated" / "local-lite" / "compose.yaml"
        ).split(":")[0],
        "port is already allocated",
    ]


def test_a_port_another_deployment_has_is_not_offered_or_taken(
    machine: Machine, capsys: pytest.CaptureFixture[str]
) -> None:
    machine.probes.busy_ports = {8090, 2500}  # something else on this machine holds them
    assert machine.install("alpha") == 0
    alpha = machine.config("alpha")
    assert alpha["network"]["public_origin"] == "http://alpha.localhost:8091"  # type: ignore[index]
    assert alpha["deployment"]["graph_port"] == 2501  # type: ignore[index]
    assert machine.install("bravo", "--address", "http://bravo.localhost:8091") == 1
    assert "already another deployment's" in capsys.readouterr().err
    assert machine.install("bravo", "--address", "http://bravo.localhost:9123") == 0
    assert machine.config("bravo")["network"]["public_origin"] == "http://bravo.localhost:9123"  # type: ignore[index]


def test_a_name_installed_already_is_refused_and_left_alone(
    machine: Machine, capsys: pytest.CaptureFixture[str]
) -> None:
    assert machine.install("alpha") == 0
    before = (machine.root / "alpha" / "osprey.yaml").read_text(encoding="utf-8")
    assert machine.install("alpha", "--force") == 1
    assert "already installed" in capsys.readouterr().err
    assert (machine.root / "alpha" / "osprey.yaml").read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    ("argv", "words"),
    [
        (("install", "--mode", "small", "--cloud", "aws", "--yes", "--name", "x"), "is Lite"),
        (("install", "--mode", "lite", "--yes", "--address", "http://x.localhost:9000"),
         "--address goes with --name"),
        (("install", "--mode", "lite", "--yes", "--name", "Bad_Name"), "cannot name a deployment"),
        # ADR-114 Amendment 38: a profile's name is the checkout's own deployment's backups
        # subfolder, so a deployment by that name would share its sets.
        (("install", "--mode", "lite", "--yes", "--name", "local-lite"), "the name of a profile"),
        (("install", "--mode", "lite", "--yes", "--name", "small"), "the name of a profile"),
        (("install", "--mode", "lite", "--yes", "--name", "cluster"), "the name of a profile"),
        (("start", "--name", "nonesuch"), "no deployment called 'nonesuch'"),
    ],
)  # fmt: skip
def test_what_cannot_be_a_named_deployment_is_refused_in_words(
    machine: Machine, argv: tuple[str, ...], words: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert machine(*argv) == 1
    assert words in capsys.readouterr().err
    assert not machine.root.exists() or not any(machine.root.iterdir())


# --- every verb takes --name -----------------------------------------------------------------------

#: Each verb that acts on a deployment, as a person types it after `--name bravo` is added.
VERBS = [
    ("start",), ("start", "--build"), ("stop",), ("status",), ("logs", "proxy"), ("open",),
    ("apply",), ("repair-sign-in",), ("uninstall", "--yes"), ("switch",),
    ("demo", "add", "hmp"), ("backup",), ("restore", "/tmp/a-backup-set"), ("update", "--check"),
    ("demo", "add", "public", "--file", "/tmp/x.csv", "--manifest", "vast-2012-mc2"),
]  # fmt: skip


@pytest.mark.parametrize("verb", VERBS, ids=lambda v: " ".join(v[:3]))
def test_name_on_every_verb_reaches_only_that_deployment(
    machine: Machine, verb: tuple[str, ...], tmp_path: Path
) -> None:
    """Three deployments — the checkout's, `alpha` and `bravo` — and the verb given `--name bravo`:
    everything it runs, asks, opens or names is bravo's, and nothing is alpha's or the checkout's."""
    checkout = machine.docker.checkout_deployment(machine.product)
    machine.docker.projects["osprey-local-lite"].running = False
    assert machine.install("alpha") == 0
    machine("stop", "--name", "alpha")
    assert machine.install("bravo") == 0
    machine.docker.calls.clear()
    machine.docker.captured.clear()
    machine.opened.clear()
    if verb[:3] == ("demo", "add", "public"):
        # Checked by the checkout's own script, through the capture: a passing check.
        def capture(argv, *, env=None, cwd=None):  # type: ignore[no-untyped-def]
            if "scripts.public_dataset" in argv:
                return 0, json.dumps({"id": "vast-2012-mc2", "name": "VAST", "source_page": "s",
                                      "licence": "l", "real_personal_data": False})  # fmt: skip
            return FakeDocker.capture(machine.docker, argv, env=env, cwd=cwd)

        machine.docker.capture = capture  # type: ignore[method-assign]

    assert machine(*verb[:1], "--name", "bravo", *verb[1:]) == 0

    said = json.dumps(
        [[a, e] for a, e, _c in machine.docker.calls]
        + machine.docker.captured
        + machine.opened
    )
    bravo, alpha = machine.root / "bravo", machine.root / "alpha"
    bravo_address = str(machine.config("bravo")["network"]["public_origin"])  # type: ignore[index]
    alpha_address = str(machine.config("alpha")["network"]["public_origin"])  # type: ignore[index]
    reached = str(bravo) in said or bravo_address in said
    assert reached, f"{verb} did not reach bravo: {said}"
    assert str(alpha) not in said and alpha_address not in said, f"{verb} reached alpha"
    assert str(checkout) not in said, f"{verb} reached the checkout's deployment"


def test_a_named_deployments_backup_goes_to_its_subfolder_of_the_backups_folder(
    machine: Machine,
) -> None:
    """ADR-114 Amendment 37 decision 3 replaces ADR-138's `<deployment folder>/backups`: the backup
    is pointed at the deployment's own `osprey.yaml` and given no `--out-root`, so `harness.backup`
    writes to `<components.storage.backups>/<deployment name>/` — by the name it reads there."""
    assert machine.install("bravo") == 0
    machine.docker.calls.clear()
    assert machine("backup", "--name", "bravo") == 0
    (argv,) = [a for a, _e, _c in machine.docker.calls if "harness.backup" in a]
    assert "--out-root" not in argv
    assert argv[argv.index("--config") + 1] == str(machine.root / "bravo" / "osprey.yaml")
    assert machine.config("bravo")["deployment"]["name"] == "bravo"  # type: ignore[index]
    assert str(machine.root / "bravo" / "backups") not in " ".join(argv)


def test_a_verb_without_name_acts_on_the_one_last_used(machine: Machine) -> None:
    machine.docker.checkout_deployment(machine.product)
    assert machine.install("alpha") == 0
    machine("stop", "--name", "alpha")
    assert machine.install("bravo") == 0
    machine("stop", "--name", "alpha")  # alpha is now the one last used
    machine.docker.calls.clear()
    assert machine("stop") == 0
    assert machine.docker.calls[-1][0] == [*_compose_for(machine.root / "alpha"), "stop"]
    assert machine("status", "--name", "default") == 0  # default is the one last used now
    machine.docker.calls.clear()
    assert machine("stop") == 0
    checkout = machine.product / "deploy" / "generated" / "local-lite"
    assert machine.docker.calls[-1][0] == [*_compose_for(checkout), "stop"]


def test_the_only_deployment_is_the_one_a_verb_acts_on(machine: Machine) -> None:
    assert machine.install("alpha") == 0
    (machine.home / ".ospreyflow" / "current").unlink()
    machine.docker.calls.clear()
    assert machine("stop") == 0
    assert machine.docker.calls[-1][0] == [*_compose_for(machine.root / "alpha"), "stop"]


# --- the checkout's own deployment ---------------------------------------------------------------


def test_the_checkout_deployment_works_unchanged_and_is_listed_as_default(
    machine: Machine, capsys: pytest.CaptureFixture[str]
) -> None:
    """The owner's everyday deployment (in the checkout) keeps working exactly as before: with no
    deployment installed by name, every verb drives the same commands, and the home folder is never
    written."""
    checkout = machine.docker.checkout_deployment(machine.product)
    for verb in (("start",), ("stop",), ("status",), ("open",)):
        assert machine(*verb) == 0
    assert [argv for argv, _e, _c in machine.docker.calls] == [
        _uploads_for(machine, checkout),
        _stores_for(machine, checkout),
        [*_compose_for(checkout), "up", "-d", "--wait"],
        [*_compose_for(checkout), "stop"],
    ]
    assert machine.opened == ["http://ospreyflow.localhost"]
    assert not (machine.home / ".ospreyflow").exists()
    capsys.readouterr()
    assert machine("deployments") == 0
    assert capsys.readouterr().out.startswith("default: no starter, http://ospreyflow.localhost, ")


def test_deployments_lists_each_with_its_starter_address_and_state(
    machine: Machine, capsys: pytest.CaptureFixture[str]
) -> None:
    machine.docker.checkout_deployment(machine.product)
    machine.docker.projects["osprey-local-lite"].running = False
    assert machine.install("alpha", "--starter", "ospreyflow-blank") == 0
    capsys.readouterr()
    assert machine("deployments") == 0
    lines = capsys.readouterr().out.splitlines()
    address = machine.config("alpha")["network"]["public_origin"]  # type: ignore[index]
    assert lines[0] == "default: no starter, http://ospreyflow.localhost, stopped"
    assert lines[2] == (
        f"alpha: ospreyflow-blank, {address}, running (the one commands act on)"
    )
    assert not [argv for argv, _e, _c in machine.docker.calls if "deployments" in argv]


def test_switch_stops_the_running_deployment_and_starts_the_named_one(machine: Machine) -> None:
    checkout = machine.docker.checkout_deployment(machine.product)
    machine.docker.projects["osprey-local-lite"].running = False
    assert machine.install("alpha") == 0
    machine.docker.calls.clear()
    assert machine("switch", "default") == 0
    assert [argv for argv, _e, _c in machine.docker.calls] == [
        [*_compose_for(machine.root / "alpha"), "stop"],
        _uploads_for(machine, checkout),
        _stores_for(machine, checkout),
        [*_compose_for(checkout), "up", "-d", "--wait"],
    ]
    assert machine.docker.refusals == []
    machine.docker.calls.clear()
    assert machine("switch", "alpha") == 0
    assert [argv for argv, _e, _c in machine.docker.calls] == [
        [*_compose_for(checkout), "stop"],
        _uploads_for(machine, machine.root / "alpha"),
        _stores_for(machine, machine.root / "alpha"),
        [*_compose_for(machine.root / "alpha"), "up", "-d", "--wait"],
    ]
    assert machine.opened[-1] == machine.config("alpha")["network"]["public_origin"]  # type: ignore[index]
    assert (machine.home / ".ospreyflow" / "current").read_text().strip() == "alpha"


def test_models_reads_the_named_deployments_own_settings(
    machine: Machine, capsys: pytest.CaptureFixture[str]
) -> None:
    """`models` runs nothing until a key changes, so it is held by what it reads: bravo's engines,
    never alpha's or the checkout's."""
    assert machine.install("alpha") == 0
    machine("stop", "--name", "alpha")
    assert machine.install("bravo") == 0
    for name, label in (("alpha", "Alpha engine"), ("bravo", "Bravo engine")):
        path = machine.root / name / "osprey.yaml"
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        config["models"] = {"local_only": False, "providers": [
            {"name": "gemini", "label": label, "roles": {"extraction": "gemini-x"}}]}
        path.write_text(yaml.safe_dump(config), encoding="utf-8")
    capsys.readouterr()
    # The stand-in for Docker runs nothing, so the Conduit's key path is not there to ask, as for a
    # stopped deployment: `exec` refuses, and the command reads the named deployment's own files
    # (ADR-135 Amendment 2: before the keys move, presence is read from its `deployment.env`).
    captured = machine.docker.capture

    def no_conduit(argv: list[str], **kw: object) -> tuple[int, str]:
        if "services.api.model_keys" in argv:
            return 1, 'service "api" is not running'
        return captured(argv, **kw)  # type: ignore[arg-type]

    machine.docker.capture = no_conduit  # type: ignore[method-assign]
    assert machine("models", "--name", "bravo") == 0
    said = capsys.readouterr().out
    assert "Bravo engine" in said and "Alpha engine" not in said


@pytest.mark.parametrize(
    "argv",
    [("demo", "add", "hmp", "--name", "bravo"), ("demo", "--name", "bravo", "add", "hmp"),
     ("--name", "bravo")],
)  # fmt: skip
def test_name_may_come_before_or_after_the_demo_packs_own_words(
    machine: Machine, argv: tuple[str, ...]
) -> None:
    """As the guide writes it (`ospreyflow demo add hmp --name crime-demo`), and after the verb."""
    assert machine.install("bravo") == 0
    (machine.home / ".ospreyflow" / "current").unlink()
    machine.docker.checkout_deployment(machine.product)
    machine.docker.calls.clear()
    words = argv if argv[0] == "demo" else ("demo", "add", "hmp", *argv)
    assert machine(*words) == 0
    (seed,) = [e for a, e, _c in machine.docker.calls if "scripts.seed_internal" in a]
    assert seed["OSPREYFLOW_DEPLOYMENT_DIR"] == str(machine.root / "bravo")


def test_the_profile_names_refused_are_the_schemas_profiles() -> None:
    """The command runs before the product's Python, so it holds the profiles' names itself; they
    must be every one the schema has, or a new profile's name becomes a deployment's."""
    from ospreyflow.deployments import PROFILE_NAMES

    from schemas.deployment import Profile

    assert set(PROFILE_NAMES) == {p.value for p in Profile}


def test_a_deployment_installed_by_a_profiles_name_before_is_still_reached(
    machine: Machine, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal is the install's: one installed as `small` before Amendment 38 is still named
    by its own verbs (this one is a bare folder, so `stop` goes on to say nothing is rendered)."""
    folder = machine.root / "small"
    folder.mkdir(parents=True)
    (folder / "osprey.yaml").write_text(yaml.safe_dump(
        {"profile": "local-lite", "deployment": {"name": "small"},
         "network": {"public_origin": "http://small.localhost:8091"}}))  # fmt: skip
    machine("stop", "--name", "small")
    said = capsys.readouterr().err
    assert "the name of a profile" not in said and "no deployment called" not in said, said


def test_the_checkouts_own_deployment_name_is_refused_for_a_named_one(
    machine: Machine, capsys: pytest.CaptureFixture[str]
) -> None:
    """The checkout's own deployment goes by `deployment.name` when its osprey.yaml gives one
    (ADR-132 Amendment 1), so a deployment installed by that name would share its backups
    subfolder (second lane-reviewer pass; ADR-114 Amendment 38 decision 6)."""
    config = machine.product / "osprey.yaml"
    raw = yaml.safe_load(config.read_text()) if config.is_file() else {}
    config.write_text(yaml.safe_dump({**(raw or {}), "deployment": {"name": "acme"}}))
    assert machine("install", "--mode", "lite", "--yes", "--name", "acme") == 1
    assert "the checkout's own deployment" in capsys.readouterr().err
    assert not (machine.root / "acme").exists()
