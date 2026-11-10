"""The guides' words for places, roles, rights and levels are the Glass's own (ADR-145 Amendment 4
decision 12): `apps/workspace/src/help/roles.ts` holds them, and the guides, the README and the welcome
page copy them by hand. This test holds every copy to that file, so a copy cannot drift from it.

What a drift would do, and the case that catches it:
- a role's sentence changed in `roles.ts` and not in a guide's role table, or the other way round, or a
  role renamed or dropped from a table (each copy lists the five built-in roles, and the Super user
  where it says the places each opens) — `test_each_role_row_says_what_roles_ts_says`;
- a role's *Places it opens* naming a place `placesByRole.json` does not give it —
  `test_each_role_row_opens_the_places_recorded`;
- a right worded in `roles.ts` and missing from, or worded differently in, the administration guide's
  rights table (either copy) — `test_the_rights_table_is_roles_ts_own`;
- a level's sentence drifting — `test_each_level_row_says_what_roles_ts_says`;
- a place's name in a table that is not `PLACE_WORDS`' name —
  `test_each_place_row_names_a_place_of_roles_ts`;
- the welcome page saying what a place is for differently from the guides —
  `test_the_welcome_page_says_each_place_as_the_guides_do`. The welcome page and the guides say what
  each place is for in their own words, not `PLACE_WORDS`' (whose sentences name releases and one queue,
  neither built); this case keeps those two in step and the names to `roles.ts`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[1]
CORE = BUILD.parent / "OspreyFlow_Core"
WORKSPACE = CORE / "apps" / "workspace" / "src"
ROLES_TS = WORKSPACE / "help" / "roles.ts"
WELCOME = WORKSPACE / "welcome" / "WelcomeAbout.tsx"
PLACES_BY_ROLE = WORKSPACE / "shell" / "placesByRole.json"

COPIES = [
    CORE / "docs" / "user-guide.md",
    CORE / "docs" / "administration-guide.md",
    CORE / "docs" / "architecture-guide.md",
    CORE / "docs" / "developer-guide.md",
    BUILD / "spec" / "10_ADMINISTRATION_GUIDE.md",
    CORE / "README.md",
    BUILD / "process" / "lanes" / "docs" / "README_DRAFT.md",
]
RIGHTS_COPIES = [CORE / "docs" / "administration-guide.md", BUILD / "spec" / "10_ADMINISTRATION_GUIDE.md"]

_ENTRY = re.compile(r'^\s*"?([\w-]+)"?:\s*\{\s*name:\s*"([^"]+)",\s*says:\s*"([^"]+)"', re.M)
_RIGHT = re.compile(r'^\s*(\w+):\s*"([^"]+)",?\s*$', re.M)


def _block(source: str, start: str) -> str:
    """The text of `start … {` up to its closing `}` at the line's start."""
    at = source.index(start)
    end = re.compile(r"^\}", re.M).search(source, at)
    assert end, f"no end to {start!r}"
    return source[at : end.start()]


def _entries(block: str) -> dict[str, tuple[str, str]]:
    return {key: (name, says) for key, name, says in _ENTRY.findall(block)}


def roles_ts(source: str | None = None) -> dict[str, dict]:
    text = source if source is not None else ROLES_TS.read_text(encoding="utf-8")
    return {
        "places": _entries(_block(text, "export const PLACE_WORDS")),
        "roles": _entries(_block(text, "const SAID_ROLES")),
        "rights": dict(_RIGHT.findall(_block(text, "export const RIGHT_WORDS"))),
        "levels": _entries(_block(text, "export const LEVEL_WORDS")),
    }


def place_says(source: str | None = None) -> dict[str, str]:
    text = source if source is not None else WELCOME.read_text(encoding="utf-8")
    return dict(_RIGHT.findall(_block(text, "const PLACE_SAYS")))


