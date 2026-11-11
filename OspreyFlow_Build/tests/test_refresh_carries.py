"""ADR-114 Amendment 39's staged refresh, its carries (CARRIES, the reviews of 10 November 2026).

The move into place:
- what must restart outlives a run that dies after the files moved —
  `test_a_run_that_dies_after_the_move_still_restarts_what_changed_next_time`;
- a file renamed into place keeps the old one's owner —
  `test_a_file_moved_into_place_keeps_its_owner`.

The staged pass:
- a stage left behind is never taken for a deployment —
  `test_a_stage_left_behind_is_never_a_deployment`;
- two refreshes of one deployment never share a stage — `test_a_second_refresh_at_once_is_refused`;
- a symlinked file is written through its link —
  `test_a_symlinked_file_is_written_through_its_link`, and `deployment.env` replaced whole there,
  the link kept —
  `test_a_symlinked_deployment_env_stays_a_link_and_is_replaced_whole`;
- a required value on an `export` line is held — `test_a_value_on_an_export_line_is_held`;
  **one only in the shell is not** (ADR-114 Amendment 39 decision 2; held for the orchestrator) —
  `test_a_value_only_in_the_shell_is_not_held`.

After the lane review of the carries (11 November 2026):
- the lock covers the whole refresh, not the files pass alone —
  `test_the_lock_is_held_through_the_build_and_the_restarts`;
- a lock file left read-only (by a run under sudo) stops no later run —
  `test_the_lock_file_is_opened_read_only`;
- a stage another account left is refused in words —
  `test_a_stage_this_account_cannot_remove_is_said`;
- the pending record outlives `--files-only` (for `update`), `update` clears it only once its
  restarts are done, and a stores refusal keeps what an earlier run owed —
  `test_files_only_leaves_the_restarts_owed`, `test_an_update_clears_the_record_after_its_restarts`,
  `test_a_stores_refusal_keeps_what_an_earlier_run_owed`.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

import pytest
from harness import atomic
from scripts import refresh

from tests import test_refresh_before_the_gateway as _gateway
from tests.test_refresh import Recorder, Registrar
from tests.test_refresh_before_the_gateway import _after_the_gateway_database, _checkout

#: The fixture, bound by name so pytest finds it here (an import would shadow every parameter).
deployment = _gateway.deployment


def _restarts(run: Recorder) -> list[str]:
    return [c[-1] for c in run.calls if "restart" in c]


def test_a_run_that_dies_after_the_move_still_restarts_what_changed_next_time(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gateway's routing table changed and was moved into place; the run then died (its build
    failed) before the gateway was restarted. The next `start --build` finds the files current, so
    without a record it restarts nothing and the gateway keeps the old table."""
    _after_the_gateway_database(deployment)
    monkeypatch.setattr(refresh.store_volumes, "move", lambda *a, **k: None)
    with pytest.raises(refresh.RefreshFailed):
        refresh.refresh(_checkout(deployment), run=Recorder(fail_on="build"), register=Registrar())
    again = Recorder()
    refresh.refresh(_checkout(deployment), run=again, register=Registrar())
    assert "litellm" in _restarts(again)
    once_more = Recorder()
    refresh.refresh(_checkout(deployment), run=once_more, register=Registrar())
    assert "litellm" not in _restarts(once_more)  # done, so not again
    assert not (deployment / "state" / refresh.PENDING_RESTARTS).exists()


