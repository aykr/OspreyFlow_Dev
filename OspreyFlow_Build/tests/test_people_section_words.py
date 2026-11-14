"""The People section's name and the Entra refusal's words, as a person reads them (v0.5.2; docs' sweep, 14
November 2026).

1. The Admin section the Conduit's refusals send people to is "People and roles": the label the Glass's side list
   takes from `apps/workspace/src/admin/sections.json`, read here from that file, never typed. No user-facing
   string says "Admin › People" alone: not a refusal, a message, a schema description (or its generated
   TypeScript), a runbook or a guide. Comments and module docstrings are not read by users and are not held.
2. On Entra ID, a refusal to set a value Entra sends says the value in words, as the Guests form does
   ("clearance", "unit", "handling codes"), never a field's name (`org_unit`, `handling_codes`).

Rule 15: the strings are read from the real source files by Python's own parser, so an f-string's text is held as
it is written; the refusal is the real `check_administrator_access`'s.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

import principal_auth
from services.api.entra_people import PersonActionRefused, check_administrator_access
from schemas.admin import PersonAccessInput

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
SECTIONS = CORE / "apps/workspace/src/admin/sections.json"
#: "Admin › People" (or "Admin -> People", the ASCII arrow) not followed by the section's own words.
ALONE = re.compile(r"Admin (?:›|->) People(?! and roles)")


def _rail_label(screen: str) -> str:
    groups = json.loads(SECTIONS.read_text(encoding="utf-8"))["groups"]
    [label] = [s["label"] for g in groups for s in g["sections"] if s.get("screen") == screen]
    return label


def test_the_people_section_s_name_is_the_one_the_side_list_draws() -> None:
    assert getattr(principal_auth, "PEOPLE_SECTION", None) == f"Admin › {_rail_label('admin/sections/People.tsx')}"


def _docstrings(tree: ast.Module) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def _strings(path: Path, *, docstrings: bool) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = set() if docstrings else _docstrings(tree)
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip]  # fmt: skip


def _said_alone() -> list[str]:
    """Every user-facing string that says "Admin › People" alone."""
    found = []
    # The Conduit's and principal_auth's words: every string but a docstring (a refusal, a message, a log).
    for folder in ("services/api", "packages/principal_auth", "harness/cloud_platform"):
        for path in sorted((CORE / folder).rglob("*.py")):
            found += [f"{path.relative_to(CORE)}:{n}" for n, s in _strings(path, docstrings=False) if ALONE.search(s)]
    # The schema: its docstrings and descriptions are the generated TypeScript's and JSON Schema's words.
    for path in sorted((CORE / "packages/schemas").glob("*.py")):
        found += [f"{path.relative_to(CORE)}:{n}" for n, s in _strings(path, docstrings=True) if ALONE.search(s)]
    for path in [*sorted((CORE / "packages/schemas/generated").glob("*.ts")), CORE / "docs/administration-guide.md",
                 CORE / "docs/user-guide.md"]:  # fmt: skip
        found += [f"{path.relative_to(CORE)}:{n}" for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                  if ALONE.search(line)]  # fmt: skip
    return found


def test_no_user_facing_string_names_the_people_section_by_its_old_name() -> None:
    assert _said_alone() == []


def test_the_scan_sees_a_refusal_an_f_string_and_a_schema_description(tmp_path: Path) -> None:
    """The scan's own red (rule 15): each shape the real files hold is found, and a comment is not."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        '"""Admin › People, a module docstring."""\n'
        "# Admin › People, a comment\n"
        'X = "is not a person Admin › People holds"\n'
        "Y = f\"set {'them'} in Admin › People\"\n"
        'Z = "set in Admin › People and roles"\n'
        'W = "An Admin -> People action"\n',
        encoding="utf-8",
    )
    said = [n for n, s in _strings(planted, docstrings=False) if ALONE.search(s)]
    assert said == [3, 4, 6]
    assert [n for n, s in _strings(planted, docstrings=True) if ALONE.search(s)] == [1, 3, 4, 6]


EVERY = frozenset({"clearance", "org_unit", "handling_codes"})
CLASSES = ["OFFICIAL", "SECRET"]


@pytest.mark.parametrize(
    ("by_administrator", "access", "words"),
    [
        (frozenset({"org_unit", "handling_codes"}), PersonAccessInput(clearance="OFFICIAL"),
         "Here a person's clearance comes from Entra ID, and is changed there."),
        (frozenset({"clearance", "handling_codes"}), PersonAccessInput(org_unit="unit-2"),
         "Here a person's unit comes from Entra ID, and is changed there."),
        (frozenset({"clearance", "org_unit"}), PersonAccessInput(receivable_handling_codes=["P"]),
         "Here a person's handling codes come from Entra ID, and are changed there."),
        (frozenset({"clearance"}), PersonAccessInput(org_unit="unit-2", receivable_handling_codes=["P"]),
         "Here a person's unit and handling codes come from Entra ID, and are changed there."),
        (frozenset({"handling_codes"}), PersonAccessInput(clearance="OFFICIAL", org_unit="unit-2"),
         "Here a person's clearance and unit come from Entra ID, and are changed there."),
    ],
)  # fmt: skip
def test_a_value_entra_sends_is_refused_in_words(by_administrator, access, words) -> None:
    with pytest.raises(PersonActionRefused) as refused:
        check_administrator_access(by_administrator, None, access, CLASSES)
    said = str(refused.value)
    assert said.startswith(words + " "), said
    assert not re.search(r"org_unit|handling_codes|receivable", said), said
