"""`ospreyflow doctor`: each prerequisite of ADR-114 decision 4 for the chosen mode, said in a
sentence with its fix. Nothing here installs anything; it reads the machine through `Probes`, which
the tests replace.
"""

from __future__ import annotations

import errno
import json
import os
import platform
import re
import shutil
import socket
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MIN_MEMORY_GB = 16.0
#: ADR-114 Amendment 33 decision 6: a Small on a server of your own asks for 30 GiB as Docker
#: reports it — a nominal 32 GB server, the size cloud Small starts at.
SERVER_MIN_MEMORY_GIB = 30.0
#: OpenSearch's own recommendation; it starts single-node without it, so below it is a warning.
MAX_MAP_COUNT = 262144
#: The platforms the releases are built for (`.github/workflows/release.yml`).
RELEASE_ARCHITECTURES = ("x86_64", "amd64")
MIN_DISK_GB = 60.0
#: The front proxy's, for the Lite address `http://ospreyflow.localhost` (ADR-114 Amendment 4): the
#: only port a Lite deployment publishes to other machines.
LITE_PORTS = (80,)


def lite_ports(product: Path) -> tuple[int, ...]:
    """The port a Lite deployment's front proxy binds: its own `network.public_origin`'s (ADR-132
    Amendment 1: a second deployment on the same machine takes another, such as 8081), else 80."""
    from urllib.parse import urlsplit

    from ospreyflow.home import public_origin

    if not (product / "osprey.yaml").is_file():
        return LITE_PORTS
    origin = urlsplit(public_origin(product))
    return (origin.port or (443 if origin.scheme == "https" else 80),)


_CLOUD_CLI = {"aws": ("aws", "AWS"), "azure": ("az", "Azure")}

#: ADR-135 Amendment 1 decision 3: the extraction model on an NVIDIA GPU when `osprey.yaml` names
#: none (`schemas.deployment.GPU_EXTRACTION_MODEL`; `test_gpu.py` holds the two to each other).
GPU_EXTRACTION_MODEL = "qwen2.5:14b-instruct"
SMALLER_EXTRACTION_MODEL = "qwen2.5:7b-instruct"
#: Decision 4: the GPU memory the 14b asks for; below it, a warning naming the 7b. 14 GiB as
#: measured on the first server, 4 November 2026: the 14b at 32k context with its KV cache at q8_0
#: used 12.0 GiB of the GPU (`nvidia-smi`), and Ollama reported 14 GB.
MIN_GPU_MEMORY_GIB = 14
#: One line per GPU — its name, its memory in MiB and the driver's version — as the test server's
#: answered: `NVIDIA GeForce RTX 5060 Ti, 16311, 595.99.02`.
NVIDIA_SMI_QUERY = ("--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits")
#: A CDI device the NVIDIA Container Toolkit generates (`nvidia-ctk cdi generate`).
_CDI_NVIDIA = "nvidia.com/gpu"
_SYSTEMS = {"Darwin": "macOS", "Windows": "Windows"}
_DRIVER_FIX = (
    "Install the NVIDIA driver for this GPU (on Ubuntu: sudo ubuntu-drivers install), restart the "
    "server, and check that nvidia-smi lists the GPU (section 2.2a of the administration guide)."
)


@dataclass(frozen=True)
class GpuPlan:
    """ADR-135 Amendment 1: the local engine on an NVIDIA GPU, and the extraction model it will run
    there (the 14b, unless `osprey.yaml` names another)."""

    extraction: str = GPU_EXTRACTION_MODEL


def gpu_plan(config: Mapping[str, object]) -> GpuPlan | None:
    """What an `osprey.yaml` (as plain data) asks of the GPU, or None for none. The command reads
    the file itself, depending on PyYAML alone; `OspreyConfig.extraction_model` is the same rule."""
    resources = config.get("resources")
    if not isinstance(resources, Mapping) or resources.get("gpu") != "nvidia":
        return None
    models = config.get("models")
    named = models.get("extraction") if isinstance(models, Mapping) else None
    return GpuPlan(str(named) if named else GPU_EXTRACTION_MODEL)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    says: str
    fix: str = ""
    #: A warning: said with its fix, but it does not stop an install (ADR-114 Amendment 33).
    warn: bool = False


@dataclass(frozen=True)
class ServerPlan:
    """What a Small on a server of your own will publish and serve (ADR-114 Amendment 33): read
    from the answers file's `server:` section, for the server's own checks."""

    host: str
    #: The organisation's own certificate and key, always (build order step 25 (b)): the answers
    #: refuse a `server:` without them, so there is no certificate the proxy obtains itself.
    certificate: str
    key: str
    port: int = 443
    dashboards: bool = True
    ca: str | None = None
    redirect_http: bool = False
    #: ADR-132: the GOV.UK brand on a name not under gov.uk earns a one-line notice (decision 10).
    govuk: bool = False
    #: Decision 5 (drop 2, unit 6): where `ospreyflow backup` writes on this server.
    backups: str | None = None
    #: Decision 4 (drop 2, unit 7): the organisation's provider (`alias`, `issuer`), if any, and
    #: whether its client secret is in this terminal (`OSPREY_ORG_SIGN_IN_SECRET`).
    organisation: dict[str, str] | None = None
    organisation_secret_given: bool = False

    @property
    def names(self) -> list[str]:
        found = [self.host, f"id.{self.host}"]
        return [*found, f"bi.{self.host}"] if self.dashboards else found

    @property
    def organisation_uris(self) -> tuple[str, str]:
        """What the organisation registers: the redirect URI the deployment's Keycloak sends and
        the post-logout redirect URI (`harness.realm.organisation_redirect_uris`, which a test
        holds this equal to; measured against Keycloak 26.0)."""
        port = "" if self.port == 443 else f":{self.port}"
        alias = (self.organisation or {}).get("alias", "")
        endpoint = f"https://id.{self.host}{port}/realms/osprey/broker/{alias}/endpoint"
        return endpoint, f"{endpoint}/logout_response"


