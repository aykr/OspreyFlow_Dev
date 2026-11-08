"""The upload folder the Conduit writes is its own before the stack starts (ADR-114 Amendment 33,
"as found on the first server, 4 November 2026").

Found on the first real Linux server (Ubuntu 24.04, v0.4.8, Small): `<ingest>/uploaded` was made by
Docker at the first `up`, owned by root and `755`, and the Conduit runs as uid 10001, so
`ospreyflow demo add operation-ledger` failed with `PermissionError: [Errno 13]`, and so would any
upload. Docker Desktop on a Mac lets any container user write a shared folder, so it never showed.

The stand-in for Linux and Docker Engine refuses what they refuse (`CLAUDE.md` rule 15): a write by
uid 10001 into a folder another owns with mode `755` is refused; a folder an account may not make
in its parent is refused; and a bind source that does not exist is made by Docker, as root, `755` —
`test_the_stand_in_refuses_as_linux_does`.

What a mistake would do, and the case that catches it (rule 12):
- the folder left to Docker, so the Conduit cannot write it — at each place that runs before `up`:
  `test_an_install_gives_the_folder_to_the_conduit_before_up`,
  `test_apply_gives_the_folder_to_the_conduit_even_when_nothing_restarts`,
  `test_start_build_gives_the_folder_to_the_conduit_before_up`,
  `test_an_update_gives_the_folder_to_the_conduit_before_anything_changes` (and
  `tests/cli/test_lifecycle.py` for `start` and `switch`, which run this module's command);
- an operator's own arrangement overwritten, or a container run every start —
  `test_a_folder_the_conduit_already_owns_runs_nothing`,
  `test_a_folder_shared_through_the_conduits_group_is_left_as_it_is`;
- a folder someone else owns left as it is — `test_a_folder_another_account_owns_is_given_over`;
- a failure passed over in silence, so the stack starts and every upload fails later —
  `test_a_failed_change_of_owner_is_refused_in_words`,
  `test_a_failed_change_of_owner_stops_an_install_before_up`,
  `test_an_update_whose_folder_cannot_be_given_over_changes_nothing`;
- the folder made writable by everyone — `test_the_folder_is_never_made_writable_by_everyone`;
- the uid drifting from the Conduit's image — `test_the_conduits_user_is_the_dockerfiles`.
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml
from harness import apply, ingest_uploads, update
from harness.ingest_uploads import CONDUIT_USER, UPLOAD_CONTAINER_PATH
from scripts import refresh

from tests.harness.test_apply_changed_settings import PASSES, Deployment, FakeCompose
from tests.harness.test_update_apply import _Host, _update

INGEST = Path("/srv/ospreyflow/ingest")
UPLOADED = INGEST / "uploaded"
INSTALLER = (1001, 1001)
ROOT = (0, 0)


class LinuxHost:
    """Folders as a Linux kernel keeps them and Docker Engine makes them: the system's own are
    root's, `755`; `/srv/ospreyflow` is the installer's, as the admin guide has it made. Every path
    is the stand-in's own: nothing on disk."""

    SYSTEM = ("/", "/srv", "/var", "/var/lib", "/opt")

    def __init__(self) -> None:
        self.folders: dict[Path, tuple[int, int, int]] = {
            **{Path(p): (*ROOT, 0o755) for p in self.SYSTEM},
            Path("/srv/ospreyflow"): (*INSTALLER, 0o755),
        }
        self.docker_refuses: str | None = None
        self.chowns: list[list[str]] = []
        self.built_chowns: list[list[str]] = []
        #: What the Conduit met writing its first file at `up`: None until then.
        self.conduit_write: str | None = None

    def add(self, path: Path, owner: tuple[int, int], mode: int = 0o755) -> None:
        self.folders[path] = (*owner, mode)

    def _owner(self, path: Path) -> tuple[int, int, int]:
        return self.folders[path]

    def exists(self, path: Path) -> bool:
        return path in self.folders

    def may_write(self, path: Path, uid: int, gid: int) -> bool:
        if uid == 0:
            return True
        owner, group, mode = self._owner(path)
        if owner == uid:
            bits = stat.S_IWUSR | stat.S_IXUSR
        elif group == gid:
            bits = stat.S_IWGRP | stat.S_IXGRP
        else:
            bits = stat.S_IWOTH | stat.S_IXOTH
        return mode & bits == bits

    def stat(self, path: Path) -> os.stat_result:
        if not self.exists(path):
            raise FileNotFoundError(2, "No such file or directory", str(path))
        uid, gid, mode = self._owner(path)
        return os.stat_result((stat.S_IFDIR | mode, 0, 0, 2, uid, gid, 4096, 0, 0, 0))

    def mkdir(self, path: Path, as_: tuple[int, int] = INSTALLER) -> None:
        """`mkdir -p` as an account."""
        for folder in [*reversed(path.parents), path]:
            if self.exists(folder):
                continue
            if not self.may_write(folder.parent, *as_):
                raise PermissionError(13, "Permission denied", str(folder))
            self.folders[folder] = (*as_, 0o755)

    def write_as_conduit(self, path: Path) -> None:
        if not self.may_write(path, *CONDUIT_USER):
            raise PermissionError(13, "Permission denied", str(path / "ledger"))

    def docker_mounts(self, source: Path) -> None:
        """A bind source that is not there is made by Docker, as root, `755`."""
        self.mkdir(source, as_=ROOT)

    def docker(self, argv: Sequence[str]) -> tuple[int, str]:
        """The one-off container (`compose run … chown`) and `up`; anything else succeeds."""
        argv = list(argv)
        if "run" in argv and "chown" in argv and argv[-1] == ingest_uploads.BUILT_CONTAINER_PATH:
            # ADR-147: the tiles folder's `built/` door, given over the same way (its own case
            # below); recorded apart so each upload case still counts its own.
            self.built_chowns.append(argv)
            return 0, ""
        if "run" in argv and "chown" in argv:
            self.chowns.append(argv)
            if self.docker_refuses is not None:
                return 1, self.docker_refuses
            assert argv[-1] == UPLOAD_CONTAINER_PATH
            self.docker_mounts(UPLOADED)
            uid, gid = (int(n) for n in argv[-2].split(":"))
            *_, mode = self._owner(UPLOADED)
            self.folders[UPLOADED] = (uid, gid, mode)
            return 0, ""
        if "up" in argv:
            self.docker_mounts(UPLOADED)
            try:
                self.write_as_conduit(UPLOADED)
                self.conduit_write = "written"
            except PermissionError as refused:
                self.conduit_write = str(refused)
        return 0, ""


