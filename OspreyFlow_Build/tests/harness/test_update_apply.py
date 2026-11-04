"""`ospreyflow update` (ADR-114 decision 13, Amendment 6 point 1, Amendment 8 points 6 and 6a).

What a mistake would do, and the case that catches it:
- a deployment that builds from its checkout moved by release images — `…builds_from_its_checkout…`;
- an unsigned release applied — `test_an_unsigned_release_changes_nothing`;
- a local change silently lost by the checkout — `test_a_local_change_the_release_would_overwrite…`;
- data at risk with no backup — `test_a_failed_backup_changes_nothing`;
- a release that fails to start left half applied — `…fails_to_start_is_rolled_back…`;
- a release running other images than its lock claims — `test_a_container_on_another_digest…`;
- a rollback that fails reported as fine — `…rollback_that_fails_says_exactly_where…`.

The host is a fake that refuses as Docker and git do: a pull of a digest the registry lacks fails,
`up --wait` fails when a service's image is one it was told is broken, and `ps` reports what is
running. The real tools are exercised by the live proof (`07_BUILD_PLAN.md`, the B5c row).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness import update
from harness.release import ReleaseRefused
from harness.signatures import Cosign, PublicKey

OLD, NEW = "sha256:" + "1" * 64, "sha256:" + "2" * 64
BROKEN = "sha256:" + "9" * 64
REG = "localhost:5055/acme"


def _lock(digest: str, *, arcadedb: str = OLD) -> str:
    rows = [
        {"service": s, "repository": f"{REG}/{s}", "tag": "x", "digest": digest,
         "source": "registry"}
        for s in ("workspace", "api", "ingest", "ner")
    ]  # fmt: skip
    rows.append({"service": "arcadedb", "repository": "arcadedata/arcadedb", "tag": "26.10.1",
                 "digest": arcadedb, "source": "registry"})  # fmt: skip
    return "# GENERATED\n" + yaml.safe_dump({"images": rows}, sort_keys=False)


def _compose(digest: str, *, build: bool = False) -> dict[str, Any]:
    services: dict[str, Any] = {
        s: {"image": f"{REG}/{s}@{digest}"} for s in ("workspace", "api", "ingest", "ner")
    }
    services["report-sync"] = {"image": f"{REG}/api@{digest}"}  # the Conduit's image, no build
    services["arcadedb"] = {"image": "arcadedata/arcadedb:26.10.1"}
    services["keycloak-db"] = {"image": "postgres:16", "restart": "no"}
    if build:
        services["api"]["build"] = {"context": "../../.."}
    return {"name": "osprey-test", "services": services}


class _Host:
    """Docker, git, cosign, backup and restore, as far as `update` can tell."""

    def __init__(self, tmp: Path, *, release: str = NEW, version: str = "v0.4.1") -> None:
        self.directory = tmp / "deploy" / "generated" / "local-lite"
        self.directory.mkdir(parents=True)
        self.repo = tmp
        (self.directory / "compose.yaml").write_text("# banner\n" + yaml.safe_dump(_compose(OLD)))
        (self.directory / "versions.lock").write_text(_lock(OLD))
        (self.directory / "deployment.env").write_text(
            f"OSPREY_RELEASE_VERSION={version}\nOSPREY_X_PASSWORD=s3cret\n"
        )
        self.release_digest = release
        self.registry = {OLD, NEW, BROKEN}
        self.broken = {BROKEN}
        self.signed = {OLD, NEW, BROKEN}
        self.running: dict[str, str] = {}
        self.actions: list[str] = []
        self.local_changes = ""
        self.conflicting: set[str] = set()
        self.head = "c0ffee"
        self.backup_fails = False
        self.restore_fails = False
        self.wrong_digest_for: str | None = None
        self.release_tag = "v0.5.0"
        self.oneshot_fails_with: str | None = None
        self.backup_vanishes = False
        self.lock_signed = True
        self.loaded_ids: dict[str, str] = {}
        self.bundle_refused = False
        #: `ollama-models`: the command its container ran, its pulls, and the state of the models
        #: each `up` of the rest of the deployment found.
        self.step_command: Any = None
        self.fetch = "done"
        self.fetch_fails = False
        self.started_with_models: list[str] = []
        self.new_pull_command: list[str] | None = None

    # -- the command runner ------------------------------------------------------------------
    def run(self, argv: Sequence[str]) -> tuple[int, str]:
        argv = list(argv)
        if argv[0] == "git":
            return self._git(argv[3:])
        if argv[:2] == ["docker", "compose"]:
            return self._compose(argv[argv.index("-f") + 2 :])
        if argv[:3] == ["docker", "inspect", "--format"]:
            service = argv[-1].removeprefix("osprey-test-").removesuffix("-1")
            if self.loaded_ids:  # images loaded from a bundle: compared by image ID
                repo = f"{REG}/api" if service == "report-sync" else _repo_of(service)
                return 0, self.loaded_ids.get(repo, "sha256:unknown")
            return 0, f"image-of-{argv[-1]}"
        if argv[:3] == ["docker", "volume", "rm"]:
            self.actions.append("volume rm " + " ".join(argv[3:]))
            return 0, ""
        if argv[:4] == ["docker", "image", "inspect", "--format"]:
            service = argv[-1].removeprefix("image-of-osprey-test-").removesuffix("-1")
            digest = self.running[service]
            if service == self.wrong_digest_for:
                digest = OLD
            repo = f"{REG}/api" if service == "report-sync" else f"{REG}/{service}"
            return 0, json.dumps([f"{repo}@{digest}"])
        raise AssertionError(argv)

    def _git(self, args: list[str]) -> tuple[int, str]:
        self.actions.append("git " + " ".join(args))
        if args[0] == "fetch":
            return 0, ""
        if args[0] == "rev-parse":
            return 0, self.head if args[1] == "HEAD" else "beefed"
        if args[0] == "status":
            return 0, self.local_changes
        if args[0] == "diff":
            return (1 if args[-1] in self.conflicting else 0), ""
        if args[0] == "checkout":
            self.head = args[-1]
            return 0, ""
        raise AssertionError(args)

    def _images(self) -> dict[str, str]:
        doc = yaml.safe_load((self.directory / "compose.yaml").read_text())
        return {name: s["image"] for name, s in doc["services"].items()}

    def _compose(self, args: list[str]) -> tuple[int, str]:
        self.actions.append("compose " + " ".join(args))
        if args[0] == "pull":
            missing = [
                i
                for i in self._images().values()
                if "@" in i and i.split("@")[1] not in self.registry
            ]
            return (1, f"manifest unknown: {missing}") if missing else (0, "")
        if args[0] == "up":
            named = [a for a in args[1:] if not a.startswith("-")]
            self._model_step(args, named)
            if named == ["ollama-models"]:
                return 0, ""
            # Whatever the rest of the deployment starts on, the model it names is there or not.
            self.started_with_models.append(self.fetch)
            images = self._images()
            # Whatever each service names runs: by digest, or (from a bundle) by a loaded tag.
            self.running = {
                n: (i.split("@")[1] if "@" in i else i)
                for n, i in images.items()
                if "@" in i or ":ospreyflow-" in i
            }
            if any(d in self.broken for d in self.running.values()):
                return 1, "dependency failed to start: container osprey-test-api-1 is unhealthy"
            return 0, ""
        if args[0] == "down":
            self.running = {}
            return 0, ""
        if args[0] == "restart":
            return 0, ""
        if args[0] == "exec" and args[2] == "ollama-models":
            # Waits until the step's pulls are done; a refused pull exits it, and the exec fails.
            if self.fetch == "fetching":
                self.fetch = "failed" if self.fetch_fails else "done"
            return (1, "exit status 137") if self.fetch == "failed" else (0, "")
        if args[0] == "ps":
            rows = [{"Service": n, "Name": f"osprey-test-{n}-1", "State": "running", "Health": "",
                     "ExitCode": 0} for n in self.running]  # fmt: skip
            # The one-shot belongs to the version running: it fails only with its release.
            failed = self.oneshot_fails_with in self.running.values()
            rows.append({"Service": "keycloak-db", "Name": "osprey-test-keycloak-db-1",
                         "State": "exited", "Health": "", "ExitCode": int(failed)})  # fmt: skip
            return 0, "\n".join(json.dumps(r) for r in rows)
        raise AssertionError(args)

    def _model_step(self, args: list[str], named: list[str]) -> None:
        """As Compose does with the one-shot `ollama-models`: an `up` that covers it (naming it, or
        naming nothing) makes it again only when its command changed, or forced; made again, it
        pulls in the background, and nothing waits for it."""
        step = yaml.safe_load((self.directory / "compose.yaml").read_text())["services"].get(
            "ollama-models"
        )
        if step is None or (named and "ollama-models" not in named):
            return
        if step["command"] != self.step_command or "--force-recreate" in args:
            self.step_command = step["command"]
            self.fetch = "fetching"

    # -- the other seams -----------------------------------------------------------------------
    def cosign_run(self, argv: Sequence[str]) -> tuple[int, str]:
        if "verify-blob" in argv:
            self.actions.append("verify the lock")
            return (0, "Verified OK") if self.lock_signed else (1, "invalid signature")
        digest = argv[-1].split("@")[1]
        return (0, "verified") if digest in self.signed else (1, "no signatures found")

    def backup(self) -> Path:
        self.actions.append("backup")
        if self.backup_fails:
            raise update.UpdateFailed("back up every store", "the graph store did not answer")
        path = self.repo / "backups" / "set-1"
        if not self.backup_vanishes:
            path.mkdir(parents=True)
        return path

    def restore(self, path: Path) -> None:
        self.actions.append(f"restore {path.name}")
        if self.restore_fails:
            raise update.UpdateFailed("restore the backup", "Postgres refused the load")

    def files_up_to_date(self) -> dict[str, bool]:
        self.actions.append("files")
        if self.new_pull_command is None:
            return {"proxy_changed": False, "theme_changed": False}
        # The new checkout's refresh writes the release's pull script (`scripts/refresh.py`).
        text = (self.directory / "compose.yaml").read_text()
        doc = yaml.safe_load(text)
        doc["services"]["ollama-models"]["command"] = self.new_pull_command
        (self.directory / "compose.yaml").write_text("# banner\n" + yaml.safe_dump(doc))
        return {"proxy_changed": True, "theme_changed": False}

    def find_release(self, tag: str | None) -> dict[str, str]:
        self.actions.append(f"find {tag}")
        return {"tag": self.release_tag, "notes": "- new", "lock": _lock(self.release_digest),
                "lock_signature": "{}"}  # fmt: skip

    def host(self) -> update.Host:
        return update.Host(
            run=self.run,
            cosign=Cosign(self.cosign_run),
            identity=lambda tag: PublicKey(Path("/k/cosign.pub")),
            backup=self.backup,
            restore=self.restore,
            files_up_to_date=self.files_up_to_date,
            find_release=self.find_release,
        )


def _repo_of(service: str) -> str:
    return "arcadedata/arcadedb" if service == "arcadedb" else f"{REG}/{service}"


def _update(fake: _Host, **kwargs: Any) -> int:
    return update.apply_update(
        fake.directory, fake.repo, fake.host(), confirm=lambda _: True, **kwargs
    )


def _changed(fake: _Host, before: dict[str, bytes]) -> bool:
    return {p.name: p.read_bytes() for p in fake.directory.iterdir() if p.is_file()} != before


def _files(fake: _Host) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in fake.directory.iterdir() if p.is_file()}


# --- refusals before anything changes ------------------------------------------------------------


def test_a_deployment_that_builds_from_its_checkout_is_refused_in_words(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    (fake.directory / "compose.yaml").write_text(yaml.safe_dump(_compose(OLD, build=True)))
    assert _update(fake) == 1
    assert "builds from its checkout" in capsys.readouterr().err
    assert fake.actions == []


def test_a_deployment_that_is_not_a_release_is_refused(tmp_path: Path) -> None:
    fake = _Host(tmp_path, version="dev-abc1234")
    assert _update(fake) == 1 and fake.actions == []


def test_a_release_that_is_not_newer_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    fake.release_tag = "v0.4.1"
    before = _files(fake)
    assert _update(fake) == 0
    assert "Already at v0.4.1" in capsys.readouterr().out
    assert fake.actions == ["find None"] and not _changed(fake, before)


def test_a_release_that_cannot_be_found_is_said_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)

    def refuse(tag: str | None) -> dict[str, str]:
        raise ReleaseRefused("acme/ospreyflow has no published release v9.9.9.")

    host = fake.host()
    host.find_release = refuse
    assert (
        update.apply_update(fake.directory, fake.repo, host, to="v9.9.9", confirm=lambda _: True)
        == 1
    )
    assert "no published release v9.9.9" in capsys.readouterr().err


def test_an_unsigned_release_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    fake.signed = {OLD}
    before = _files(fake)
    assert _update(fake) == 1
    said = capsys.readouterr().err
    assert f"{REG}/api@{NEW}" in said and "Nothing was changed" in said
    assert "backup" not in fake.actions and not any(
        a.startswith("git checkout") for a in fake.actions
    )
    assert not _changed(fake, before)


def test_a_local_change_the_release_would_overwrite_is_refused_before_the_backup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A change of the operator's own to a file the release also changes would stop the checkout;
    one to a file the release leaves alone (the install's `osprey.yaml`) travels with it."""
    fake = _Host(tmp_path)
    fake.local_changes = " M osprey.yaml\n M harness/render.py\n"
    fake.conflicting = {"harness/render.py"}
    assert _update(fake) == 1
    said = capsys.readouterr().err
    assert "harness/render.py" in said and "osprey.yaml" not in said
    assert "backup" not in fake.actions


