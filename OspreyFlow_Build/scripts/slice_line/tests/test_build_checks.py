"""017, item 1 (the owner, 25 November 2026): the merge's container checks run in the build account's rootless Docker
on the test server, and count at the merge as the server's green does. The build account commits each result on its
local branch build-results; its backup timer pushes it to the backup repository; the Mac fetches that branch from the
backup repository into a cache of the line's own (never over SSH into the build account, never into the main
checkout) and takes from the Mac's gate only the container checks a finished pass for exactly this candidate names.

Behind the owner's own switch (build_counts, off as built), and only beside a server green that counts. The backup
repository is stood in by a bare repository in the test world; the full gate is stood in as in test_server_counts.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from test_gates import sh, world  # noqa: F401  (world is a fixture)
from test_server_counts import X, Y, candidate_tree, gate_plan, green, setup

BRID = "b0b0b0b0b0b0b0b0"
SERVER_PASSED = ["lint-tools", "lint", "typecheck", "test"]   # the server ran no container check


def backup(w, result=None, path=None, url_file=True):
    """The backup repository, as the build account's timer leaves it: branch build-results holding the result at
    results/<slice>/<tip>.json."""
    bare = w["tmp"] / "backup.git"
    if not bare.exists():
        sh(["git", "init", "-q", "--bare", str(bare)], w["tmp"], w["env"])
    if result is not None:
        work = w["tmp"] / "backup-work"
        if not work.exists():
            sh(["git", "init", "-q", "-b", "build-results", str(work)], w["tmp"], w["env"])
        f = work / (path or f"results/{result['slice']}/{result['tip']}.json")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(result))
        sh("git add -A && git commit -qm result && git push -qf ../backup.git build-results", work, w["env"])
    if url_file:
        (w["data"] / "build_backup").write_text(str(bare) + "\n")
    return bare


def build_switch(w, text="on\n"):
    f = w["data"] / "build_counts"
    f.unlink(missing_ok=True)
    if text is not None:
        f.write_text(text)


def built_green(w, tip, **change):
    main = sh("git rev-parse main", w["repo"]).stdout.strip()
    r = {"state": "done", "id": BRID, "runner": "bc-1", "slice": "S1", "tip": tip, "main": main,
         "tree": candidate_tree(w, tip), "verdict": "pass", "passed_targets": ["opentofu-check", "trivy"],
         "failing": {"targets": [], "tests": []}, "not_run": {"targets": []}}
    r.update(change)
    return r


def ready(w):
    wt, tip = setup(w)
    green(w, tip, passed_targets=SERVER_PASSED)
    build_switch(w)
    return tip


def mk_of(plan):
    return next(x[4] for x in plan if x[:3] == ["make", "-f", "Makefile"])


def test_a_build_green_for_exactly_this_tree_takes_the_container_checks_from_the_mac(world):
    w = world
    tip = ready(w)
    backup(w, built_green(w, tip))
    p, plan, server = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan == [["make", "-k", "client-name-check"],
                    ["make", "-f", "Makefile", "-f", mk_of(plan), "server-test-files",
                     f"SERVER_TEST_FILES=../{Y} ../{X}"]], plan
    assert server["build"] == {"counted": True, "run_id": BRID, "taken": ["opentofu-check", "trivy"]}, server
    assert "opentofu-check" in server["taken"] and "core:trivy" in server["taken"], server
    log = next((w["data"] / "records/S1").glob("merge-*.log")).read_text()
    assert f"the build account's run {BRID} counts for the container checks: opentofu-check, trivy" in log


def test_without_it_the_mac_runs_the_container_checks_as_before(world):
    w = world
    tip = ready(w)
    build_switch(w, None)
    backup(w, built_green(w, tip))
    p, plan, server = gate_plan(w)
    assert plan[0] == ["make", "-k", "opentofu-check", "client-name-check"], plan
    assert ["make", "-k", "-C", "../OspreyFlow_Core", "trivy"] in plan, plan
    assert server["build"] == {"counted": False, "why": "the owner's switch (build_counts) is off"}, server


@pytest.mark.parametrize("how,why", [
    ("switch-not-the-word", "switch (build_counts) is off"),
    ("no-backup-named", "no backup repository named"),
    ("backup-unfetchable", "could not be fetched"),
    ("backup-two-lines", "no backup repository named"),
    ("no-result", "no result for this slice at this tip"),
    ("another-tree", "candidate tree"),
    ("main-moved", "main has moved"),
    ("another-tip-inside", "not its runner's own"),
    ("another-runner", "not its runner's own"),
    ("bad-run-id", "not its runner's own"),
    ("red", "not a finished pass"),
    ("error", "ended without a verdict"),
    ("not-json", "not JSON"),
    ("only-other-targets", "names no container check"),
])
def test_anything_short_of_a_build_pass_for_exactly_this_tree_leaves_the_container_checks_on_the_mac(world, how, why):
    w = world
    tip = ready(w)
    r = built_green(w, tip)
    if how == "switch-not-the-word":
        build_switch(w, "yes\n")
        backup(w, r)
    elif how == "no-backup-named":
        backup(w, r, url_file=False)
    elif how == "backup-unfetchable":
        backup(w, r)
        (w["data"] / "build_backup").write_text(str(w["tmp"] / "nowhere.git") + "\n")
    elif how == "backup-two-lines":
        bare = backup(w, r)
        (w["data"] / "build_backup").write_text(f"{bare}\n{w['tmp'] / 'elsewhere.git'}\n")
    elif how == "no-result":
        backup(w, r, path="results/S1/" + "e" * 40 + ".json")
    elif how == "another-tree":
        backup(w, {**r, "tree": "0" * 40})
    elif how == "main-moved":
        backup(w, {**r, "main": sh("git rev-parse main~1", w["repo"]).stdout.strip()})
    elif how == "another-tip-inside":
        backup(w, {**r, "tip": "f" * 40}, path=f"results/S1/{tip}.json")
    elif how == "another-runner":
        backup(w, {**r, "runner": "ew-2"})
    elif how == "bad-run-id":
        backup(w, {**r, "id": "not-a-run"})
    elif how == "red":
        backup(w, {**r, "verdict": "fail", "failing": {"targets": ["trivy"], "tests": []}})
    elif how == "error":
        backup(w, {**r, "verdict": "error", "words": "DOCKER_HOST is not this account's rootless socket"})
    elif how == "not-json":
        backup(w, r)
        work = w["tmp"] / "backup-work"
        (work / f"results/S1/{tip}.json").write_text("{not json")
        sh("git add -A && git commit -qm broken && git push -qf ../backup.git build-results", work, w["env"])
    elif how == "only-other-targets":
        backup(w, {**r, "passed_targets": ["client-name-check", "test"]})
    p, plan, server = gate_plan(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan[0][:3] == ["make", "-k", "opentofu-check"], (how, plan)
    assert ["make", "-k", "-C", "../OspreyFlow_Core", "trivy"] in plan, (how, plan)
    assert server["counted"] is True, server                     # the server's own green still counts
    assert server["build"]["counted"] is False and why in server["build"]["why"], (how, server["build"])


def test_a_build_result_naming_a_target_that_is_not_a_container_check_takes_only_the_container_checks(world):
    w = world
    tip = ready(w)
    backup(w, built_green(w, tip, passed_targets=["opentofu-check", "client-name-check", "trivy"]))
    p, plan, server = gate_plan(w)
    assert plan[0] == ["make", "-k", "client-name-check"], plan   # still the Mac's: no client-name list on the server
    assert server["build"]["taken"] == ["opentofu-check", "trivy"], server


def test_a_build_green_counts_only_beside_a_server_green_that_counts(world):
    w = world
    wt, tip = setup(w)
    green(w, tip, passed_targets=SERVER_PASSED, verdict="fail")
    build_switch(w)
    backup(w, built_green(w, tip))
    p, plan, server = gate_plan(w)
    assert plan is None, plan                                      # the whole gate, as now
    assert server["counted"] is False and "build" not in server, server


def test_the_mac_reads_the_backup_into_a_cache_of_its_own_and_never_the_main_checkout(world):
    w = world
    tip = ready(w)
    backup(w, built_green(w, tip))
    gate_plan(w)
    refs = sh(["git", "for-each-ref", "--format=%(refname)"], w["repo"]).stdout
    assert "build-results" not in refs, refs
    cache = w["data"] / "build-backup.git"
    assert subprocess.run(["git", "--git-dir", str(cache), "rev-parse", "refs/heads/build-results"],
                          capture_output=True).returncode == 0
    assert not (w["repo"] / ".git/FETCH_HEAD").exists() or "backup.git" not in (w["repo"] / ".git/FETCH_HEAD").read_text()