@pytest.fixture
def linux(monkeypatch: pytest.MonkeyPatch) -> LinuxHost:
    host = LinuxHost()
    monkeypatch.setattr(ingest_uploads, "DOCKER_ENFORCES_OWNERSHIP", True)
    monkeypatch.setattr(ingest_uploads, "_stat", host.stat)
    monkeypatch.setattr(ingest_uploads, "_make", host.mkdir)
    return host


def _compose_file(folder: Path, *, upload_source: str = str(UPLOADED)) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "deployment.env").write_text("X=1\n", encoding="utf-8")
    compose = folder / "compose.yaml"
    api = {
        "image": "ghcr.io/acme/api@sha256:" + "1" * 64,
        "volumes": [
            f"{INGEST}:/var/lib/osprey/ingest:ro",
            f"{upload_source}:{UPLOAD_CONTAINER_PATH}",
        ],
    }
    compose.write_text(yaml.safe_dump({"services": {"api": api}}), encoding="utf-8")
    return compose


def _no_run(argv: Sequence[str]) -> tuple[int, str]:
    raise AssertionError(f"nothing should have been run: {argv}")


# --- the stand-in ---------------------------------------------------------------------------------


def test_the_stand_in_refuses_as_linux_does(linux: LinuxHost) -> None:
    linux.add(UPLOADED, ROOT, 0o755)
    with pytest.raises(PermissionError):
        linux.write_as_conduit(UPLOADED)
    linux.add(UPLOADED, CONDUIT_USER, 0o755)
    linux.write_as_conduit(UPLOADED)
    linux.add(UPLOADED, INSTALLER, 0o755)
    with pytest.raises(PermissionError):
        linux.write_as_conduit(UPLOADED)
    with pytest.raises(PermissionError):
        linux.mkdir(Path("/var/lib/osprey/ingest"))  # root's /var/lib, not the installer's
    linux.docker_mounts(Path("/opt/elsewhere/uploaded"))
    assert linux.stat(Path("/opt/elsewhere/uploaded")).st_uid == 0


