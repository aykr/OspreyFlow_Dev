"""017, item 1 (the owner's answer of 25 November 2026): the build account's runner (build_server/runner.py), the
forced command of the Mac's key. `checks <ID>` takes a bundle of exactly main's tip and one slice's tip on standard
input, answers "started" at once, and a detached job runs the container checks on the candidate the Mac's merge
builds (main, the slice merged --no-ff, its scan rows applied), in this account's own rootless Docker only, and commits
the result on its clone's local branch build-results, for the backup timer to push. 017-2's verbs are refused until
built; anything else is refused, logged by reason and length, never its text.

The world is the real one's shape: the slice's branch is on the Mac only (never in the dev repository, which holds
main); the build account's clone is a clone of the dev repository; the runner is installed apart from it (bin/ and
data/). It runs as sshd runs a forced command: no arguments, the asked-for words in SSH_ORIGINAL_COMMAND, PATH, HOME
and XDG_RUNTIME_DIR only. make and git are real; docker, uv and npm are stood in, and the stand-in docker refuses as
the real one does: it answers only on this account's socket, and says "rootless" only for a rootless daemon. The
wrapper sets what the line's tests need (a direct launch, the system socket paths, test variables kept), never a
switch the runner reads.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
RUNNER_SRC = HERE.parent / "build_server" / "runner.py"
sys.path.insert(0, str(HERE.parent))
import server_gate  # noqa: E402

BUILD_MK = """ci: lint-tools opentofu-check chart-check cp-policy-check
lint-tools:
\t@echo lint-tools >> "$(MARKS)"
opentofu-check:
\t@echo opentofu-check >> "$(MARKS)"
chart-check:
\t@echo chart-check >> "$(MARKS)"
cp-policy-check:
\t@echo cp-policy-check >> "$(MARKS)"; docker run --rm alpine true
"""
CORE_MK = """check: lint trivy trivy-image-api harness-a11y
lint:
\t@echo lint >> "$(MARKS)"
trivy:
\t@echo trivy >> "$(MARKS)"
trivy-image-api:
\t@echo trivy-image-api >> "$(MARKS)"; test -z "$(FAIL_API)"
harness-a11y:
\t@echo harness-a11y >> "$(MARKS)"
"""
DOCKER = """#!/bin/sh
echo "$DOCKER_HOST $*" >> "$FAKE_DOCKER_LOG"
[ "$DOCKER_HOST" = "unix://$XDG_RUNTIME_DIR/docker.sock" ] || {
  echo "Cannot connect to the Docker daemon at ${DOCKER_HOST:-unix:///var/run/docker.sock}" >&2; exit 1; }
if [ "$1" = info ]; then
  if [ -n "$FAKE_ROOTFUL" ]; then echo '["name=seccomp,profile=builtin"]'; else
  echo '["name=seccomp,profile=builtin","name=rootless","name=cgroupns"]'; fi
fi
"""
WRAP = """import json, sys
runner_py, harness = sys.argv[1], json.loads(open(sys.argv[2]).read())
sys.path.insert(0, runner_py.rsplit("/", 1)[0])
import runner
runner.LAUNCH = harness.get("launch", "direct")
runner.OWN_ENV = harness.get("own_env", ["env"])
runner.TMUX = harness.get("tmux", getattr(runner, "TMUX", "tmux"))
runner.WORKER = [sys.executable, __file__, runner_py, sys.argv[2], "_work"]
runner.SYSTEM_SOCKETS = tuple(harness.get("sockets", []))
runner.KEPT = runner.KEPT + tuple(harness.get("keep", []))
runner.MAX_QUEUE = harness.get("max_queue", runner.MAX_QUEUE)
runner.MAX_BUNDLE = harness.get("max_bundle", runner.MAX_BUNDLE)
runner.SEAT_WORKER = [sys.executable, __file__, runner_py, sys.argv[2], "_seat"]
if harness.get("seat_run"):
    runner.SEAT_RUN = harness["seat_run"]
