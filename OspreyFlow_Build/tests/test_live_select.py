"""`scripts/live_select.py`, the live tests a change can reach (admin's T1 part 3, 10 November 2026).

Red if the selection can come out empty, if a path no rule covers selects anything less than the full set, or if
an import the test's run would make (inside a function, or a module named in a string, as the worker's registry
and the harness's sub-commands load them) is missed. The synthetic repositories below are laid out as this one is:
`OspreyFlow_Core` (with `packages`) and `OspreyFlow_Build` (with `tests` and a Makefile whose `test` target ignores
the live files).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import live_select

ROUTE_RIGHTS = "tests/services/api/test_route_rights.py"


def _repo(tmp_path: Path, files: dict[str, str], live: list[str], rules: str = "") -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    ignores = " ".join(f"--ignore=../OspreyFlow_Build/{t}" for t in [ROUTE_RIGHTS, *live])
    (tmp_path / "OspreyFlow_Build" / "Makefile").write_text(f"test:\n\t$(PYTEST) {ignores} ../OspreyFlow_Build/tests\n\n")
    (tmp_path / "OspreyFlow_Build" / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "OspreyFlow_Build" / "scripts" / "live_map.tsv").write_text(rules)
    return tmp_path


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def make(files: dict[str, str], live: list[str], rules: str = "") -> live_select.Repo:
        root = _repo(tmp_path, {f"OspreyFlow_Build/{ROUTE_RIGHTS}": "def test_x(): pass\n", **files}, live, rules)
        return live_select.Repo(root)

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
    r = repo(_ADAPTER, _LIVE)
    picked = live_select.select(["OspreyFlow_Core/packages/adapters/graph.py"], r)
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


def test_a_rule_names_none_all_or_tests(repo) -> None:  # type: ignore[no-untyped-def]
    rules = "**/*.md\tnone\tdocuments\nOspreyFlow_Core/osprey.yaml\tall\tconfiguration\n" \
            "OspreyFlow_Core/recipes/**\ttests/conformance/graph_port\trecipes\n"
    r = repo(_ADAPTER, _LIVE, rules)
    assert live_select.select(["OspreyFlow_Build/process/x.md"], r) == [ROUTE_RIGHTS]
    assert live_select.select(["OspreyFlow_Core/osprey.yaml"], r) == r.live_set()
    assert live_select.select(["OspreyFlow_Core/recipes/a.yaml"], r) == sorted(
        [ROUTE_RIGHTS, "tests/conformance/graph_port/test_suite.py"]
    )


def test_an_import_inside_a_function_and_a_module_named_in_a_string_are_followed(repo) -> None:  # type: ignore[no-untyped-def]
    files = {
        **_ADAPTER,
        "OspreyFlow_Core/services/__init__.py": "",
        "OspreyFlow_Core/services/worker.py": "HANDLERS = {'x': 'services.jobs:run'}\n",
        "OspreyFlow_Core/services/jobs.py": "def run():\n    from adapters.other import o\n",
        "OspreyFlow_Build/tests/test_worker_live.py": "import services.worker\n",
    }
    r = repo(files, [*_LIVE, "tests/test_worker_live.py"])
    picked = live_select.select(["OspreyFlow_Core/packages/adapters/other.py"], r)
    assert "tests/test_worker_live.py" in picked and "tests/services/api/test_other_store.py" in picked


def test_a_conftest_s_imports_count_for_every_test_beneath_it(repo) -> None:  # type: ignore[no-untyped-def]
    files = {**_ADAPTER, "OspreyFlow_Build/tests/services/conftest.py": "from adapters.graph import g\n"}
    r = repo(files, _LIVE)
    picked = live_select.select(["OspreyFlow_Core/packages/adapters/graph.py"], r)
    assert "tests/services/api/test_other_store.py" in picked


def test_the_live_set_is_this_repository_s_makefile_list_and_holds_route_rights() -> None:
    live = live_select.Repo().live_set()
    assert ROUTE_RIGHTS in live and "tests/conformance/graph_port/test_suite.py" in live
    assert len(live) > 200
