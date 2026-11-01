"""ADR-137 decision 1 and 2: `harness.apply --reapply` (what `ospreyflow apply` runs) re-renders an
installed deployment from its changed `osprey.yaml`, keeps every secret, takes a newly enabled
provider's key from the terminal or a hidden prompt, restarts only the services whose rendered files
changed, runs no first-install step, never touches a data volume, and leaves `deployment.env` `600`.

Found 1 November 2026: no supported command could apply a changed `osprey.yaml` to an installed
deployment, and `apply` wrote `deployment.env` readable by every account on the machine.

These drive the real `harness.apply`, standing in only for the preflight checks (where a case does
not exercise the real port check) and for Docker. The stand-in for Docker refuses what Compose
refuses where it matters here (`CLAUDE.md` rule 15): an `up` naming a service the compose file does
not have, and an env file that is not there — `test_the_stand_in_compose_refuses_as_compose_does`.

What a mistake would do, and the case that catches it (rule 12):
- a provider enabled in `osprey.yaml` never reaching the gateway, or its key landing anywhere but
  `deployment.env` —
  `test_it_renders_a_newly_enabled_provider_and_stores_its_key_from_the_terminal`;
- the key asked for where it shows — `test_with_no_key_in_the_terminal_it_is_asked_for_hidden`;
- a secret minted afresh — `test_every_other_secret_is_unchanged`;
- an invalid file half applied — `test_an_invalid_osprey_yaml_changes_nothing`;
- every service restarted, or one that changed left running the old settings —
  `test_it_restarts_only_the_services_whose_rendered_files_changed`,
  `test_nothing_changed_restarts_nothing`,
  `test_what_reaches_a_service_decides_whether_it_restarts`;
- an install step run again (accounts, first admin, packs, seeding, a rebuild, a volume) —
  `test_it_runs_no_first_install_step`;
- the secrets file readable by others — `test_deployment_env_is_600_after_an_install`,
  `test_deployment_env_is_600_after_apply_even_if_it_was_not_before`,
  `test_a_render_on_its_own_writes_deployment_env_600`;
- the deployment's own running ports refusing its own apply, or another program's port let through —
  `test_preflight_does_not_refuse_the_deployments_own_ports`,
  `test_preflight_still_refuses_a_port_something_else_holds`.
"""

from __future__ import annotations

import contextlib
import json
import socket
import stat
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from harness import apply
from harness.preflight import ports
from harness.preflight.result import passed

GEMINI_KEY = "AIza-gemini-NEVER-PRINTED-0123456789"
PASSES = SimpleNamespace(check=lambda _context: passed("ports"))
GEMINI = {
    "local_only": False,
    "sendable_handling_codes": ["P"],
    "providers": [
        {"name": "gemini", "label": "Gemini", "roles": {"extraction": "gemini-2.5-flash"}}
    ],
    "defaults": {"extraction": "gemini"},
}
SECRET = ("PASSWORD", "SECRET", "SECRET_KEY", "ACCESS_KEY")


