"""One start that brings a running deployment up to date with the checkout.

Seen on the owner's deployment: after a code change the Glass, the API and the sign-in page all
stayed as they were, because the launcher's Start only ran `docker compose up`, which never
rebuilds an image and never rewrites the mounted sign-in theme. Each fix then needed its own
command, and one of them (restarting Keycloak) silently removed the demo administrator, whose
password `deployment.env` still named, so the password "stopped working".

`scripts/refresh.py` is the one sequence: write the theme, build the owned images, bring the stack
up, restart Keycloak when its theme changed, and register the sign-in accounts again. It never
re-renders the deployment, so no secret is regenerated. Each test names what it would catch.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from harness.keycloak_theme import THEME_DIRECTORY, THEME_NAME, write_login_theme
from scripts import refresh

SECRETS = "OSPREY_POSTGRES_PASSWORD=pg-secret-77\nOSPREY_KEYCLOAK_PORT=8081\n"
TOKENS = ":root { --brass: #c08a34; }\n"


class Recorder:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, argv: Sequence[str]) -> None:
        self.calls.append(list(argv))
        if self.fail_on and self.fail_on in argv:
            raise refresh.RefreshFailed(" ".join(argv))


class Registrar:
    def __init__(self, *, ok: bool = True) -> None:
        self.calls: list[list[str]] = []
        self.ok = ok

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(argv)
        return 0 if self.ok else 1


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    out = tmp_path / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "deployment.env").write_text(SECRETS, encoding="utf-8")
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    tokens = tmp_path / "apps" / "workspace" / "src" / "design" / "tokens.css"
    tokens.parent.mkdir(parents=True)
    tokens.write_text(TOKENS, encoding="utf-8")
    write_login_theme(out, tokens_css=TOKENS)  # the theme is already current
    return tmp_path


def _subcommands(calls: list[list[str]]) -> list[str]:
    """The compose verb of each call, e.g. build / up / restart."""
    verbs = {"build", "up", "restart"}
    return [next(a for a in c if a in verbs) for c in calls]


def test_it_builds_the_owned_images_then_brings_the_stack_up_in_that_order(repo: Path) -> None:
    """Catches the original fault: `up` alone starts the old image."""
    run, register = Recorder(), Registrar()
    refresh.refresh(repo, run=run, register=register)
    assert _subcommands(run.calls) == ["build", "up"]
    out = repo / "deploy" / "generated" / "local-lite"
    for argv in run.calls:
        assert argv[argv.index("--env-file") + 1] == str(out / "deployment.env")
        assert argv[argv.index("-f") + 1] == str(out / "compose.yaml")
    assert run.calls[1][-3:] == ["up", "-d", "--wait"]


def test_it_never_renders_again_so_no_secret_changes(repo: Path) -> None:
    """Catches a refresh that calls `harness.apply`: that mints new passwords for stores that
    keep the old ones (the database, the identity provider), locking the owner out."""
    env = repo / "deploy" / "generated" / "local-lite" / "deployment.env"
    before = env.read_bytes()
    run = Recorder()
    refresh.refresh(repo, run=run, register=Registrar())
    assert env.read_bytes() == before
    assert not any("harness.apply" in " ".join(c) for c in run.calls)


def test_it_never_removes_volumes_or_forces_containers_to_be_recreated(repo: Path) -> None:
    """Catches a refresh that could destroy the owner's data: no `down`, no `-v`, no
    `--force-recreate`."""
    run = Recorder()
    refresh.refresh(repo, run=run, register=Registrar())
    flat = " ".join(" ".join(c) for c in run.calls)
    for forbidden in ("down", " -v", "--force-recreate", "--volumes", "prune"):
        assert forbidden not in flat


def test_an_unchanged_theme_does_not_restart_the_identity_provider(repo: Path) -> None:
    """Catches a restart on every start: it signs everyone out and removes registered accounts."""
    run = Recorder()
    refresh.refresh(repo, run=run, register=Registrar())
    assert "restart" not in _subcommands(run.calls)


def test_a_changed_theme_is_written_and_the_identity_provider_restarted_then_waited_on(
    repo: Path,
) -> None:
    """Catches the theme staying stale: Keycloak reads a mounted theme at start, so rewriting the
    files alone changes nothing on screen."""
    (repo / "apps" / "workspace" / "src" / "design" / "tokens.css").write_text(
        ":root { --brass: #aa8833; }\n", encoding="utf-8"
    )
    run = Recorder()
    refresh.refresh(repo, run=run, register=Registrar())
    written = (
        repo / "deploy/generated/local-lite" / THEME_DIRECTORY / THEME_NAME / "login/resources/css"
    ).joinpath("osprey.css")
    assert "#aa8833" in written.read_text(encoding="utf-8")
    assert _subcommands(run.calls) == ["build", "up", "restart", "up"]
    assert "keycloak" in run.calls[2]


def test_sign_in_accounts_are_registered_after_everything_has_been_restarted(repo: Path) -> None:
    """Catches the lost administrator: Keycloak's database is not persisted, so a restart removes
    the demo administrator while `deployment.env` still names their password."""
    (repo / "apps/workspace/src/design/tokens.css").write_text(":root {}\n", encoding="utf-8")
    events: list[str] = []
    run = Recorder()
    register = Registrar()
    original_call = run.__call__

    def tracking_run(argv: Sequence[str]) -> None:
        events.append("compose")
        original_call(argv)

    def tracking_register(argv: list[str]) -> int:
        events.append("register")
        return register(argv)

    refresh.refresh(repo, run=tracking_run, register=tracking_register)
    assert events[-1] == "register"
    assert events.count("register") == 1
    argv = register.calls[0]
    assert argv[argv.index("--out-root") + 1] == str(repo / "deploy" / "generated")
    assert argv[argv.index("--profile") + 1] == "local-lite"
    assert argv[argv.index("--keycloak-url") + 1] == "http://127.0.0.1:8081"


def test_a_failed_registration_is_reported_by_name_and_the_stack_is_left_up(repo: Path) -> None:
    """Catches a silent failure: the stack is up but nobody can sign in as the administrator, and
    the message must say which command repairs it."""
    with pytest.raises(refresh.RefreshFailed, match="make register-sign-in"):
        refresh.refresh(repo, run=Recorder(), register=Registrar(ok=False))


def test_a_failed_build_stops_before_anything_is_started(repo: Path) -> None:
    """Catches starting a half-updated stack after a broken build."""
    run = Recorder(fail_on="build")
    with pytest.raises(refresh.RefreshFailed):
        refresh.refresh(repo, run=run, register=Registrar())
    assert _subcommands(run.calls) == ["build"]


def test_with_no_rendered_deployment_it_says_what_to_run_instead_of_guessing(
    tmp_path: Path,
) -> None:
    run = Recorder()
    with pytest.raises(refresh.NothingToRefresh, match="harness.apply"):
        refresh.refresh(tmp_path, run=run, register=Registrar())
    assert run.calls == []
