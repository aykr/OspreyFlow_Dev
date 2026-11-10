"""`tools/live_select.py`, the live tests a change can reach (admin's T1 part 3, 10 November 2026).

Red if the selection can come out empty, if a path no rule covers (or a removed or renamed file) selects anything less
than the full set, or if an import a test's run makes is missed: inside a function, through a conftest or the test's
own package, relative, or a module named in a string or an f-string. The synthetic repositories are laid out as this
one is (`OspreyFlow_Core` with `packages`, `OspreyFlow_Build` with `tests` and a Makefile whose `test` target ignores
the live files); the last cases run on this repository itself, for the brief's own examples.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import live_select

ROUTE_RIGHTS = "tests/services/api/test_route_rights.py"


def _repo(tmp_path: Path, files: dict[str, str], live: list[str], rules: str) -> live_select.Repo:
    for rel, text in {f"OspreyFlow_Build/{ROUTE_RIGHTS}": "def test_x(): pass\n", **files}.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    ignores = " ".join(f"--ignore=../OspreyFlow_Build/{t}" for t in [ROUTE_RIGHTS, *live])
    (tmp_path / "OspreyFlow_Build" / "Makefile").write_text(
        f"test:\n\t$(IN_CORE) $(PYTEST) {ignores} ../OspreyFlow_Build/tests\n\n"
    )
    (tmp_path / "OspreyFlow_Build" / "tools").mkdir(parents=True, exist_ok=True)
    (tmp_path / "OspreyFlow_Build" / "tools" / "live_map.tsv").write_text(rules)
    return live_select.Repo(tmp_path)


@pytest.fixture
def repo(tmp_path: Path):  # type: ignore[no-untyped-def]
    def make(files: dict[str, str], live: list[str], rules: str = "") -> live_select.Repo:
        return _repo(tmp_path, files, live, rules)

    return make


_ADAPTER = {
    "OspreyFlow_Core/packages/adapters/__init__.py": "",
    "OspreyFlow_Core/packages/adapters/graph.py": "def g(): pass\n",
    "OspreyFlow_Core/packages/adapters/other.py": "def o(): pass\n",
    "OspreyFlow_Build/tests/conformance/graph_port/test_suite.py": "from adapters.graph import g\n",
    "OspreyFlow_Build/tests/services/api/test_other_store.py": "from adapters.other import o\n",
}
_LIVE = ["tests/conformance/graph_port", "tests/services/api/test_other_store.py"]


def test_a_change_to_the_graph_adapter_selects_what_imports_it_and_route_rights(repo) -> None:  # type: ignore[no-untyped-def]
    picked = live_select.select(["OspreyFlow_Core/packages/adapters/graph.py"], repo(_ADAPTER, _LIVE))
    assert picked == sorted([ROUTE_RIGHTS, "tests/conformance/graph_port/test_suite.py"])


def test_an_empty_change_still_selects_route_rights(repo) -> None:  # type: ignore[no-untyped-def]
    assert live_select.select([], repo(_ADAPTER, _LIVE)) == [ROUTE_RIGHTS]


def test_a_path_no_rule_covers_selects_the_full_set(repo) -> None:  # type: ignore[no-untyped-def]
    r = repo(_ADAPTER, _LIVE)
    why: list[str] = []
    picked = live_select.select(["OspreyFlow_Core/recipes/new_recipe.yaml"], r, why=why)
    assert picked == r.live_set() and len(picked) == 3
    assert "no rule covers it" in why[0]


def test_a_removed_python_file_selects_the_full_set(repo) -> None:  # type: ignore[no-untyped-def]
    r = repo(_ADAPTER, _LIVE)
    assert live_select.select(["OspreyFlow_Core/packages/adapters/gone.py"], r) == r.live_set()


def test_a_rename_is_its_old_path_and_its_new_one_so_the_old_selects_the_full_set(tmp_path: Path) -> None:
    """At the real call site: `changed_paths` on a real repository whose branch renames a module."""
    r = _repo(tmp_path, _ADAPTER, _LIVE, "")
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "base"], check=True)
    subprocess.run([*git, "switch", "-q", "-c", "lane"], check=True)
    subprocess.run([*git, "mv", "OspreyFlow_Core/packages/adapters/other.py", "OspreyFlow_Core/packages/adapters/renamed.py"], check=True)
    subprocess.run([*git, "commit", "-qm", "rename"], check=True)
    changed = live_select.changed_paths(r, "main")
    assert "OspreyFlow_Core/packages/adapters/other.py" in changed, changed
    assert live_select.select(changed, r) == r.live_set()


def test_main_prints_the_selection_for_the_branch_s_change(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    r = _repo(tmp_path, _ADAPTER, _LIVE, "")
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "base"], check=True)
    (tmp_path / "OspreyFlow_Core/packages/adapters/graph.py").write_text("def g(): return 1\n")
    assert live_select.main(["--why"], repo=r) == 0
    out, err = capsys.readouterr()
    assert out.split() == sorted([ROUTE_RIGHTS, "tests/conformance/graph_port/test_suite.py"])
    assert "2 of 3 live test files" in err


def test_a_rule_names_none_all_or_tests(repo) -> None:  # type: ignore[no-untyped-def]
    rules = ("**/*.md\tnone\tdocuments\nOspreyFlow_Core/osprey.yaml\tall\tconfiguration\n"
             "OspreyFlow_Core/recipes/**\ttests/conformance/graph_port\trecipes\n")  # fmt: skip
    r = repo(_ADAPTER, _LIVE, rules)
    assert live_select.select(["OspreyFlow_Build/process/x.md"], r) == [ROUTE_RIGHTS]
    assert live_select.select(["OspreyFlow_Core/osprey.yaml"], r) == r.live_set()
    assert live_select.select(["OspreyFlow_Core/recipes/a.yaml"], r) == sorted(
        [ROUTE_RIGHTS, "tests/conformance/graph_port/test_suite.py"]
    )


def test_an_adding_rule_adds_to_what_imports_reach(repo) -> None:  # type: ignore[no-untyped-def]
    """A live test that reads other Python as text: imports cannot see it, so its rule adds rather than decides."""
    files = {**_ADAPTER, "OspreyFlow_Build/tests/scenarios/test_reads_text.py": "def test_x(): pass\n"}
    rules = "OspreyFlow_Core/packages/adapters/**/*.py\t+tests/scenarios/test_reads_text.py\treads them as text\n"
    r = repo(files, [*_LIVE, "tests/scenarios/test_reads_text.py"], rules)
    picked = live_select.select(["OspreyFlow_Core/packages/adapters/graph.py"], r)
    assert picked == sorted(
        [ROUTE_RIGHTS, "tests/conformance/graph_port/test_suite.py", "tests/scenarios/test_reads_text.py"]
    )


def test_a_rule_naming_no_live_file_is_refused(repo) -> None:  # type: ignore[no-untyped-def]
    r = repo(_ADAPTER, _LIVE, "OspreyFlow_Core/recipes/**\ttests/ingests\ta typo\n")
    with pytest.raises(SystemExit, match="names no live test file"):
        live_select.select(["OspreyFlow_Core/recipes/a.yaml"], r)


def test_imports_inside_functions_strings_and_f_strings_are_followed(repo) -> None:  # type: ignore[no-untyped-def]
    files = {
        **_ADAPTER,
        "OspreyFlow_Core/services/__init__.py": "",
        "OspreyFlow_Core/services/worker.py": "HANDLERS = {'x': 'services.jobs:run'}\n",
        "OspreyFlow_Core/services/jobs.py": "def run():\n    from adapters.other import o\n",
        "OspreyFlow_Core/services/checks/__init__.py": "",
        "OspreyFlow_Core/services/checks/one.py": "import adapters.graph\n",
        "OspreyFlow_Build/tests/test_worker_live.py": "import services.worker\n",
        "OspreyFlow_Build/tests/test_checks_live.py": (
            "from importlib import import_module\n"
            "def test_x(name='one'):\n    import_module(f'services.checks.{name}')\n"
        ),
    }
    r = repo(files, [*_LIVE, "tests/test_worker_live.py", "tests/test_checks_live.py"])
    other = live_select.select(["OspreyFlow_Core/packages/adapters/other.py"], r)
    assert "tests/test_worker_live.py" in other and "tests/services/api/test_other_store.py" in other
    graph = live_select.select(["OspreyFlow_Core/packages/adapters/graph.py"], r)
    assert "tests/test_checks_live.py" in graph


def test_a_relative_import_is_followed(repo) -> None:  # type: ignore[no-untyped-def]
    files = {
        **_ADAPTER,
        "OspreyFlow_Build/tests/__init__.py": "",
        "OspreyFlow_Build/tests/scenarios/__init__.py": "",
        "OspreyFlow_Build/tests/scenarios/support.py": "from adapters.graph import g\n",
        "OspreyFlow_Build/tests/scenarios/test_uses_support.py": "from .support import g\n",
    }
    r = repo(files, [*_LIVE, "tests/scenarios/test_uses_support.py"])
    picked = live_select.select(["OspreyFlow_Core/packages/adapters/graph.py"], r)
    assert "tests/scenarios/test_uses_support.py" in picked


def test_a_conftest_and_the_test_s_own_package_count_for_every_test_beneath_them(repo) -> None:  # type: ignore[no-untyped-def]
    files = {
        **_ADAPTER,
        "OspreyFlow_Build/tests/services/conftest.py": "from adapters.graph import g\n",
        "OspreyFlow_Build/tests/__init__.py": "",
        "OspreyFlow_Build/tests/conformance/__init__.py": "import adapters.other\n",
    }
    r = repo(files, _LIVE)
    assert "tests/services/api/test_other_store.py" in live_select.select(
        ["OspreyFlow_Core/packages/adapters/graph.py"], r
    )
    assert "tests/conformance/graph_port/test_suite.py" in live_select.select(
        ["OspreyFlow_Core/packages/adapters/other.py"], r
    )


# --- this repository: the brief's own examples, and the committed map ---------------------------------------


@pytest.fixture(scope="module")
def here() -> live_select.Repo:
    return live_select.Repo()


def test_the_live_set_is_the_makefile_s_list_and_holds_route_rights(here: live_select.Repo) -> None:
    live = here.live_set()
    assert ROUTE_RIGHTS in live and "tests/conformance/graph_port/test_suite.py" in live
    assert len(live) > 200


def test_every_rule_in_the_committed_map_names_live_files(here: live_select.Repo) -> None:
    assert here.rules  # loading them refuses a rule whose tests match no live file


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        ("OspreyFlow_Core/packages/adapters/graph_arcadedb/adapter.py", ["tests/conformance/graph_port/test_suite.py"]),
        ("OspreyFlow_Core/services/api/scheduler.py",
         ["tests/services/api/test_schedule_executor.py", "tests/services/api/test_scheduler_lifespan.py"]),
        ("OspreyFlow_Core/services/api/recipe_run.py", ["tests/services/api/test_recipe_run_ledger.py"]),
        ("OspreyFlow_Core/services/api/scheduler.py", ["tests/scenarios/test_phase7_stage6c_watch_routes.py"]),
    ],
)  # fmt: skip
def test_the_brief_s_examples_on_this_repository(here: live_select.Repo, changed: str, expected: list[str]) -> None:
    picked = live_select.select([changed], here)
    assert ROUTE_RIGHTS in picked
    for t in expected:
        assert t in picked, (changed, t)
