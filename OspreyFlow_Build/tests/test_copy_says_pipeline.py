"""The Conduit's words to a person say "pipeline", the Ingest Studio's word, never "recipe", the
code's (CARRIES 234; the owner, 13 November 2026: the screens' word is Pipeline). The Glass's own
copy is held by `apps/workspace/src/copyWords.test.ts`.

**What is scanned.** The string literals of the modules whose words reach a screen:
- the Conduit's routes and services (`services/api`);
- the ingest engine and its rules (`services/ingest`), whose refusals the Studio shows;
- the graph adapter (`packages/adapters`), whose refusals reach a run's result;
- the shared models (`packages/schemas`).

That covers a refusal's words, an f-string's text, and a string joined from parts.

**What is not words to a person, and is not scanned:** identifiers (`recipe_id`), docstrings and
strings standing alone as comments, a log line, SQL, and argparse's help. Nor is a word with no
space beside it (an id, a key), nor a key quoted in backticks (a manifest's `` `recipe` `` field,
which its author types).

Shown red by `test_the_check_finds_the_word_in_every_shape_a_message_takes`, planted in the shapes
the Conduit's messages took before this change.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
SCANNED = [
    CORE / "services" / "api",
    CORE / "services" / "ingest",
    CORE / "packages" / "adapters",
    CORE / "packages" / "schemas",
]
WORD = re.compile(r"\brecipes?\b", re.IGNORECASE)
SQL = re.compile(r"^\s*(CREATE|SELECT|INSERT|UPDATE|DELETE|ALTER|WITH|DROP)\b", re.IGNORECASE)
#: Calls whose strings are not shown to a person.
NOT_SHOWN = frozenset(
    {"debug", "info", "warning", "error", "exception", "add_argument", "ArgumentParser"}
)
#: A query in another language (Gremlin's `.by(…).values(…)`), not words.
QUERY = re.compile(r"\.\w+\(.*\.\w+\(")


def _words(text: str) -> str:
    """`text` without any token holding a slash or quoted in backticks: a path (`recipes/{id}.yaml`)
    and a key a person types (a manifest's `recipe`) are names, not words."""
    return " ".join(
        token for token in text.split() if "/" not in token and not token.startswith("`")
    )


def found(path: Path, source: str | None = None) -> list[tuple[int, str]]:
    """`(line, text)` for each string a person can be shown that says "recipe"."""
    text = source if source is not None else path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    silent: set[int] = set()
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            silent.add(id(node.value))  # a docstring, or a string standing as a comment
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        words = node.value
        whole = words
        call = parents.get(id(node))
        if isinstance(call, ast.JoinedStr):
            # A fragment of an f-string is judged by the f-string's whole text: `f"recipe {id}"`.
            whole = "".join(v.value if isinstance(v, ast.Constant) else " {} " for v in call.values)
            call = parents.get(id(call))
        if isinstance(call, ast.keyword):
            call = parents.get(id(call))
        if id(node) in silent or not WORD.search(_words(words)) or not whole.strip().count(" "):
            continue
        if SQL.match(whole) or QUERY.search(whole):
            continue
        if isinstance(call, ast.Call):
            name = call.func.attr if isinstance(call.func, ast.Attribute) else ""
            name = name or getattr(call.func, "id", "")
            if name in NOT_SHOWN:
                continue
        hits.append((node.lineno, " ".join(words.split())))
    return hits


def _modules(roots: Iterable[Path]) -> list[Path]:
    return sorted(p for root in roots for p in root.rglob("*.py"))


def test_no_message_to_a_person_says_recipe() -> None:
    hits = [
        f"{p.relative_to(CORE)}:{line}: {words}"
        for p in _modules(SCANNED)
        for line, words in found(p)
    ]
    assert hits == []


def test_the_check_finds_the_word_in_every_shape_a_message_takes() -> None:
    """Rule 15, at the shapes the Conduit's messages took before this change."""
    planted = """
from fastapi import HTTPException

class ScheduleRefused(Exception): ...

def refuse(recipe_id: str, name: str) -> None:
    raise HTTPException(status_code=409, detail="another run of this recipe is in progress")

def run(recipe) -> None:
    raise ScheduleRefused(f"the previous run of {recipe.id} recipe is still going")

def publish(recipe) -> None:
    raise ScheduleRefused(f"recipe {recipe.id!r} already has a live version")

WORDS = (
    "the recipe has been published again since these rows were held; "
    "run it again"
)
"""
    assert sorted(line for line, _ in found(Path("planted.py"), planted)) == [7, 10, 13, 16]


def test_the_check_leaves_what_is_not_words_alone() -> None:
    clean = '''
"""A recipe's docstring, which no person is shown."""
import logging

log = logging.getLogger(__name__)

def run(recipe_id: str) -> None:
    """The recipe runs."""
    "a recipe string standing as a comment"
    log.info("ran the recipe %s", recipe_id)
    parser.add_argument("--recipe", help="Path to the recipe YAML file")
    sql = "CREATE TABLE studio_recipes (recipe_id TEXT, label TEXT)"
    key = "recipe_id"
    path = "/v1/ingest/recipes"
    held = f"recipes/{recipe_id}.yaml"
    query = f'g.V().by(fold().project("n","recipe")).by(values("{recipe_id}"))'
    parser = argparse.ArgumentParser(description="Run one ingest recipe against one source file.")
    raise ValueError("`recipe` names a .yaml file beside the manifest, without a folder")
'''
    assert found(Path("clean.py"), clean) == []
