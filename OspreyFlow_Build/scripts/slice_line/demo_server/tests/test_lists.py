"""The named lists against this repository (the owner's rulings 1 and 3), and each kind of drift shown red, planted in
the shapes the repository's own tests and Makefiles use."""
from __future__ import annotations

import sys

import pytest

from conftest import DEMO

sys.path.insert(0, str(DEMO))
import lists  # noqa: E402

REPO = DEMO.parents[3]


def test_the_lists_match_this_repository():
    assert lists.check(REPO) == []


def test_every_ci_target_that_starts_a_container_or_binds_a_fixed_port_is_not_run_here():
    rows = {(r["kind"], r["name"]): r for r in lists.read_tsv(lists.LISTS)}
    for name in ("opentofu-check", "chart-check", "cp-policy-check"):
        assert rows[("ci", name)]["verdict"] == "not-run"
    assert rows[("ci", "client-name-check")]["reason"] == "client-names"
    assert rows[("core", "harness-a11y")]["reason"] == "fixed-port"
    assert all(r["verdict"] == "not-run" for (k, n), r in rows.items() if n.startswith("trivy-image-"))


MAKE_BUILD = "ci: core-check good-check\ncore-check:\n\t$(MAKE) -C ../OspreyFlow_Core check\ngood-check:\n\techo ok\n"
MAKE_CORE = "check: lint\nlint:\n\techo ok\n"
LISTS = ("kind\tname\tverdict\treason\tevidence\tnote\n"
         "ci\tcore-check\trun\tsplit\t\t\nci\tgood-check\trun\t-\t\t\ncore\tlint\trun\t-\t\t\n")


@pytest.fixture
def tree(tmp_path):
    t = tmp_path / "tree"
    for rel, text in {"OspreyFlow_Build/Makefile": MAKE_BUILD, "OspreyFlow_Core/Makefile": MAKE_CORE,
                      "OspreyFlow_Build/tests/test_plain.py": "def test_a():\n    assert True\n",
                      "lists.tsv": LISTS, "mac_only.tsv": "name\tsnapshots\tevidence\n"}.items():
        (t / rel).parent.mkdir(parents=True, exist_ok=True)
        (t / rel).write_text(text)
    return t


def problems(t):
    return lists.check(t, t / "lists.tsv", t / "mac_only.tsv")


def plant(t, rel, text):
    (t / rel).parent.mkdir(parents=True, exist_ok=True)
    (t / rel).write_text(text)


def test_the_miniature_is_green(tree):
    assert problems(tree) == []


@pytest.mark.parametrize("rel,code", [
    ("OspreyFlow_Build/tests/test_new.py", 'subprocess.run(["docker", "compose", "-f", f, "up", "-d"])\n'),
    ("OspreyFlow_Build/tests/test_new.py", '_docker("run", "-d", "--name", stand_in, image)\n'.replace('_docker(', 'run(["docker", ')),
    ("OspreyFlow_Build/tests/test_new.py", "subprocess.check_call(f\"docker build -t x {d}\", shell=True)\n"),
    ("OspreyFlow_Build/tests/harness/helper.py", "from testcontainers.postgres import PostgresContainer\n"),
])
def test_a_new_test_that_starts_a_container_is_red_until_listed(tree, rel, code):
    plant(tree, rel, "import subprocess\n" + code)
    found = problems(tree)
    assert any(rel in p and "starts a container" in p and "neither list" in p for p in found), found
    with (tree / "lists.tsv").open("a") as fh:
        fh.write(f"test\t{rel}\trun\tcontainer-guarded\t{rel}:2\t\n")
    assert problems(tree) == []


@pytest.mark.parametrize("rel,code", [
    ("OspreyFlow_Build/tests/test_srv.py", 'server = ThreadingHTTPServer(("127.0.0.1", 8123), Handler)\n'),
    ("OspreyFlow_Build/tests/test_srv.py", 'server = await asyncio.start_server(answer, "127.0.0.1", 18123)\n'),
    ("OspreyFlow_Build/tests/test_srv.py", 'sock.bind(("127.0.0.1", 2480))\n'),
    ("OspreyFlow_Build/tests/test_srv.py", 'subprocess.Popen([py, "-m", "harness.webapp", "--port", "7217"])\n'),
    ("OspreyFlow_Core/apps/pages/test/server/x.test.ts", 'await new Promise((r) => fake.http.listen(5184, "127.0.0.1", r));\n'),
])
def test_a_new_test_that_binds_a_fixed_port_is_red_until_listed(tree, rel, code):
    plant(tree, rel, code)
    found = problems(tree)
    assert any(rel in p and "binds a fixed port" in p for p in found), found
    with (tree / "lists.tsv").open("a") as fh:
        fh.write(f"test\t{rel}\tnot-run\tfixed-port\t{rel}:1\t\n")
    assert problems(tree) == []


def test_port_zero_is_not_a_fixed_port(tree):
    plant(tree, "OspreyFlow_Build/tests/test_zero.py", 'server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)\n'
          'sock.bind(("127.0.0.1", 0))\nawait asyncio.start_server(answer, "127.0.0.1", 0)\n')
    assert problems(tree) == []


def test_a_fixed_port_test_listed_run_needs_a_note_saying_why(tree):
    plant(tree, "OspreyFlow_Build/tests/test_srv.py", 'sock.bind(("127.0.0.1", 8123))\n')
    with (tree / "lists.tsv").open("a") as fh:
        fh.write("test\tOspreyFlow_Build/tests/test_srv.py\trun\tfixed-port\tx:1\t\n")
    assert any("listed run with no note" in p for p in problems(tree))