class FakeCompose:
    """Stands in for `docker compose` (`apply._run`). Records each command; answers `ps` as Compose
    does (one JSON object per line, with `Publishers`); and refuses as Compose does an `up` naming a
    service the compose file does not have, and an `--env-file` that is not there."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        #: service -> host ports its running container publishes.
        self.published: dict[str, list[int]] = {}
        self.running = True

    def __call__(self, args: list[str], *, stage: str, **_kwargs: object) -> str:
        self.calls.append(list(args))
        env_file = Path(args[args.index("--env-file") + 1])
        compose_file = Path(args[args.index("-f") + 1])
        if not env_file.is_file():
            raise apply.ApplyFailed(stage, f"couldn't find env file: {env_file}")
        services = yaml.safe_load(compose_file.read_text(encoding="utf-8"))["services"]
        verb = args[args.index("-f") + 2]
        if verb == "ps":
            if not self.running:
                return ""
            unpublished = {"URL": "", "TargetPort": 9, "PublishedPort": 0, "Protocol": "tcp"}
            return "\n".join(
                json.dumps({
                    "Service": name, "State": "running", "Health": "healthy",
                    "Publishers": [
                        {"URL": "0.0.0.0", "TargetPort": 1, "PublishedPort": p, "Protocol": "tcp"}
                        for p in self.published.get(name, [])
                    ] + [unpublished],
                })
                for name in services
            )  # fmt: skip
        if verb == "up":
            named = [a for a in args[args.index("up") + 1 :] if not a.startswith("-")]
            unknown = [n for n in named if n not in services]
            if unknown:
                raise apply.ApplyFailed(stage, f"no such service: {unknown[0]}")
        return ""

    def ups(self) -> list[list[str]]:
        return [c for c in self.calls if "up" in c]

    def restarted(self) -> set[str]:
        found: set[str] = set()
        for call in self.ups():
            found |= {a for a in call[call.index("up") + 1 :] if not a.startswith("-")}
        return found


@pytest.fixture
def compose(monkeypatch: pytest.MonkeyPatch) -> FakeCompose:
    fake = FakeCompose()
    monkeypatch.setattr(apply, "_run", fake)
    monkeypatch.setattr(apply, "answer_localhost_with_loopback", lambda: None)
    monkeypatch.setattr(apply, "ALL_CHECKS", [PASSES])
    return fake


class Deployment:
    def __init__(self, root: Path, compose: FakeCompose) -> None:
        self.root = root
        self.compose = compose
        self.config = root / "osprey.yaml"
        self.out_root = root / "generated"
        self.prompts: list[str] = []
        self.replies: list[str] = []

    @property
    def folder(self) -> Path:
        return self.out_root / "local-lite"

    @property
    def env(self) -> Path:
        return self.folder / "deployment.env"

    def install(self, models: dict[str, Any] | None = None) -> None:
        """The first install, by the real `apply.main`, stopped at its first compose command."""
        self.write_config(models)

        def refuse(args: list[str], *, stage: str, **_kwargs: object) -> str:
            raise apply.ApplyFailed(stage, "no Docker in this test")

        before = apply._run
        apply._run = refuse  # type: ignore[assignment]
        try:
            argv = ["--config", str(self.config), "--out-root", str(self.out_root),
                    "--demo-analyst"]  # fmt: skip
            assert apply.main(argv) == 1
        finally:
            apply._run = before  # type: ignore[assignment]
        assert self.env.is_file()

    def write_config(self, models: dict[str, Any] | None = None, **extra: Any) -> None:
        body: dict[str, Any] = {**extra}
        if models is not None:
            body["models"] = models
        self.config.write_text(yaml.safe_dump(body), encoding="utf-8")

    def ask_secret(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else ""

    def reapply(self, environ: dict[str, str] | None = None) -> int:
        return apply.main(
            ["--reapply", "--config", str(self.config), "--out-root", str(self.out_root)],
            environ=environ or {},
            ask_secret=self.ask_secret,
        )

    def snapshot(self) -> dict[Path, tuple[bytes, int, int]]:
        return {
            p: (p.read_bytes(), p.stat().st_mtime_ns, stat.S_IMODE(p.stat().st_mode))
            for p in self.out_root.rglob("*")
            if p.is_file()
        }


@pytest.fixture
def deployment(tmp_path: Path, compose: FakeCompose) -> Deployment:
    found = Deployment(tmp_path, compose)
    found.install()
    compose.calls.clear()
    return found


def _pairs(env: Path) -> dict[str, str]:
    return {
        k: v
        for k, s, v in (
            line.partition("=") for line in env.read_text(encoding="utf-8").splitlines()
        )
        if s and not k.startswith("#")
    }


def _secrets(env: Path) -> dict[str, str]:
    return {k: v for k, v in _pairs(env).items() if k.endswith(SECRET)}


def test_the_stand_in_compose_refuses_as_compose_does(deployment: Deployment) -> None:
    """Rule 15: a test against this stand-in is trusted only once it has been shown to refuse."""
    compose_file = deployment.folder / "compose.yaml"
    with pytest.raises(apply.ApplyFailed, match="no such service: nonesuch"):
        deployment.compose([*apply._compose(compose_file), "up", "-d", "nonesuch"], stage="up")
    deployment.env.rename(deployment.env.with_suffix(".gone"))
    with pytest.raises(apply.ApplyFailed, match="couldn't find env file"):
        deployment.compose([*apply._compose(compose_file), "up", "-d", "api"], stage="up")


def test_it_renders_a_newly_enabled_provider_and_stores_its_key_from_the_terminal(
    deployment: Deployment, capsys: pytest.CaptureFixture[str]
) -> None:
    deployment.write_config(GEMINI)
    assert deployment.reapply({"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY}) == 0

    assert _pairs(deployment.env)["OSPREY_MODEL_KEY_GEMINI"] == GEMINI_KEY
    gateway = yaml.safe_load((deployment.folder / "litellm.yaml").read_text(encoding="utf-8"))
    names = [m["model_name"] for m in gateway["model_list"]]
    assert "gemini/gemini-2.5-flash" in names
    copy = yaml.safe_load((deployment.folder / "osprey.yaml").read_text(encoding="utf-8"))
    assert copy["models"]["providers"][0]["name"] == "gemini"
    # The key is in deployment.env alone: no other file, no output, no prompt.
    holding = [p.name for p in deployment.out_root.rglob("*")
               if p.is_file() and GEMINI_KEY.encode() in p.read_bytes()]  # fmt: skip
    assert holding == ["deployment.env"]
    out = capsys.readouterr()
    assert GEMINI_KEY not in out.out + out.err
    assert deployment.prompts == []
    assert not any(GEMINI_KEY in word for call in deployment.compose.calls for word in call)


def test_with_no_key_in_the_terminal_it_is_asked_for_hidden(deployment: Deployment) -> None:
    deployment.write_config(GEMINI)
    deployment.replies.append(GEMINI_KEY)
    assert deployment.reapply() == 0
    assert deployment.prompts == ["Key for Gemini (OSPREY_MODEL_KEY_GEMINI; not shown): "]
    assert _pairs(deployment.env)["OSPREY_MODEL_KEY_GEMINI"] == GEMINI_KEY


def test_no_key_given_changes_nothing(
    deployment: Deployment, capsys: pytest.CaptureFixture[str]
) -> None:
    before = deployment.snapshot()
    deployment.write_config(GEMINI)
    assert deployment.reapply() == 1
    assert "OSPREY_MODEL_KEY_GEMINI" in capsys.readouterr().err
    assert deployment.snapshot() == before
    assert deployment.compose.ups() == []


def test_a_key_already_held_is_kept_and_not_asked_for(deployment: Deployment) -> None:
    deployment.write_config(GEMINI)
    assert deployment.reapply({"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY}) == 0
    deployment.write_config({**GEMINI, "sendable_handling_codes": ["P", "O"]})
    assert deployment.reapply() == 0
    assert deployment.prompts == []
    assert _pairs(deployment.env)["OSPREY_MODEL_KEY_GEMINI"] == GEMINI_KEY


def test_every_other_secret_is_unchanged(deployment: Deployment) -> None:
    first = _secrets(deployment.env)
    assert len(first) >= 10, first.keys()
    deployment.write_config(GEMINI)
    assert deployment.reapply({"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY}) == 0
    after = _secrets(deployment.env)
    assert {k: v for k, v in after.items() if k in first} == first
    assert set(first) <= set(after)


@pytest.mark.parametrize(
    "bad",
    [
        "models: {provider: {name: openai, roles: {extraction: m}}, providers: [{name: gemini, "
        "roles: {extraction: m}}]}\n",
        "profile: not-a-profile\n",
        "models: [unclosed\n",
    ],
)
def test_an_invalid_osprey_yaml_changes_nothing(
    deployment: Deployment, bad: str, capsys: pytest.CaptureFixture[str]
) -> None:
    before = deployment.snapshot()
    deployment.config.write_text(bad, encoding="utf-8")
    assert deployment.reapply({"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY}) == 1
    err = capsys.readouterr().err
    assert "osprey.yaml" in err and "nothing was changed" in err.lower()
    assert "Traceback" not in err
    assert deployment.snapshot() == before
    assert deployment.compose.calls == []
    assert deployment.prompts == []
    assert not list(deployment.out_root.glob(".*staging"))


def test_a_deployment_not_installed_is_refused(
    tmp_path: Path, compose: FakeCompose, capsys: pytest.CaptureFixture[str]
) -> None:
    found = Deployment(tmp_path, compose)
    found.write_config(GEMINI)
    assert found.reapply({"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY}) == 1
    assert "ospreyflow install" in capsys.readouterr().err
    assert not found.out_root.exists() or not any(found.out_root.iterdir())


def test_it_restarts_only_the_services_whose_rendered_files_changed(
    deployment: Deployment,
) -> None:
    deployment.write_config(GEMINI)
    assert deployment.reapply({"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY}) == 0
    # The gateway (its routing table, and its key by interpolation); the Conduit (its osprey.yaml,
    # and the engines it is told of); and the other services that read deployment.env whole, whose
    # own environment now blanks the key (ADR-135). Not a store, not the identity provider, not the
    # proxy, not the local models.
    assert deployment.compose.restarted() == {"litellm", "api", "workspace", "ingest", "ner"}
    (up,) = deployment.compose.ups()
    assert "--force-recreate" in up and "--no-deps" in up


def test_nothing_changed_restarts_nothing(
    deployment: Deployment, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _pairs(deployment.env)
    assert deployment.reapply() == 0
    assert deployment.compose.ups() == []
    assert "Nothing changed" in capsys.readouterr().out
    assert _pairs(deployment.env) == before


def test_what_reaches_a_service_decides_whether_it_restarts(tmp_path: Path) -> None:
    """The rule on its own: a changed variable reaches a service through `env_file` unless its own
    `environment` sets it, or by `${...}` in its definition; a changed mounted file reaches the
    services that mount it."""
    old, new = tmp_path / "old", tmp_path / "new"
    services = {
        "reads_whole": {"image": "a", "env_file": ["deployment.env"]},
        "blanks_it": {"image": "a", "env_file": ["deployment.env"], "environment": {"K": ""}},
        "interpolates": {"image": "a", "environment": {"X": "${K:-}"}},
        "mounts": {"image": "a", "volumes": ["./table.yaml:/t.yaml:ro", "./theme/x:/x:ro"]},
        "untouched": {"image": "a", "volumes": ["data:/data"]},
    }
    for folder, key, table, theme in ((old, "1", "a", "a"), (new, "2", "b", "b")):
        (folder / "theme" / "x").mkdir(parents=True)
        (folder / "compose.yaml").write_text(yaml.safe_dump({"services": services}), "utf-8")
        (folder / "deployment.env").write_text(f"# c\nK={key}\nSAME=1\n", "utf-8")
        (folder / "table.yaml").write_text(table, "utf-8")
        (folder / "theme" / "x" / "page.css").write_text(theme, "utf-8")
    assert apply.services_to_restart(old, new) == {"reads_whole", "interpolates", "mounts"}
    (new / "deployment.env").write_text("# other comment\nSAME=1\nK=1\n", "utf-8")
    (new / "table.yaml").write_text("a", "utf-8")
    assert apply.services_to_restart(old, new) == {"mounts"}  # the theme still differs
    (new / "theme" / "x" / "page.css").write_text("a", "utf-8")
    assert apply.services_to_restart(old, new) == set()


def test_it_runs_no_first_install_step(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[str] = []
    for name in ("grant_service_account_roles", "set_demo_admin_password",
                 "set_demo_analyst_password", "create_investigation", "seed"):  # fmt: skip
        monkeypatch.setattr(apply, name, lambda *_a, _n=name, **_k: ran.append(_n))
    import harness.verify

    monkeypatch.setattr(harness.verify, "run_verify", lambda **_k: ran.append("verify"))
    deployment.write_config(GEMINI)
    assert deployment.reapply({"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY}) == 0
    assert ran == []
    # Compose is asked what runs, and to start services again — nothing else: no rebuild, no
    # one-off run, no removal. And `up` only with flags that keep every volume.
    verbs = {call[call.index("-f") + 2] for call in deployment.compose.calls}
    assert verbs <= {"ps", "up"}, verbs
    for up in deployment.compose.ups():
        flags = {a for a in up[up.index("up") + 1 :] if a.startswith("-")}
        assert flags <= {"-d", "--no-deps", "--force-recreate", "--wait", "--remove-orphans"}


def test_deployment_env_is_600_after_an_install(deployment: Deployment) -> None:
    assert stat.S_IMODE(deployment.env.stat().st_mode) == 0o600


def test_deployment_env_is_600_after_apply_even_if_it_was_not_before(
    deployment: Deployment,
) -> None:
    deployment.env.chmod(0o644)  # as both of the owner's deployments were, before ADR-137
    deployment.write_config(GEMINI)
    assert deployment.reapply({"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY}) == 0
    assert stat.S_IMODE(deployment.env.stat().st_mode) == 0o600


def test_a_render_on_its_own_writes_deployment_env_600(tmp_path: Path) -> None:
    """`python -m harness.render` writes the file too, before any secret is in it."""
    from harness.render import load_config, render, write

    write(render(load_config(tmp_path / "none.yaml"), allow_unpinned=True), tmp_path)
    assert stat.S_IMODE((tmp_path / "deployment.env").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "compose.yaml").stat().st_mode) != 0o600


# ---- the port check, on a deployment that is already running ---------------------------------


@contextlib.contextmanager
def _held_port() -> Iterator[int]:
    """A real socket listening on a port, as a running container's published port would be."""
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        yield int(held.getsockname()[1])