def test_a_local_change_the_release_leaves_alone_does_not_stop_it(tmp_path: Path) -> None:
    fake = _Host(tmp_path)
    fake.local_changes = " M osprey.yaml\n"
    assert _update(fake) == 0


def test_a_failed_backup_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    fake.backup_fails = True
    before = _files(fake)
    assert _update(fake) == 1
    assert "Nothing was changed" in capsys.readouterr().err
    assert not any(a.startswith("git checkout") for a in fake.actions)
    assert not _changed(fake, before)


def test_declining_changes_nothing(tmp_path: Path) -> None:
    fake = _Host(tmp_path)
    assert update.apply_update(fake.directory, fake.repo, fake.host(), confirm=lambda _: False) == 1
    assert "backup" not in fake.actions


# --- an update that succeeds ----------------------------------------------------------------------


def test_an_update_backs_up_moves_the_checkout_pins_by_digest_and_verifies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    assert _update(fake) == 0
    order = [a.split()[0] + (" " + a.split()[1] if a.startswith(("git", "compose")) else "")
             for a in fake.actions]  # fmt: skip
    assert order[order.index("backup") :][:5] == [
        "backup", "git checkout", "files", "compose pull", "compose up",
    ]  # fmt: skip
    assert "git checkout --quiet v0.5.0" in fake.actions
    images = fake._images()
    assert images["api"] == f"{REG}/api@{NEW}"
    assert images["report-sync"] == f"{REG}/api@{NEW}"  # the Conduit's image, wherever it runs
    assert images["arcadedb"] == f"arcadedata/arcadedb@{OLD}"  # third party: pinned by digest
    assert yaml.safe_load((fake.directory / "versions.lock").read_text()) == yaml.safe_load(
        _lock(NEW)
    )
    assert (fake.directory / "compose.yaml").read_text().startswith("# banner\n")
    said = capsys.readouterr().out
    assert "Updated to v0.5.0" in said and "set-1" in said
    assert "s3cret" not in said