sys.exit(runner.main(sys.argv[3:]))
"""
EXPECTED = ["opentofu-check", "chart-check", "cp-policy-check", "trivy", "trivy-image-api", "harness-a11y"]
KEEP = ["MARKS", "FAIL_API", "FAKE_ROOTFUL", "FAKE_DOCKER_LOG", "DOCKER_HOST"]


def sh(cmd, cwd, env, check=True):
    p = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, shell=isinstance(cmd, str))
    if check and p.returncode != 0:
        raise AssertionError(f"{cmd}: {p.stdout}{p.stderr}")
    return p.stdout.strip()


@pytest.fixture
def bw(tmp_path):
    fake, run = tmp_path / "bin", tmp_path / "run"
    server = tmp_path / "server"
    home = server / "home"
    for d in (fake, run, home, server / "bin"):
        d.mkdir(parents=True)
    shutil.copy(RUNNER_SRC, server / "bin" / "runner.py")
    (server / "bin" / "harness-a11y.ready").write_text("")                # demo-server has proved it runs here
    for name, text in (("docker", DOCKER), ("uv", "#!/bin/sh\n[ \"$1 $2\" = 'sync --frozen' ] || exit 2\n"),
                       ("npm", "#!/bin/sh\n[ \"$1\" = ci ] || exit 2\n")):
        (fake / name).write_text(text)
        (fake / name).chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "DOCKER_", "SSH_"))}
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.invalid")
    origin, mac = tmp_path / "dev.git", tmp_path / "mac"
    sh(["git", "init", "-q", "--bare", "-b", "main", str(origin)], tmp_path, env)
    sh(["git", "init", "-q", "-b", "main", str(mac)], tmp_path, env)
    files = {"OspreyFlow_Build/Makefile": BUILD_MK, "OspreyFlow_Core/Makefile": CORE_MK,
             ".github/workflows/ci.yml": 'env:\n  UV_PYTHON: "3.12"\n',
             "OspreyFlow_Build/scripts/slice_line/scan_map.tsv": "pattern\tscans\n"}
    for rel, text in files.items():
        (mac / rel).parent.mkdir(parents=True, exist_ok=True)
        (mac / rel).write_text(text)
    sh("git add -A && git commit -qm base && git switch -qc lane/slice-S1 && echo f > feature.txt && git add -A "
       "&& git commit -qm 'S1: the feature' && git switch -q main && echo later > later.txt && git add -A "
       "&& git commit -qm 'main moves'", mac, env)
    sh(["git", "push", "-q", str(origin), "main"], mac, env)          # the dev repository: main only, as on GitHub
    sh(["git", "clone", "-q", str(origin), str(home / "ospreyflow")], tmp_path, env)
    harness = tmp_path / "harness.json"
    harness.write_text(json.dumps({"keep": KEEP}))
    w = {"tmp": tmp_path, "env": env, "origin": origin, "mac": mac, "server": server, "home": home,
         "clone": home / "ospreyflow", "data": server / "data", "harness": harness, "wrap": tmp_path / "wrap.py",
         "tip": sh(["git", "rev-parse", "lane/slice-S1"], mac, env), "main": sh(["git", "rev-parse", "main"], mac, env),
         "marks": tmp_path / "marks", "docker_log": tmp_path / "docker.log",
         "sshd": {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}", "HOME": str(home), "XDG_RUNTIME_DIR": str(run),
                  "MARKS": str(tmp_path / "marks"), "FAKE_DOCKER_LOG": str(tmp_path / "docker.log")}}
    w["wrap"].write_text(WRAP)
    return w


def bundle(w, *refs, name="b.bundle"):
    """A bundle as early_warning.make_bundle makes it, from the Mac's repository."""
    b = w["tmp"] / name
    b.unlink(missing_ok=True)
    sh(["git", "bundle", "create", "-q", str(b), *(refs or ("refs/heads/main", "refs/heads/lane/slice-S1"))],
       w["mac"], w["env"])
    return b.read_bytes()


def forced(w, command, stdin=b"", harness=None, **extra):
    """runner.py as sshd's forced command runs it: no arguments; the words, if any, in SSH_ORIGINAL_COMMAND."""
    h = w["harness"]
    if harness:
        h = w["tmp"] / "harness-call.json"
        h.write_text(json.dumps({"keep": KEEP, **harness}))
    env = {**w["sshd"], **extra}
    if command is not None:
        env["SSH_ORIGINAL_COMMAND"] = command
    p = subprocess.run([sys.executable, str(w["wrap"]), str(w["server"] / "bin/runner.py"), str(h)], input=stdin,
                       env=env, capture_output=True)
    lines = [ln for ln in p.stdout.decode().splitlines() if ln.strip()]
    return p.returncode, (json.loads(lines[-1]) if lines else None)


def done(w, rid, seconds=60):
    f = w["data"] / "jobs" / rid / "result.json"
    end = time.monotonic() + seconds
    while not f.exists():
        assert time.monotonic() < end, f"job {rid} never finished"
        time.sleep(0.1)
    return json.loads(f.read_text())


def checks(w, **kw):
    code, said = forced(w, "checks S1", bundle(w), **kw)
    assert code == 0 and said["state"] == "started", said
    return done(w, said["id"]), said


