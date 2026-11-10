"""P5b's owed live proof (ADR-114 Amendment 38 decision 9) on a real named deployment, under
platform-b's lease. Run from `OspreyFlow_Core` on the test server, with `PYTHONPATH=.:packages:cli`:

    .venv/bin/python ../OspreyFlow_Build/process/lanes/platform-b/gates/p5b_live_update.py

1. `ospreyflow install --mode lite --name osprey-p5b-test` into a throwaway home folder, seeded with
   the synthetic `fixture-corp` (rule 9: in-repo, synthetic). The backups folder is a throwaway one.
2. With the Conduit stopped, a snapshot of the graph store, then `update.real_host(...).backup()`.
   The set must land in `<backups folder>/osprey-p5b-test/`, and the harness must be named the
   deployment's own `osprey.yaml` and folder.
3. A forced failure's rollback: `update._roll_back`, as `update.main` calls it on a failed step. It
   runs `down -v` on this deployment's project, starts it again, restores the set with `real_host`'s
   restore and checks that it runs. The `git checkout` of the old commit is NOT EXERCISED: it passes
   through, because the copy on the server holds no `.git`; P5b does not change that step.
4. A second snapshot, which must equal the first.

On a shared server (CARRIES' owed-proof row; on 10 November 2026 a cleanup by a before/after
   difference of tags deleted three images another lane built while it ran):
- the image tags the install's build names are claimed with the IDs it made; at teardown a tag is
  put back to its old ID if it had one, removed if it was new, and left alone if it no longer names
  the run's image (another lane built it again meanwhile) (`OwnImages`);
- every removal the driver or the rollback sends passes `guarded`: a compose project (`-p` or
  `--project-name`) and compose file of this run's alone, volumes and containers named
  `osprey-p5b-*` alone, no image removal but `OwnImages`'s; a refusal in teardown is said and the
  rest of the cleanup runs;
- the after-check fails if anything outside `osprey-p5b-*` changed, anything of the run's is left,
  or an image tag that existed before names another image or is gone (`tags_changed`).
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml

NAME = "osprey-p5b-test"
CORE = Path.cwd()


def say(line: str) -> None:
    print(f"p5b-live: {line}", flush=True)


def run(argv: list[str], env: dict[str, str]) -> None:
    say("$ " + " ".join(argv))
    done = subprocess.run(argv, env=env, cwd=CORE, check=False)
    if done.returncode != 0:
        raise SystemExit(f"p5b-live: FAILED ({done.returncode}): {' '.join(argv)}")


def docker_state() -> tuple[set[str], set[str]]:
    """Every container (by name) and every volume on this machine, for the before-after record."""
    names = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True, text=True, check=True
    ).stdout.split()
    volumes = subprocess.run(
        ["docker", "volume", "ls", "-q"], capture_output=True, text=True, check=True
    ).stdout.split()
    return set(names), set(volumes)


def image_table() -> dict[str, str]:
    """Every image tag on this machine and the image ID it names."""
    out = subprocess.run(
        ["docker", "images", "--no-trunc", "--format", "{{.Repository}}:{{.Tag}} {{.ID}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    table: dict[str, str] = {}
    for line in out:
        tag, _, image_id = line.partition(" ")
        if not tag.endswith(":<none>") and image_id:
            table[tag] = image_id
    return table


def inspect_image(name: str) -> str | None:
    done = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", name],
        capture_output=True,
        text=True,
        check=False,
    )
    return (done.stdout.strip() or None) if done.returncode == 0 else None


class OwnImages:
    """The image tags this run's build names, claimed with the IDs it made (CARRIES' owed-proof
    row): put back to the ID each named before, or removed if it was new, and in either case only
    while it still names the run's image. Never a before-and-after difference of the machine's
    tags."""

    def __init__(
        self,
        before: dict[str, str],
        *,
        inspect: Callable[[str], str | None] = inspect_image,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.before = dict(before)
        self.inspect = inspect
        self.runner = runner
        self.made: dict[str, str] = {}

    def claim(self, names: Iterable[str]) -> None:
        """Each name as the run's build left it, read at once."""
        for name in names:
            image_id = self.inspect(name)
            if image_id is not None and image_id != self.before.get(name):
                self.made[name] = image_id

    def made_ids(self) -> set[str]:
        return set(self.made.values())

    def restore(self) -> list[str]:
        said: list[str] = []
        for name, made_id in self.made.items():
            now = self.inspect(name)
            if now != made_id:
                said.append(f"{name}: left alone, another build names it now ({now})")
            elif name in self.before:
                self.runner(["docker", "tag", self.before[name], name], check=False)
                said.append(f"{name}: put back to {self.before[name]}")
            else:
                self.runner(["docker", "rmi", name], check=False)
                said.append(f"{name}: the run's own, removed")
        return said