OLD_PULLS = ["pull_and_verify qwen2.5:7b-instruct 845dbda0ea48\nexec sleep infinity\n"]
NEW_PULLS = ["pull_and_verify qwen2.5:14b-instruct 7cdf5a0187d5\nexec sleep infinity\n"]


def _with_the_model_step(fake: _Host) -> None:
    doc = yaml.safe_load((fake.directory / "compose.yaml").read_text())
    doc["services"]["ollama-models"] = {
        "image": "ollama/ollama:0.12.6", "command": OLD_PULLS, "restart": "no"
    }  # fmt: skip
    (fake.directory / "compose.yaml").write_text("# banner\n" + yaml.safe_dump(doc))
    fake.step_command = OLD_PULLS
    fake.new_pull_command = NEW_PULLS


def test_the_stand_in_starts_the_model_step_again_only_when_its_command_changed(
    tmp_path: Path,
) -> None:
    """Rule 15: as Compose does, an `up` that leaves the step out, or finds its command unchanged,
    fetches nothing; one that makes it again does not wait for its pulls."""
    fake = _Host(tmp_path)
    _with_the_model_step(fake)
    compose = ["docker", "compose", "-f", str(fake.directory / "compose.yaml")]
    fake.run([*compose, "up", "-d", "--wait"])
    fake.run([*compose, "up", "-d", "--no-deps", "api"])
    assert fake.fetch == "done" and fake.step_command == OLD_PULLS
    fake.files_up_to_date()
    fake.run([*compose, "up", "-d", "--no-deps", "api"])
    assert fake.step_command == OLD_PULLS
    fake.run([*compose, "up", "-d", "--wait"])
    assert fake.started_with_models[-1] == "fetching"
    fake.fetch_fails = True
    assert fake.run([*compose, "exec", "-T", "ollama-models", "true"])[0] == 1