@pytest.fixture
def real_port_check(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> Callable[[int], None]:
    """The real `ports` check, alone, with ArcadeDB's published port moved to `port`."""

    def use(port: int) -> None:
        monkeypatch.setenv("OSPREY_ARCADEDB_PORT", str(port))
        monkeypatch.setattr(apply, "ALL_CHECKS", [ports])

    return use


def _every_other_declared_port(deployment: Deployment, port: int) -> dict[str, list[int]]:
    """Each port the deployment publishes but `port`, as its own running containers', so whatever
    else this machine runs (the owner's own deployment on 80, say) cannot decide the case."""
    rendered = yaml.safe_load((deployment.folder / "compose.yaml").read_text(encoding="utf-8"))
    published: dict[str, list[int]] = {}
    for service, held in ports.declared_ports(rendered):
        if held != port:
            published.setdefault(service, []).append(held)
    return published


def test_preflight_does_not_refuse_the_deployments_own_ports(
    deployment: Deployment, real_port_check: Callable[[int], None]
) -> None:
    """Its own running proxy holds the port (ArcadeDB's, published through it): that is not a reason
    to refuse its own apply."""
    with _held_port() as port:
        real_port_check(port)
        deployment.compose.published = _every_other_declared_port(deployment, port)
        deployment.compose.published.setdefault("proxy", []).append(port)
        deployment.write_config(GEMINI)
        assert deployment.reapply({"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY}) == 0


def test_preflight_still_refuses_a_port_something_else_holds(
    deployment: Deployment,
    real_port_check: Callable[[int], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The deployment's containers publish nothing there (or are stopped), so another program holds
    it, and the apply is refused with nothing changed."""
    before = deployment.snapshot()
    with _held_port() as port:
        real_port_check(port)
        deployment.compose.published = _every_other_declared_port(deployment, port)
        deployment.write_config(GEMINI)
        assert deployment.reapply({"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY}) == 1
        assert f"{port} (proxy)" in capsys.readouterr().err  # ArcadeDB is published by the proxy
    assert deployment.snapshot() == before
    assert deployment.compose.ups() == []


def test_own_ports_are_read_from_composes_own_answer(deployment: Deployment) -> None:
    deployment.compose.published = {"arcadedb": [2480], "proxy": [80, 443]}
    assert apply.own_published_ports(deployment.folder / "compose.yaml") == {80, 443, 2480}
    deployment.compose.running = False
    assert apply.own_published_ports(deployment.folder / "compose.yaml") == set()