class Probes(Protocol):
    def which(self, tool: str) -> str | None: ...
    def docker_info(self) -> dict[str, object] | None: ...
    def compose_version(self) -> str | None: ...
    def free_disk_gb(self, path: Path) -> float: ...
    def port_free(self, port: int) -> bool: ...
    def ours(self, port: int) -> bool: ...
    def kube_context(self) -> str | None: ...
    # ADR-114 Amendment 33 decision 8: what a server of your own is asked.
    def port_free_everywhere(self, port: int) -> bool | None: ...
    def clock_synchronised(self) -> bool | None: ...
    def max_map_count(self) -> int | None: ...
    def docker_enabled_at_boot(self) -> bool | None: ...
    def python_version(self) -> tuple[int, int] | None: ...
    def running_as_root(self) -> bool: ...
    def resolves(self, name: str) -> bool: ...
    def certificate(
        self, product: Path, certificate: str, key: str, ca: str | None, names: Sequence[str]
    ) -> tuple[int, str]: ...
    # ADR-135 Amendment 1 decision 4: what a GPU's checks ask.
    def system(self) -> str: ...
    def nvidia_smi(self, arguments: Sequence[str]) -> tuple[int, str] | None: ...


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

    def model_key_states(self) -> dict[str, str] | None:
        """ADR-135 Amendment 2 decision 9: each model engine's key state, as the running Conduit's
        key path says (`set`, `none` or `lost`), or None where no deployment answers."""
        if self._compose is None:
            return None
        text = self._run(
            [*self._compose, "exec", "-T", "api", "python", "-m", "services.api.model_keys",
             "status"]
        )  # fmt: skip
        if text is None:
            return None
        found: dict[str, str] = {}
        for line in text.splitlines():  # `<name> set|none|lost`, as `ospreyflow.models` reads it
            name, _, state = line.strip().partition(" ")
            if name and state in ("set", "none", "lost"):
                found[name] = state
        return found

    def kube_context(self) -> str | None:
        """The context `kubectl` uses, when the cluster behind it answers."""
        context = self._run(["kubectl", "config", "current-context"])
        if (
            not context
            or self._run(["kubectl", "get", "--raw", "/readyz", "--request-timeout=10s"]) is None
        ):
            return None
        return context.strip()

    def free_disk_gb(self, path: Path) -> float:
        probe = path
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        return shutil.disk_usage(probe).free / 1e9

    def port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            return sock.connect_ex(("127.0.0.1", port)) != 0

    def port_free_everywhere(self, port: int) -> bool | None:
        """Whether `port` can be had on every interface (ADR-114 Amendment 33): a real bind of the
        wildcard address, which a listener on any one address of the machine refuses
        (`EADDRINUSE`). A port below 1024 an ordinary account may not bind (`EACCES`, Linux's
        default) is asked of `ss` instead; None when neither can tell."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("0.0.0.0", port))  # noqa: S104 - the point is every interface
            except OSError as error:
                if error.errno == errno.EADDRINUSE:
                    return False
                if error.errno not in (errno.EACCES, errno.EPERM):
                    return None
            else:
                return True
        listening = self._run(["ss", "-H", "-l", "-t", "-n", f"sport = :{port}"])
        return None if listening is None else not listening.strip()

    def clock_synchronised(self) -> bool | None:
        said = self._run(["timedatectl", "show", "--property=NTPSynchronized", "--value"])
        return None if said is None else said.strip() == "yes"

    def max_map_count(self) -> int | None:
        try:
            return int(Path("/proc/sys/vm/max_map_count").read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def docker_enabled_at_boot(self) -> bool | None:
        try:
            done = subprocess.run(
                ["systemctl", "is-enabled", "docker"],
                capture_output=True, text=True, timeout=30, check=False,
            )  # fmt: skip
        except (OSError, subprocess.TimeoutExpired):
            return None
        return done.stdout.strip() == "enabled"

    def python_version(self) -> tuple[int, int] | None:
        """The newest of the machine's `python3` and a Python 3.12 or later uv can find."""
        found: list[tuple[int, int]] = []
        said = self._run(["python3", "-c", "import sys; print('%d.%d' % sys.version_info[:2])"])
        if said and re.fullmatch(r"\d+\.\d+", said.strip()):
            major, minor = said.strip().split(".")
            found.append((int(major), int(minor)))
        if self._run(["uv", "python", "find", ">=3.12"]) is not None:
            found.append((3, 12))
        return max(found) if found else None

    def running_as_root(self) -> bool:
        return hasattr(os, "geteuid") and os.geteuid() == 0

    def resolves(self, name: str) -> bool:
        try:
            socket.getaddrinfo(name, 443, type=socket.SOCK_STREAM)
        except OSError:
            return False
        return True

    def certificate(
        self, product: Path, certificate: str, key: str, ca: str | None, names: Sequence[str]
    ) -> tuple[int, str]:
        """`harness.tls_check` in the checkout's own environment (the command has PyYAML alone)."""
        from ospreyflow.home import python_for

        argv = [*python_for(product), "-m", "harness.tls_check",
                "--certificate", certificate, "--key", key]  # fmt: skip
        if ca:
            argv += ["--ca", ca]
        for name in names:
            argv += ["--name", name]
        paths = os.pathsep.join((str(product), str(product / "packages")))
        try:
            done = subprocess.run(
                argv, capture_output=True, text=True, timeout=60, check=False,
                env={**os.environ, "PYTHONPATH": paths}, cwd=product,
            )  # fmt: skip
        except (OSError, subprocess.TimeoutExpired) as error:
            return 1, f"refused: the certificate could not be checked ({error})"
        return done.returncode, done.stdout + done.stderr

    def system(self) -> str:
        """The operating system, as Python names it: Linux, Darwin (macOS) or Windows."""
        return platform.system()

    def nvidia_smi(self, arguments: Sequence[str]) -> tuple[int, str] | None:
        """`nvidia-smi` asked `arguments`: its exit and all it printed, or None where it is not
        installed. A failure is kept, not dropped: without its driver it says so (exit 9)."""
        program = shutil.which("nvidia-smi")
        if program is None:
            return None
        try:
            done = subprocess.run(
                [program, *arguments], capture_output=True, text=True, timeout=30, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return 1, str(error)
        return done.returncode, done.stdout + done.stderr

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


def model_key_checks(states: Mapping[str, str] | None) -> list[Check]:
    """ADR-135 Amendment 2 decision 9: a key the gateway no longer holds (a restore from another
    deployment, or its encryption key changed) is said by name; the engine is offered to no analyst
    until the key is entered again. Nothing where no deployment answered."""
    if not states:
        return []
    lost = sorted(name for name, state in states.items() if state == "lost")
    if not lost:
        return [Check("model-keys", True, "the model gateway holds every engine's key that is set")]
    return [
        Check(
            "model-keys",
            False,
            f"the model gateway no longer holds the key of {', '.join(lost)}; "
            f"{'that engine is' if len(lost) == 1 else 'those engines are'} offered to no analyst",
            fix="enter each key again in Admin › Models, or run: ospreyflow models key <name>",
            warn=True,
        )
    ]


def run_doctor(
    mode: str,
    probes: Probes,
    *,
    product: Path = Path("."),
    cloud: str | None = None,
    ports: tuple[int, ...] | None = None,
    server: ServerPlan | None = None,
    gpu: GpuPlan | None = None,
    joins_by_email: bool = False,
    model_states: Mapping[str, str] | None = None,
) -> list[Check]:
    """Every check for `mode`, in the order a person should fix them. `ports` are a deployment's
    own when it is not the checkout's (ADR-138: one installed by name, at an address of its own).
    `server` is a Small on a server of your own (ADR-114 Amendment 33), checked as that server.
    `gpu` is the local engine on an NVIDIA GPU (ADR-135 Amendment 1), checked after the rest.
    `joins_by_email`: the installed `osprey.yaml` joins organisation arrivals by email ("Step 33"),
    warned of as the answers' own setting is."""
    checks = _mode_checks(mode, probes, product=product, cloud=cloud, ports=ports, server=server)
    if gpu is not None and (mode == "lite" or server is not None):
        # A cloud's servers have no GPU: the answers and the schema refuse one there.
        checks += gpu_checks(probes, gpu)
    if joins_by_email and not any(c.name == "organisation-trust-email" for c in checks):
        checks.append(trust_email_check())
    return checks + model_key_checks(model_states)


def _mode_checks(
    mode: str,
    probes: Probes,
    *,
    product: Path,
    cloud: str | None,
    ports: tuple[int, ...] | None,
    server: ServerPlan | None,
) -> list[Check]:
    git = _tool(probes, "git", "git", "Git", "Install Git from https://git-scm.com/downloads.")
    uv = _tool(
        probes, "uv", "uv", "uv",
        "Install uv: https://docs.astral.sh/uv/getting-started/installation/.",
    )  # fmt: skip
    if mode == "small" and server is not None:
        return _server_checks(probes, product, server, git, uv)
    if mode == "lite":
        return [
            *_docker_checks(probes, product),
            git,
            uv,
            *(_port_check(probes, port) for port in (ports or lite_ports(product))),
        ]
    if mode == "enterprise":
        kube_tools = [
            _tool(probes, "kubectl", "kubectl", "kubectl",
                  "Install kubectl: https://kubernetes.io/docs/tasks/tools/."),
            _tool(probes, "helm", "helm", "Helm", "Install Helm: https://helm.sh/docs/intro/install/."),
        ]  # fmt: skip
        if cloud:
            # ADR-114 Amendment 19: the cluster is built first, so there is none to reach yet.
            checks = [git, uv, *kube_tools, *_build_tools(probes, mode, cloud)]
            if cloud == "azure":
                checks.append(
                    _tool(
                        probes, "kubelogin", "kubelogin", "kubelogin",
                        "Install it: https://azure.github.io/kubelogin/install.html "
                        "(or `az aks install-cli`).",
                        " (the cluster takes Entra ID sign-ins only, through kubelogin)",
                    )
                )  # fmt: skip
            return checks
        # ADR-114 Amendment 16: onto a cluster `kubectl` already reaches.
        context = probes.kube_context() if probes.which("kubectl") else None
        cluster = Check(
            "cluster",
            context is not None,
            f"kubectl reaches the cluster {context}." if context
            else "No cluster answers kubectl.",
            "" if context else "Point kubectl at the cluster (kubectl config use-context …) and "
            "check `kubectl get nodes` answers.",
        )  # fmt: skip
        return [git, uv, *kube_tools, cluster]
    return [git, uv, *_build_tools(probes, mode, cloud)]


def _server_checks(
    probes: Probes, product: Path, plan: ServerPlan, git: Check, uv: Check
) -> list[Check]:
    """ADR-114 Amendment 33 decision 8: a Small on a server of your own, every store in a
    container, as cloud Small's first boot would have prepared it — checked, not installed."""
    docker = _docker_checks(probes, product)
    # Lite's memory and disk are replaced by the server's own (the floor, and Docker's disk).
    checks = [c for c in docker if c.name not in ("memory", "disk")]
    at_boot = probes.docker_enabled_at_boot() if probes.which("docker") else None
    checks.append(
        Check("docker-at-boot", True, "Docker starts when the server starts.")
        if at_boot
        else Check(
            "docker-at-boot",
            False,
            "Docker does not start when the server starts"
            + (" (systemctl could not say)" if at_boot is None else "")
            + ", so OspreyFlow would not come back after a restart.",
            "Run sudo systemctl enable --now docker.",
        )
    )
    info = probes.docker_info()
    if info is not None:
        architecture = str(info.get("Architecture") or "unknown")
        amd64 = architecture in RELEASE_ARCHITECTURES
        checks.append(
            Check(
                "architecture",
                amd64,
                f"This server is {architecture}"
                + ("." if amd64 else "; OspreyFlow's releases are built for linux/amd64 only."),
                "" if amd64 else "Install on an x86-64 (amd64) server.",
            )
        )
        total = info.get("MemTotal")
        gibibytes = float(total) / 2**30 if isinstance(total, int | float) else 0.0
        enough = gibibytes >= SERVER_MIN_MEMORY_GIB
        checks.append(
            Check(
                "memory",
                enough,
                f"Docker has {gibibytes:.1f} GiB of memory; a Small server needs at least "
                f"{SERVER_MIN_MEMORY_GIB:.0f} GiB (a 32 GB server).",
                "" if enough else "Give the server at least 32 GB of memory.",
            )
        )
        root = Path(str(info.get("DockerRootDir") or "/var/lib/docker"))
        free = probes.free_disk_gb(root)
        roomy = free >= MIN_DISK_GB
        checks.append(
            Check(
                "disk",
                roomy,
                f"{free:.0f} GB of disk is free where Docker keeps its data ({root}); OspreyFlow "
                f"needs at least {MIN_DISK_GB:.0f} GB there, plus what you load.",
                "" if roomy else "Give Docker's data root more space (the server's data disk), "
                "or move it there (data-root in /etc/docker/daemon.json).",
            )
        )  # fmt: skip
        if plan.backups:
            checks.append(_backups_disk(probes, Path(plan.backups)))
    checks += [git, uv]
    version = probes.python_version()
    modern = version is not None and version >= (3, 12)
    checks.append(
        Check(
            "python",
            modern,
            f"Python {version[0]}.{version[1]} is available (3.12 or later is needed)."
            if version is not None
            else "Python 3.12 or later is not available (3.12 or later is needed).",
            "" if modern else "Install Python 3.12 (Ubuntu 24.04's own python3 is 3.12), or let "
            "uv install one: uv python install 3.12.",
        )
    )  # fmt: skip
    synchronised = probes.clock_synchronised()
    checks.append(
        Check("clock", True, "The server's clock is synchronised.")
        if synchronised
        else Check(
            "clock",
            False,
            "The server's clock is not synchronised"
            + (" (timedatectl could not say)" if synchronised is None else "")
            + "; sign-in tokens are checked against the time, so a wrong clock refuses sign-in.",
            "Turn on time synchronisation: sudo timedatectl set-ntp true (and allow the "
            "organisation's time server).",
        )
    )
    wanted = [plan.port]
    if plan.redirect_http:
        wanted.insert(0, 80)  # the redirect, and nothing else
    checks += [_server_port_check(probes, port) for port in wanted]
    graph = _port_check(probes, 2480)
    checks.append(
        Check(graph.name, graph.ok, graph.says.replace("Port 2480", "Port 2480 (the graph "
              "store's door, on this server only)"), graph.fix)
    )  # fmt: skip
    code, said = probes.certificate(product, plan.certificate, plan.key, plan.ca, plan.names)
    refused = [line.removeprefix("refused: ") for line in said.splitlines()
               if line.startswith("refused: ")]  # fmt: skip
    warned = [line.removeprefix("warning: ") for line in said.splitlines()
              if line.startswith("warning: ")]  # fmt: skip
    if code == 0:
        checks.append(
            Check("certificate", True, f"The certificate covers {', '.join(plan.names)}.")
        )
    else:
        checks.append(
            Check(
                "certificate",
                False,
                "The certificate is refused: " + ("; ".join(refused) or said.strip()) + ".",
                "Fix the files named in server: (section 5a of the administration guide), "
                "then run this again.",
            )
        )
    checks += [Check("certificate-expiry", True, w, "", warn=True) for w in warned]
    count = probes.max_map_count()
    if count is None or count < MAX_MAP_COUNT:
        checks.append(
            Check(
                "vm-max-map-count",
                True,
                f"vm.max_map_count is {count if count is not None else 'unknown'}; OpenSearch asks "
                f"for {MAX_MAP_COUNT} (it starts on one node without it).",
                f"Set it: sudo sysctl -w vm.max_map_count={MAX_MAP_COUNT}, and in "
                "/etc/sysctl.d/99-ospreyflow.conf to keep it.",
                warn=True,
            )
        )
    else:
        checks.append(Check("vm-max-map-count", True, f"vm.max_map_count is {count}."))
    root = probes.running_as_root()
    checks.append(
        Check(
            "account",
            True,
            "This is running as root." if root else "This is not running as root.",
            "Install as a service account in the docker group (which is root-equivalent), not "
            "as root." if root else "",
            warn=root,
        )
    )  # fmt: skip
    unresolved = [name for name in plan.names if not probes.resolves(name)]
    checks.append(
        Check(
            "names",
            True,
            f"{', '.join(unresolved)} do not resolve from this server."
            if unresolved
            else f"{', '.join(plan.names)} resolve from this server.",
            "Ask for them in the organisation's DNS, pointing at this server; the install's own "
            "tools reach them on this server without it." if unresolved else "",
            warn=bool(unresolved),
        )
    )  # fmt: skip
    if plan.organisation:
        checks += _organisation_checks(probes, plan)
    if plan.govuk and not (plan.host == "gov.uk" or plan.host.endswith(".gov.uk")):
        checks.append(
            Check(
                "govuk-brand",
                True,
                "The GOV.UK header and typeface are for services on a gov.uk domain.",
                "Check with your service owner.",
                warn=True,
            )
        )
    return checks


#: Decision 5: below this much free where backups are written, the doctor stops the install. Each
#: set is about the size of the deployment's data (the graph, the database dump, the objects); 20 GB
#: is the doctor's own floor for a first install, not a measured figure.
MIN_BACKUP_DISK_GB = 20.0


def _backups_disk(probes: Probes, folder: Path) -> Check:
    """Free disk where `ospreyflow backup` writes (decision 5), asked of the nearest folder that
    exists: the backups folder is made by the first backup."""
    existing = folder
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    free = probes.free_disk_gb(existing)
    roomy = free >= MIN_BACKUP_DISK_GB
    return Check(
        "backups-disk",
        roomy,
        f"{free:.0f} GB of disk is free where backups are written ({folder}); each backup is "
        "about the size of the deployment's data.",
        "" if roomy else f"Give {folder} at least {MIN_BACKUP_DISK_GB:.0f} GB (a disk of its own "
        "is best), or name another folder as server.backups.",
    )  # fmt: skip


#: ADR-114 Amendment 33, "Step 33": joining by email, said by the doctor and the install whenever
#: it is on — a warning, not a refusal: the organisation's security officer has decided it.
TRUST_EMAIL_SAYS = (
    "Sign-in through the organisation joins by email (sign_in.organisation.trust_email): a person "
    "arriving through the organisation's provider is joined, automatically, to the OspreyFlow "
    "account holding the same email address, with its roles and clearance. Anyone who can make the "
    "provider give that address, an address a person can set themselves or another tenant can "
    'claim, takes that account over: the 2023 "nOAuth" account takeovers were exactly this.'
)
TRUST_EMAIL_FIX = (
    "Keep it on only with the organisation's security officer's written sign-off that every "
    "address its provider gives is verified and cannot be changed by the person who holds it. "
    "Otherwise set trust_email: false (the default): a person whose email an account holds is "
    "refused in words, and an administrator joins them in Admin, People and roles."
)


def trust_email_check() -> Check:
    return Check("organisation-trust-email", True, TRUST_EMAIL_SAYS, TRUST_EMAIL_FIX, warn=True)


def joins_by_email(config: Mapping[str, object]) -> bool:
    """Whether an `osprey.yaml` (as plain data) joins organisation arrivals by email."""
    governance = config.get("governance")
    provider = governance.get("organisation_provider") if isinstance(governance, Mapping) else None
    return isinstance(provider, Mapping) and provider.get("trust_email") is True


def _organisation_checks(probes: Probes, plan: ServerPlan) -> list[Check]:
    """Decision 4: the organisation's identity provider — its client secret in this terminal for
    the install, the two addresses the organisation registers, and Keycloak's one route out."""
    from urllib.parse import urlsplit

    assert plan.organisation is not None
    redirect, logout = plan.organisation_uris
    registers = (
        f"The organisation registers OspreyFlow's application with the redirect URI {redirect} "
        f"and the post-logout redirect URI {logout}, assigned to the people who may sign in."
    )
    checks = [
        Check("organisation-sign-in", True, registers)
        if plan.organisation_secret_given
        else Check(
            "organisation-sign-in",
            False,
            registers + " Its client secret is not set in this terminal.",
            "Set OSPREY_ORG_SIGN_IN_SECRET to the client secret the organisation issued (it is "
            "kept only in the deployment's own secrets file), then run this again.",
        )
    ]
    if plan.organisation.get("trust_email") == "true":
        checks.append(trust_email_check())
    provider = urlsplit(plan.organisation.get("issuer", "")).hostname or ""
    if provider and not probes.resolves(provider):
        checks.append(
            Check(
                "organisation-route",
                True,
                f"{provider} does not resolve from this server; Keycloak reads the organisation's "
                "sign-in from it.",
                f"Allow this server to reach {provider} on 443 (Entra ID is on the internet: "
                "login.microsoftonline.com), through the organisation's proxy if it has one.",
                warn=True,
            )
        )
    return checks


def _server_port_check(probes: Probes, port: int) -> Check:
    """A port a server publishes on every interface (ADR-114 Amendment 33 decision 2), asked of
    every interface — not of loopback, which cannot see a port held on the server's own address."""
    name = f"port-{port}"
    free = probes.port_free_everywhere(port)
    if free:
        return Check(name, True, f"Port {port} is free on every interface.")
    if probes.ours(port):
        return Check(name, True, f"Port {port} is already in use by this deployment.")
    if free is None:
        return Check(
            name,
            False,
            f"Could not tell whether port {port} is free on every interface.",
            f"Check with: sudo ss -ltnp 'sport = :{port}'; stop whatever holds it, then run this "
            "again.",
        )
    return Check(
        name,
        False,
        f"Port {port} is already in use on one of this server's interfaces.",
        f"Stop whatever is using port {port} (sudo ss -ltnp 'sport = :{port}' names it), then "
        "run this again.",
    )


def _build_tools(probes: Probes, mode: str, cloud: str | None) -> list[Check]:
    """OpenTofu and the cloud's command line, which build a cloud install from this machine."""
    tofu = _tool(
        probes, "tofu", "tofu", "OpenTofu",
        "Install OpenTofu from https://opentofu.org/docs/intro/install/.",
        f" (it builds the {mode} install in your cloud account)",
    )  # fmt: skip
    tofu = Check(
        tofu.name,
        tofu.ok,
        tofu.says if not tofu.ok else "OpenTofu is installed.",
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
            f"The {label} command line is not installed (the {mode} install needs it).",
            "Install it and sign in to your account.",
        )
    return [tofu, cli]


def gpu_checks(probes: Probes, plan: GpuPlan) -> list[Check]:
    """ADR-135 Amendment 1 decision 4: before anything starts on the GPU — a Linux machine; the
    NVIDIA driver (`nvidia-smi` answers, and names the GPU and its memory); Docker able to run a
    container on it (the Container Toolkit's `nvidia` runtime, or a CDI device); and, for the 14b,
    14 GiB of GPU memory, below which it is a warning naming the 7b. OspreyFlow installs neither the
    driver nor the toolkit."""
    system = probes.system()
    if system != "Linux":
        name = _SYSTEMS.get(system, system)
        return [
            Check(
                "gpu-host",
                False,
                f"The local engine on an NVIDIA GPU needs Linux, and this computer runs {name}: "
                "Docker Desktop gives a container no NVIDIA GPU.",
                "Install on a Linux server or computer with the GPU, or set the GPU to none "
                "(server.gpu in the answers, resources.gpu in osprey.yaml).",
            )
        ]
    checks: list[Check] = []
    said = probes.nvidia_smi(NVIDIA_SMI_QUERY)
    gpus: list[tuple[str, float, str]] = []
    if said is None:
        checks.append(
            Check("gpu", False, "nvidia-smi is not installed, so the NVIDIA driver is not.",
                  _DRIVER_FIX)
        )  # fmt: skip
    elif said[0] != 0:
        first = next((line.strip() for line in said[1].splitlines() if line.strip()), "")
        checks.append(
            Check(
                "gpu",
                False,
                f"nvidia-smi does not answer (exit {said[0]}): {first or 'it printed nothing'}",
                "The driver is not loaded: restart the server after installing it, or install "
                "the driver for this GPU (on Ubuntu: sudo ubuntu-drivers install), then check "
                "that nvidia-smi lists the GPU.",
            )
        )
    else:
        for line in said[1].splitlines():
            fields = [f.strip() for f in line.split(",")]
            if len(fields) == 3 and fields[1].isdigit():
                gpus.append((fields[0], int(fields[1]) / 1024, fields[2]))
        if gpus:
            listed = "; ".join(f"{name}, {gib:.1f} GiB" for name, gib, _ in gpus)
            checks.append(Check("gpu", True, f"The NVIDIA GPU is {listed} (driver {gpus[0][2]})."))
        else:
            checks.append(
                Check("gpu", False, f"nvidia-smi lists no GPU ({said[1].strip() or 'nothing'}).",
                      _DRIVER_FIX)
            )  # fmt: skip
    checks.append(_gpu_docker_check(probes))
    if gpus and plan.extraction == GPU_EXTRACTION_MODEL:
        total = sum(gib for _, gib, _ in gpus)
        enough = total >= MIN_GPU_MEMORY_GIB
        checks.append(
            Check(
                "gpu-memory",
                True,
                f"The GPU has {total:.1f} GiB of memory; {GPU_EXTRACTION_MODEL} asks for at least "
                f"{MIN_GPU_MEMORY_GIB} GiB" + ("." if enough else ", so it would run partly on "
                "the CPU."),
                "" if enough else f"Name the smaller model, which runs on this GPU: "
                f"models.extraction: {SMALLER_EXTRACTION_MODEL} in osprey.yaml (then ospreyflow "
                "apply).",
                warn=not enough,
            )
        )  # fmt: skip
    return checks


def _gpu_docker_check(probes: Probes) -> Check:
    """Docker can run a container on the GPU: `docker info` lists the Container Toolkit's `nvidia`
    runtime (`nvidia-ctk runtime configure`), or an NVIDIA CDI device (`nvidia-ctk cdi generate`,
    which Docker 28 lists as a discovered device)."""
    info = probes.docker_info()
    if info is None:
        return Check(
            "gpu-docker",
            False,
            "Docker did not answer, so whether it can run a container on the GPU is not known.",
            "Start Docker and run this again.",
        )
    runtimes = info.get("Runtimes")
    names = sorted(runtimes) if isinstance(runtimes, Mapping) else []
    if "nvidia" in names:
        return Check("gpu-docker", True, "Docker can run a container on the GPU (the nvidia "
                     "runtime of the NVIDIA Container Toolkit).")  # fmt: skip
    devices = info.get("DiscoveredDevices")
    for device in devices if isinstance(devices, list) else []:
        found = str(device.get("ID", "")) if isinstance(device, Mapping) else ""
        if found.startswith(_CDI_NVIDIA):
            return Check(
                "gpu-docker",
                True,
                f"Docker can run a container on the GPU (the CDI device {found}).",
            )
    return Check(
        "gpu-docker",
        False,
        f"Docker cannot run a container on the GPU: it lists no nvidia runtime (only "
        f"{', '.join(names) or 'none'}) and no NVIDIA CDI device, so the NVIDIA Container Toolkit "
        "is not installed or not configured.",
        "Install the NVIDIA Container Toolkit, then run sudo nvidia-ctk runtime configure "
        "--runtime=docker and sudo systemctl restart docker (section 2.2a of the administration "
        "guide).",
    )


def format_check(check: Check) -> str:
    if check.warn:
        return f"⚠ {check.says} — {check.fix}"
    return f"✔ {check.says}" if check.ok else f"✘ {check.says} — {check.fix}"


# ---- ADR-114 Amendment 37 decisions 4 and 5: the backups folder ---------------------------------

#: `harness.backup.LEGACY_PLACEHOLDER` and `SET_NAME`: this command runs before the product's own
#: Python, so it applies the backup's rule to `osprey.yaml` as a mapping;
#: `test_the_doctor_and_the_backup_agree_on_the_folder` holds the two to one rule.
LEGACY_BACKUPS_PLACEHOLDER = "/var/lib/osprey/backups"
SET_NAME = re.compile(r"^(?P<stamp>\d{8}T\d{6}Z)-(?P<name>.+)-(?P<sha>[0-9A-Za-z]+)$")
#: Decision 5: the folders a sync client copies by default, under the home folder, on macOS
#: (iCloud Drive, the File Provider clients — Google Drive, OneDrive, Dropbox — and iCloud's
#: Desktop and Documents).
MACOS_SYNCED = ("Library/CloudStorage", "Library/Mobile Documents", "Documents", "Desktop")


def _section(config: Mapping[str, object], *keys: str) -> Mapping[str, object]:
    found: object = config
    for key in keys:
        found = found.get(key) if isinstance(found, Mapping) else None
    return found if isinstance(found, Mapping) else {}


def deployment_name_of(config: Mapping[str, object]) -> str:
    """`deployment.name`, else the profile (`schemas.deployment.generated_folder`)."""
    name = _section(config, "deployment").get("name")
    return str(name or config.get("profile") or "local-lite")


def backups_folder_of(config: Mapping[str, object], *, home: Path) -> Path:
    """`harness.backup.backups_folder`'s folder: `components.storage.backups` when one is named,
    else `~/OspreyFlow/backups`. The placeholder is a folder named only on Small on a server of
    your own (no `external:`), where Amendment 33 always wrote one."""
    value = _section(config, "components", "storage").get("backups")
    own_server = config.get("profile") == "small" and not any(
        _section(config, "external").values()
    )
    text = str(value or "").strip()
    placeholder = bool(text) and Path(text) == Path(LEGACY_BACKUPS_PLACEHOLDER)
    if text and (not placeholder or own_server):
        if text == "~" or text.startswith("~/"):
            return home / text[2:]
        return Path(text).expanduser()
    return home / "OspreyFlow" / "backups"


def _git_checkout(product: Path) -> Path | None:
    """`harness.backup.checkout_root`: the product, or the folder above it, that holds `.git`.
    None where neither does: the doctor may run where there is no checkout at all."""
    for candidate in (product, product.parent):
        if (candidate / ".git").exists():
            return candidate
    return None


def _is_inside(folder: Path, root: Path, *, ignore_case: bool = False) -> bool:
    """`harness.backup.is_inside`: compared by the folder each existing ancestor is, so a link, a
    bind mount or another letter case on a disk that ignores case is the folder it shows; a root
    that does not exist yet is compared by spelling, without case where the disk has none."""
    target = folder.expanduser().resolve()
    if root.exists():
        for candidate in (target, *target.parents):
            try:
                if candidate.exists() and os.path.samefile(candidate, root):
                    return True
            except OSError:
                continue
    spelt = Path(os.path.abspath(root)).resolve()
    if ignore_case:
        return str(target).casefold().startswith(str(spelt).casefold().rstrip("/") + "/") or (
            str(target).casefold() == str(spelt).casefold()
        )
    return target.is_relative_to(spelt)


def _size(folder: Path) -> tuple[int, bool]:
    """The bytes this account can read under `folder`, and whether any of it could not be read (a
    server's sets are 0700, and may be root's)."""
    total, unread = 0, False

    def note(_error: OSError) -> None:
        nonlocal unread
        unread = True

    for root, _dirs, files in os.walk(folder, onerror=note):
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
            except OSError:
                unread = True
    return total, unread


def _human(size: int) -> str:
    for unit, scale in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if size >= scale:
            return f"{size / scale:.1f} {unit}"
    return f"{size} bytes"


def _sets_in(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        c for c in folder.iterdir() if c.is_dir() and SET_NAME.match(c.name) is not None
    )


def _left_behind(where: Path, sets: Sequence[Path], destination: Path) -> Check:
    """Decision 4: named, with their size and the one command that moves them; never moved."""
    import shlex

    to = shlex.quote(str(destination))
    moved = " ".join(shlex.quote(str(s)) for s in sets)
    sizes = [_size(s) for s in sets]
    unread = any(u for _b, u in sizes)
    size = _human(sum(b for b, _u in sizes))
    return Check(
        "backups-left-behind",
        True,
        f"{len(sets)} backup set{'' if len(sets) == 1 else 's'}, "
        f"{f'at least {size} (some of it could not be read by this account)' if unread else size}"
        f", left in {where}: {', '.join(s.name for s in sets)}",
        f"move {'it' if len(sets) == 1 else 'them'} to the backups folder with: "
        f"mkdir -p {to} && mv {moved} {to}/"
        + (" (as the sets' owner: prefix each command with sudo)" if unread else ""),
        warn=True,
    )


def _synced_root(folder: Path, *, home: Path, system: str) -> Path | None:
    """Decision 5: the root a sync client copies that holds `folder`, as given or as its links
    resolve, or None."""
    if system == "Darwin":
        for root in MACOS_SYNCED:
            if _is_inside(folder, home / root, ignore_case=True):
                return home / root
    for seen in dict.fromkeys((folder, folder.resolve())):
        for index, part in enumerate(seen.parts):
            # OneDrive's own folder: `OneDrive`, or `OneDrive - <organisation>` for a work account.
            if part == "OneDrive" or part.startswith("OneDrive - "):
                return Path(*seen.parts[: index + 1])
    return None


def backups_checks(
    probes: Probes,
    product: Path,
    deployments: Sequence[tuple[str, Mapping[str, object]]],
    *,
    home: Path,
) -> list[Check]:
    """ADR-114 Amendment 37 decisions 4 and 5 for each deployment (`(name, its osprey.yaml)`; a
    named one's own folder is `~/.ospreyflow/deployments/<name>`): sets left in the checkout's
    `backups/`, a named deployment's old `backups/` or the top of the backups folder, and a backups
    folder a sync client copies. Warnings only."""
    checks: list[Check] = []
    # A relative folder is the product's: `ospreyflow backup` runs the harness there.
    folders = {
        name: product / folder if not folder.is_absolute() else folder
        for name, config in deployments
        for folder in (backups_folder_of(config, home=home),)
    }
    fallback = home / "OspreyFlow" / "backups"

    def home_of(set_name: str) -> Path:
        name = SET_NAME.match(set_name)["name"]  # type: ignore[index]
        return folders.get(name, next(iter(folders.values()), fallback)) / name

    places = [product / "backups"]
    places += [home / ".ospreyflow" / "deployments" / name / "backups" for name in folders]
    places += list(dict.fromkeys(folders.values()))
    for where in dict.fromkeys(places):
        grouped: dict[Path, list[Path]] = {}
        for found in _sets_in(where):
            grouped.setdefault(home_of(found.name), []).append(found)
        checks += [_left_behind(where, sets, to) for to, sets in grouped.items()]
    checkout = _git_checkout(product)
    for folder in dict.fromkeys(folders.values()):
        darwin = probes.system() == "Darwin"
        if checkout is not None and _is_inside(folder, checkout, ignore_case=darwin):
            checks.append(
                Check(
                    "backups-in-checkout",
                    False,
                    f"The backups folder {folder} is inside the checkout ({checkout}), where "
                    "every backup, and every update's own, is refused",
                    "name a folder outside it as components.storage.backups, for example "
                    "~/OspreyFlow/backups",
                )
            )
        root = _synced_root(folder, home=home, system=probes.system())
        if root is not None:
            checks.append(
                Check(
                    "backups-synced",
                    True,
                    f"The backups folder {folder} is inside {root}, which a sync client copies; "
                    "each backup holds the deployment's data and any real-data exception it was "
                    "given, which are then copied off this machine",
                    "name a folder outside it as folders.backups (components.storage.backups), "
                    "for example ~/OspreyFlow/backups, unless that copy is intended",
                    warn=True,
                )
            )
    return checks