def test_an_update_that_changes_the_models_fetches_them_before_the_release_starts(
    tmp_path: Path,
) -> None:
    """Defect 9's shape in `update`: the release's `up` makes `ollama-models` again for its new
    command, and starts the gateway and the Conduit on the new model beside it, waiting for
    nothing. The step is started by name and waited on first."""
    fake = _Host(tmp_path)
    _with_the_model_step(fake)
    assert _update(fake) == 0
    assert fake.started_with_models == ["done"] * len(fake.started_with_models)
    fetch = fake.actions.index("compose up -d --no-deps ollama-models")
    assert fake.actions[fetch + 1].startswith("compose exec -T ollama-models")
    assert fetch < fake.actions.index("compose up -d --wait")


def test_a_refused_model_download_rolls_the_update_back(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    _with_the_model_step(fake)
    fake.fetch_fails = True
    before = _files(fake)
    assert _update(fake) == 1
    said = capsys.readouterr().err
    assert "ollama-models" in said
    assert "restore set-1" in fake.actions
    assert _files(fake) == before


# --- an update that fails is rolled back ----------------------------------------------------------


def test_a_release_that_fails_to_start_is_rolled_back_with_the_backup_restored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path, release=BROKEN)
    before = _files(fake)
    assert _update(fake) == 1
    after_failure = fake.actions[fake.actions.index("compose up -d --wait") + 1 :]
    assert after_failure[:5] == [
        "git checkout --quiet c0ffee", "compose down -v", "compose up -d --wait",
        "restore set-1", "compose ps --all --format json",
    ]  # fmt: skip
    assert _files(fake) == before  # every file the update wrote, put back
    assert set(fake.running.values()) == {OLD}
    said = capsys.readouterr().err
    assert "start the release" in said and "unhealthy" in said
    assert "rolled back to v0.4.1" in said and "set-1" in said


