"""ADR-114 Amendment 39: refresh refuses, in words and changing nothing, a deployment rendered
before the model gateway kept its own database (ADR-135 Amendment 2), and any compose file Compose
could not interpolate; and it declares every named volume a mount it adds refers to.

Found by the v0.5.0 upgrade rehearsal (10 November 2026): `ospreyflow update` from v0.4.12 wrote a
compose file naming `${OSPREY_LITELLM_…:?}` secrets the deployment did not hold, and mounts of
volumes it never declared, so Compose refused every command, the update rolled back, and `stop` and
`apply` were locked out with it.

`fixtures/deployment_v0_4_12/` is v0.4.12's own render (commit 964a2a9, default settings), installed
from a release: the owned images pinned by digest in `ghcr.io/aykr`, its `versions.lock`, the fixed
gateway key `sk-ospreyflow-dev` on the gateway and the Conduit, and every secret v0.4.12's compose
requires held (synthetic values). It is placed as a deployment kept by name, as the rehearsal's was.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from harness import update
from harness.keycloak_theme import write_login_theme
from harness.render import render
from scripts import refresh

from schemas.deployment import OspreyConfig

FIXTURE = Path(__file__).parent / "fixtures" / "deployment_v0_4_12"
CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
TOKENS = ":root { --brass: #c08a34; }\n"


@pytest.fixture
def deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The v0.4.12 release install, kept by name, with a checkout of today's beside it."""
    out = tmp_path / "home" / ".ospreyflow" / "deployments" / "osprey-upg"
    shutil.copytree(FIXTURE, out)
    (out / "deployment.env").chmod(0o600)
    tokens = tmp_path / "checkout" / "apps" / "workspace" / "src" / "design" / "tokens.css"
    tokens.parent.mkdir(parents=True)
    tokens.write_text(TOKENS, encoding="utf-8")
    write_login_theme(out, tokens_css=TOKENS)
    monkeypatch.setenv(refresh.DEPLOYMENT_DIR_VARIABLE, str(out))
    return out


def _checkout(deployment: Path) -> Path:
    return deployment.parents[3] / "checkout"


def _hashes(folder: Path) -> dict[str, str]:
    """Every file's bytes and every file's and folder's mode, folders included."""
    return {
        str(p.relative_to(folder)): (
            hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "folder"
        )
        + oct(p.stat().st_mode & 0o777)
        for p in sorted(folder.rglob("*"))
    }


def _compose(folder: Path) -> dict:  # type: ignore[type-arg]
    return dict(yaml.safe_load((folder / "compose.yaml").read_text(encoding="utf-8")))


def _write_compose(folder: Path, document: dict) -> None:  # type: ignore[type-arg]
    text = (folder / "compose.yaml").read_text(encoding="utf-8")
    banner = text[: text.index("\nname:") + 1]
    body = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
    (folder / "compose.yaml").write_text(banner + body, encoding="utf-8")


def _built_from_source(folder: Path) -> None:
    """The v0.4.12 deployment as `apply --build` leaves it: owned images built here, no lock."""
    document = _compose(folder)
    for name in ("api", "workspace", "ingest", "ner"):
        service = document["services"][name]
        service["image"] = f"osprey/{name}:local"
        where = "apps" if name == "workspace" else "services"
        service["build"] = {"context": "../../..", "dockerfile": f"{where}/{name}/Dockerfile"}
    _write_compose(folder, document)
    (folder / "versions.lock").unlink()


# --- refused, and nothing in the folder changes --------------------------------------------------


@pytest.mark.parametrize("shape", ["a release install", "built from source"])
def test_a_v0_4_12_deployment_is_refused_and_nothing_in_its_folder_changes(
    deployment: Path, shape: str
) -> None:
    if shape == "built from source":
        _built_from_source(deployment)
    before = _hashes(deployment)
    with pytest.raises(refresh.RefreshFailed) as refused:
        refresh.files_up_to_date(_checkout(deployment))
    assert _hashes(deployment) == before
    words = str(refused.value)
    assert "\n" not in words  # `update` shows the last line its files step prints
    steps = ("backup", "apply", "update", "start --build")
    for step in (f"{verb} --name osprey-upg" for verb in steps):
        assert step in words, words
    assert not list(deployment.parent.glob(".*staging"))
    held = (deployment / "deployment.env").read_text(encoding="utf-8")
    assert (
        "OSPREY_MODEL_KEY_GEMINI=held-gemini-key\n" in held
    )  # a provider's key stays where it was