def tags_changed(before: dict[str, str], after: dict[str, str], made_ids: set[str]) -> list[str]:
    """Tags the run must not have touched and did: one that existed before naming another image or
    gone, or one naming the run's own image left behind. Another lane's new tag is not one."""
    changed = [tag for tag, image_id in before.items() if after.get(tag) != image_id]
    left = [tag for tag, image_id in after.items() if tag not in before and image_id in made_ids]
    return sorted(changed + left)


def ours(name: str) -> bool:
    return name.startswith("osprey-p5b-")


def _project(argv: list[str]) -> str | None:
    for flag in ("-p", "--project-name"):
        if flag in argv:
            return argv[argv.index(flag) + 1]
    return None


def _refuse(why: str, argv: list[str], teardown: bool) -> None:
    if teardown:
        say(f"REFUSED, {why}: {argv} (the cleanup goes on)")
        return None
    raise SystemExit(f"p5b-live: REFUSED, {why}: {argv}")


def guarded(argv: list[str], home: Path, *, teardown: bool = False) -> list[str] | None:
    """Every removal this run sends, its own alone (the orchestrator's guards): a compose project
    and compose file of this run's, volumes and containers named `osprey-p5b-*`, and no image
    removal (the run's images go through `OwnImages`). Anything else passes as it is. Refused, it
    raises; in teardown it is said and `None` returned, so the rest of the cleanup still runs."""
    if argv[:2] == ["docker", "compose"]:
        if not {"down", "rm"} & set(argv):
            return argv
        files = [Path(argv[i + 1]) for i, a in enumerate(argv) if a == "-f"]
        if not files or not all(f.resolve().is_relative_to(home.resolve()) for f in files):
            return _refuse("a compose file outside the throwaway home", argv, teardown)
        for f in files:
            if yaml.safe_load(f.read_text()).get("name") != NAME:
                return _refuse(f"{f} is another project", argv, teardown)
        project = _project(argv)
        if project is not None:
            return argv if project == NAME else _refuse("another project", argv, teardown)
        return ["docker", "compose", "-p", NAME, *argv[2:]]
    if argv[:1] != ["docker"]:
        return argv
    rest = argv[1:]
    if rest[:1] == ["rmi"] or rest[:2] in (["image", "rm"], ["image", "prune"]):
        return _refuse("an image removed outside OwnImages", argv, teardown)
    if rest[:2] in (["volume", "prune"], ["system", "prune"], ["container", "prune"]):
        return _refuse("a prune", argv, teardown)
    if rest[:2] in (["volume", "rm"], ["container", "rm"]) or rest[:1] == ["rm"]:
        skip = 2 if rest[0] in ("volume", "container") else 1
        names = [a for a in rest[skip:] if not a.startswith("-")]
        if not names or not all(ours(n) for n in names):
            return _refuse("a volume or container not this run's", argv, teardown)
    return argv


def _teardown_step(label: str, step: Callable[[], object]) -> None:
    """One cleanup step; a failure is said and the next step runs."""
    try:
        step()
    except BaseException as failed:  # noqa: BLE001 - teardown says every failure and goes on
        say(f"teardown step '{label}' failed: {failed!r} (the cleanup goes on)")