def test_a_container_on_another_digest_than_the_lock_is_a_failed_update(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    fake.wrong_digest_for = "api"
    assert _update(fake) == 1
    said = capsys.readouterr().err
    assert "api runs" in said and "rolled back" in said


def test_a_pull_the_registry_refuses_is_rolled_back(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    fake.registry = {OLD}
    assert _update(fake) == 1
    assert "manifest unknown" in capsys.readouterr().err
    assert "restore set-1" in fake.actions


def test_a_rollback_that_fails_says_exactly_where_things_stand(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path, release=BROKEN)
    fake.restore_fails = True
    assert _update(fake) == 2
    said = capsys.readouterr().err
    assert "The rollback did not finish" in said
    assert "restore the backup" in said and "Postgres refused the load" in said
    assert "ospreyflow restore" in said and str(tmp_path / "backups" / "set-1") in said


def test_the_stores_are_never_emptied_when_the_backup_is_not_on_disk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rollback empties the stores only to restore the backup into them: with the backup gone
    (a disk cleared, a folder moved) it must stop before `down -v` and say so."""
    fake = _Host(tmp_path, release=BROKEN)
    fake.backup_vanishes = True
    assert _update(fake) == 2
    assert "compose down -v" not in fake.actions
    assert "is not there" in capsys.readouterr().err


def test_a_one_shot_step_that_failed_fails_the_update(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A finished one-shot (the database set-up, a model download) counts only if it succeeded."""
    fake = _Host(tmp_path)
    fake.oneshot_fails_with = NEW
    assert _update(fake) == 1
    assert "keycloak-db is exited" in capsys.readouterr().err


def test_a_release_whose_lock_does_not_verify_changes_nothing_and_is_checked_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    fake.lock_signed = False
    before = _files(fake)
    assert _update(fake) == 1
    said = capsys.readouterr().err
    assert "versions.lock is not signed" in said and "Nothing was changed" in said
    assert fake.actions == ["find None", "verify the lock"]
    assert not _changed(fake, before)


def test_the_lock_is_verified_before_any_image(tmp_path: Path) -> None:
    fake = _Host(tmp_path)
    assert _update(fake) == 0
    assert fake.actions[:2] == ["find None", "verify the lock"]


# --- from a bundle (Amendment 8 point 10) ------------------------------------------------------


def _from_bundle(fake: _Host, tmp_path: Path) -> update.Host:
    from harness.bundle import BundleRefused

    configs = {_repo_of(s): "sha256:" + str(i) * 64 for i, s in
               enumerate(("workspace", "api", "ingest", "ner", "arcadedb"), 3)}  # fmt: skip

    def open_bundle(path: Path) -> dict[str, Any]:
        fake.actions.append(f"open {path.name}")
        return {"tag": "v0.5.0", "notes": "- new", "lock": _lock(NEW), "lock_signature": "{}",
                "root": tmp_path / "opened"}  # fmt: skip

    def check_bundle(root: Path, identity: Any) -> dict[str, tuple[str, str]]:
        fake.actions.append("check the bundle offline")
        if fake.bundle_refused:
            raise BundleRefused(f"{REG}/api: its image file loaded as another image")
        fake.loaded_ids = dict(configs)
        return {r: (f"{r}:ospreyflow-v0.5.0", c) for r, c in configs.items()}

    host = fake.host()
    host.open_bundle = open_bundle
    host.check_bundle = check_bundle
    return host


def test_an_update_from_a_bundle_pulls_nothing_and_runs_the_loaded_images(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    host = _from_bundle(fake, tmp_path)
    bundle = tmp_path / "ospreyflow-v0.5.0.tar"
    assert update.apply_update(fake.directory, fake.repo, host, bundle=bundle,
                               confirm=lambda _: True) == 0  # fmt: skip
    assert fake.actions[:2] == ["open ospreyflow-v0.5.0.tar", "check the bundle offline"]
    assert not any(a.startswith("compose pull") for a in fake.actions)
    assert "compose up -d --wait --pull never" in fake.actions
    source = str(tmp_path / "opened" / "source.bundle")
    assert f"git fetch {source} refs/tags/v0.5.0:refs/tags/v0.5.0" in fake.actions
    assert not any(a.startswith("git fetch --tags origin") for a in fake.actions)
    images = fake._images()
    assert images["api"] == f"{REG}/api:ospreyflow-v0.5.0"
    assert images["report-sync"] == f"{REG}/api:ospreyflow-v0.5.0"
    assert images["arcadedb"] == "arcadedata/arcadedb:ospreyflow-v0.5.0"
    assert "Updated to v0.5.0" in capsys.readouterr().out


def test_a_bundle_that_fails_its_checks_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    fake.bundle_refused = True
    host = _from_bundle(fake, tmp_path)
    before = _files(fake)
    assert update.apply_update(fake.directory, fake.repo, host, bundle=tmp_path / "b.tar",
                               confirm=lambda _: True) == 1  # fmt: skip
    said = capsys.readouterr().err
    assert "loaded as another image" in said and "Nothing was changed" in said
    assert "backup" not in fake.actions and not _changed(fake, before)


def test_from_a_bundle_a_container_on_another_image_than_loaded_is_a_failed_update(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    host = _from_bundle(fake, tmp_path)
    original = host.check_bundle

    def check(root: Path, identity: Any) -> dict[str, tuple[str, str]]:
        images = original(root, identity)
        fake.loaded_ids[f"{REG}/ner"] = "sha256:" + "f" * 64  # running something else
        return images

    host.check_bundle = check
    assert update.apply_update(fake.directory, fake.repo, host, bundle=tmp_path / "b.tar",
                               confirm=lambda _: True) == 1  # fmt: skip
    assert "ner runs another image" in capsys.readouterr().err



# --- making a bundle: only of a release verified online (Amendment 8 point 10) ------------------


def test_a_bundle_is_made_only_of_a_release_that_verifies_online(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    fake.signed = {OLD}
    made: list[Path] = []
    host = fake.host()
    out = tmp_path / "ospreyflow-v0.5.0.tar"
    code = update.make_bundle_for(fake.repo, host, out, to=None,
                                  write=lambda *a, **k: made.append(out))  # fmt: skip
    assert code == 1 and made == [] and not out.exists()
    assert f"{REG}/api@{NEW}" in capsys.readouterr().err


def test_a_bundle_of_a_verified_release_is_written_and_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    written: list[tuple[Path, str]] = []
    out = tmp_path / "ospreyflow-v0.5.0.tar"

    def write(path: Path, release: dict[str, str], *_: Any, **__: Any) -> Path:
        written.append((path, release["tag"]))
        return path

    assert update.make_bundle_for(fake.repo, fake.host(), out, to="v0.5.0", write=write) == 0
    assert written == [(out, "v0.5.0")]
    said = capsys.readouterr().out
    assert "ospreyflow update --from" in said and out.name in said


def test_a_bundle_is_made_for_linux_amd64_unless_another_platform_is_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Build order step 29: the platform reaches the writer, linux/amd64 by default."""
    fake = _Host(tmp_path)
    asked: list[str] = []

    def write(path: Path, *_: Any, platform: str) -> Path:
        asked.append(platform)
        return path

    out = tmp_path / "ospreyflow-v0.5.0.tar"
    assert update.make_bundle_for(fake.repo, fake.host(), out, to="v0.5.0", write=write) == 0
    assert "for linux/amd64" in capsys.readouterr().out
    assert update.make_bundle_for(fake.repo, fake.host(), out, to="v0.5.0", write=write,
                                  platform="linux/arm64") == 0  # fmt: skip
    assert asked == ["linux/amd64", "linux/arm64"]


def test_a_bundle_for_a_platform_no_release_is_built_for_is_refused_before_any_lookup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    host = fake.host()
    looked: list[Any] = []
    host.find_release = lambda tag: looked.append(tag) or {}  # type: ignore[func-returns-value]
    out = tmp_path / "ospreyflow-v0.5.0.tar"
    code = update.make_bundle_for(fake.repo, host, out, to=None, platform="linux/arm/v7",
                                  write=lambda *a, **k: out)  # fmt: skip
    said = capsys.readouterr().err
    assert code == 1 and looked == []
    assert "linux/arm/v7" in said and "linux/amd64 and linux/arm64" in said


def test_platform_without_make_bundle_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        update.main(["--deployment", "/nowhere", "--platform", "linux/amd64", "--from", "x.tar"])
    assert stopped.value.code == 2
    # Its own words, not argparse's "unrecognized arguments" (whose usage line names it too).
    assert "so it goes with --make-bundle FILE" in capsys.readouterr().err


# --- an install from a release (Amendment 8 point 10, B5e) --------------------------------------


def test_an_install_s_release_is_verified_before_its_lock_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    out = tmp_path / ".install" / "release.lock"
    fake.signed = {OLD}
    assert update.verify_for_install(fake.host(), "v0.5.0", out) == 1
    assert not out.exists()
    assert f"{REG}/api@{NEW}" in capsys.readouterr().err
    fake.signed = {OLD, NEW}
    assert update.verify_for_install(fake.host(), "v0.5.0", out) == 0
    assert out.read_text() == _lock(NEW)
    assert fake.actions[-2:] == ["find v0.5.0", "verify the lock"]


def test_an_install_names_the_release_its_checkout_is_on(tmp_path: Path) -> None:
    fake = _Host(tmp_path)
    fake.release_tag = "v0.6.0"  # what GitHub answers is not the tag asked for
    out = tmp_path / "release.lock"
    assert update.verify_for_install(fake.host(), "v0.5.0", out) == 1
    assert not out.exists()


def test_a_superset_container_on_another_digest_than_the_lock_is_a_failed_update(
    tmp_path: Path,
) -> None:
    """Build order step 20a: once the release's lock names Superset (an owned image, signed by the
    release), the update's verification holds its container to the lock's digest too."""
    directory = tmp_path / "deployment"
    directory.mkdir()
    services = {"superset": {"image": f"{REG}/superset@{NEW}"}}
    (directory / "compose.yaml").write_text(yaml.safe_dump({"services": services}))
    lock = "# GENERATED\n" + yaml.safe_dump({"images": [
        {"service": "superset", "repository": f"{REG}/superset", "tag": "x", "digest": NEW,
         "source": "registry"}]}, sort_keys=False)  # fmt: skip

    def run(argv: Sequence[str]) -> tuple[int, str]:
        argv = list(argv)
        if "ps" in argv:
            return 0, json.dumps({"Service": "superset", "Name": "osprey-superset-1",
                                  "State": "running", "Health": "healthy"})  # fmt: skip
        if argv[:2] == ["docker", "inspect"]:
            return 0, "sha256:" + "c" * 64
        if argv[:3] == ["docker", "image", "inspect"]:
            return 0, json.dumps([f"{REG}/superset@{OLD}"])  # still the old image
        raise AssertionError(argv)

    host = update.Host(run=run, cosign=Cosign(run), identity=lambda _: PublicKey(Path("/k")),
                       backup=lambda: tmp_path, restore=lambda _: None,
                       files_up_to_date=lambda: {}, find_release=lambda _: {})  # fmt: skip
    with pytest.raises(update.UpdateFailed, match="superset runs another image"):
        update.verify_running(host, directory, lock)


# ---- ADR-114 Amendment 33 decision 5 (drop 2, unit 6): update on Small on a server of your own ---


def test_update_moves_a_self_contained_small(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ospreyflow update` works on a self-contained Small (unlike cloud Small, whose backup
    refuses its managed database): its backup is taken by `harness.backup` into the folder
    `server.backups` names (`components.storage.backups`), and the update goes on from there."""
    directory = tmp_path / "deploy" / "generated" / "small"
    directory.mkdir(parents=True)
    backups = tmp_path / "srv-backups"
    (directory / "osprey.yaml").write_text(yaml.safe_dump({
        "profile": "small",
        "network": {"public_origin": "https://osprey.example.internal",
                    "tls": {"certificate": "/etc/ospreyflow/tls/osprey.crt",
                            "key": "/etc/ospreyflow/tls/osprey.key"}},
        "components": {"storage": {"backups": str(backups)}},
    }))  # fmt: skip
    ran: list[list[str]] = []

    def subprocess_(argv: Sequence[str], cwd: Path | None = None) -> tuple[int, str]:
        ran.append(list(argv))
        if "harness.backup" in argv:
            out = Path(argv[argv.index("--out-root") + 1])
            (out / "20261103T000000Z-small-abc").mkdir(parents=True)
        return 0, ""

    monkeypatch.setattr(update, "_subprocess", subprocess_)
    host = update.real_host(directory, tmp_path)
    made = host.backup()
    assert made.parent == backups
    (argv,) = [a for a in ran if "harness.backup" in a]
    assert argv[argv.index("--out-root") + 1] == str(backups)


# --- the stores moved to named volumes (ADR-114 Amendment 35) -----------------------------------


class _Move:
    """`harness.store_volumes.move` as `update` calls it; the move itself is
    `tests/harness/test_store_volumes.py`'s, against its Docker stand-in."""

    def __init__(self, fake: _Host, failure: Any = None, made: Sequence[str] = ()) -> None:
        self.fake = fake
        self.failure = failure
        self.made = list(made)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, compose_file: Path, **kwargs: Any) -> Any:
        from harness import store_volumes

        self.fake.actions.append("move the stores")
        self.calls.append({"compose": compose_file, **kwargs})
        if self.failure is not None:
            raise self.failure
        return store_volumes.Moved(services=["postgres"], left=["a1b2c3"], made=self.made)


def test_an_update_moves_the_stores_after_its_backup_and_before_it_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path)
    move = _Move(fake)
    monkeypatch.setattr(update.store_volumes, "move", move)
    assert _update(fake) == 0
    order = fake.actions
    first_up = next(i for i, a in enumerate(order) if a.startswith("compose up"))
    assert order.index("backup") < order.index("compose pull") < order.index("move the stores")
    assert order.index("move the stores") < first_up
    assert move.calls[0]["compose"] == fake.directory / "compose.yaml"
    assert move.calls[0]["run"] == fake.run
    said = capsys.readouterr().out
    assert "docker volume rm a1b2c3" in said


def test_a_failed_move_rolls_the_update_back_on_its_untouched_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Amendment 35 point 4: the move never replaces a container of the deployment's, so every
    store's data is still where it was — the old version is started on it, with nothing emptied and
    nothing restored."""
    from harness import store_volumes

    fake = _Host(tmp_path)
    before = _files(fake)
    failure = store_volumes.StoresNotMoved(
        "copy postgres's /var/lib/postgresql/data: No space left on device",
        stopped=True, old=["a1b2c3"],
    )  # fmt: skip
    monkeypatch.setattr(update.store_volumes, "move", _Move(fake, failure))
    assert _update(fake) == 1
    assert not any(a.startswith("compose down") for a in fake.actions)
    assert not any(a.startswith("restore") for a in fake.actions)
    assert fake.head == "c0ffee" and not _changed(fake, before)
    assert fake.actions[-2:] == ["compose up -d --wait", "compose ps --all --format json"]
    err = capsys.readouterr().err
    assert "No space left on device" in err and "a1b2c3" in err
    assert "on its own data, which was never moved; nothing was restored" in err


def test_a_release_that_fails_after_the_move_restores_the_backup_and_removes_its_volumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The move succeeded and the release then failed to start: the stores are emptied and the
    backup restored as for any failed update, and the named volumes the move filled (which the old
    compose file does not declare, so `down -v` leaves them) are removed too."""
    fake = _Host(tmp_path, release=BROKEN)
    monkeypatch.setattr(
        update.store_volumes, "move", _Move(fake, made=["osprey-test_arcadedb-databases"])
    )
    assert _update(fake) == 1
    order = fake.actions
    assert (
        order.index("compose down -v")
        < order.index("volume rm osprey-test_arcadedb-databases")
        < order.index("restore set-1")
    )