def committed(w, slice_id="S1", tip=None):
    return json.loads(sh(["git", "show", f"refs/heads/build-results:results/{slice_id}/{tip or w['tip']}.json"],
                         w["clone"], w["env"]))


def marks(w):
    return w["marks"].read_text().split() if w["marks"].exists() else []


def jobs(w):
    d = w["data"] / "jobs"
    return list(d.iterdir()) if d.exists() else []


def mac_merge_tree(w, rows=None):
    """The Mac's merge, by hand: main, the slice --no-ff, and its scan rows applied and amended in."""
    m = w["tmp"] / "merge"
    shutil.rmtree(m, ignore_errors=True)
    sh(["git", "clone", "-q", str(w["mac"]), str(m)], w["tmp"], w["env"])
    sh(f"git merge -q --no-ff -m m {w['tip']}", m, w["env"])
    if rows:
        (m / "OspreyFlow_Build/scripts/slice_line/scan_map.tsv").write_text("pattern\tscans\n" + rows)
        sh("git add -A && git rm -q OspreyFlow_Build/process/lanes/v062/scan_rows/S1.tsv && "
           "git commit -q --amend --no-edit", m, w["env"])
    return sh(["git", "rev-parse", "HEAD^{tree}"], m, w["env"])


def test_the_world_holds_the_slice_on_the_mac_only(bw):
    w = bw
    for repo in (w["origin"], w["clone"]):
        assert subprocess.run(["git", "cat-file", "-e", w["tip"]], cwd=str(repo), env=w["env"],
                              capture_output=True).returncode != 0, repo


def test_checks_runs_the_container_checks_on_the_macs_candidate_from_the_bundle_alone(bw):
    w = bw
    r, said = checks(w)
    assert said["holds_main"] == w["main"] and re.fullmatch(r"[0-9a-f]{16}", said["id"]), said
    assert r["verdict"] == "pass" and r["runner"] == "bc-1" and r["id"] == said["id"], r
    assert (r["slice"], r["tip"], r["main"]) == ("S1", w["tip"], w["main"]), r
    assert r["passed_targets"] == EXPECTED and marks(w) == EXPECTED, r      # lint and lint-tools are not its to run
    assert r["tree"] == mac_merge_tree(w), r
    assert committed(w) == r                                                 # on the clone's build-results
    names = {x["name"] for x in r["not_run"]["targets"]}
    assert "trivy-image-ingest" in names and "trivy-image-api" not in names, r


def test_harness_a11y_stays_on_the_mac_until_it_is_proved_on_the_server(bw):
    w = bw
    (w["server"] / "bin" / "harness-a11y.ready").unlink()
    r, _ = checks(w)
    rest = [t for t in EXPECTED if t != "harness-a11y"]
    assert r["verdict"] == "pass" and r["passed_targets"] == rest and marks(w) == rest, r
    why = {x["name"]: x["why"] for x in r["not_run"]["targets"]}
    assert "the Mac keeps it" in why["harness-a11y"], why
    assert "harness-a11y" in server_gate.BUILD_TARGETS                  # the Mac takes only what the result passed


def test_results_go_back_only_through_the_backup_branch_and_nothing_is_pushed(bw):
    w = bw
    checks(w)
    assert sh(["git", "status", "--porcelain"], w["clone"], w["env"]) == ""        # the clone's own tree untouched
    assert sh(["git", "for-each-ref", "--format=%(refname)"], w["origin"], w["env"]) == "refs/heads/main"
    clone_refs = sh(["git", "for-each-ref", "--format=%(refname)"], w["clone"], w["env"]).split()
    assert "refs/heads/build-results" in clone_refs and not any("slice" in r for r in clone_refs), clone_refs
    jobs_refs = sh(["git", "for-each-ref", "refs/jobs/"], w["data"] / "source.git", w["env"])
    assert jobs_refs == "", jobs_refs                                               # the job's refs let go


def test_its_result_has_the_shape_the_macs_merge_reads_and_names_only_the_targets_the_mac_takes(bw):
    w = bw
    r, _ = checks(w)
    sys.path.insert(0, str(RUNNER_SRC.parent))
    import runner as rn
    assert {t for _f, _g, t in rn.TARGETS} == set(server_gate.BUILD_TARGETS)       # one list, both sides
    assert r["runner"] == server_gate.BUILD_RUNNER and server_gate.RUN_ID.match(r["id"]), r
    assert r["state"] == "done" and r["verdict"] in server_gate.VERDICTS and isinstance(r["passed_targets"], list), r
    assert set(r["passed_targets"]) <= set(server_gate.BUILD_TARGETS), r