# --- the step -------------------------------------------------------------------------------------


def test_a_missing_folder_is_made_and_given_to_the_conduit(
    linux: LinuxHost, tmp_path: Path
) -> None:
    compose = _compose_file(tmp_path)
    linux.add(INGEST, INSTALLER)
    said = ingest_uploads.prepare(compose, run=linux.docker)
    assert "given to the Conduit" in said
    (chown,) = linux.chowns
    assert chown[: chown.index("run")] == [
        "docker", "compose", "--env-file", str(tmp_path / "deployment.env"),
        "-f", str(compose),
    ]  # fmt: skip
    assert chown[chown.index("run") :] == [
        "run", "--rm", "--no-deps", "--user", "0", "--entrypoint", "chown", "api",
        "10001:10001", "/var/lib/osprey/ingest/uploaded",
    ]  # fmt: skip
    linux.write_as_conduit(UPLOADED)


def test_a_root_owned_folder_docker_made_is_given_over(linux: LinuxHost, tmp_path: Path) -> None:
    """The first server's own state: every v0.4.8 deployment on Linux has this."""
    linux.add(INGEST, INSTALLER)
    linux.add(UPLOADED, ROOT, 0o755)
    ingest_uploads.prepare(_compose_file(tmp_path), run=linux.docker)
    linux.write_as_conduit(UPLOADED)


def test_a_folder_the_conduit_already_owns_runs_nothing(linux: LinuxHost, tmp_path: Path) -> None:
    linux.add(UPLOADED, CONDUIT_USER, 0o750)
    said = ingest_uploads.prepare(_compose_file(tmp_path), run=_no_run)
    assert "can already write" in said


def test_a_folder_shared_through_the_conduits_group_is_left_as_it_is(
    linux: LinuxHost, tmp_path: Path
) -> None:
    """An operator's own arrangement: their folder, the Conduit's group, `2775`."""
    linux.add(UPLOADED, (1001, CONDUIT_USER[1]), 0o2775)
    ingest_uploads.prepare(_compose_file(tmp_path), run=_no_run)
    assert linux.folders[UPLOADED] == (1001, CONDUIT_USER[1], 0o2775)


def test_a_folder_another_account_owns_is_given_over(linux: LinuxHost, tmp_path: Path) -> None:
    linux.add(UPLOADED, INSTALLER, 0o755)
    ingest_uploads.prepare(_compose_file(tmp_path), run=linux.docker)
    assert len(linux.chowns) == 1
    linux.write_as_conduit(UPLOADED)


def test_the_folder_is_never_made_writable_by_everyone(linux: LinuxHost, tmp_path: Path) -> None:
    linux.add(UPLOADED, ROOT, 0o755)
    ingest_uploads.prepare(_compose_file(tmp_path), run=linux.docker)
    *_, mode = linux.folders[UPLOADED]
    assert mode & stat.S_IWOTH == 0
    assert all("chmod" not in argv for argv in linux.chowns)