def tables(text: str) -> list[tuple[str, list[list[str]]]]:
    """Each Markdown table as (its first header cell, its body rows' cells)."""
    found: list[tuple[str, list[list[str]]]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith("|") and i + 1 < len(lines) and re.match(r"^\|\s*:?-{3,}", lines[i + 1]):
            header = _cells(lines[i])[0]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            found.append((header, rows))
        else:
            i += 1
    return found


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _bold(cell: str) -> str | None:
    m = re.match(r"^\*\*([^*]+)\*\*", cell)
    return m.group(1) if m else None


def _plain(cell: str) -> str:
    """A cell's sentence without the copy's own pointer, `(section 7)`, or its last full stop."""
    cell = re.sub(r"\s*\((?:section|developer|administration|user)[^)]*\)\.?$", "", cell)
    return cell.rstrip(".").strip()


def rows_of(text: str, header: str) -> list[list[str]]:
    return [row for head, rows in tables(text) if head == header for row in rows]


WORDS = roles_ts()
EXISTING = [p for p in COPIES if p.exists()]
each_copy = pytest.mark.parametrize("path", EXISTING, ids=[p.name for p in EXISTING])


#: The five built-in roles every copy's role table lists; the Super user preset is listed where the
#: table says the places each opens (the administration guide), and said in prose elsewhere.
BUILT_IN = ("analyst", "data_engineer", "osprey-admin", "reports_viewer", "rule_author")


def role_drift(text: str, words: dict) -> list[str]:
    """Each role table's rows against roles.ts: every row a role roles.ts names, saying what it says,
    and every built-in role (and, in a table of the places each opens, the Super user) listed, so a
    role renamed or dropped on either side fails."""
    by_name = {name: says for name, says in words["roles"].values()}
    drift = []
    for head, rows in tables(text):
        if head != "Role":
            continue
        named = [_bold(row[0]) for row in rows]
        for row, name in zip(rows, named):
            if name not in by_name:
                drift.append(f"{row[0]!r} is not a role in roles.ts")
            elif _plain(row[1]) != by_name[name].rstrip("."):
                drift.append(f"{name}: {row[1]!r} is not {by_name[name]!r}")
        wanted = list(BUILT_IN) + (["super"] if rows and len(rows[0]) > 2 else [])
        for key in wanted:
            if key in words["roles"] and words["roles"][key][0] not in named:
                drift.append(f"{words['roles'][key][0]} missing from a role table")
    return drift


def level_drift(text: str, words: dict) -> list[str]:
    by_name = {name: says for name, says in words["levels"].values()}
    return [
        f"{_bold(row[0])}: {row[1]!r} is not {by_name[_bold(row[0])]!r}"
        for row in rows_of(text, "Level")
        if _bold(row[0]) in by_name and _plain(row[1]) != by_name[_bold(row[0])].rstrip(".")
    ]


def rights_drift(text: str, words: dict) -> list[str]:
    table = {row[0].strip("`"): row[1] for row in rows_of(text, "Right")}
    drift = [f"{r} missing" for r in words["rights"] if r not in table]
    drift += [f"{r} not in roles.ts" for r in table if r not in words["rights"]]
    drift += [
        f"{r}: {table[r]!r} is not {says!r}" for r, says in words["rights"].items() if r in table and table[r] != says
    ]
    return drift


def _place_key(name: str, words: dict) -> str | None:
    bare = re.sub(r"\(.*?\)", "", name).strip().lower()
    bare = re.sub(r"^the ", "", bare)
    for key, (place, _) in words["places"].items():
        if re.sub(r"^the ", "", place.lower()) == bare:
            return key
    return None


def places_drift(text: str, words: dict, recorded: dict) -> list[str]:
    key_of = {name: key for key, (name, _) in words["roles"].items()}
    drift = []
    for row in rows_of(text, "Role"):
        name = _bold(row[0])
        if name not in key_of or len(row) < 3:
            continue
        said = row[2].strip()
        given = set(recorded[key_of[name]]["places"])
        if said == "All four":
            opened = set(words["places"])
        else:
            opened = {_place_key(p, words) for p in said.split(",")}
        if opened != given:
            drift.append(f"{name}: {said!r} is not {sorted(given)}")
    return drift


@each_copy
def test_each_role_row_says_what_roles_ts_says(path: Path) -> None:
    assert role_drift(path.read_text(encoding="utf-8"), WORDS) == []


@each_copy
def test_each_role_row_opens_the_places_recorded(path: Path) -> None:
    recorded = json.loads(PLACES_BY_ROLE.read_text(encoding="utf-8"))["roles"]
    assert places_drift(path.read_text(encoding="utf-8"), WORDS, recorded) == []


@pytest.mark.parametrize("path", RIGHTS_COPIES, ids=[p.name for p in RIGHTS_COPIES])
def test_the_rights_table_is_roles_ts_own(path: Path) -> None:
    assert rights_drift(path.read_text(encoding="utf-8"), WORDS) == []


@each_copy
def test_each_level_row_says_what_roles_ts_says(path: Path) -> None:
    assert level_drift(path.read_text(encoding="utf-8"), WORDS) == []


@each_copy
def test_each_place_row_names_a_place_of_roles_ts(path: Path) -> None:
    for row in rows_of(path.read_text(encoding="utf-8"), "Place"):
        assert _place_key(_bold(row[0]) or row[0], WORDS), f"{row[0]!r} is not a place in roles.ts"


@each_copy
def test_the_welcome_page_says_each_place_as_the_guides_do(path: Path) -> None:
    assert place_drift(path.read_text(encoding="utf-8"), WORDS, place_says()) == []


def test_the_copies_are_read() -> None:
    """Every kind of table is found somewhere, so a renamed header cannot leave a case with nothing to check."""
    texts = [p.read_text(encoding="utf-8") for p in EXISTING]
    for header in ("Role", "Level", "Place", "Right"):
        assert any(rows_of(t, header) for t in texts), f"no {header} table in any copy"
    assert len(WORDS["roles"]) == 6 and len(WORDS["levels"]) == 3 and len(WORDS["places"]) == 4
    assert len(WORDS["rights"]) >= 51


# Rule 15: each check shown red by a drift in the shape the copies take.
def test_a_role_sentence_changed_is_caught() -> None:
    text = (CORE / "docs" / "user-guide.md").read_text(encoding="utf-8")
    planted = text.replace("works alerts and keeps watches. Reads figures", "works alerts. Reads figures", 1)
    assert role_drift(text, WORDS) == [] and role_drift(planted, WORDS)


def test_a_right_reworded_or_dropped_is_caught() -> None:
    text = RIGHTS_COPIES[0].read_text(encoding="utf-8")
    assert rights_drift(text.replace("| Start a case. |", "| Open a case. |", 1), WORDS)
    assert rights_drift(re.sub(r"^\| `create_case` .*\n", "", text, count=1, flags=re.M), WORDS)


def test_a_level_sentence_changed_is_caught() -> None:
    text = (CORE / "docs" / "user-guide.md").read_text(encoding="utf-8")
    assert level_drift(text.replace("Changes nothing in it.", "Changes little.", 1), WORDS)


def test_a_place_wrongly_opened_is_caught() -> None:
    recorded = json.loads(PLACES_BY_ROLE.read_text(encoding="utf-8"))["roles"]
    text = RIGHTS_COPIES[0].read_text(encoding="utf-8")
    planted = text.replace("| The Glass, Rules and Monitoring |\n| **Data", "| The Glass |\n| **Data", 1)
    assert planted != text and places_drift(planted, WORDS, recorded)


def test_roles_ts_changed_is_caught() -> None:
    """The drift from the other side: roles.ts reworded, every copy left."""
    source = ROLES_TS.read_text(encoding="utf-8").replace('"Draw on a case\'s boards."', '"Draw on boards."', 1)
    text = RIGHTS_COPIES[0].read_text(encoding="utf-8")
    assert rights_drift(text, roles_ts(source)) == ["draw_on_boards: \"Draw on a case's boards.\" is not 'Draw on boards.'"]


def test_a_role_renamed_or_dropped_is_caught() -> None:
    text = (CORE / "docs" / "user-guide.md").read_text(encoding="utf-8")
    renamed = text.replace("| **Rule author** |", "| **Rules author** |", 1)
    dropped = re.sub(r"^\| \*\*Reports Viewer\*\* .*\n", "", text, count=1, flags=re.M)
    assert renamed != text and dropped != text
    assert role_drift(renamed, WORDS) == [
        "'**Rules author**' is not a role in roles.ts",
        "Rule author missing from a role table",
    ]
    assert role_drift(dropped, WORDS) == ["Reports Viewer missing from a role table"]
    admin = RIGHTS_COPIES[0].read_text(encoding="utf-8")
    no_super = re.sub(r"^\| \*\*Super user\*\* .*\n", "", admin, count=1, flags=re.M)
    assert role_drift(no_super, WORDS) == ["Super user missing from a role table"]


def place_drift(text: str, words: dict, says: dict[str, str]) -> list[str]:
    """Each place table's rows against PLACE_WORDS' names and PLACE_SAYS' sentences."""
    drift = []
    if set(says) != set(words["places"]):
        drift.append("PLACE_SAYS names other places than PLACE_WORDS")
    for row in rows_of(text, "Place"):
        key = _place_key(_bold(row[0]) or row[0], words)
        sentence = _plain(row[2] if len(row) > 2 and row[1].startswith("`") else row[1])
        if not key:
            drift.append(f"{row[0]!r} is not a place in roles.ts")
        elif sentence != says[key].rstrip("."):
            drift.append(f"{row[0]}: {sentence!r} is not {says[key]!r}")
    return drift


def test_the_welcome_page_drifting_is_caught() -> None:
    text = (CORE / "docs" / "user-guide.md").read_text(encoding="utf-8")
    source = WELCOME.read_text(encoding="utf-8")
    planted = source.replace("the domain model and held rows.", "and releases.", 1)
    assert planted != source
    assert place_drift(text, WORDS, place_says(source)) == []
    assert place_drift(text, WORDS, place_says(planted)) == [
        "**Ingest Studio**: 'Bring data in: sources, pipelines, the domain model and held rows' "
        "is not 'Bring data in: sources, pipelines, and releases.'"
    ]
