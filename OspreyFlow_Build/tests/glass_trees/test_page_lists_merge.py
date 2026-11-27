"""Two pages built side by side merge without a conflict in the two lists every page adds a line to (the owner's word of
27 November 2026: page parts kept conflicting in the same shared files, which broke trains and cost rounds).

A GOV.UK page adds one line to each of two lists, and to no other shared file:
- `apps/pages/tree-govuk/routes.yaml`: its path, one to a line;
- `apps/pages/server/pageList.ts`: its import, one to a line, and its module, one to a line in `PAGES`.

Both take git's union merge (`.gitattributes`), so two branches that each add a page keep both lines. Union is safe only
where every change is a line added. It is not safe where a line is edited in place, because two branches that edit the
same line keep BOTH versions. So the lists hold nothing a page edits in place: no count of pages, no sentence naming
each page, and `PAGES` one module to a line. What union could still let through is caught here, on the real files, at
every gate:
- the route list is `routes:` and one path to a line, each listed once;
- the page list imports each module once, lists each imported page once in `PAGES` and lists nothing it did not
  import, and no line of it appears twice.
`test/govuk/help.test.ts` (HP9) holds the route list and the pages that name the GOV.UK tree in step, and the type
check (`make ci`) holds the page list to TypeScript.

Not union, and why:
- `spec/08_ACCEPTANCE_SCENARIOS.md`: two parts of the same page edit the same paragraphs in place (GR1b and GR1e both
  edit Scenario CS), so union would keep both versions of a paragraph, silently.
- `apps/pages/scripts/build.mjs`: it no longer has a list; it bundles the server files that import the shared package.
- the tests: no test pins the whole route list or counts the pages (`test_route_pins.py`).

Every case runs git in a temporary directory, never in the real repository, on copies of the real files and the real
`.gitattributes`, committed on the base before the branches part (the attributes come from the tree being merged).
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from tools.layout import ROOT

ROUTES = "OspreyFlow_Core/apps/pages/tree-govuk/routes.yaml"
PAGE_LIST = "OspreyFlow_Core/apps/pages/server/pageList.ts"
LEDGER = "OspreyFlow_Build/spec/ADR_RESERVATIONS.md"
UNION = [LEDGER, ROUTES, PAGE_LIST]
NOT_UNION = [
    "OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md",
    "OspreyFlow_Core/apps/pages/scripts/build.mjs",
    "OspreyFlow_Core/apps/pages/FUNCTIONS.yaml",
    "OspreyFlow_Core/apps/pages/test/govuk/help.test.ts",
]

IMPORT = re.compile(r'^import \{ ([A-Za-z0-9_, ]+) \} from "(\./[A-Za-z0-9_/]+\.js)";$')
PAGES_OPEN = "export const PAGES: readonly PageModule[] = ["


# --- the checks ---------------------------------------------------------------------------------------------------


def route_list_problems(text: str) -> list[str]:
    """`routes:` and one path to a line, each listed once (what union could leave: a path twice, a line broken)."""
    found: list[str] = []
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines or lines[0] != "routes:":
        return ["the route list does not start `routes:`"]
    paths = []
    for line in lines[1:]:
        m = re.fullmatch(r"  - (/[^\s\"']*)", line)
        if not m:
            found.append(f"not one path to a line: {line!r}")
        else:
            paths.append(m.group(1))
    try:
        if yaml.safe_load(text) != {"routes": paths}:
            found.append("the route list does not read as `routes:` and its paths")
    except yaml.YAMLError as e:
        found.append(f"the route list is not YAML: {e}")
    for path in sorted({p for p in paths if paths.count(p) > 1}):
        found.append(f"{path} is listed {paths.count(path)} times")
    return found


def page_list_problems(text: str) -> list[str]:
    """Each module imported once, each imported page listed once in `PAGES` one to a line, nothing else listed, and
    no line of the file twice (what union could leave)."""
    found: list[str] = []
    lines = text.splitlines()
    seen: dict[str, int] = {}
    for line in lines:
        if line.strip() not in ("", "*", "/**", "*/", "];"):
            seen[line] = seen.get(line, 0) + 1
    found += [f"a line is there {n} times: {line.strip()!r}" for line, n in seen.items() if n > 1]
    imported: list[str] = []
    sources: list[str] = []
    for line in lines:
        if line.startswith("import ") and not line.startswith("import type "):
            m = IMPORT.match(line)
            if not m:
                found.append(f"not one import to a line: {line!r}")
                continue
            imported += [n.strip() for n in m.group(1).split(",")]
            sources.append(m.group(2))
    found += [f"{s} is imported {sources.count(s)} times" for s in sorted(set(sources)) if sources.count(s) > 1]
    if lines.count(PAGES_OPEN) != 1:
        return [*found, "the page list has no `PAGES` opened on a line of its own"]
    start = lines.index(PAGES_OPEN) + 1
    end = lines.index("];", start) if "];" in lines[start:] else len(lines)
    listed = []
    for line in lines[start:end]:
        m = re.fullmatch(r"  ([A-Za-z0-9_]+),", line)
        if not m:
            found.append(f"not one page to a line in PAGES: {line!r}")
        else:
            listed.append(m.group(1))
    # A page listed twice is a line there twice, said above.
    found += [f"{n} is in PAGES and not imported" for n in listed if n not in imported]
    found += [f"{n} is imported and not in PAGES" for n in imported if n not in listed]
    return found


# --- git, in a temporary directory --------------------------------------------------------------------------------


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="Test",
               GIT_AUTHOR_EMAIL="test@example.invalid", GIT_COMMITTER_NAME="Test",
               GIT_COMMITTER_EMAIL="test@example.invalid")
    return subprocess.run(["git", *args], cwd=cwd, env=env, text=True, capture_output=True, check=check)


def _real(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


def _write(repo: Path, rel: str, text: str) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text, encoding="utf-8")


def _new_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, ".gitattributes", _real(".gitattributes"))
    for rel in (ROUTES, PAGE_LIST):
        _write(repo, rel, _real(rel))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _branch(repo: Path, name: str, **edits: Callable[[str], str]) -> None:
    _git(repo, "checkout", "-q", "-b", name, "main")
    for rel, edit in ((ROUTES, edits.get("routes")), (PAGE_LIST, edits.get("pages"))):
        if edit:
            _write(repo, rel, edit(_read(repo, rel)))
    _git(repo, "commit", "-q", "-am", name)
    _git(repo, "checkout", "-q", "main")


def _merge(repo: Path, branch: str) -> tuple[bool, list[str]]:
    done = _git(repo, "merge", "--no-ff", "--no-edit", branch, check=False)
    return done.returncode == 0, _git(repo, "diff", "--name-only", "--diff-filter=U").stdout.split()


def add_route(path: str) -> Callable[[str], str]:
    """What a page does to the route list: its path on a line of its own, at the end."""
    return lambda text: text.rstrip("\n") + f"\n  - {path}\n"


def add_page(name: str, module: str) -> Callable[[str], str]:
    """What a page does to the page list: its import after the last import, and its module at the end of `PAGES` (on
    a line of its own where `PAGES` is one to a line, at the end of the one line where it is not)."""

    def edit(text: str) -> str:
        lines = text.splitlines()
        last = max(i for i, line in enumerate(lines) if line.startswith("import "))
        lines.insert(last + 1, f'import {{ {name} }} from "./{module}.js";')
        if PAGES_OPEN in lines:
            end = lines.index("];", lines.index(PAGES_OPEN))
            lines.insert(end, f"  {name},")
        else:
            i = next(i for i, line in enumerate(lines) if line.startswith(PAGES_OPEN))
            lines[i] = lines[i].replace("];", f", {name}];")
        return "\n".join(lines) + "\n"

    return edit


# --- the attributes -----------------------------------------------------------------------------------------------


def test_gitattributes_lists_the_two_page_lists_beside_the_reservations_table_and_says_why_the_rest_are_not() -> None:
    text = _real(".gitattributes")
    entries = [line.split() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    assert entries == [[rel, "merge=union"] for rel in UNION], entries
    comment = " ".join(line for line in text.splitlines() if line.startswith("#"))
    for rel in NOT_UNION:
        assert Path(rel).name in comment, f"the comment must say why {rel} is not listed"


# --- the real files -------------------------------------------------------------------------------------------------


def test_the_real_route_list_passes_its_check() -> None:
    assert route_list_problems(_real(ROUTES)) == []


def test_the_real_page_list_passes_its_check() -> None:
    assert page_list_problems(_real(PAGE_LIST)) == []


# --- two pages side by side ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("order", [("a", "b"), ("b", "a")], ids=["a-first", "b-first"])
def test_two_pages_added_side_by_side_merge_clean_in_either_order_and_keep_both(tmp_path: Path, order) -> None:
    repo = _new_repo(tmp_path)
    _branch(repo, "a", routes=add_route("/page-a"), pages=add_page("pageA", "pageA"))
    _branch(repo, "b", routes=add_route("/page-b"), pages=add_page("pageB", "pageB"))
    for branch in order:
        clean, conflicted = _merge(repo, branch)
        assert clean, f"merging {branch} conflicted in {conflicted}"
    routes, pages = _read(repo, ROUTES), _read(repo, PAGE_LIST)
    assert {"/page-a", "/page-b"} <= set(yaml.safe_load(routes)["routes"]), routes
    assert "  pageA,\n" in pages and "  pageB,\n" in pages, pages
    assert route_list_problems(routes) == [] and page_list_problems(pages) == []


def test_a_third_page_after_two_merged_merges_clean_too(tmp_path: Path) -> None:
    repo = _new_repo(tmp_path)
    for name in ("a", "b", "c"):
        _branch(repo, name, routes=add_route(f"/page-{name}"), pages=add_page(f"page{name.upper()}", f"page{name}"))
    for name in ("a", "b", "c"):
        clean, conflicted = _merge(repo, name)
        assert clean, f"merging {name} conflicted in {conflicted}"
    assert page_list_problems(_read(repo, PAGE_LIST)) == [] and route_list_problems(_read(repo, ROUTES)) == []


# --- what union lets through, and the checks that catch it ----------------------------------------------------------


def test_the_same_page_added_by_both_branches_in_a_conflict_merges_and_the_checks_are_red(tmp_path: Path) -> None:
    """Where git can line the two copies up it takes the addition once; where they fall in a conflict beside other lines
    (one branch adds it before another page, the other after one), union keeps it twice, and both checks say so."""
    repo = _new_repo(tmp_path)
    _branch(repo, "a", routes=lambda t: add_route("/a")(add_route("/twice")(t)),
            pages=lambda t: add_page("pageA", "pageA")(add_page("twice", "twice")(t)))
    _branch(repo, "b", routes=lambda t: add_route("/twice")(add_route("/b")(t)),
            pages=lambda t: add_page("twice", "twice")(add_page("pageB", "pageB")(t)))
    assert _merge(repo, "a") == (True, [])
    assert _merge(repo, "b") == (True, [])
    routes, pages = _read(repo, ROUTES), _read(repo, PAGE_LIST)
    assert any("/twice is listed 2 times" in p for p in route_list_problems(routes)), routes
    assert any("twice" in p for p in page_list_problems(pages)), pages


def test_the_same_page_added_by_both_branches_after_the_same_line_is_taken_once(tmp_path: Path) -> None:
    repo = _new_repo(tmp_path)
    for name in ("a", "b"):
        _branch(repo, name, routes=add_route("/same"), pages=add_page("same", "same"))
    assert _merge(repo, "a") == (True, []) and _merge(repo, "b") == (True, [])
    assert route_list_problems(_read(repo, ROUTES)) == [] and page_list_problems(_read(repo, PAGE_LIST)) == []


def test_one_page_renamed_differently_in_two_branches_merges_and_the_page_list_check_is_red(tmp_path: Path) -> None:
    """An edit in place, the shape union is not safe for: both versions are kept, and the check says so."""
    repo = _new_repo(tmp_path)

    def rename(to: str) -> Callable[[str], str]:
        return lambda t: re.sub(r"\bcasesPage\b", to, t)

    _branch(repo, "a", pages=rename("casesList"))
    _branch(repo, "b", pages=rename("caseIndex"))
    assert _merge(repo, "a") == (True, [])
    assert _merge(repo, "b") == (True, []), "union merges an edit in place without a word"
    pages = _read(repo, PAGE_LIST)
    problems = page_list_problems(pages)
    assert any("./cases.js is imported 2 times" in p for p in problems), problems


@pytest.mark.parametrize("plant, said", [
    (lambda t: t + "  - /help\n", "listed 2 times"),
    (lambda t: t.replace("routes:", "routes:\n  - /a /b"), "one path to a line"),
    (lambda t: t.replace("routes:\n", ""), "does not start"),
], ids=["a-path-twice", "two-on-a-line", "no-heading"])
def test_the_route_list_check_is_red_for_each_thing_union_could_leave(plant, said) -> None:
    assert any(said in p for p in route_list_problems(plant(_real(ROUTES))))


@pytest.mark.parametrize("plant, said", [
    (lambda t: t.replace("  help,\n", "  help,\n  help,\n"), "times"),
    (lambda t: t.replace("  help,\n", ""), "imported and not in PAGES"),
    (lambda t: t.replace('import { help } from "./help.js";\n', ""), "not imported"),
    (lambda t: t.replace('import { help } from "./help.js";\n',
                         'import { help } from "./help.js";\nimport { helpAgain } from "./help.js";\n'), "imported 2 times"),
    (lambda t: t.replace("  help,\n", "  help, adminPeople,\n"), "one page to a line"),
], ids=["a-page-twice", "a-page-left-out", "a-page-not-imported", "a-module-imported-twice", "two-on-a-line"])
def test_the_page_list_check_is_red_for_each_thing_union_could_leave(plant, said) -> None:
    text = _real(PAGE_LIST)
    planted = plant(text)
    assert planted != text, "the plant's anchor is not in the real page list"
    assert any(said in p for p in page_list_problems(planted)), page_list_problems(planted)
