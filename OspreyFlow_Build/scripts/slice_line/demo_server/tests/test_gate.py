"""The runner's real gate (not the stand-in) on a miniature candidate: what it runs, what it names "not run", the
environment it runs in, and that no Docker is reachable from it. The make targets record what ran in a file."""
from __future__ import annotations

import json
import time

from conftest import out, runner, sh

CI_YML = 'env:\n  UV_PYTHON: "3.12"\njobs:\n  a:\n    steps:\n      - uses: actions/setup-node@v4\n        with: { node-version: "22" }\n'


def mini(w):
    ran = w["tmp"] / "ran.txt"
    repo = w["repo"]
    files = {
        ".github/workflows/ci.yml": CI_YML,
        "OspreyFlow_Build/scripts/lane_ports.tsv": "# lanes\nmerger\t13\n",
        "OspreyFlow_Build/Makefile": (
            "ci: core-check good-check docker-check client-name-check red-check\n"
            "core-check:\n\t$(MAKE) -C ../OspreyFlow_Core check\n"
            f"good-check:\n\t@echo good-check >> {ran}\n"
            "docker-check:\n\tdocker run --rm alpine true\n"
            f"client-name-check:\n\t@echo client-name-check >> {ran}\n"
            "red-check:\n\t@echo 'FAILED ../OspreyFlow_Build/tests/test_r.py::test_q - boom'\n\t@false\n"
            "test:\n"
            f"\t@echo \"addopts=$$PYTEST_ADDOPTS\" >> {ran}\n"
            f"\t@echo \"env docker_host=$$DOCKER_HOST slot=$$OSPREY_PORTS_SLOT arcade=$$ARCADEDB_HTTP_PORT workers=$$TEST_WORKERS uvpy=$$UV_PYTHON pytest_base=$$PYTEST_DEBUG_TEMPROOT\" >> {ran}\n"
            f"\t@test -f $$OSPREY_LEASE_DIR/no-local-stacks && echo lease-switch-on >> {ran}\n"
            f"\t@echo \"root=$$(git rev-parse --path-format=absolute --git-common-dir) remotes=$$(git remote | wc -l | tr -d ' ')\" >> {ran}\n"
            f"\t@docker ps >/dev/null 2>&1 && echo docker-reached >> {ran} || echo docker-refused >> {ran}\n"
            f"\t@docker ps >> {ran} 2>&1 || true\n"
            "\t@echo 'SKIPPED [1] ../OspreyFlow_Build/tests/test_docker_thing.py:3: a server-only test: it calls the docker CLI (docker ps)'\n"
            "\t@echo 'FAILED ../OspreyFlow_Build/tests/test_x.py::test_y - boom'\n"),
        "OspreyFlow_Core/Makefile": (
            "check: lint trivy-image-x\n"
            f"lint:\n\t@echo core-lint >> {ran}\n"
            "trivy-image-x:\n\tdocker build -t ospreyflow/x:ci .\n"),
        "OspreyFlow_Core/pyproject.toml": "[project]\nname = 'x'\n",
        "OspreyFlow_Build/tests/test_docker_thing.py": "import subprocess\n\ndef test_a():\n    subprocess.run([\"docker\", \"ps\"])\n",
        "OspreyFlow_Build/tests/test_fixed.py": "import socket\n\ndef test_b():\n    socket.socket().bind((\"127.0.0.1\", 8123))\n",
        "OspreyFlow_Build/scripts/slice_line/demo_server/mac_only.tsv": "name\tsnapshots\tevidence\n",
        "OspreyFlow_Build/scripts/slice_line/demo_server/lists.tsv": (
            "kind\tname\tverdict\treason\tevidence\tnote\n"
            "ci\tcore-check\trun\tsplit\t\t\n"
            "ci\tgood-check\trun\t-\t\t\n"
            "ci\tdocker-check\tnot-run\tcontainer\tOspreyFlow_Build/Makefile:7\t\n"
            "ci\tclient-name-check\tnot-run\tclient-names\tOspreyFlow_Build/Makefile:9\t\n"
            "ci\tred-check\trun\t-\t\t\n"
            "core\tlint\trun\t-\t\t\n"
            "core\ttrivy-image-x\tnot-run\tcontainer\tOspreyFlow_Core/Makefile:5\t\n"
            "test\tOspreyFlow_Build/tests/test_docker_thing.py\trun\tcontainer-guarded\tx:4\t\n"
            "test\tOspreyFlow_Build/tests/test_fixed.py\tnot-run\tfixed-port\tOspreyFlow_Build/tests/test_fixed.py:4\t\n"),
    }
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    sh("git add -A && git commit -qm 'chore: a miniature candidate'", repo, w["env"])
    sh(["git", "switch", "-q", "lane/slice-S1"], repo, w["env"])
    (repo / "OspreyFlow_Build/tests").mkdir(parents=True, exist_ok=True)
    (repo / "OspreyFlow_Build/tests/test_unlisted.py").write_text(
        "import subprocess\n\ndef test_c():\n    subprocess.run([\"docker\", \"run\", \"x\"])\n")
    sh("git add -A && git commit -qm 'test: S1 adds a container test the list does not name'", repo, w["env"])
    tip = out(["git", "rev-parse", "HEAD"], repo)
    sh(["git", "switch", "-q", "main"], repo, w["env"])
    tools = w["remote"] / "data/tools"
    (tools / "uv").mkdir(parents=True)
    # the venv's python: its version, and DuckDB's extension step answered as the real one answers it (005)
    fake_py = tools / "fake_python"
    fake_py.write_text('#!/bin/sh\nif [ "$1" = -c ]; then echo "$HOME" >> %s.spatial; '
                       'echo \'{"version": "1.5.6", "platform": "linux_amd64", "sha256": "%s", "status": "installed"}\'; '
                       'else echo Python 3.12.9; fi\n' % (ran, "0" * 64))
    (tools / "uv/uv").write_text(f"#!/bin/sh\nmkdir -p .venv/bin\ncp {fake_py} .venv/bin/python\nchmod +x .venv/bin/python\n")
    node = tools / "node/v22/bin"
    node.mkdir(parents=True)
    (node / "node").write_text("#!/bin/sh\necho v22.23.5\n")
    (node / "npm").write_text("#!/bin/sh\nexit 0\n")
    for f in (tools / "uv/uv", node / "node", node / "npm"):
        f.chmod(0o755)
    return ran, tip