def test_the_slices_scan_rows_are_applied_in_the_candidate_as_the_macs_merge_applies_them(bw):
    w = bw
    rows = w["mac"] / "OspreyFlow_Build/process/lanes/v062/scan_rows/S1.tsv"
    rows.parent.mkdir(parents=True, exist_ok=True)
    rows.write_text("# the slice's rows\nfeature.txt\tlint\n")
    sh("git add -A && git commit -qm 'S1 scan rows'", w["mac"], w["env"])
    r, _ = checks(w)
    assert r["tree"] == mac_merge_tree(w, rows="feature.txt\tlint\n"), r


def test_a_failing_container_check_is_a_fail_naming_it_and_the_others_still_run(bw):
    w = bw
    r, _ = checks(w, FAIL_API="1")
    assert r["verdict"] == "fail" and r["failing"]["targets"] == ["trivy-image-api"], r
    assert r["passed_targets"] == [t for t in EXPECTED if t != "trivy-image-api"] and marks(w) == EXPECTED, r


def test_the_job_uses_this_accounts_own_socket_whatever_its_caller_set(bw):
    w = bw
    r, _ = checks(w, DOCKER_HOST="unix:///var/run/docker.sock")
    assert r["verdict"] == "pass", r
    own = f"unix://{w['sshd']['XDG_RUNTIME_DIR']}/docker.sock"
    calls = w["docker_log"].read_text().splitlines()
    assert len(calls) == 2 and all(c.startswith(own + " ") for c in calls), calls  # docker info, and the run


@pytest.mark.parametrize("how,words", [
    ("system-socket-answers", "the system Docker's socket"),
    ("rootful-daemon", "does not answer as rootless"),
])
def test_nothing_runs_unless_docker_is_this_accounts_own_rootless_daemon(bw, how, words):
    w = bw
    srv, path = None, f"/tmp/bc-{os.getpid()}.sock"                       # short: a unix socket path is limited
    if how == "system-socket-answers":
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(path)
        srv.listen(1)
    try:
        code, said = forced(w, "checks S1", bundle(w), harness={"sockets": [path]} if srv else None,
                            **({"FAKE_ROOTFUL": "1"} if how == "rootful-daemon" else {}))
        r = done(w, said["id"])
    finally:
        if srv:
            srv.close()
            os.unlink(path)
    assert r["verdict"] == "error" and words in r["words"] and r["passed_targets"] == [], r
    assert marks(w) == [], marks(w)                                         # no container check ran


def test_a_slice_that_does_not_merge_cleanly_is_a_conflict_and_nothing_runs(bw):
    w = bw
    (w["mac"] / "feature.txt").write_text("main's own\n")
    sh("git add -A && git commit -qm 'main takes feature.txt'", w["mac"], w["env"])
    r, _ = checks(w)
    assert r["verdict"] == "conflict" and r["passed_targets"] == [] and marks(w) == [], r


@pytest.mark.parametrize("command,reason", [
    (None, "shape"), ("", "shape"), ("checks", "shape"), ("checks s1", "shape"), ("checks S1 extra", "shape"),
    ("checks S1;sh", "shape"), ("checks  S1", "shape"), ("bash", "shape"), ("_work", "shape"),
    ("start S1", "shape"), ("stop S1", "shape"), ("status", "shape"), ("start S1 scout", "shape"),
    ("start s1 builder", "shape"), ("status S1 builder extra", "shape"), ("start S1 builder;sh", "shape"),
    ("restart S1 builder", "shape"), ("attach S1 builder", "shape"), ("_seat S1 builder", "shape"),  # a fourth verb
    ("sh -c id", "shape"), ("bash -l", "shape"), ("tmux attach", "shape"),                            # a shell
])
def test_anything_but_the_four_verbs_is_refused_and_logged_by_reason_and_length_never_its_text(bw, command, reason):
    w = bw
    code, said = forced(w, command, bundle(w))
    assert code == 3 and said["state"] == "refused" and said["reason"] == reason, said
    log = (w["data"] / "refusals.log").read_text()
    assert f"\t{reason}\t{len(command) if command is not None else 0}\n" in log, log
    if command:
        assert command not in log.split("\t", 1)[1], log
    assert jobs(w) == [] and marks(w) == []


def test_work_is_never_reachable_over_ssh(bw):
    w = bw
    env = {**w["sshd"], "SSH_ORIGINAL_COMMAND": "checks S1"}
    p = subprocess.run([sys.executable, str(w["wrap"]), str(w["server"] / "bin/runner.py"), str(w["harness"]),
                        "_work"], input=b"", env=env, capture_output=True)
    assert p.returncode == 3 and b'"bundle-shape"' in p.stdout, p.stdout   # taken as the forced command, not _work