def main() -> int:
    scratch = Path(tempfile.mkdtemp(prefix="osprey-p5b-"))
    home = scratch / "home"
    backups = scratch / "backups"
    home.mkdir()
    real_home = os.environ["HOME"]
    os.environ.pop("COMPOSE_PROJECT_NAME", None)  # no project from the environment
    containers_before, volumes_before = docker_state()
    tags_before = image_table()
    say(f"docker before: {len(tags_before)} image tags: {' '.join(sorted(tags_before))}")
    listed = " ".join(sorted(containers_before))
    say(f"docker before: {len(containers_before)} containers: {listed}")
    say(f"docker before: {len(volumes_before)} volumes: {' '.join(sorted(volumes_before))}")
    env = {
        **os.environ,
        "HOME": str(home),
        "DOCKER_CONFIG": os.environ.get("DOCKER_CONFIG", f"{real_home}/.docker"),
        "OSPREYFLOW_HOME": str(CORE),
        "PYTHONPATH": ".:packages:cli",
    }
    directory = home / ".ospreyflow" / "deployments" / NAME
    compose = ["docker", "compose", "-p", NAME, "-f", str(directory / "compose.yaml")]
    python = str(CORE / ".venv" / "bin" / "python")
    own_images = OwnImages(tags_before)
    ok = False
    try:
        answers = scratch / "answers.yaml"
        answers.write_text(
            yaml.safe_dump(
                {
                    "mode": "lite",
                    "folders": {
                        "backups": str(backups),
                        "ingest": str(scratch / "ingest"),
                        "tiles": str(scratch / "tiles"),
                    },
                    "demo_packs": [],
                }
            )
        )
        install = [
            python, "-m", "ospreyflow", "install", "--mode", "lite", "--name", NAME,
            "--config", str(answers), "--yes", "--no-demo-accounts",
        ]  # fmt: skip
        say("$ " + " ".join(install))
        installed = subprocess.run(install, env=env, cwd=CORE, check=False).returncode == 0
        if (directory / "compose.yaml").is_file():
            rendered = yaml.safe_load((directory / "compose.yaml").read_text())
            # Claimed at once, built or not: what the build tagged is the run's to put back.
            own_images.claim(
                s["image"] for s in rendered["services"].values() if "build" in s and "image" in s
            )
            say(f"the run's images: {own_images.made or 'none'}")
        if not installed:
            raise SystemExit("p5b-live: FAILED: the install")
        config = directory / "osprey.yaml"
        stored = yaml.safe_load(config.read_text())["components"]["storage"]["backups"]
        assert stored == str(backups), stored
        run(
            [python, "-m", "harness.apply", "--config", str(config), "--out-root",
             str(directory.parent), "--seed", "fixture-corp", "--no-build"],
            env,
        )  # fmt: skip
        run([*compose, "stop", "api"], env)

        os.environ.update(env)  # the harness reads HOME for its fallback folder
        sys.path[:0] = [str(CORE), str(CORE / "packages")]
        from harness import update
        from harness.compare import take_snapshot

        before = take_snapshot(directory / "compose.yaml")
        assert before.total_records > 0, "fixture-corp seeded nothing: the comparison is vacuous"
        say(f"before: {before.total_records} records")
        host = update.real_host(directory, CORE)
        made = host.backup()
        say(f"the update's backup: {made}")
        assert made.parent == backups / NAME, made
        assert not (CORE / "backups").exists() and not (CORE / "~").exists()

        def passing_git(argv: object) -> tuple[int, str]:
            seq = list(argv)  # type: ignore[call-overload]
            if seq and seq[0] == "git":
                say("$ " + " ".join(seq) + "   (NOT EXERCISED: no .git in the server's copy)")
                return 0, ""
            sent = guarded(seq, home)
            assert sent is not None
            say("$ " + " ".join(sent))
            return host.run(sent)

        forced = dataclasses.replace(host, run=passing_git)
        point = update._keep_rollback_point(directory, "p5b-before", "HEAD")
        say("forced failure: rolling back as update.main does on a failed step")
        code = update._roll_back(forced, directory, CORE, point, "HEAD", made, "p5b-before")
        assert code == 1, f"the rollback did not finish (exit {code})"
        run([*compose, "stop", "api"], env)
        after = take_snapshot(directory / "compose.yaml")
        differences = after.differences_from(before)
        assert not differences, differences
        say(f"after the rollback's restore: {after.total_records} records, no differences")
        ok = True
    finally:
        say("teardown: down -v on " + NAME + " only, its volumes, the run's images, the folders")

        def down() -> None:
            if not (directory / "compose.yaml").is_file():
                return
            envfile = ["--env-file", str(directory / "deployment.env")]
            sent = guarded(
                [*compose, *envfile, "down", "-v", "--remove-orphans"], home, teardown=True
            )
            if sent is not None:
                say("$ " + " ".join(sent))
                subprocess.run(sent, env=env, cwd=CORE, check=False)

        def volumes() -> None:
            left = subprocess.run(
                ["docker", "volume", "ls", "-q", "--filter", f"name={NAME}"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.split()
            if left:
                sent = guarded(["docker", "volume", "rm", *left], home, teardown=True)
                if sent is not None:
                    subprocess.run(sent, check=False)

        def images() -> None:
            for line in own_images.restore():
                say(f"image {line}")

        _teardown_step("down -v", down)
        _teardown_step("volumes", volumes)
        _teardown_step("images", images)
        _teardown_step("folders", lambda: shutil.rmtree(scratch, ignore_errors=True))
        containers_after, volumes_after = docker_state()
        tags_after = image_table()
        say(f"docker after: {len(tags_after)} image tags: {' '.join(sorted(tags_after))}")
        listed = " ".join(sorted(containers_after))
        say(f"docker after: {len(containers_after)} containers: {listed}")
        say(f"docker after: {len(volumes_after)} volumes: {' '.join(sorted(volumes_after))}")
        others = {x for x in containers_before ^ containers_after if not ours(x)}
        others |= {x for x in volumes_before ^ volumes_after if not ours(x)}
        left_ours = {x for x in containers_after | volumes_after if ours(x)}
        tags = tags_changed(tags_before, tags_after, own_images.made_ids())
        say(f"changed outside osprey-p5b-*: {sorted(others) or 'nothing'}")
        say(f"osprey-p5b-* left: {sorted(left_ours) or 'nothing'}")
        say(f"image tags changed or left: {tags or 'nothing'}")
        if others or left_ours or tags:
            ok = False
    say("PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
