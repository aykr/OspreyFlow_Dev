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

    # -- the command runner ------------------------------------------------------------------
    def run(self, argv: Sequence[str]) -> tuple[int, str]:
        argv = list(argv)
        if argv[0] == "git":
            return self._git(argv[3:])
        if argv[:2] == ["docker", "compose"]:
            return self._compose(argv[argv.index("-f") + 2 :])
        if argv[:3] == ["docker", "inspect", "--format"]:
            return 0, f"image-of-{argv[-1]}"
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
            images = self._images()
            self.running = {n: i.split("@")[1] for n, i in images.items() if "@" in i}
            if any(d in self.broken for d in self.running.values()):
                return 1, "dependency failed to start: container osprey-test-api-1 is unhealthy"
            return 0, ""
        if args[0] == "down":
            self.running = {}
            return 0, ""
        if args[0] == "restart":
            return 0, ""
        if args[0] == "ps":
            rows = [{"Service": n, "Name": f"osprey-test-{n}-1", "State": "running", "Health": "",
                     "ExitCode": 0} for n in self.running]  # fmt: skip
            # The one-shot belongs to the version running: it fails only with its release.
            failed = self.oneshot_fails_with in self.running.values()
            rows.append({"Service": "keycloak-db", "Name": "osprey-test-keycloak-db-1",
                         "State": "exited", "Health": "", "ExitCode": int(failed)})  # fmt: skip
            return 0, "\n".join(json.dumps(r) for r in rows)
        raise AssertionError(args)

    # -- the other seams -----------------------------------------------------------------------
    def cosign_run(self, argv: Sequence[str]) -> tuple[int, str]:
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
        return {"proxy_changed": False, "theme_changed": False}

    def find_release(self, tag: str | None) -> dict[str, str]:
        self.actions.append(f"find {tag}")
        return {"tag": self.release_tag, "notes": "- new", "lock": _lock(self.release_digest)}

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