@pytest.mark.parametrize("refs", [
    ("refs/heads/main",),
    ("refs/heads/lane/slice-S1",),
    ("refs/heads/main", "refs/heads/lane/slice-S1", "refs/heads/other"),
    "garbage",
])
def test_a_bundle_of_anything_but_main_and_one_slice_branch_is_refused(bw, refs):
    w = bw
    if refs == "garbage":
        data = b"not a bundle at all\n"
    else:
        sh("git branch -q other lane/slice-S1", w["mac"], w["env"])
        data = bundle(w, *refs)
    code, said = forced(w, "checks S1", data)
    assert code == 3 and said["reason"] == "bundle-shape", said
    assert jobs(w) == [] and marks(w) == []


def test_an_incremental_bundle_needs_what_it_is_built_on_and_the_next_one_is_smaller(bw):
    w = bw
    code, said = forced(w, "checks S1", bundle(w, "refs/heads/main", "refs/heads/lane/slice-S1", "^main~1"))
    assert code == 3 and said["reason"] == "bundle-prerequisites", said        # this copy holds nothing yet
    checks(w)                                                                  # in full
    sh("echo again > again.txt && git add -A && git commit -qm again", w["mac"], w["env"])
    code, said = forced(w, "checks S1", bundle(w, "refs/heads/main", "refs/heads/lane/slice-S1", f"^{w['main']}"))
    assert code == 0 and said["state"] == "started", said                      # built on what it now holds
    assert done(w, said["id"])["verdict"] == "pass"


def test_jobs_wait_their_turn_and_a_full_queue_is_refused(bw):
    w = bw
    ids = []
    for _ in range(3):
        code, said = forced(w, "checks S1", bundle(w))
        assert code == 0, said
        ids.append(said["id"])
    results = [done(w, i) for i in ids]
    assert [r["verdict"] for r in results] == ["pass"] * 3
    log = sh(["git", "log", "--format=%s", "refs/heads/build-results"], w["clone"], w["env"]).splitlines()
    assert len(log) == 3 and all(i in " ".join(log) for i in ids), log
    stuck = w["data"] / "jobs" / ("f" * 16)                                   # a job received, not yet run
    stuck.mkdir(parents=True)
    (stuck / "job.json").write_text("{}")
    code, said = forced(w, "checks S1", bundle(w), harness={"max_queue": 1})
    assert code == 3 and said["reason"] == "busy", said


def test_a_bundle_larger_than_the_cap_is_refused_and_nothing_is_kept(bw):
    w = bw
    data = bundle(w)
    code, said = forced(w, "checks S1", data, harness={"max_bundle": len(data) - 1})
    assert code == 3 and said["reason"] == "too-large", said
    assert jobs(w) == [] and marks(w) == []


def test_a_job_it_cannot_read_is_recorded_as_an_error_and_the_next_still_runs(bw):
    w = bw
    broken = w["data"] / "jobs" / ("0" * 16)                                  # older than any job sent after it
    broken.mkdir(parents=True)
    (broken / "job.json").write_text("{}")
    r, _ = checks(w)
    assert r["verdict"] == "pass", r
    said = json.loads((broken / "result.json").read_text())
    assert said["verdict"] == "error" and "could not be run or recorded" in said["words"], said


@pytest.mark.parametrize("part", ["AD1c", "PL7f", "IS5a0", "SE8f", "GR3a"])
def test_checks_takes_the_lines_real_part_names(bw, part):
    """The line's parts end in a small letter (AD1c, PL7f; IS5a0 has a digit after it): the forced command takes the
    early warning's own shape for a part's name (protocol.SLICE_PATTERN, a capital first), not capitals and digits
    only. Before 26 November 2026 every real part was refused as the wrong shape."""
    w = bw
    sh(["git", "branch", "-f", f"lane/slice-{part}", "lane/slice-S1"], w["mac"], w["env"])
    code, said = forced(w, f"checks {part}", bundle(w, "refs/heads/main", f"refs/heads/lane/slice-{part}"))
    assert code == 0 and said["state"] == "started", said
    r = done(w, said["id"])
    assert r["slice"] == part and r["verdict"] in ("pass", "fail"), r
    assert committed(w, part)["slice"] == part


@pytest.mark.parametrize("cmd", ["checks ad1c", "checks 1AD", "checks AD1c-x", "checks AD1cAD1cAD1cAD1cA"])
def test_checks_still_refuses_what_is_not_a_parts_name(bw, cmd):
    code, said = forced(bw, cmd, bundle(bw))
    assert code != 0 and said["reason"] == "shape", said
