"""The People section's name and the Entra refusal's words, as a person reads them (ADR-148 Amendment 19; v0.5.2,
route W, from docs' sweep, 14 November 2026).

1. The Admin section people are sent to is "People and roles": the label the Glass's side list takes from
   `apps/workspace/src/admin/sections.json`, read here from that file, never typed. No user-facing string says
   "Admin › People" alone. That covers a refusal, an error body, a log line, a route's OpenAPI description, a
   schema description (and its generated TypeScript), the CLI, the harness and its runbooks, the Glass's own
   strings and the shipped guides. Comments, test names and module docstrings are not read by users and are not
   held; a guide's version rows keep what each version said.
2. On Entra ID, a refusal to set a value Entra sends says the values in words, as the Guests form does
   ("clearance", "unit", "handling codes", in its order), and which values are set here, never a field's name and
   never that all three come from Entra.

Rule 15: Python strings are read by Python's own parser, so an f-string or an implicit concatenation is held as a
person reads it; the guides and the Glass's source are read whole, so a name split over two lines is still found;
the refusals are the real ones.
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import principal_auth
from principal_auth import OwnerNotHeld, OwnerRecordUnavailable
from schemas.admin import PersonAccessInput
from services.api.entra_people import PersonActionRefused, check_administrator_access

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
SECTIONS = CORE / "apps/workspace/src/admin/sections.json"
#: "Admin › People" (or ">" or the ASCII "->", any spacing, across a line break) not followed by "and roles".
ALONE = re.compile(r"Admin\s*(?:›|->|>)\s*People(?!\s+and\s+roles)")
VERSION_ROW = re.compile(r"^\| \d+\.\d+ \|")
ROUTE_VERBS = {"get", "post", "put", "patch", "delete"}


def _rail_label(screen: str) -> str:
    groups = json.loads(SECTIONS.read_text(encoding="utf-8"))["groups"]
    [label] = [s["label"] for g in groups for s in g["sections"] if s.get("screen") == screen]
    return label


def test_the_people_section_s_name_is_the_one_the_side_list_draws() -> None:
    assert getattr(principal_auth, "PEOPLE_SECTION", None) == f"Admin › {_rail_label('admin/sections/People.tsx')}"


def _is_route(node: ast.AST) -> bool:
    """A FastAPI route: its docstring is the route's description in the published OpenAPI."""
    return any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_VERBS
               for d in getattr(node, "decorator_list", []))  # fmt: skip


def _unread_docstrings(tree: ast.Module) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and not _is_route(node):
                found.add(id(first.value))
    return found


def _python(path: Path, *, docstrings: bool) -> list[int]:
    """The lines of `path`'s strings that say the name alone; docstrings only where they are read."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = set() if docstrings else _unread_docstrings(tree)
    return sorted(n.lineno for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
                  and ALONE.search(n.value))  # fmt: skip


def _text(text: str, *, comments: bool = False) -> list[int]:
    """The lines of a guide or a source file where the name alone starts, read whole (a name over a line break is
    one name). A guide's version rows are kept as written; a source file's comments, when asked, are left out."""
    if comments:
        text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group()), text, flags=re.S)
        text = re.sub(r"(?m)(^|[^:])//.*$", r"\1", text)
    lines = text.split("\n")
    found = []
    for m in ALONE.finditer(text):
        n = text.count("\n", 0, m.start()) + 1
        if not VERSION_ROW.match(lines[n - 1]):
            found.append(n)
    return found


def _said_alone() -> list[str]:
    found = []
    for folder in ("services", "packages/principal_auth", "harness", "cli"):
        for path in sorted((CORE / folder).rglob("*.py")):
            found += [f"{path.relative_to(CORE)}:{n}" for n in _python(path, docstrings=False)]
    for path in sorted((CORE / "packages/schemas").glob("*.py")):  # its docstrings are the schema's descriptions
        found += [f"{path.relative_to(CORE)}:{n}" for n in _python(path, docstrings=True)]
    glass = [p for p in sorted((CORE / "apps/workspace/src").rglob("*.ts*")) if ".test." not in p.name]
    for path in [*sorted((CORE / "packages/schemas/generated").glob("*.ts")), *glass]:
        found += [f"{path.relative_to(CORE)}:{n}" for n in _text(path.read_text(encoding="utf-8"), comments=True)
                  ]  # fmt: skip
    for path in [*sorted((CORE / "docs").glob("*.md")), CORE / "DEMO_GUIDE.md", CORE / "README.md"]:
        found += [f"{path.relative_to(CORE)}:{n}" for n in _text(path.read_text(encoding="utf-8"))]
    return found


def test_no_user_facing_string_names_the_people_section_by_its_old_name() -> None:
    assert _said_alone() == []


def test_the_scan_finds_each_shape_the_real_files_hold(tmp_path: Path) -> None:
    """The scan's own red (rule 15), one plant for each shape it reads, and what it must leave alone."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        '"""Admin › People, a module docstring: not read."""\n'      # 1
        "# Admin › People, a comment\n"                              # 2
        'X = "is not a person Admin › People holds"\n'              # 3 a refusal
        "Y = f\"set {'them'} in Admin › People\"\n"                 # 4 an f-string
        'Z = "set in Admin › People and roles"\n'                   # 5 the new name: not found
        'W = "An Admin -> People action"\n'                         # 6 the ASCII arrow
        'V = ("in Admin › " "People: refresh")\n'                   # 7 an implicit concatenation
        "@app.get('/x')\n"                                           # 8
        "def route():\n"                                             # 9
        '    """Lists what Admin › People holds."""\n'               # 10 a route's OpenAPI description
        "def helper():\n"                                            # 11
        '    """Admin › People\'s helper."""\n',                     # 12 a helper's docstring: not read
        encoding="utf-8",
    )
    assert _python(planted, docstrings=False) == [3, 4, 6, 7, 10]
    assert _python(planted, docstrings=True) == [1, 3, 4, 6, 7, 10, 12]
    guide = ("**Version 2.12**\n"
             "| 2.01 | 2026-11-13 | set in *Admin › People* (a version row) |\n"
             "an administrator sets it for each person in *Admin ›\n"
             "People* with **Access**; and in Admin › People and roles too.\n")  # fmt: skip
    assert _text(guide) == [3]  # split over a line break, found; the version row and the new name, not
    source = ('// Admin › People › Roles, a comment\n'
              '/* Admin ›\n   People, a block comment */\n'
              'const words = "That person is not in Admin › People";\n'
              'const url = "https://x.example/y"; // Admin › People\n')  # fmt: skip
    assert _text(source, comments=True) == [4]