def test_a_folder_whose_parent_the_installer_cannot_write_is_made_by_docker_and_given_over(
    linux: LinuxHost, tmp_path: Path
) -> None:
    """`/srv/ospreyflow/ingest` not made yet, in a parent the installer may not write: the one-off
    container's mount makes it, as `up` would have, and hands it over."""
    del linux.folders[Path("/srv/ospreyflow")]
    ingest_uploads.prepare(_compose_file(tmp_path), run=linux.docker)
    linux.write_as_conduit(UPLOADED)


def test_a_failed_change_of_owner_is_refused_in_words(linux: LinuxHost, tmp_path: Path) -> None:
    linux.add(UPLOADED, ROOT, 0o755)
    linux.docker_refuses = "Error response from daemon: pull access denied for ghcr.io/acme/api"
    with pytest.raises(ingest_uploads.UploadFolderRefused) as refused:
        ingest_uploads.prepare(_compose_file(tmp_path), run=linux.docker)
    said = str(refused.value)
    assert str(UPLOADED) in said
    assert "pull access denied" in said
    assert "Nothing was started" in said
    assert f"sudo chown 10001:10001 {UPLOADED}" in said


def test_docker_desktop_is_left_as_it_was(
    linux: LinuxHost, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Docker Desktop's file sharing lets the container's user write: nothing is made or run."""
    monkeypatch.setattr(ingest_uploads, "DOCKER_ENFORCES_OWNERSHIP", False)
    ingest_uploads.prepare(_compose_file(tmp_path), run=_no_run)
    assert UPLOADED not in linux.folders


def test_a_relative_bind_source_is_read_from_the_compose_files_folder(tmp_path: Path) -> None:
    compose = _compose_file(
        tmp_path / "deploy" / "generated" / "local-lite",
        upload_source="../../../../OspreyFlow_Data/ingest/uploaded",
    )
    assert ingest_uploads.upload_folder(compose) == (
        tmp_path.parent / "OspreyFlow_Data" / "ingest" / "uploaded"
    )


def test_a_deployment_whose_conduit_mounts_no_upload_folder_runs_nothing(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text(yaml.safe_dump({"services": {"api": {"image": "x"}}}), encoding="utf-8")
    assert ingest_uploads.prepare(compose, run=_no_run) == "the Conduit mounts no upload folder"


def test_the_command_says_why_and_exits_nonzero(
    linux: LinuxHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What `ospreyflow start` and `switch` run before `up`."""
    linux.add(UPLOADED, ROOT, 0o755)
    linux.docker_refuses = "permission denied while trying to connect to the Docker daemon"
    assert ingest_uploads.main([str(_compose_file(tmp_path))], run=linux.docker) == 1
    assert "cannot write /srv/ospreyflow/ingest/uploaded" in capsys.readouterr().err
    linux.docker_refuses = None
    assert ingest_uploads.main([str(_compose_file(tmp_path))], run=linux.docker) == 0
    linux.write_as_conduit(UPLOADED)


def test_the_conduits_user_is_the_dockerfiles() -> None:
    dockerfile = Path(ingest_uploads.__file__).parents[1] / "services" / "api" / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")
    (uid,) = re.findall(r"useradd\b[^\n]*--uid (\d+) osprey", text)
    assert int(uid) == CONDUIT_USER[0]
    # `useradd` gives the user a group of its own name; with no `--gid`, Debian numbers it as the
    # uid (10001 on the first server, by `docker exec … id`).
    assert "--gid" not in text and "groupadd" not in text
    assert CONDUIT_USER[1] == CONDUIT_USER[0]
    assert re.search(r"^USER osprey$", text, re.MULTILINE)


# --- at each place that runs before `up` ----------------------------------------------------------


class LinuxCompose(FakeCompose):
    """`apply._run` on the stand-in: the one-off container and `up` as Docker Engine on Linux does
    them. `up` stops the install there, after the Conduit's first write, so nothing more is run."""

    def __init__(self, host: LinuxHost) -> None:
        super().__init__()
        self.host = host

    def __call__(self, args: list[str], *, stage: str, **kwargs: object) -> str:
        said = super().__call__(args, stage=stage, **kwargs)
        code, out = self.host.docker(args)
        if code != 0:
            raise apply.ApplyFailed(stage, out)
        if "up" in args and stage == "up" and "--no-deps" not in args:
            raise apply.ApplyFailed(stage, "the test stops here")
        return said or out


@pytest.fixture
def on_linux(
    linux: LinuxHost, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[LinuxCompose, Deployment]:
    fake = LinuxCompose(linux)
    monkeypatch.setattr(apply, "_run", fake)
    monkeypatch.setattr(apply, "answer_localhost_with_loopback", lambda: None)
    monkeypatch.setattr(apply, "answer_the_deployment_here", lambda _config: None)
    monkeypatch.setattr(apply, "ALL_CHECKS", [PASSES])
    deployment = Deployment(tmp_path, fake)
    deployment.write_config(components={"storage": {"ingest": str(INGEST)}})
    return fake, deployment


def _install(deployment: Deployment) -> int:
    return apply.main(
        ["--config", str(deployment.config), "--out-root", str(deployment.out_root)],
        environ={},
    )


def test_an_install_gives_the_folder_to_the_conduit_before_up(
    on_linux: tuple[LinuxCompose, Deployment], linux: LinuxHost
) -> None:
    """The defect at its own call site: `ospreyflow install` (`harness.apply`), up to `up`."""
    compose, deployment = on_linux
    linux.add(INGEST, INSTALLER)
    assert _install(deployment) == 1  # stopped by the stand-in at `up`
    assert linux.conduit_write == "written"
    verbs = [c[c.index("-f") + 2] for c in compose.calls]
    assert verbs.index("run") < verbs.index("up")


def test_a_failed_change_of_owner_stops_an_install_before_up(
    on_linux: tuple[LinuxCompose, Deployment],
    linux: LinuxHost,
    capsys: pytest.CaptureFixture[str],
) -> None:
    compose, deployment = on_linux
    linux.add(UPLOADED, ROOT, 0o755)
    linux.docker_refuses = "no space left on device"
    assert _install(deployment) == 1
    assert compose.ups() == []
    assert linux.conduit_write is None
    said = capsys.readouterr()
    assert "cannot write /srv/ospreyflow/ingest/uploaded" in said.out + said.err


def test_apply_gives_the_folder_to_the_conduit_even_when_nothing_restarts(
    on_linux: tuple[LinuxCompose, Deployment], linux: LinuxHost
) -> None:
    """`ospreyflow apply` on a deployment installed before the fix: nothing in its files changed,
    so no service restarts, and the folder Docker made is still given to the Conduit."""
    _compose, deployment = on_linux
    linux.add(INGEST, INSTALLER)
    _install(deployment)
    linux.add(UPLOADED, ROOT, 0o755)  # as v0.4.8 left it
    linux.chowns.clear()
    assert deployment.reapply() == 0
    assert len(linux.chowns) == 1
    linux.write_as_conduit(UPLOADED)


def test_start_build_gives_the_folder_to_the_conduit_before_up(
    linux: LinuxHost, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ospreyflow start --build` (`scripts.refresh`): built, then the folder, then `up`."""
    _compose_file(tmp_path / "deploy" / "generated" / "local-lite")
    linux.add(UPLOADED, ROOT, 0o755)
    nothing_changed = {"theme_changed": False, "proxy_changed": False, "routing_changed": False}
    monkeypatch.setattr(refresh, "files_up_to_date", lambda _repo: nothing_changed)
    monkeypatch.setattr(refresh, "_identity_origin", lambda _env: "https://id.example")
    ran: list[str] = []

    def run(argv: Sequence[str]) -> None:
        ran.append("chown" if "chown" in argv else next(a for a in argv if a in ("build", "up")))
        code, said = linux.docker(argv)
        if code != 0:
            raise refresh.RefreshFailed(said)

    refresh.refresh(tmp_path, run=run, register=lambda _argv: 0)
    assert ran == ["build", "chown", "up"]
    assert linux.conduit_write == "written"


class LinuxUpdateHost(_Host):
    """`test_update_apply.py`'s host, its Conduit mounting the upload folder, on the stand-in."""

    def __init__(self, tmp: Path, linux: LinuxHost) -> None:
        super().__init__(tmp)
        self.linux = linux
        compose = self.directory / "compose.yaml"
        banner, document = update._split_banner(compose.read_text(encoding="utf-8"))
        document["services"]["api"]["volumes"] = [f"{UPLOADED}:{UPLOAD_CONTAINER_PATH}"]
        compose.write_text(banner + yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    def run(self, argv: Sequence[str]) -> tuple[int, str]:
        if "chown" in argv:
            self.actions.append("chown")
            return self.linux.docker(argv)
        if "up" in argv:
            self.linux.docker(argv)
        return super().run(argv)


def test_an_update_gives_the_folder_to_the_conduit_before_anything_changes(
    linux: LinuxHost, tmp_path: Path
) -> None:
    """`ospreyflow update` from a release that has the fix: with the running version's own Conduit
    image, before the backup and the checkout."""
    linux.add(UPLOADED, ROOT, 0o755)
    fake = LinuxUpdateHost(tmp_path, linux)
    assert _update(fake) == 0
    assert fake.actions.index("chown") < fake.actions.index("backup")
    assert linux.conduit_write == "written"


def test_an_update_whose_folder_cannot_be_given_over_changes_nothing(
    linux: LinuxHost, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    linux.add(UPLOADED, ROOT, 0o755)
    linux.docker_refuses = "Cannot connect to the Docker daemon"
    fake = LinuxUpdateHost(tmp_path, linux)
    assert _update(fake) == 1
    assert "backup" not in fake.actions
    assert not any(a.startswith("git checkout") for a in fake.actions)
    said = capsys.readouterr().err
    assert "cannot write /srv/ospreyflow/ingest/uploaded" in said
    assert "Nothing was changed." in said


# --- ADR-147 decision 3: the tiles folder's `built/` door is the same case ---


def test_the_tiles_folder_s_built_door_is_given_to_the_conduit_before_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A basemap built in the Conduit is written to `<tiles>/built`, bind-mounted writable over the
    read-only tiles folder (`harness/render.py`). Made by Docker at the first `up`, it is root's and
    the build is refused, as the upload folder's was; so `prepare` gives it over too."""
    tiles = tmp_path / "tiles"
    compose = tmp_path / "deploy" / "compose.yaml"
    compose.parent.mkdir()
    (compose.parent / "deployment.env").write_text("X=1\n", encoding="utf-8")
    api = {"volumes": [
        f"{tiles}:/data/tiles:ro", f"{tiles}/built:/data/tiles/built",
    ]}  # fmt: skip
    compose.write_text(yaml.safe_dump({"services": {"api": api}}), encoding="utf-8")
    root_owned = os.stat_result((stat.S_IFDIR | 0o755, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    monkeypatch.setattr(ingest_uploads, "DOCKER_ENFORCES_OWNERSHIP", True)
    monkeypatch.setattr(ingest_uploads, "_stat", lambda _p: root_owned)
    made: list[Path] = []
    monkeypatch.setattr(ingest_uploads, "_make", made.append)
    ran: list[list[str]] = []

    def run(argv: Sequence[str]) -> tuple[int, str]:
        ran.append(list(argv))
        return 0, ""

    said = ingest_uploads.prepare(compose, run=run)

    assert made == [tiles / "built"]
    assert [a[a.index("chown") + 2 :] for a in ran] == [["10001:10001", "/data/tiles/built"]]
    assert "given to the Conduit" in said