def test_a_new_ci_target_is_red_until_listed_and_a_container_one_cannot_be_listed_run_bare(tree):
    mk = tree / "OspreyFlow_Build/Makefile"
    mk.write_text(mk.read_text().replace("ci: core-check good-check", "ci: core-check good-check image-check")
                  + "image-check:\n\tdocker run --rm alpine/helm:3.16.3 lint /chart\n")
    assert any("image-check" in p and "neither list" in p for p in problems(tree))
    with (tree / "lists.tsv").open("a") as fh:
        fh.write("ci\timage-check\trun\t-\t\t\n")
    assert any("image-check is listed run but container" in p for p in problems(tree))


def test_a_container_reached_through_a_make_variable_or_a_tool_is_found(tree):
    mk = tree / "OspreyFlow_Build/Makefile"
    mk.write_text("HELM := docker run --rm alpine/helm:3.16.3\n" + mk.read_text()
                  .replace("ci: core-check good-check", "ci: core-check good-check chart-check tool-check")
                  + "chart-check:\n\t$(HELM) lint /chart\ntool-check:\n\t$(PY) -m tools.helm_chart\n")
    plant(tree, "OspreyFlow_Build/tools/helm_chart.py", 'command = ["docker", "run", "--rm", "-i", HELM]\n')
    found = {k: w for k, w in ((t["name"], t["found"]) for t in lists.derive_targets(tree))}
    assert found["chart-check"] and found["tool-check"][0][1] == "OspreyFlow_Build/tools/helm_chart.py:1"


def test_a_stale_row_is_red(tree):
    with (tree / "lists.tsv").open("a") as fh:
        fh.write("test\tOspreyFlow_Build/tests/test_gone.py\tnot-run\tcontainer\tx:1\t\nci\tgone-check\trun\t-\t\t\n")
    found = problems(tree)
    assert any("test_gone.py" in p and "stale" in p for p in found) and any("gone-check" in p and "stale" in p for p in found)


def test_a_pending_row_may_name_a_file_the_tree_does_not_have_yet(tree):
    """004: PL11's rows are written before PL11 merges. A row noted `pending: <slice>` for an absent file is not stale;
    without the note it is."""
    with (tree / "lists.tsv").open("a") as fh:
        fh.write("test\tOspreyFlow_Build/tests/test_later.py\trun\tcontainer-guarded\tx:1\tpending: XX9. later\n")
    assert problems(tree) == []
    (tree / "lists.tsv").write_text((tree / "lists.tsv").read_text().replace("pending: XX9. later", "later"))
    assert any("test_later.py" in p and "stale" in p for p in problems(tree))


def test_a_pending_row_is_checked_as_any_other_once_its_file_is_there(tree):
    with (tree / "lists.tsv").open("a") as fh:
        fh.write("test\tOspreyFlow_Build/tests/test_later.py\trun\tcontainer-guarded\tx:1\tpending: XX9. later\n")
    plant(tree, "OspreyFlow_Build/tests/test_later.py", "def test_a():\n    assert True\n")  # there, and no candidate
    assert any("test_later.py" in p and "stale" in p for p in problems(tree))
    plant(tree, "OspreyFlow_Build/tests/test_later.py", 'import subprocess\nsubprocess.run(["docker", "run", "x"])\n')
    assert problems(tree) == []  # there, a candidate, and its row stands


def test_the_pl11_rows_stand_on_a_tree_that_has_pl11s_files(tree):
    """The two rows written for PL11 (004), on a tree holding the two files as PL11 has them (their docker words, at
    the lines the rows name): no drift, and both run under the docker guard."""
    rows = [r for r in lists.read_tsv(lists.LISTS) if "licence_check/test_register_" in r["name"]]
    assert [r["verdict"] + " " + r["reason"] for r in rows] == ["run container-guarded"] * 2
    with (tree / "lists.tsv").open("a") as fh:
        for r in rows:
            fh.write("\t".join([r["kind"], r["name"], r["verdict"], r["reason"], r["evidence"], r["note"]]) + "\n")
    assert problems(tree) == []  # absent here: pending
    for r in rows:
        plant(tree, r["name"], '"""An image a `docker run` call names."""\nPLANTED = \'["docker", "run", "--rm", "x"]\'\n')
    assert problems(tree) == []  # present: candidates, as the detector reads them, and listed


def test_a_snapshot_for_macos_only_is_red_until_listed_and_one_with_linux_is_not(tree):
    snaps = tree / "OspreyFlow_Core/apps/workspace/map-verify/contrast.spec.ts-snapshots"
    plant(tree, "OspreyFlow_Core/apps/workspace/map-verify/contrast.spec.ts", "test('x', () => {});\n")
    plant(tree, str((snaps / "map-contrast-dark-darwin.png").relative_to(tree)), "png")
    found = problems(tree)
    assert any("contrast.spec.ts" in p and "only for another platform" in p for p in found), found
    with (tree / "mac_only.tsv").open("a") as fh:
        fh.write("OspreyFlow_Core/apps/workspace/map-verify/contrast.spec.ts\t1\tmap-contrast-dark-darwin.png\n")
    assert problems(tree) == []
    plant(tree, str((snaps / "map-contrast-dark-linux.png").relative_to(tree)), "png")
    assert any("no longer platform-only" in p for p in problems(tree))


def test_the_runner_leaves_out_every_unlisted_candidate(tree):
    plant(tree, "OspreyFlow_Build/tests/test_new.py", 'run(["docker", "run", "x"])\n')
    listed, unlisted = lists.not_run_tests(tree, tree / "lists.tsv")
    assert unlisted == ["OspreyFlow_Build/tests/test_new.py"]
