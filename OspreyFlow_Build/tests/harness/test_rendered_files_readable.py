"""What a container reads through a bind mount it can read, whatever the installer's umask
(ADR-114 Amendment 33, as found on the first server, 4 November 2026).

Found installing v0.4.6 as Small on an Ubuntu 24.04 server: the installer ran as the service account
under `umask 077` (a CIS-hardened server's 027 fails the same way), every rendered file was written
600 and every folder 700, and Keycloak — uid 1000, not the installer — could not read the
bind-mounted `realm.json`: "ERROR: Failed to run import: .../data/import/realm.json". The install
stopped at "build and start the deployment".

The refusal modelled is the kernel's: a process that is neither the file's owner nor in its group
reads it only through the "other" bits, and walks a folder only with "other" execute. A service runs
as the caller only when its `user:` resolves to the caller's uid (the proxy, as the key's owner);
every other service is checked. What a mistake would do, and the case that catches it:
- a mounted file or folder rendered owner-only under a strict umask —
  `test_every_bind_mounted_file_is_readable_by_the_services_that_mount_it`;
- `deployment.env` loosened along with them —
  `test_the_secrets_stay_the_owners_alone_under_any_umask`;
- the update notice's folder, which the Conduit mounts, made owner-only by `update --check` —
  `test_the_update_notice_is_readable_by_the_conduit`;
- the organisation's CA, which Keycloak mounts, not readable by it — `test_tls_check.py`'s
  `test_a_ca_file_keycloak_cannot_read_is_refused_in_words`.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from harness import release
from harness.apply import stage_deployment
from harness.render import load_config

from .tls_fixtures import write_set

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX modes")


@pytest.fixture
def strict_umask() -> Iterator[None]:
    previous = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(previous)


def _small_on_its_own_server(tmp_path: Path) -> Path:
    files = write_set(tmp_path / "tls")
    # The organisation's own file, not one the install writes: left 600 by the strict umask, the
    # install refuses it in words (`test_tls_check.py`), so it is handed over readable, as asked.
    files.ca.chmod(0o644)
    path = tmp_path / "osprey.yaml"
    path.write_text(yaml.safe_dump({
        "profile": "small",
        "network": {"public_origin": "https://osprey.example.internal",
                    "tls": {"certificate": str(files.certificate), "key": str(files.key),
                            "ca": str(files.ca)}},
        "reporting": {"sync": True, "superset": True},
    }), encoding="utf-8")  # fmt: skip
    return path


def _stage(tmp_path: Path) -> Path:
    config_path = _small_on_its_own_server(tmp_path)
    stage = tmp_path / "deploy" / "generated" / "small"
    stage_deployment(
        load_config(config_path), config_path, stage, realm="osprey", demo_analyst=False,
        images_from=None, previous_env="", environ={},
    )  # fmt: skip
    return stage


def _env(folder: Path) -> dict[str, str]:
    pairs = {}
    for line in (folder / "deployment.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            name, _, value = line.partition("=")
            pairs[name] = value
    return pairs


def _uid_of(user: str, env: dict[str, str]) -> str:
    """A compose `user:` as the uid it runs as, with `${NAME:?}` read from `deployment.env`."""
    uid = user.partition(":")[0]
    if uid.startswith("${"):
        uid = env[uid[2:].split(":")[0].rstrip("}")]
    return uid


def _unreadable_by_other(source: Path) -> list[str]:
    def wants(path: Path) -> int:
        return stat.S_IROTH | (stat.S_IXOTH if path.is_dir() else 0)

    paths = [source, *source.rglob("*")] if source.is_dir() else [source]
    return [
        f"{path} is {stat.S_IMODE(path.stat().st_mode):o}"
        for path in paths
        if stat.S_IMODE(path.stat().st_mode) & wants(path) != wants(path)
    ]


def test_every_bind_mounted_file_is_readable_by_the_services_that_mount_it(
    tmp_path: Path, strict_umask: None
) -> None:
    stage = _stage(tmp_path)
    env = _env(stage)
    services = yaml.safe_load((stage / "compose.yaml").read_text(encoding="utf-8"))["services"]
    caller = str(os.getuid())
    checked: set[str] = set()
    problems: list[str] = []
    for name, service in services.items():
        if "user" in service and _uid_of(str(service["user"]), env) == caller:
            continue
        for volume in service.get("volumes", []):
            source = str(volume).split(":")[0]
            if not source.startswith("./"):
                continue
            path = (stage / source).resolve()
            if not path.exists():
                continue  # Docker makes a missing source itself, as root, 755
            checked.add(source)
            problems += [f"{name}: {problem}" for problem in _unreadable_by_other(path)]
    assert {"./realm.json", "./keycloak-theme/osprey", "./glass.json", "./osprey.yaml",
            "./litellm.yaml"} <= checked, checked  # fmt: skip
    assert problems == [], "\n".join(problems)


def test_the_secrets_stay_the_owners_alone_under_any_umask(
    tmp_path: Path, strict_umask: None
) -> None:
    os.umask(0o002)
    stage = _stage(tmp_path)
    assert stat.S_IMODE((stage / "deployment.env").stat().st_mode) == 0o600


def test_the_update_notice_is_readable_by_the_conduit(tmp_path: Path, strict_umask: None) -> None:
    """The Conduit (its own user) mounts `./state`; `update --check` writes the notice there."""
    written = release.write_notice(tmp_path, {"latest": "v0.4.7"})
    assert _unreadable_by_other(written.parent) == []
