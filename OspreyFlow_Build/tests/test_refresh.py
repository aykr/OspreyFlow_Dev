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


# --- ADR-095: the deployment's own models brought up to date, nothing else re-rendered ---------


def _rendered(repo: Path, extraction: str = "qwen2.5:7b-instruct") -> Path:
    """A deployment rendered before ADR-095: the developer stack's pull script, no route for the
    chosen model, no model lines in `deployment.env`, and secrets that must survive."""
    import yaml
    from harness.render import _OLLAMA_PULL_SCRIPT, render

    from schemas.deployment import ModelsConfig, OspreyConfig

    out = repo / "deploy" / "generated" / "local-lite"
    config = OspreyConfig(models=ModelsConfig(extraction=extraction))  # type: ignore[arg-type]
    artefacts = render(config, allow_unpinned=True).artefacts
    compose = artefacts["compose.yaml"]
    banner = compose[: compose.index("\nname:") + 1]
    document = yaml.safe_load(compose)
    document["services"]["ollama"]["command"] = [_OLLAMA_PULL_SCRIPT]
    old = banner + yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
    assert old != compose  # the old file really lacks the line
    (out / "compose.yaml").write_text(old, encoding="utf-8")
    env = "\n".join(
        line for line in artefacts["deployment.env"].splitlines() if "_MODEL=" not in line
    )
    (out / "deployment.env").write_text(env + "\n" + SECRETS, encoding="utf-8")
    (out / "litellm.yaml").write_text("model_list: []\n", encoding="utf-8")
    (out / "osprey.yaml").write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    return out


def test_the_chosen_models_are_brought_up_to_date_and_no_secret_changes(repo: Path) -> None:
    """Catches the gap found building ADR-095: refresh never renders, so a running deployment
    never learnt its extraction model, and the Conduit asked the proxy for a model it had no route
    to. Only the model parts change; every secret line stays byte for byte."""
    import yaml
    from harness.render import render, render_litellm_config

    from schemas.deployment import ModelsConfig, OspreyConfig

    out = _rendered(repo, "qwen2.5:14b-instruct")
    secrets_before = [
        line for line in (out / "deployment.env").read_text().splitlines() if "_MODEL=" not in line
    ]
    run = Recorder()
    refresh.refresh(repo, run=run, register=Registrar())

    config = OspreyConfig(models=ModelsConfig(extraction="qwen2.5:14b-instruct"))
    assert (out / "compose.yaml").read_text() == render(config, allow_unpinned=True).artefacts[
        "compose.yaml"
    ]
    assert (out / "litellm.yaml").read_text() == render_litellm_config(config)
    env = (out / "deployment.env").read_text().splitlines()
    assert [line for line in env if "_MODEL=" not in line] == secrets_before
    assert "OSPREY_EXTRACTION_MODEL=qwen2.5:14b-instruct" in env
    assert (
        "pull_and_verify qwen2.5:14b-instruct"
        in yaml.safe_load((out / "compose.yaml").read_text())["services"]["ollama"]["command"][0]
    )
    # The proxy reads its routing table at start: restarted after `up`, and waited on.
    assert _subcommands(run.calls) == ["build", "up", "restart", "up"]
    assert run.calls[2][-1] == "litellm"


def test_bringing_the_models_up_to_date_twice_changes_nothing_the_second_time(repo: Path) -> None:
    out = _rendered(repo)
    refresh.refresh(repo, run=Recorder(), register=Registrar())
    before = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
    run = Recorder()
    refresh.refresh(repo, run=run, register=Registrar())
    assert {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()} == before
    assert _subcommands(run.calls) == ["build", "up"]


# --- services a later render adds reach an existing deployment (ADR-098 decision 2) -------------


def test_a_service_added_since_the_deployment_was_rendered_is_brought_in_and_nothing_else_moves(
    repo: Path,
) -> None:
    """Catches the gap found adding the recogniser: refresh never renders, so a deployment made
    before `ner` existed would never run it, and the Conduit would never be told where it is. The
    new service and the Conduit's new setting are added; every existing service and every secret
    stays byte for byte."""
    import yaml

    out = _rendered(repo)
    document = yaml.safe_load((out / "compose.yaml").read_text())
    document["services"].pop("ner")
    document["services"]["api"]["environment"].pop("OSPREY_RECOGNISER_URL")
    document["services"]["api"]["environment"]["OSPREY_LOCAL_SETTING"] = "kept"
    text = (out / "compose.yaml").read_text()
    banner = text[: text.index("\nname:") + 1]
    (out / "compose.yaml").write_text(banner + yaml.safe_dump(document, sort_keys=False))
    before = yaml.safe_load((out / "compose.yaml").read_text())
    secrets_before = (out / "deployment.env").read_text()

    refresh.refresh(repo, run=Recorder(), register=Registrar())

    after = yaml.safe_load((out / "compose.yaml").read_text())
    assert "ner" in after["services"]
    assert after["services"]["api"]["environment"]["OSPREY_RECOGNISER_URL"] == "http://ner:8000"
    # What the deployment already had is left exactly as it was, including a local setting.
    assert after["services"]["api"]["environment"]["OSPREY_LOCAL_SETTING"] == "kept"
    for name, service in before["services"].items():
        if name in {"api", "ollama"}:  # ollama: the model step brings its pull up to date
            continue
        assert after["services"][name] == service
    assert (out / "deployment.env").read_text().splitlines()[: len(secrets_before.splitlines())]
    assert [
        line for line in (out / "deployment.env").read_text().splitlines() if "_MODEL=" not in line
    ] == [line for line in secrets_before.splitlines() if "_MODEL=" not in line]


