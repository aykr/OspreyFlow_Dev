"""`ospreyflow update` (ADR-114 decision 13, Amendment 6 point 1, Amendment 8).

`update [--to vX.Y.Z] [--yes]` moves a release install to a newer release: it refuses a deployment
that builds from its checkout, finds the release and its `versions.lock`, checks every owned image's
signature, refuses a local change the release would overwrite, backs up every store, keeps a
rollback point, checks out the release's tag, brings the deployment's files up to date from it,
pins every image by the lock's digest, pulls, starts, and verifies. A failure after the backup rolls
back: the old commit and files put back, the stores emptied and the backup restored, the old
version verified — or, if that fails too, exactly where things stand is said.

`--check` asks the user repository's GitHub releases from the machine this runs on and writes the
notice the Conduit reads (`state/update.json`); the deployment itself never calls out. The version
checked is the one the deployment was rendered with (`OSPREY_RELEASE_VERSION` in its
`deployment.env`), not whatever the checkout has moved to since.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from harness.release import (
    GITHUB_API,
    ReleaseRefused,
    check_for_update,
    checkout_version,
    find_release,
    github_repository,
    is_version,
    newer,
    origin_url,
    read_notice,
    write_notice,
)
from harness.signatures import (
    OWNED_SERVICES,
    Cosign,
    Identity,
    Keyless,
    SignatureRefused,
    verify_release,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def deployed_version(directory: Path, repo_root: Path) -> str:
    """The version the deployment was rendered with; the checkout's if it does not say (rendered
    before B5)."""
    try:
        lines = (directory / "deployment.env").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        if line.startswith("OSPREY_RELEASE_VERSION="):
            value = line.split("=", 1)[1].strip()
            if value:
                return value
    return checkout_version(repo_root)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(directory: Path, repo_root: Path, *, github_api: str = GITHUB_API) -> int:
    current = deployed_version(directory, repo_root)
    try:
        repository = github_repository(origin_url(repo_root))
    except ReleaseRefused as refused:
        write_notice(directory, {
            "current": current, "checked_at": _now(), "latest": None, "update_available": False,
            "notes": None, "url": None, "problem": str(refused),
        })  # fmt: skip
        print(f"ospreyflow: {refused}", file=sys.stderr)
        return 1
    notice = check_for_update(current, repository, now=_now(), api_base=github_api)
    write_notice(directory, notice)
    if notice["problem"]:
        print(f"ospreyflow: the update check did not answer: {notice['problem']}", file=sys.stderr)
        return 1
    latest = notice["latest"]
    if notice["update_available"]:
        print(f"OspreyFlow {latest} is available (this deployment is {current}).")
        if notice["notes"]:
            print()
            print(notice["notes"])
            print()
        print("Update with: ospreyflow update")
    elif current.startswith("dev-"):
        print(
            f"This deployment builds from its checkout ({current}); it moves with git pull and "
            f"ospreyflow start --build. The newest release is {latest}."
        )
    else:
        print(f"Up to date: {current} is the newest release.")
    return 0


# --- update -------------------------------------------------------------------------------------

Run = Callable[[Sequence[str]], tuple[int, str]]


class UpdateFailed(Exception):
    """A step of an update (or of its rollback) that did not finish, and why."""

    def __init__(self, step: str, why: str) -> None:
        super().__init__(f"{step}: {why}")
        self.step = step
        self.why = why


@dataclass
class Host:
    """What an update does to the world. `real_host` is the machine's; a test gives its own."""

    run: Run
    cosign: Cosign
    identity: Callable[[str], Identity]
    backup: Callable[[], Path]
    restore: Callable[[Path], None]
    files_up_to_date: Callable[[], dict[str, bool]]
    find_release: Callable[[str | None], dict[str, str]]


def _compose_argv(directory: Path) -> list[str]:
    return [
        "docker", "compose", "--env-file", str(directory / "deployment.env"),
        "-f", str(directory / "compose.yaml"),
    ]  # fmt: skip


def _repository(ref: str) -> str:
    """`ghcr.io/acme/api:tag` and `ghcr.io/acme/api@sha256:…` are both `ghcr.io/acme/api`."""
    name = ref.split("@", 1)[0]
    head, _, last = name.rpartition("/")
    return f"{head}/{last.split(':', 1)[0]}" if head else last.split(":", 1)[0]


