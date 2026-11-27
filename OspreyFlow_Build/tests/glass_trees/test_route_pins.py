"""A page added to the GOV.UK tree changes no other page's test (the owner's word of 27 November 2026: page parts kept
conflicting in the same shared files; "counts like 'seven pages' are not" union-safe).

Each page's own scenario test checks its own path: in the tree's route list, once. Whether the list and the pages that
name the GOV.UK tree agree is checked in one place, `apps/pages/test/govuk/help.test.ts` (HP9, `routeListProblems`),
from the files themselves. So no test pins the whole list, no test or shared list says how many pages there are, and
`scripts/build.mjs` names no page's file.
"""

from __future__ import annotations

import copy
import importlib
import re
from pathlib import Path

import pytest
import yaml
from tools.layout import ROOT

CORE = ROOT / "OspreyFlow_Core"
BUILD = ROOT / "OspreyFlow_Build"
PAGES = CORE / "apps" / "pages"
ROUTES = PAGES / "tree-govuk" / "routes.yaml"
EIGHTH = "/an-eighth-page"

SCENARIO_TESTS = [
    "test_govuk_help_scenario",
    "test_govuk_admin_people_scenario",
    "test_govuk_alert_monitoring_scenario",
    "test_govuk_pack_trends_scenario",
    "test_govuk_cases_scenario",
    "test_govuk_boards_scenario",
    "test_govuk_alert_queue_scenario",
]

#: The page's own path, where its test has no `PATH` (or `ROUTE`) of its own.
OWN_PATH = {"test_govuk_help_scenario": "/help"}

#: The files every page used to edit, beyond its own: the shared lists, and the tests that pinned them.
SHARED = [
    PAGES / "server" / "pageList.ts",
    ROUTES,
    PAGES / "scripts" / "build.mjs",
    PAGES / "test" / "govuk" / "help.test.ts",
    PAGES / "test" / "govuk" / "admin-people.test.ts",
    BUILD / "tests" / "glass_trees" / "test_tree_parity.py",
    BUILD / "tests" / "harness" / "test_pages_setting.py",
]

COUNT = re.compile(r"\b(?:three|four|five|six|seven|eight|nine|ten|eleven|twelve) (?:pages|routes)\b"
                   r"|\b(?:third|fourth|fifth|sixth|seventh|eighth|ninth|tenth) page\b"
                   r"|\bthe (?:third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b", re.I)


def routes() -> list[str]:
    return yaml.safe_load(ROUTES.read_text(encoding="utf-8"))["routes"]


def scenario(name: str):
    return importlib.import_module(f"tests.glass_trees.{name}")


@pytest.mark.parametrize("name", SCENARIO_TESTS)
def test_an_eighth_page_in_the_route_list_leaves_each_page_s_own_route_check_green(name: str) -> None:
    m = scenario(name)
    data = copy.deepcopy(m.inputs())
    assert m.route_problems(data) == []
    data["routes"] = [*data["routes"], EIGHTH]
    assert m.route_problems(data) == [], "a page's test pins the whole route list: a new page would have to edit it"


@pytest.mark.parametrize("name", SCENARIO_TESTS)
def test_each_page_s_route_check_is_still_red_when_its_own_path_is_left_out_or_listed_twice(name: str) -> None:
    m = scenario(name)
    data = copy.deepcopy(m.inputs())
    path = getattr(m, "PATH", None) or getattr(m, "ROUTE", None) or OWN_PATH[name]
    assert path in data["routes"], (name, path)
    left_out = {**data, "routes": [p for p in data["routes"] if p != path]}
    assert m.route_problems(left_out), "a page's own path left out of the list is not caught"
    twice = {**data, "routes": [*data["routes"], path]}
    assert m.route_problems(twice), "a page's own path listed twice is not caught"


def _named_routes(text: str, listed: list[str]) -> set[str]:
    return {p for p in listed if re.search(r"[\"'`]" + re.escape(p) + r"[\"'`]", text)}


def test_no_test_names_every_route_of_the_list() -> None:
    """A file that names every route pins the list (HP9 reads the list from the file instead)."""
    listed = routes()
    files = [*sorted((PAGES / "test").rglob("*.ts")), *sorted((BUILD / "tests").rglob("test_*.py"))]
    pinned = [str(f.relative_to(ROOT)) for f in files
              if f.name != Path(__file__).name and _named_routes(f.read_text(encoding="utf-8"), listed) == set(listed)]
    assert pinned == []


def test_no_shared_file_counts_the_tree_s_pages_or_names_its_place_in_order() -> None:
    found = []
    for f in SHARED:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if COUNT.search(line):
                found.append(f"{f.relative_to(ROOT)}:{n}: {COUNT.search(line).group(0)!r}")
    assert found == []


def _shared_package_files() -> list[str]:
    """The server files that import the shared package, roughly (the test of the build's finder holds the exact rule):
    their names, as a test that pinned them would write them."""
    pattern = re.compile(r"""\bfrom\s*["']@ospreyflow/glass-shared["']""")
    return sorted(f.stem for f in (PAGES / "server").rglob("*.ts")
                  if not f.name.endswith(".d.ts") and pattern.search(f.read_text(encoding="utf-8")))


def test_no_test_names_every_server_file_that_imports_the_shared_package() -> None:
    """A test that names each such file pins the list, and every new page's words file would edit it (the owner's 66b,
    27 November 2026: `shared-entries.test.ts` named the four words files)."""
    names = _shared_package_files()
    assert len(names) > 1, names
    files = [*sorted((PAGES / "test").rglob("*.ts")), *sorted((BUILD / "tests").rglob("test_*.py"))]
    pinned = [str(f.relative_to(ROOT)) for f in files
              if f.name != Path(__file__).name and all(re.search(rf"\b{re.escape(n)}\b", f.read_text(encoding="utf-8")) for n in names)]
    assert pinned == []


def test_build_mjs_names_no_server_file_of_a_page() -> None:
    """It bundles the server files that import the shared package, found by reading them, not from a list."""
    text = (PAGES / "scripts" / "build.mjs").read_text(encoding="utf-8")
    named = re.findall(r'"[\w./-]+\.ts"', text)
    assert named == [], named