def test_a_new_owned_service_is_built_like_the_deployments_others_when_it_was_rendered_to_build(
    repo: Path,
) -> None:
    """Found running it on the owner's deployment: `apply --build` builds the owned images from
    the checkout but leaves the copied `osprey.yaml` without `source_path`, so refresh rendered the
    recogniser in pull mode, a registry image that does not exist (`denied`). A deployment whose
    owned services build from source gets the new one built from source too."""
    import yaml
    from harness.render import render

    from schemas.deployment import OspreyConfig

    out = _rendered(repo)
    for dockerfile in (
        "apps/workspace/Dockerfile",
        "services/api/Dockerfile",
        "services/ingest/Dockerfile",
        "services/ner/Dockerfile",
    ):
        (repo / dockerfile).parent.mkdir(parents=True, exist_ok=True)
        (repo / dockerfile).write_text("FROM scratch\n", encoding="utf-8")
    building = OspreyConfig().model_copy(
        update={
            "components": OspreyConfig().components.model_copy(update={"source_path": str(repo)})
        }
    )
    document = yaml.safe_load(render(building, allow_unpinned=True).artefacts["compose.yaml"])
    document["services"].pop("ner")
    text = (out / "compose.yaml").read_text()
    banner = text[: text.index("\nname:") + 1]
    (out / "compose.yaml").write_text(banner + yaml.safe_dump(document, sort_keys=False))

    refresh.refresh(repo, run=Recorder(), register=Registrar())

    ner = yaml.safe_load((out / "compose.yaml").read_text())["services"]["ner"]
    assert ner["image"] == "osprey/ner:local"
    assert ner["build"]["dockerfile"] == "services/ner/Dockerfile"


def _pinned_before(out: Path) -> None:
    """The deployment as rendered before ADR-101: ArcadeDB 25.5.1, without the Groovy engine, with
    an operator's own setting beside it and the lock naming the old tag."""
    import yaml

    text = (out / "compose.yaml").read_text()
    banner = text[: text.index("\nname:") + 1]
    document = yaml.safe_load(text)
    arcadedb = document["services"]["arcadedb"]
    arcadedb["image"] = "arcadedata/arcadedb:25.5.1"
    arcadedb["environment"]["JAVA_OPTS"] = (
        "-Darcadedb.server.rootPassword=${OSPREY_ARCADEDB_PASSWORD:?}"
    )
    arcadedb["environment"]["OPERATOR_SETTING"] = "kept"
    (out / "compose.yaml").write_text(banner + yaml.safe_dump(document, sort_keys=False))
    lock = (out / "versions.lock").read_text() if (out / "versions.lock").exists() else ""
    (out / "versions.lock").write_text(
        lock + "images:\n- service: arcadedb\n  repository: arcadedata/arcadedb\n  tag: 25.5.1\n"
        "  digest: unresolved\n  source: unresolved\n"
    )


def test_a_third_party_service_moves_to_the_checkouts_pin_with_its_launch_options(
    repo: Path,
) -> None:
    """ADR-101: refresh never renders, so a store the checkout moved to a new version (ArcadeDB
    26.10.1, whose Gremlin needs `-Darcadedb.gremlin.engine=groovy`) stayed on the old one. The
    service takes the rendered image and the rendered values of the settings the render names; a
    setting of the operator's own stays, no secret changes, and the lock names the new tag."""
    import yaml
    from harness.render import load_config, render

    out = _rendered(repo)
    _pinned_before(out)
    secrets_before = (out / "deployment.env").read_text()
    before = yaml.safe_load((out / "compose.yaml").read_text())

    refresh.refresh(repo, run=Recorder(), register=Registrar())

    wanted = yaml.safe_load(
        render(load_config(out / "osprey.yaml"), allow_unpinned=True).artefacts["compose.yaml"]
    )["services"]["arcadedb"]
    after = yaml.safe_load((out / "compose.yaml").read_text())
    arcadedb = after["services"]["arcadedb"]
    assert arcadedb["image"] == wanted["image"] != "arcadedata/arcadedb:25.5.1"
    assert arcadedb["environment"]["JAVA_OPTS"] == wanted["environment"]["JAVA_OPTS"]
    assert arcadedb["environment"]["OPERATOR_SETTING"] == "kept"
    for name, service in before["services"].items():
        if name in {"arcadedb", "ollama"}:  # ollama: the model step brings its pull up to date
            continue
        assert after["services"][name] == service
    lock = yaml.safe_load((out / "versions.lock").read_text())
    (entry,) = [i for i in lock["images"] if i["service"] == "arcadedb"]
    assert entry["tag"] == wanted["image"].rsplit(":", 1)[1]
    assert [
        line for line in (out / "deployment.env").read_text().splitlines() if "_MODEL=" not in line
    ] == [line for line in secrets_before.splitlines() if "_MODEL=" not in line]


def test_an_operators_edit_to_a_service_on_the_checkouts_pin_stays(repo: Path) -> None:
    """The move happens only when the pin changed: an operator's heap or option on a store already
    at the checkout's version is theirs."""
    import yaml

    out = _rendered(repo)
    text = (out / "compose.yaml").read_text()
    banner = text[: text.index("\nname:") + 1]
    document = yaml.safe_load(text)
    document["services"]["arcadedb"]["environment"]["JAVA_OPTS"] = "-Doperator=own"
    (out / "compose.yaml").write_text(banner + yaml.safe_dump(document, sort_keys=False))

    refresh.refresh(repo, run=Recorder(), register=Registrar())

    after = yaml.safe_load((out / "compose.yaml").read_text())
    assert after["services"]["arcadedb"]["environment"]["JAVA_OPTS"] == "-Doperator=own"