def _lock_digests(lock_text: str) -> dict[str, str]:
    entries = (yaml.safe_load(lock_text) or {}).get("images") or []
    return {
        str(e["repository"]): str(e["digest"])
        for e in entries
        if isinstance(e, dict) and str(e.get("digest", "")).startswith("sha256:")
    }


def _split_banner(text: str) -> tuple[str, dict[str, Any]]:
    at = text.find("\nname:") + 1
    return text[:at], yaml.safe_load(text) or {}


def pin_images(directory: Path, lock_text: str) -> None:
    """Each service whose image the lock names runs it by the lock's digest; the lock is written."""
    path = directory / "compose.yaml"
    banner, document = _split_banner(path.read_text(encoding="utf-8"))
    digests = _lock_digests(lock_text)
    for service in (document.get("services") or {}).values():
        image = service.get("image") if isinstance(service, dict) else None
        if isinstance(image, str) and _repository(image) in digests:
            service["image"] = f"{_repository(image)}@{digests[_repository(image)]}"
    path.write_text(
        banner + yaml.safe_dump(document, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    (directory / "versions.lock").write_text(lock_text, encoding="utf-8")


def _builds_from_checkout(directory: Path) -> bool:
    document = yaml.safe_load((directory / "compose.yaml").read_text(encoding="utf-8")) or {}
    return any(
        isinstance(s, dict) and "build" in s for s in (document.get("services") or {}).values()
    )


def verify_lock(cosign: Cosign, lock: str, signature: str, identity: Identity) -> None:
    """The release's lock against its own signature (Amendment 8 point 11), before any image."""
    with tempfile.TemporaryDirectory(prefix="ospreyflow-lock-") as folder:
        lock_path = Path(folder) / "versions.lock"
        signature_path = Path(folder) / "versions.lock.sigstore.json"
        lock_path.write_text(lock, encoding="utf-8")
        signature_path.write_text(signature, encoding="utf-8")
        cosign.verify_blob(lock_path, signature_path, identity)


def _ok(host: Host, argv: Sequence[str], step: str) -> str:
    code, said = host.run(argv)
    if code != 0:
        last = [line for line in said.splitlines() if line.strip()]
        raise UpdateFailed(step, last[-1] if last else f"exit {code}")
    return said


def verify_running(host: Host, directory: Path, lock_text: str | None) -> None:
    """Every service running and healthy (a one-shot step finished cleanly counts), and each owned
    container running the image the lock names."""
    said = _ok(host, [*_compose_argv(directory), "ps", "--all", "--format", "json"], "verify")
    rows = [json.loads(line) for line in said.splitlines() if line.strip().startswith("{")]
    if not rows:
        raise UpdateFailed("verify", "nothing is running")
    for row in rows:
        state, health = str(row.get("State")), str(row.get("Health") or "")
        finished = state == "exited" and int(row.get("ExitCode") or 0) == 0
        if not finished and (state != "running" or health not in ("", "healthy")):
            raise UpdateFailed("verify", f"{row.get('Service')} is {state} {health}".strip())
    if lock_text is None:
        return
    digests = _lock_digests(lock_text)
    document = yaml.safe_load((directory / "compose.yaml").read_text(encoding="utf-8")) or {}
    services = document.get("services") or {}
    for row in rows:
        name = str(row.get("Service"))
        image = (services.get(name) or {}).get("image", "")
        repository = _repository(str(image))
        if repository not in digests or not any(
            repository.endswith(f"/{s}") for s in OWNED_SERVICES
        ):
            continue
        image_id = _ok(
            host, ["docker", "inspect", "--format", "{{.Image}}", str(row["Name"])], "verify"
        )
        repo_digests = _ok(
            host,
            ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image_id.strip()],
            "verify",
        )  # fmt: skip
        wanted = f"{repository}@{digests[repository]}"
        if wanted not in json.loads(repo_digests or "[]"):
            raise UpdateFailed("verify", f"{name} runs another image than the release's {wanted}")


#: What `update` may write in the deployment's folder; all kept at the rollback point.
_KEPT_DIRECTORIES = ("keycloak-theme",)


def _keep_rollback_point(directory: Path, version: str, commit: str) -> Path:
    point = directory / "rollback" / f"{version}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    point.mkdir(parents=True)
    for item in directory.iterdir():
        if item.is_file():
            shutil.copy2(item, point / item.name)
        elif item.name in _KEPT_DIRECTORIES:
            shutil.copytree(item, point / item.name)
    (point / ".commit").write_text(commit, encoding="utf-8")
    return point


def _put_back(directory: Path, point: Path) -> None:
    for item in directory.iterdir():
        if item.is_file() and not (point / item.name).exists():
            item.unlink()
    for item in point.iterdir():
        if item.name == ".commit":
            continue
        if item.is_dir():
            shutil.rmtree(directory / item.name, ignore_errors=True)
            shutil.copytree(item, directory / item.name)
        else:
            shutil.copy2(item, directory / item.name)


def _conflicts(host: Host, repo: Path, tag: str) -> list[str]:
    said = _ok(host, ["git", "-C", str(repo), "status", "--porcelain"], "look at the checkout")
    changed = [line[3:].strip() for line in said.splitlines() if line.strip()]
    return [
        path for path in changed
        if host.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD", tag, "--", path])[0] != 0
    ]  # fmt: skip


def apply_update(
    directory: Path,
    repo: Path,
    host: Host,
    *,
    to: str | None = None,
    confirm: Callable[[str], bool],
) -> int:
    """0 updated (or already current), 1 refused or failed and rolled back, 2 rollback failed."""
    if _builds_from_checkout(directory):
        print(
            "ospreyflow: this deployment builds from its checkout; it moves with git pull and "
            "ospreyflow start --build, not with a release.",
            file=sys.stderr,
        )
        return 1
    current = deployed_version(directory, repo)
    if not is_version(current):
        print(f"ospreyflow: this deployment ({current}) is not a release.", file=sys.stderr)
        return 1
    try:
        release = host.find_release(to)
    except ReleaseRefused as refused:
        print(f"ospreyflow: {refused}", file=sys.stderr)
        return 1
    tag, lock = release["tag"], release["lock"]
    if tag == current:
        print(f"Already at {current}; nothing to do.")
        return 0
    if not newer(tag, current):
        print(
            f"ospreyflow: {tag} is older than {current}; update moves forward only.",
            file=sys.stderr,
        )
        return 1
    try:
        verify_lock(host.cosign, lock, release.get("lock_signature", ""), host.identity(tag))
        verify_release(lock, host.identity(tag), host.cosign)
        _ok(host, ["git", "-C", str(repo), "fetch", "--tags", "origin"], "fetch the release's tag")
        conflicts = _conflicts(host, repo, tag)
        if conflicts:
            raise UpdateFailed(
                "check the checkout",
                "changes of this machine's own to files the release also changes: "
                + ", ".join(conflicts)
                + ". Commit or undo them first.",
            )
    except (SignatureRefused, UpdateFailed) as refused:
        print(f"ospreyflow: {refused}. Nothing was changed.", file=sys.stderr)
        return 1
    if not confirm(
        f"Update from {current} to {tag}? Every store is backed up first, and a failure puts "
        f"{current} and its data back. The deployment is unavailable while it runs."
    ):
        print("Nothing was changed.")
        return 1
    commit = _ok(host, ["git", "-C", str(repo), "rev-parse", "HEAD"], "read the checkout").strip()
    try:
        backup = host.backup()
    except UpdateFailed as failed:
        print(
            f"ospreyflow: the backup did not finish ({failed}). Nothing was changed.",
            file=sys.stderr,
        )
        return 1
    point = _keep_rollback_point(directory, current, commit)
    compose = _compose_argv(directory)
    try:
        _ok(host, ["git", "-C", str(repo), "checkout", "--quiet", tag], "check out the release")
        changed = host.files_up_to_date()
        pin_images(directory, lock)
        _ok(host, [*compose, "pull"], "pull the release's images")
        _ok(host, [*compose, "up", "-d", "--wait"], "start the release")
        for service, flag in (("litellm", "proxy_changed"), ("keycloak", "theme_changed")):
            if changed.get(flag):
                _ok(host, [*compose, "restart", service], "start the release")
                _ok(host, [*compose, "up", "-d", "--wait"], "start the release")
        verify_running(host, directory, lock)
    except UpdateFailed as failed:
        print(
            f"ospreyflow: the update to {tag} failed at '{failed.step}': {failed.why}",
            file=sys.stderr,
        )
        return _roll_back(host, directory, repo, point, commit, backup, current)
    notice = read_notice(directory / "state")
    if notice is not None:
        latest = notice.get("latest")
        notice.update(current=tag, update_available=bool(latest) and newer(str(latest), tag))
        write_notice(directory, notice)
    print(f"Updated to {tag}. The backup taken before it is {backup}.")
    return 0


def _roll_back(
    host: Host, directory: Path, repo: Path, point: Path, commit: str, backup: Path, version: str
) -> int:
    compose = _compose_argv(directory)
    try:
        _ok(
            host, ["git", "-C", str(repo), "checkout", "--quiet", commit], "put the old commit back"
        )
        _put_back(directory, point)
        if not backup.exists():
            raise UpdateFailed("restore the backup", f"the backup {backup} is not there")
        # A backup restores into an empty deployment (harness.restore): the stores are emptied only
        # now, with the old images back and the backup on disk.
        _ok(host, [*compose, "down", "-v"], "empty the stores")
        _ok(host, [*compose, "up", "-d", "--wait"], "start the old version")
        host.restore(backup)
        verify_running(host, directory, None)
    except UpdateFailed as failed:
        print(
            f"ospreyflow: The rollback did not finish, at '{failed.step}': {failed.why}. The "
            f"deployment's files are those of {version} (kept in {point}); its data is in the "
            f"backup {backup}. Restore it by hand: ospreyflow restore {backup} --yes",
            file=sys.stderr,
        )
        return 2
    print(
        f"ospreyflow: rolled back to {version}, with its data restored from {backup}.",
        file=sys.stderr,
    )
    return 1


def _subprocess(argv: Sequence[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        done = subprocess.run(
            list(argv), capture_output=True, text=True, check=False, cwd=cwd, timeout=7200
        )
    except (OSError, subprocess.SubprocessError) as failed:
        return 1, str(failed)
    return done.returncode, (done.stdout + done.stderr).strip()


def real_host(directory: Path, repo: Path, *, github_api: str = GITHUB_API) -> Host:
    python = [sys.executable]

    def run(argv: Sequence[str]) -> tuple[int, str]:
        return _subprocess(argv, cwd=repo)

    def backup() -> Path:
        root = repo / "backups"
        before = set(root.iterdir()) if root.is_dir() else set()
        _ok_real(run, [*python, "-m", "harness.backup", "--profile", directory.name,
                       "--out-root", str(root)], "back up every store")  # fmt: skip
        made = sorted(set(root.iterdir()) - before) if root.is_dir() else []
        if not made:
            raise UpdateFailed("back up every store", "no backup set was written")
        return made[-1]

    def restore(path: Path) -> None:
        _ok_real(run, [*python, "-m", "harness.restore", str(path), "--profile", directory.name,
                       "--yes"], "restore the backup")  # fmt: skip

    def files() -> dict[str, bool]:
        said = _ok_real(
            run, [*python, "-m", "scripts.refresh", "--files-only"], "bring the files up to date"
        )
        changed = json.loads(said.splitlines()[-1])
        return {str(k): bool(v) for k, v in changed.items()}

    def identity(tag: str) -> Identity:
        owner, name = github_repository(origin_url(repo))
        return Keyless(owner, name, tag)

    def release(tag: str | None) -> dict[str, str]:
        return find_release(github_repository(origin_url(repo)), tag, api_base=github_api)

    return Host(run=run, cosign=Cosign(), identity=identity, backup=backup, restore=restore,
                files_up_to_date=files, find_release=release)  # fmt: skip


def _ok_real(run: Run, argv: Sequence[str], step: str) -> str:
    code, said = run(argv)
    if code != 0:
        last = [line for line in said.splitlines() if line.strip()]
        raise UpdateFailed(step, last[-1] if last else f"exit {code}")
    return said


def main(argv: Sequence[str] | None = None, *, repo_root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(prog="ospreyflow update", description=__doc__)
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="say whether a newer release exists")
    parser.add_argument(
        "--github-api", default=GITHUB_API, help="the GitHub API's address (GitHub Enterprise)"
    )
    parser.add_argument("--to", help="a release to move to; the newest if not given")
    parser.add_argument("--yes", action="store_true", help="ask nothing")
    args = parser.parse_args(argv)
    if args.check:
        return check(args.deployment, repo_root, github_api=args.github_api)
    host = real_host(args.deployment, repo_root, github_api=args.github_api)

    def confirm(question: str) -> bool:
        if args.yes:
            return True
        return input(f"{question} Continue? [y/N] ").strip().lower() in ("y", "yes")

    return apply_update(args.deployment, repo_root, host, to=args.to, confirm=confirm)


if __name__ == "__main__":
    raise SystemExit(main())