def test_start_build_says_the_refusal_in_words_and_starts_nothing(
    deployment: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ospreyflow start --build` runs `python -m scripts.refresh` (cli main.py `_start`)."""
    monkeypatch.setattr(refresh, "answer_localhost_with_loopback", lambda: None)
    ran: list[list[str]] = []

    def recorded(argv: list[str], *_: object, **__: object) -> subprocess.CompletedProcess[str]:
        ran.append(list(argv))  # what `refresh._run` would start: never Docker itself
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(refresh.subprocess, "run", recorded)
    before = _hashes(deployment)
    assert refresh.main([], repo_root=_checkout(deployment)) == 1
    said = capsys.readouterr()
    assert "ospreyflow apply --name osprey-upg" in said.err and "Traceback" not in said.err
    assert ran == [] and _hashes(deployment) == before


def test_updates_own_files_step_reports_the_refusal_as_a_step(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`harness.update.real_host` runs `python -m scripts.refresh --files-only` in the checkout
    through `_subprocess` and reports the last line it prints (`_ok_real`); v0.4.12's update does
    the same, then rolls back."""
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(CORE), str(CORE / "packages")]))
    before = _hashes(deployment)
    code, said = update._subprocess(
        [sys.executable, "-m", "scripts.refresh", "--files-only"], cwd=CORE
    )
    assert code == 1 and "Traceback" not in said, said
    with pytest.raises(update.UpdateFailed) as failed:
        update._ok_real(lambda _argv: (code, said), [], "bring the files up to date")
    assert failed.value.step == "bring the files up to date"
    assert "ospreyflow apply --name osprey-upg" in failed.value.why
    assert _hashes(deployment) == before


def test_a_list_form_gateway_environment_is_read_too(deployment: Path) -> None:
    document = _compose(deployment)
    gateway = document["services"]["litellm"]
    gateway["environment"] = [f"{k}={v}" for k, v in gateway["environment"].items()]
    _write_compose(deployment, document)
    assert refresh._predates_the_gateway_database(deployment)
    gateway["environment"].append("LITELLM_SALT_KEY=${OSPREY_LITELLM_SALT_SECRET:?set}")
    _write_compose(deployment, document)
    assert not refresh._predates_the_gateway_database(deployment)


def test_no_gateway_is_no_refusal_on_its_account(deployment: Path) -> None:
    document = _compose(deployment)
    del document["services"]["litellm"]
    _write_compose(deployment, document)
    assert not refresh._predates_the_gateway_database(deployment)


# --- after Amendment 2: a deployment Compose could not interpolate, or one with new mounts --------


def _after_the_gateway_database(deployment: Path) -> None:
    """The v0.4.12 deployment as `ospreyflow apply` leaves it past Amendment 2, but before the
    Conduit's settings mounts: today's gateway and its database, the Conduit's key for it, and the
    three secrets held; still v0.4.12's api mounts and top-level volumes."""
    today = yaml.safe_load(render(OspreyConfig(), allow_unpinned=True).artefacts["compose.yaml"])
    document = _compose(deployment)
    for name in ("litellm", "litellm-db"):
        document["services"][name] = today["services"][name]
    document["services"]["api"]["environment"]["LITELLM_API_KEY"] = today["services"]["api"][
        "environment"
    ]["LITELLM_API_KEY"]
    _write_compose(deployment, document)
    with (deployment / "deployment.env").open("a", encoding="utf-8") as env:
        env.write(
            "OSPREY_LITELLM_MASTER_SECRET=sk-held-master\n"
            "OSPREY_LITELLM_SALT_SECRET=held-salt\n"
            "OSPREY_LITELLM_DB_PASSWORD=held-db\n"
        )


def test_a_required_secret_the_deployment_does_not_hold_is_refused_and_nothing_changes(
    deployment: Path,
) -> None:
    """The generic case: the salt required and not held (as a half-run refresh left one)."""
    _after_the_gateway_database(deployment)
    env = deployment / "deployment.env"
    env.write_text(
        "".join(
            line + "\n"
            for line in env.read_text().splitlines()
            if not line.startswith("OSPREY_LITELLM_SALT_SECRET=")
        ),  # fmt: skip
        encoding="utf-8",
    )
    before = _hashes(deployment)
    with pytest.raises(refresh.RefreshFailed) as refused:
        refresh.files_up_to_date(_checkout(deployment))
    assert "ospreyflow apply --name osprey-upg" in str(refused.value)
    assert "held-" not in str(refused.value)  # names and steps, never a value
    assert _hashes(deployment) == before


def test_every_named_volume_a_mount_refers_to_is_declared(deployment: Path) -> None:
    _after_the_gateway_database(deployment)
    refresh.files_up_to_date(_checkout(deployment))
    document = _compose(deployment)
    declared = set(document.get("volumes") or {})
    mounted = {
        str(volume).split(":", 1)[0]
        for service in document["services"].values()
        for volume in service.get("volumes") or []
        if ":" in str(volume) and not str(volume).startswith((".", "/", "~", "$"))
    }
    assert {"map-settings", "model-settings"} <= mounted  # what refresh gave the Conduit
    assert sorted(mounted - declared) == []
    assert refresh._unset_required(deployment) == []
    lines = (deployment / "deployment.env").read_text().splitlines()
    held = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    assert held["OSPREY_LITELLM_MASTER_SECRET"] == "sk-held-master"  # nothing minted or changed


def test_compose_itself_accepts_the_refreshed_project(deployment: Path) -> None:
    """Compose's own reading, not ours: `config -q` needs no daemon, but calls the docker CLI, so on
    a machine with local stacks off it is skipped in words (tests/local_docker_guard.py)."""
    _after_the_gateway_database(deployment)
    refresh.files_up_to_date(_checkout(deployment))
    done = subprocess.run(  # noqa: S603, S607 - the docker CLI's own check of the project
        [
            "docker",
            "compose",
            "-f",
            str(deployment / "compose.yaml"),
            "--env-file",
            str(deployment / "deployment.env"),
            "config",
            "-q",
        ],  # fmt: skip
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr


def test_the_refusal_words_always_name_the_deployment(tmp_path: Path) -> None:
    named = tmp_path / "deployments" / "osprey-upg"
    own = tmp_path / "deploy" / "generated" / "local-lite"
    assert "ospreyflow apply --name osprey-upg" in refresh.before_the_gateway_database(named)
    words = refresh.before_the_gateway_database(own)
    assert "`ospreyflow apply --name default`" in words  # never "the one last used"
    assert re.search(r"git checkout <its tag>", words)


# --- the staged pass: private while it runs, and moved into place whole -------------------------


def test_the_stage_is_private_while_the_pass_runs(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _after_the_gateway_database(deployment)
    seen: list[str] = []
    real = refresh._files_up_to_date_in

    def look(stage: Path, repo_root: Path) -> dict[str, bool]:
        seen.append(oct(stage.stat().st_mode & 0o777))
        seen.append(oct((stage / "deployment.env").stat().st_mode & 0o777))
        return real(stage, repo_root)

    monkeypatch.setattr(refresh, "_files_up_to_date_in", look)
    refresh.files_up_to_date(_checkout(deployment))
    assert seen == ["0o700", "0o600"]


def test_an_interrupted_move_into_place_leaves_whole_files_and_the_secrets_as_they_were(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _after_the_gateway_database(deployment)
    before = {p.name: p.read_bytes() for p in deployment.iterdir() if p.is_file()}
    real = os.replace
    moved: list[str] = []

    def second_fails(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        if moved:
            raise OSError("interrupted")
        moved.append(Path(dst).name)
        real(src, dst)

    monkeypatch.setattr(os, "replace", second_fails)  # the one refresh calls
    with pytest.raises(OSError, match="interrupted"):
        refresh.files_up_to_date(_checkout(deployment))
    assert moved and moved[0] != "deployment.env"
    assert (deployment / "deployment.env").read_bytes() == before["deployment.env"]
    in_place = refresh._mounted_files(deployment)  # written whole, in place, before the renames
    for path in deployment.iterdir():
        if path.is_file() and path.name not in moved and path.name not in in_place:
            assert path.read_bytes() == before[path.name], path.name  # old, whole
    assert yaml.safe_load((deployment / moved[0]).read_text()) is not None  # new, whole
    assert not list(deployment.parent.glob(".*staging"))


# --- which deployment an update's files step brings up to date -----------------------------------


def _rollback_point(folder: Path, minutes_ago: int = 1) -> None:
    """As v0.4.12's `_keep_rollback_point` leaves it (964a2a9 `harness/update.py` 278-287)."""
    made = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    point = folder / "rollback" / f"v0.4.12-{made.strftime('%Y%m%dT%H%M%SZ')}"
    point.mkdir(parents=True)
    (point / ".commit").write_text("964a2a9", encoding="utf-8")


def _the_checkouts_own(deployment: Path) -> Path:
    own = _checkout(deployment) / "deploy" / "generated" / "local-lite"
    shutil.copytree(deployment, own, ignore=shutil.ignore_patterns("rollback"))
    return own


def test_an_update_from_an_earlier_release_reaches_the_deployment_it_is_moving(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """v0.4.12's `update` names no deployment to `--files-only`; its rollback point, kept in the
    deployment's own folder just before, says which (the rehearsal, 10 November 2026)."""
    own = _the_checkouts_own(deployment)
    _rollback_point(deployment)
    monkeypatch.delenv(refresh.DEPLOYMENT_DIR_VARIABLE)
    monkeypatch.setenv("HOME", str(deployment.parents[2]))
    before = _hashes(own)
    assert refresh.main(["--files-only"], repo_root=_checkout(deployment)) == 1
    assert "ospreyflow apply --name osprey-upg" in capsys.readouterr().err  # the named one, refused
    assert _hashes(own) == before  # the checkout's own deployment never touched


def test_two_updates_under_way_are_refused_and_nothing_changes(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    own = _the_checkouts_own(deployment)
    _rollback_point(deployment)
    _rollback_point(own)
    monkeypatch.delenv(refresh.DEPLOYMENT_DIR_VARIABLE)
    monkeypatch.setenv("HOME", str(deployment.parents[2]))
    before = (_hashes(own), _hashes(deployment))
    assert refresh.main(["--files-only"], repo_root=_checkout(deployment)) == 1
    said = capsys.readouterr().err
    assert "More than one deployment has an update under way" in said and str(own) in said
    assert (_hashes(own), _hashes(deployment)) == before


def _the_owners_shape(deployment: Path) -> dict[str, Path]:
    """Three deployments kept by name and the checkout's own, as on the owner's machine."""
    folders = {"default": _the_checkouts_own(deployment), "osprey-upg": deployment}
    for name in ("govuk", "demo"):
        folders[name] = deployment.parent / name
        shutil.copytree(deployment, folders[name], ignore=shutil.ignore_patterns("rollback"))
    return folders


def test_on_the_owners_shape_only_the_deployment_under_way_is_reached(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folders = _the_owners_shape(deployment)
    _rollback_point(folders["govuk"])  # the one being updated
    _rollback_point(folders["default"], minutes_ago=180)  # an update of hours ago
    _rollback_point(folders["demo"], minutes_ago=24 * 60)
    (folders["osprey-upg"] / "rollback" / "notes").mkdir(parents=True)  # not a rollback point
    monkeypatch.delenv(refresh.DEPLOYMENT_DIR_VARIABLE)
    monkeypatch.setenv("HOME", str(deployment.parents[2]))
    others = {n: _hashes(f) for n, f in folders.items() if n != "govuk"}
    assert refresh.main(["--files-only"], repo_root=_checkout(deployment)) == 1
    assert "ospreyflow apply --name govuk" in capsys.readouterr().err
    assert {n: _hashes(f) for n, f in folders.items() if n != "govuk"} == others


def test_on_the_owners_shape_two_under_way_are_refused_by_name(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folders = _the_owners_shape(deployment)
    _rollback_point(folders["govuk"])
    _rollback_point(folders["demo"], minutes_ago=30)
    monkeypatch.delenv(refresh.DEPLOYMENT_DIR_VARIABLE)
    monkeypatch.setenv("HOME", str(deployment.parents[2]))
    before = {n: _hashes(f) for n, f in folders.items()}
    assert refresh.main(["--files-only"], repo_root=_checkout(deployment)) == 1
    said = capsys.readouterr().err
    assert str(folders["govuk"]) in said and str(folders["demo"]) in said
    assert "ospreyflow update --name <deployment>" in said
    assert {n: _hashes(f) for n, f in folders.items()} == before


def test_with_no_update_under_way_the_checkouts_own_is_found_as_before(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    own = _the_checkouts_own(deployment)
    monkeypatch.delenv(refresh.DEPLOYMENT_DIR_VARIABLE)
    monkeypatch.setenv("HOME", str(deployment.parents[2]))
    refresh._for_an_update(_checkout(deployment))
    assert refresh.DEPLOYMENT_DIR_VARIABLE not in os.environ
    assert refresh._find_deployment_dir(_checkout(deployment)) == own


def test_todays_update_names_its_deployment_to_the_files_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "deployments" / "osprey-upg"
    folder.mkdir(parents=True)
    (folder / "osprey.yaml").write_text("{}\n", encoding="utf-8")
    seen: list[dict[str, str]] = []

    def fake(argv: object, cwd: Path | None = None, env: dict[str, str] | None = None) -> tuple:  # type: ignore[type-arg]
        seen.append(dict(env or {}))
        return 0, '{"proxy_changed": false, "theme_changed": false, "routing_changed": false}'

    monkeypatch.setattr(update, "_subprocess", fake)
    update.real_host(folder, tmp_path).files_up_to_date()
    assert seen and seen[0][update.DEPLOYMENT_DIR] == str(folder)


def test_the_salt_check_alone_refuses_a_v0_4_12_gateway_whose_secrets_are_held(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generic check passes this one (every required name held, as a half-run refresh of the
    withdrawn minting could leave it); only the top-of-pass check stands before the pass."""
    with (deployment / "deployment.env").open("a", encoding="utf-8") as env:
        env.write(
            "OSPREY_LITELLM_MASTER_SECRET=sk-held-master\n"
            "OSPREY_LITELLM_SALT_SECRET=held-salt\n"
            "OSPREY_LITELLM_DB_PASSWORD=held-db\n"
        )
    passes: list[Path] = []
    monkeypatch.setattr(refresh, "_files_up_to_date_in", lambda d, r: passes.append(d) or {})
    before = _hashes(deployment)
    with pytest.raises(refresh.RefreshFailed):
        refresh.files_up_to_date(_checkout(deployment))
    assert passes == [] and _hashes(deployment) == before
    assert not list(deployment.parent.glob(".*staging"))


def test_a_file_a_service_mounts_on_its_own_keeps_its_inode(deployment: Path) -> None:
    """`./glass.json` is the workspace's `deployment.json`, served per visit: a rename would leave
    the running container serving the old one."""
    _after_the_gateway_database(deployment)
    glass = deployment / "glass.json"
    glass.write_text('{"stale": true}\n', encoding="utf-8")
    inode = glass.stat().st_ino
    refresh.files_up_to_date(_checkout(deployment))
    assert glass.read_text(encoding="utf-8") != '{"stale": true}\n'  # it was brought up to date
    assert glass.stat().st_ino == inode


@pytest.mark.parametrize("stamp", ["future", "20261399T000000Z"])
def test_a_rollback_point_from_the_future_or_no_clock_marks_nothing(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, stamp: str
) -> None:
    if stamp == "future":
        _rollback_point(deployment, minutes_ago=-30)
    else:
        point = deployment / "rollback" / f"v0.4.12-{stamp}"
        point.mkdir(parents=True)
        (point / ".commit").write_text("964a2a9", encoding="utf-8")
    monkeypatch.setenv("HOME", str(deployment.parents[2]))
    assert refresh._being_updated(_checkout(deployment)) == []


def test_a_long_syntax_mount_declares_its_own_named_volume(deployment: Path) -> None:
    _after_the_gateway_database(deployment)
    document = _compose(deployment)
    document["services"]["api"].setdefault("volumes", []).append(
        {"type": "volume", "source": "operator-notes", "target": "/srv/notes"}
    )
    _write_compose(deployment, document)
    refresh.files_up_to_date(_checkout(deployment))
    declared = set(_compose(deployment)["volumes"])
    assert "operator-notes" in declared and not any(name.startswith("{") for name in declared)