def bundle(w):
    f = w["tmp"] / "b.bundle"
    sh(["git", "bundle", "create", "-q", str(f), "refs/heads/main", "refs/heads/lane/slice-S1"], w["repo"], w["env"])
    return f.read_bytes()


def run_real_gate(w):
    p = runner(w, "run", bundle(w), harness={"gate": None})
    jid = json.loads(p.stdout.decode().splitlines()[-1])["id"]
    end = time.monotonic() + 60
    while time.monotonic() < end:
        a = json.loads(runner(w, "result " + jid).stdout.decode().splitlines()[-1])
        if a["state"] != "running":
            return a
        time.sleep(0.3)
    raise AssertionError("the job did not finish")


def test_the_real_gate_runs_only_what_the_list_allows_with_no_docker_reachable(world):
    w = world
    ran, tip = mini(w)
    a = run_real_gate(w)
    text = ran.read_text()
    assert a["state"] == "done" and a["tip"] == tip and a["lists_from"] == "the candidate's"
    assert "good-check" in text and "core-lint" in text  # the runnable parts ran
    assert "client-name-check" not in text  # never run, so never passed
    assert "docker-refused" in text and "docker-reached" not in text and "lease-switch-on" in text
    assert "refused: no container is started on the demo server" in text  # the runner's own docker, first on PATH
    assert "env docker_host= slot=13 arcade=59991 workers=6 uvpy=3.12 pytest_base=" in text  # no DOCKER_HOST (005)
    base = text.split("pytest_base=", 1)[1].split()[0]
    root = next(ln for ln in text.splitlines() if ln.startswith("root="))
    common, remotes = root.split()[0][5:], root.split()[1]
    assert common.endswith("/tree/.git") and remotes == "remotes=0"  # its own repository's root; no remote (005)
    assert not base.startswith(common[:-len("/.git")])  # the job's temp folders lie outside that root
    assert base.startswith(str(w["remote"] / "data/jobs")) and base.endswith("/pytest")  # its own, in the work folder
    addopts = next(ln for ln in text.splitlines() if ln.startswith("addopts="))
    assert addopts.split()[0] == "addopts=-rfEs" and "--ignore=../OspreyFlow_Build/tests/test_fixed.py" in addopts
    assert "--ignore=../OspreyFlow_Build/tests/test_unlisted.py" in addopts  # unlisted: never run
    assert a["verdict"] == "fail" and "red-check" in a["failing"]["targets"]
    assert "../OspreyFlow_Build/tests/test_x.py::test_y" in a["failing"]["tests"]
    by = a["failing"]["by_target"]  # each failing test under the target that failed after it (002, item 3)
    assert by["red-check"] == ["../OspreyFlow_Build/tests/test_r.py::test_q"]
    # the miniature's make test prints a failure but exits 0: named under its step, the fallback for that case
    assert by["(make test)"] == ["../OspreyFlow_Build/tests/test_x.py::test_y"]
    nr = {t["name"]: t["why"] for t in a["not_run"]["targets"]}
    assert nr["docker-check"] == "container" and nr["trivy-image-x"] == "container"
    assert nr["client-name-check"] == "client-names" and a["client_names"].startswith("not run")
    files = {t["name"]: t["why"] for t in a["not_run"]["test_files"]}
    assert files["OspreyFlow_Build/tests/test_fixed.py"] == "fixed-port"
    assert files["OspreyFlow_Build/tests/test_unlisted.py"].startswith("unlisted")
    assert a["not_run"]["docker_skipped"] == ["../OspreyFlow_Build/tests/test_docker_thing.py"]
    assert any("test_unlisted.py" in d and "neither list" in d for d in a["list_drift"])
    assert a["not_run"]["live_step"].startswith("not run")
    assert a["duckdb_spatial"]["status"] == "installed" and a["duckdb_spatial"]["sha256"] == "0" * 64
    spatial_home = (w["tmp"] / "ran.txt.spatial").read_text().strip()
    assert spatial_home.endswith("/home") and "/jobs/" in spatial_home  # into the job's own home, which the tests use


def test_the_real_gate_with_everything_green_is_a_pass(world):
    w = world
    ran, tip = mini(w)
    mk = w["repo"] / "OspreyFlow_Build/Makefile"
    sh(["git", "switch", "-q", "main"], w["repo"], w["env"])
    mk.write_text(mk.read_text().replace("red-check:\n\t@echo 'FAILED ../OspreyFlow_Build/tests/test_r.py::test_q - boom'\n\t@false\n", "red-check:\n\t@true\n")
                  .replace("\t@echo 'FAILED ../OspreyFlow_Build/tests/test_x.py::test_y - boom'\n", ""))
    sh("git commit -qam 'chore: green'", w["repo"], w["env"])
    a = run_real_gate(w)
    assert a["verdict"] == "pass" and a["failing"]["targets"] == [] and a["failing"]["tests"] == []
    assert not any(a["failing"].get("by_target", {}).values())
