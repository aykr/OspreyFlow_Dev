"""No message the product shows a person tells them to run `make` (ADR-114 Amendment 22): an
operator runs `ospreyflow`; `make` is the developer's. Read from the product's Python itself — every
string a person can see, comments and docstrings aside, which may well name a developer's target.

What a drift would do, and the case that catches it: a refusal or a hint that sends an operator to a
`make` target their install does not have — `test_no_message_names_a_make_command`; and a check that
could not see one — `test_a_message_naming_make_is_found` with
`test_a_comment_or_a_docstring_naming_make_is_not_a_message`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.layout import CORE

FOLDERS = ("harness", "scripts", "cli", "services")
MAKE = re.compile(r"`make [a-z][a-z-]*")


def messages_naming_make(source: str) -> list[str]:
    """Every string in `source` a person can see that names a backticked `make` command."""
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found += MAKE.findall(node.value)
    return found


def _product_files() -> list[Path]:
    return [
        path
        for folder in FOLDERS
        for path in sorted((CORE / folder).rglob("*.py"))
        if "/tests/" not in path.as_posix() and ".venv" not in path.parts
    ]


def test_a_message_naming_make_is_found() -> None:
    source = 'raise SystemExit(f"{name} is missing; run `make register-sign-in` and try again")\n'
    assert messages_naming_make(source) == ["`make register-sign-in"]


def test_a_comment_or_a_docstring_naming_make_is_not_a_message() -> None:
    source = '"""Checked by `make ci`."""\n# `make dev-up` brings it up\ndef f():\n    """See `make test`."""\n'
    assert messages_naming_make(source) == []


def test_no_message_names_a_make_command() -> None:
    found = {
        path.relative_to(CORE).as_posix(): hits
        for path in _product_files()
        if (hits := messages_naming_make(path.read_text(encoding="utf-8")))
    }
    assert found == {}, f"messages that send an operator to make: {found}"
