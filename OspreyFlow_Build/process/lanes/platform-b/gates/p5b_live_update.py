"""P5b's one live run (the orchestrator's grant, 10 November 2026): ADR-114 Amendment 38 decision 9 on
a real named deployment. Run from `OspreyFlow_Core` on the test server, under platform-b's lease:

    PYTHONPATH=.:packages:cli .venv/bin/python ../OspreyFlow_Build/process/lanes/platform-b/gates/p5b_live_update.py

1. `ospreyflow install --mode lite --name osprey-p5b-test` into a throwaway home folder, seeded with
   the synthetic `fixture-corp` (rule 9: in-repo, synthetic). The backups folder is a throwaway one.
2. With the Conduit stopped, a snapshot of the graph store, then `update.real_host(...).backup()`.
   The set must land in `<backups folder>/osprey-p5b-test/`, and the harness must be named the
   deployment's own `osprey.yaml` and folder.
3. A forced failure's rollback: `update._roll_back`, as `update.main` calls it on a failed step. It runs
   `down -v` on this deployment's project, starts it again, restores the set with `real_host`'s
   restore and checks that it runs. The `git checkout` of the old commit is NOT EXERCISED: it passes
   through, because the copy on the server holds no `.git`; P5b does not change that step.
4. A second snapshot, which must equal the first.

Teardown always runs: `down -v` on `osprey-p5b-test` only, then the throwaway folders are removed.
It touches nothing else: not osprey-small, not osprey-test-*, not a leased stack's containers.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

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
    """Every container (by name) and every volume on this machine, for the before-and-after record."""
    names = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}"],
                           capture_output=True, text=True, check=True).stdout.split()  # fmt: skip
    volumes = subprocess.run(["docker", "volume", "ls", "-q"],
                             capture_output=True, text=True, check=True).stdout.split()  # fmt: skip
    return set(names), set(volumes)


def ours(name: str) -> bool:
    return name.startswith("osprey-p5b-")


def guarded(argv: list[str], home: Path) -> list[str]:
    """The orchestrator's guard 1: a compose command that removes anything names this project, with
    -p, and a compose file under the throwaway home whose own name is this project; else refused."""
    if argv[:2] != ["docker", "compose"] or not {"down", "rm"} & set(argv):
        return argv
    files = [Path(argv[i + 1]) for i, a in enumerate(argv) if a == "-f"]
    if not files or not all(f.resolve().is_relative_to(home.resolve()) for f in files):
        raise SystemExit(f"p5b-live: REFUSED, a compose file outside the throwaway home: {argv}")
    for f in files:
        named = yaml.safe_load(f.read_text()).get("name")
        if named != NAME:
            raise SystemExit(f"p5b-live: REFUSED, {f} is the project {named!r}, not {NAME}")
    if "-p" in argv:
        if argv[argv.index("-p") + 1] != NAME:
            raise SystemExit(f"p5b-live: REFUSED, another project: {argv}")
        return argv
    return ["docker", "compose", "-p", NAME, *argv[2:]]


def main() -> int:
    scratch = Path(tempfile.mkdtemp(prefix="osprey-p5b-"))
    home = scratch / "home"
    backups = scratch / "backups"
    home.mkdir()
    real_home = os.environ["HOME"]
    os.environ.pop("COMPOSE_PROJECT_NAME", None)  # guard 1: no project from the environment
    containers_before, volumes_before = docker_state()
    say(f"docker before: {len(containers_before)} containers: {' '.join(sorted(containers_before))}")
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
    ok = False
    try:
        # A defect older than P5b, routed to the orchestrator: the preflight resolves the published
        # `${OSPREY_ARCADEDB_PORT:-2480}` against the process environment, not the deployment's
        # own deployment.env, so a named install fails wherever 2480 is held (osprey-small holds
        # it here). The driver puts the port the install will choose into the environment itself,
        # chosen as the install chooses it, and checks the install chose the same.
        import socket

        sys.path[:0] = [str(CORE / "cli")]
        from ospreyflow.deployments import FIRST_GRAPH_PORT, next_free_port

        def port_free(port: int) -> bool:
            with socket.socket() as probe:
                return probe.connect_ex(("127.0.0.1", port)) != 0

        graph = next_free_port(FIRST_GRAPH_PORT, (), port_free)
        env["OSPREY_ARCADEDB_PORT"] = str(graph)
        say(f"OSPREY_ARCADEDB_PORT={graph} (the preflight's environment; see above)")
        answers = scratch / "answers.yaml"
        answers.write_text(yaml.safe_dump({
            "mode": "lite",
            "folders": {"backups": str(backups), "ingest": str(scratch / "ingest"),
                        "tiles": str(scratch / "tiles")},
            "demo_packs": [],
        }))  # fmt: skip
        run([python, "-m", "ospreyflow", "install", "--mode", "lite", "--name", NAME,
             "--config", str(answers), "--yes", "--no-demo-accounts"], env)  # fmt: skip
        config = directory / "osprey.yaml"
        stored = yaml.safe_load(config.read_text())["components"]["storage"]["backups"]
        assert stored == str(backups), stored
        chosen = yaml.safe_load(config.read_text())["deployment"]["graph_port"]
        assert chosen == graph, f"the install chose {chosen}, the environment says {graph}"
        run([python, "-m", "harness.apply", "--config", str(config), "--out-root",
             str(directory.parent), "--seed", "fixture-corp"], env)  # fmt: skip
        run([*compose, "stop", "api"], env)

        os.environ.update(env)  # the harness reads HOME for its fallback folder
        sys.path[:0] = [str(CORE), str(CORE / "packages")]
        from harness import update
        from harness.compare import take_snapshot

        before = take_snapshot(directory / "compose.yaml")
        assert before.total_records > 0, (
            "fixture-corp seeded nothing: the comparison would be vacuous"
        )
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
            seq = guarded(seq, home)
            say("$ " + " ".join(seq))
            return host.run(seq)

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
        say("teardown: down -v on " + NAME + " only, then the throwaway folders")
        if (directory / "compose.yaml").is_file():
            down = guarded([*compose, "down", "-v", "--remove-orphans"], home)
            say("$ " + " ".join(down))
            subprocess.run(down, env=env, cwd=CORE, check=False)
        left = subprocess.run(["docker", "volume", "ls", "-q", "--filter", f"name={NAME}"],
                              capture_output=True, text=True, check=False).stdout.split()  # fmt: skip
        left = [v for v in left if ours(v)]
        if left:
            subprocess.run(["docker", "volume", "rm", *left], check=False)
        shutil.rmtree(scratch, ignore_errors=True)
        still = subprocess.run(["docker", "ps", "-aq", "--filter", f"name={NAME}"],
                               capture_output=True, text=True, check=False).stdout.split()  # fmt: skip
        say(f"teardown done: containers left {len(still)}, volumes left {len(left)} (removed)")
        containers_after, volumes_after = docker_state()
        say(f"docker after: {len(containers_after)} containers: {' '.join(sorted(containers_after))}")
        say(f"docker after: {len(volumes_after)} volumes: {' '.join(sorted(volumes_after))}")
        # Guard 2: nothing outside osprey-p5b-* changed, and nothing of ours is left.
        others = {x for x in containers_before ^ containers_after if not ours(x)}
        others |= {x for x in volumes_before ^ volumes_after if not ours(x)}
        left_ours = {x for x in containers_after | volumes_after if ours(x)}
        say(f"changed outside osprey-p5b-*: {sorted(others) or 'nothing'}")
        say(f"osprey-p5b-* left: {sorted(left_ours) or 'nothing'}")
        if others or left_ours:
            ok = False
    say("PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