def test_a_file_moved_into_place_keeps_its_owner(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under sudo a rename leaves the file root's: each file renamed into place first takes the
    owner of the one it replaces. The deployment's old files alone are given an owner the runner is
    not (4242); any other path (a staged file, the stage) answers root's (0), so a version that took
    the runner's or the staged file's owner fails (the orchestrator's review of c5209b1, item 4)."""
    _after_the_gateway_database(deployment)
    old_files = {p.resolve() for p in deployment.iterdir() if p.is_file()}
    given: list[tuple[int, int]] = []
    monkeypatch.setattr(atomic, "_as_root", lambda: True)
    monkeypatch.setattr(
        atomic, "_owner_of", lambda p: (4242, 4343) if Path(p).resolve() in old_files else (0, 0)
    )
    monkeypatch.setattr(atomic.os, "fchown", lambda _fd, uid, gid: given.append((uid, gid)))
    refresh.files_up_to_date(_checkout(deployment))
    assert given, "nothing was given an owner"
    assert set(given) == {(4242, 4343)}


def test_a_stage_left_behind_is_never_a_deployment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refresh killed outright leaves `.<name>.refresh-staging/compose.yaml`; it must not count as
    a second rendered deployment ("no single deployment")."""
    generated = tmp_path / "deploy" / "generated"
    for folder in ("lab", ".lab.refresh-staging"):
        (generated / folder).mkdir(parents=True)
        (generated / folder / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "osprey.yaml").write_text("deployment:\n  name: other\n", encoding="utf-8")
    monkeypatch.delenv(refresh.DEPLOYMENT_DIR_VARIABLE, raising=False)
    assert refresh._find_deployment_dir(tmp_path) == generated / "lab"


def test_a_second_refresh_at_once_is_refused(deployment: Path) -> None:
    _after_the_gateway_database(deployment)
    lock = deployment.parent / f".{deployment.name}.refresh-lock"
    with lock.open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)  # another refresh of it, under way
        with pytest.raises(
            refresh.RefreshFailed, match="another refresh or update of this deployment"
        ):
            refresh.files_up_to_date(_checkout(deployment))
    refresh.files_up_to_date(_checkout(deployment))  # released: it goes ahead


def test_a_symlinked_file_is_written_through_its_link(deployment: Path) -> None:
    """An operator keeps `compose.yaml` elsewhere and links it in: the pass reads it through the
    link (it was silently left out of the stage) and brings it up to date there, and the link stays
    a link. (`litellm.yaml`, which a service mounts, is written in place and so through a link
    too.)"""
    _after_the_gateway_database(deployment)
    elsewhere = deployment.parent / "compose-kept-elsewhere.yaml"
    (deployment / "compose.yaml").rename(elsewhere)
    (deployment / "compose.yaml").symlink_to(elsewhere)
    before = elsewhere.read_text(encoding="utf-8")
    refresh.files_up_to_date(_checkout(deployment))
    assert (deployment / "compose.yaml").is_symlink()
    assert elsewhere.read_text(encoding="utf-8") != before  # the mounts it gained, written there
    assert "map-settings" in elsewhere.read_text(encoding="utf-8")


def _without_the_salt(deployment: Path) -> Path:
    env = deployment / "deployment.env"
    lines = env.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not line.startswith("OSPREY_LITELLM_SALT_SECRET=")]
    env.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return env


def test_a_value_on_an_export_line_is_held(deployment: Path) -> None:
    """Compose reads `export NAME=v` in the env file; so must the check, or it refuses what Compose
    would run."""
    _after_the_gateway_database(deployment)
    env = _without_the_salt(deployment)
    env.write_text(env.read_text(encoding="utf-8") + "export OSPREY_LITELLM_SALT_SECRET=s\n",
                   encoding="utf-8")  # fmt: skip
    assert refresh._unset_required(deployment) == []
    refresh.files_up_to_date(_checkout(deployment))


def test_a_value_only_in_the_shell_is_not_held(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-114 Amendment 39 decision 2: only a value `deployment.env` holds counts, since a compose
    file only this shell could interpolate would lock out the next `stop` or `apply` from any other
    (CARRIES row 104 asked otherwise; held for the orchestrator, the carries' server log Q1)."""
    _after_the_gateway_database(deployment)
    _without_the_salt(deployment)
    monkeypatch.setenv("OSPREY_LITELLM_SALT_SECRET", "only-in-this-shell")
    assert refresh._unset_required(deployment) == ["OSPREY_LITELLM_SALT_SECRET"]


def test_a_symlinked_deployment_env_stays_a_link_and_is_replaced_whole(deployment: Path) -> None:
    _after_the_gateway_database(deployment)
    elsewhere = deployment.parent / "secrets-kept-elsewhere.env"
    (deployment / "deployment.env").rename(elsewhere)
    # A line the files pass writes back, so the file certainly changes (the orchestrator's review
    # of c5209b1: the witness was asserted only if it happened to).
    lines = elsewhere.read_text(encoding="utf-8").splitlines()
    elsewhere.write_text(
        "".join(x + "\n" for x in lines if not x.startswith("OSPREY_EXTRACTION_MODEL=")),
        encoding="utf-8",
    )
    (deployment / "deployment.env").symlink_to(elsewhere)
    witness = deployment.parent / "witness.env"
    os.link(elsewhere, witness)
    before = elsewhere.read_bytes()
    refresh.files_up_to_date(_checkout(deployment))
    assert (deployment / "deployment.env").is_symlink()
    assert b"OSPREY_EXTRACTION_MODEL=" in elsewhere.read_bytes()  # changed, through the link
    assert witness.read_bytes() == before  # replaced, never rewritten under the old inode


def test_deployment_env_moved_into_place_is_600(deployment: Path) -> None:
    """Every other writer of deployment.env makes it 600 (ADR-137 decision 2); refresh's move kept
    the staged copy's mode, so a 644 file stayed readable by every account (the orchestrator's
    review of c5209b1, minors)."""
    _after_the_gateway_database(deployment)
    env = deployment / "deployment.env"
    lines = env.read_text(encoding="utf-8").splitlines()
    env.write_text(
        "".join(x + "\n" for x in lines if not x.startswith("OSPREY_EXTRACTION_MODEL=")),
        encoding="utf-8",
    )
    env.chmod(0o644)
    refresh.files_up_to_date(_checkout(deployment))
    assert b"OSPREY_EXTRACTION_MODEL=" in env.read_bytes()
    assert env.stat().st_mode & 0o777 == 0o600


def test_the_lock_is_held_through_the_build_and_the_restarts(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _after_the_gateway_database(deployment)
    monkeypatch.setattr(refresh.store_volumes, "move", lambda *a, **k: None)
    lock = deployment.parent / f".{deployment.name}.refresh-lock"
    free_when: dict[str, bool] = {}

    class Probe(Recorder):
        def __call__(self, argv: list[str]) -> None:  # type: ignore[override]
            super().__call__(argv)
            with lock.open("r") as other:  # another process's own open of the lock
                try:
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    free_when[" ".join(argv[-3:])] = True
                except BlockingIOError:
                    free_when[" ".join(argv[-3:])] = False

    refresh.refresh(_checkout(deployment), run=Probe(), register=Registrar())
    assert free_when and not any(free_when.values()), free_when


def test_the_lock_file_is_opened_read_only(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _after_the_gateway_database(deployment)
    opened: list[int] = []
    real_open = os.open

    def spy(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if str(path).endswith(".refresh-lock"):
            opened.append(flags)
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(refresh.os, "open", spy)
    refresh.files_up_to_date(_checkout(deployment))
    assert opened and all(f & (os.O_WRONLY | os.O_RDWR | os.O_APPEND) == 0 for f in opened)


def test_a_new_lock_file_is_644_whatever_the_umask(deployment: Path) -> None:
    """The orchestrator's review of c5209b1, item 5: `os.open(..., 0o644)` is subject to the umask,
    so under sudo with umask 077 the lock was made root's `600`, and the operator's next run could
    not open it. Its mode is set on the open file."""
    _after_the_gateway_database(deployment)
    lock = deployment.parent / f".{deployment.name}.refresh-lock"
    lock.unlink(missing_ok=True)
    before = os.umask(0o077)
    try:
        refresh.files_up_to_date(_checkout(deployment))
    finally:
        os.umask(before)
    assert lock.stat().st_mode & 0o777 == 0o644


@pytest.mark.skipif(os.geteuid() == 0, reason="root opens any file, so none is unreadable to it")
def test_a_lock_this_account_cannot_open_is_said_in_words(deployment: Path) -> None:
    """A lock another account left that this one may not read (root's `600`): a refusal naming it
    and what to do, never a PermissionError traceback, and nothing changed."""
    _after_the_gateway_database(deployment)
    lock = deployment.parent / f".{deployment.name}.refresh-lock"
    lock.write_bytes(b"")
    lock.chmod(0o000)  # as root's 600 is to the operator
    before = {p.name: p.read_bytes() for p in deployment.iterdir() if p.is_file()}
    try:
        with pytest.raises(refresh.RefreshFailed) as refused:
            refresh.files_up_to_date(_checkout(deployment))
    finally:
        lock.chmod(0o644)
    words = str(refused.value)
    assert str(lock) in words and "sudo rm" in words and "nothing was changed" in words
    assert {p.name: p.read_bytes() for p in deployment.iterdir() if p.is_file()} == before


def test_a_stage_this_account_cannot_remove_is_said(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _after_the_gateway_database(deployment)
    stage = deployment.parent / f".{deployment.name}.refresh-staging"
    stage.mkdir()
    (stage / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    real_rmtree = refresh.shutil.rmtree

    def as_another_account(path: object, *a: object, **k: object) -> None:
        if Path(str(path)) == stage and stage.exists() and k.get("ignore_errors"):
            return  # root's files: nothing this account may remove
        real_rmtree(path, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(refresh.shutil, "rmtree", as_another_account)
    with pytest.raises(refresh.RefreshFailed, match="sudo rm -rf"):
        refresh.files_up_to_date(_checkout(deployment))


def test_files_only_leaves_the_restarts_owed(
    deployment: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`update` takes the restarts from `--files-only`'s answer and does them after its pull and
    the stores' move; an `update` killed before then must leave them owed, not cleared."""
    _after_the_gateway_database(deployment)
    assert refresh.main(["--files-only"], repo_root=_checkout(deployment)) == 0
    said = json.loads(capsys.readouterr().out)
    owed = json.loads((deployment / "state" / refresh.PENDING_RESTARTS).read_text("utf-8"))
    assert said["proxy_changed"] and owed["proxy_changed"]


def test_a_stores_refusal_keeps_what_an_earlier_run_owed(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _after_the_gateway_database(deployment)
    (deployment / "state").mkdir(exist_ok=True)
    record = deployment / "state" / refresh.PENDING_RESTARTS
    record.write_text(json.dumps({"routing_changed": True}), encoding="utf-8")

    def refused(*_a: object, **_k: object) -> None:
        full = "postgres: No space left on device"
        raise refresh.store_volumes.StoresNotMoved(full, stopped=True)

    monkeypatch.setattr(refresh.store_volumes, "move", refused)
    with pytest.raises(refresh.RefreshFailed):
        refresh.refresh(_checkout(deployment), run=Recorder(), register=Registrar())
    assert json.loads(record.read_text(encoding="utf-8")) == {"routing_changed": True}


def test_an_update_clears_the_record_after_its_restarts(tmp_path: Path) -> None:
    from tests.harness.test_update_apply import _Host, _update, _with_the_model_step

    fake = _Host(tmp_path)
    _with_the_model_step(fake)  # its files pass calls for the gateway's restart
    record = fake.directory / "state" / refresh.PENDING_RESTARTS
    record.parent.mkdir(exist_ok=True)
    seen_at_restart: list[bool] = []
    real_run = fake.run

    def run(argv: list[str]) -> tuple[int, str]:
        if "restart" in argv:
            seen_at_restart.append(record.exists())
        return real_run(argv)

    files = fake.files_up_to_date

    def files_writing_the_record() -> dict[str, bool]:
        changed = files()
        record.write_text(json.dumps(changed), encoding="utf-8")  # as `--files-only` leaves it
        return changed

    fake.files_up_to_date = files_writing_the_record  # type: ignore[method-assign]
    fake.run = run  # type: ignore[method-assign]
    assert _update(fake) == 0
    assert seen_at_restart and all(seen_at_restart)  # still owed while restarting
    assert not record.exists()  # done, so cleared