EVERY = frozenset({"clearance", "org_unit", "handling_codes"})
CLASSES = ["OFFICIAL", "SECRET"]


@pytest.mark.parametrize(
    ("by_administrator", "access", "words"),
    [
        (frozenset({"org_unit", "handling_codes"}), PersonAccessInput(clearance="OFFICIAL"),
         "Here a person's clearance comes from Entra ID, and is changed there. "
         "Their unit and handling codes are set here, with Access."),
        (frozenset({"clearance", "handling_codes"}), PersonAccessInput(org_unit="unit-2"),
         "Here a person's unit comes from Entra ID, and is changed there. "
         "Their clearance and handling codes are set here, with Access."),
        (frozenset({"clearance", "org_unit"}), PersonAccessInput(receivable_handling_codes=["P"]),
         "Here a person's handling codes come from Entra ID, and are changed there. "
         "Their clearance and unit are set here, with Access."),
        (frozenset({"clearance"}), PersonAccessInput(org_unit="unit-2", receivable_handling_codes=["P"]),
         "Here a person's unit and handling codes come from Entra ID, and are changed there. "
         "Their clearance is set here, with Access."),
        (frozenset({"handling_codes"}), PersonAccessInput(clearance="OFFICIAL", org_unit="unit-2"),
         "Here a person's clearance and unit come from Entra ID, and are changed there. "
         "Their handling codes are set here, with Access."),
        (frozenset({"org_unit"}), PersonAccessInput(clearance="OFFICIAL", receivable_handling_codes=["P"]),
         "Here a person's clearance and handling codes come from Entra ID, and are changed there. "
         "Their unit is set here, with Access."),
    ],
)  # fmt: skip
def test_a_value_entra_sends_is_refused_in_words(by_administrator, access, words) -> None:
    with pytest.raises(PersonActionRefused) as refused:
        check_administrator_access(by_administrator, None, access, CLASSES)
    assert refused.value.error == "entra_holds_accounts"
    assert str(refused.value) == words


@pytest.mark.parametrize(
    ("error", "words"),
    [
        (OwnerNotHeld("gone"), "the rule's author, x, is not held in Admin › People and roles"),
        (OwnerRecordUnavailable("down"),
         "the people store behind Admin › People and roles could not be read to act as the rule's author"),
    ],
)  # fmt: skip
def test_a_rule_s_author_refused_names_the_section(error, words) -> None:
    from services.api.rule_schedule import RuleScheduleExecutor, _Refused

    async def resolve(_owner: str):
        raise error

    executor = RuleScheduleExecutor(rules=None, valkey=None, resolve_owner=resolve, check_case=None, judge=None)  # type: ignore[arg-type]
    with pytest.raises(_Refused) as refused:
        asyncio.run(executor._author(SimpleNamespace(owner_id="x")))  # type: ignore[arg-type]
    assert str(refused.value) == words


# --- rights said as the screens say them (ADR-148 Amendment 19, the orchestrator's A2 point 3) ---------------------


def _glass_right_names() -> dict[str, str]:
    """The Glass's exceptions to "the id with spaces, capitalised" (`help/roles.ts`'s RIGHT_NAMES), read there."""
    source = (CORE / "apps/workspace/src/help/roles.ts").read_text(encoding="utf-8")
    block = re.search(r"const RIGHT_NAMES[^{]*\{(.*?)\};", source, re.S)
    assert block, "help/roles.ts no longer has RIGHT_NAMES"
    return dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", block.group(1)))


def test_each_right_is_named_as_the_glass_names_it() -> None:
    from schemas.rights import Right, right_name

    glass = _glass_right_names()
    for right in Right:
        words = right.value.replace("_", " ")
        assert right_name(right) == glass.get(right.value, words[:1].upper() + words[1:]), right
    assert right_name("administer_system") == "Administer system"
    assert right_name("edit_target_model") == "Edit domain model"


def test_a_right_the_giver_does_not_hold_is_refused_by_its_name() -> None:
    from schemas.rights import Right
    from services.api.custom_roles import RoleRefused, role_refusal

    with pytest.raises(RoleRefused) as refused:
        role_refusal("Desk", ["administer_system", "manage_models"], giver_rights=[Right.MANAGE_PEOPLE], names_taken=[])
    assert str(refused.value) == "you cannot give a right you do not hold: Administer system and Manage models"
    assert refused.value.detail["rights"] == ["administer_system", "manage_models"]  # the ids, for the Glass's code
    with pytest.raises(RoleRefused) as pair:
        role_refusal("Desk", ["promote_to_dataset", "review_promotions"], giver_rights=list(Right), names_taken=[])
    assert str(pair.value).startswith("a role cannot hold both Promote to dataset and Review promotions: ")
