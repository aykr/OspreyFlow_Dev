"""The sign-in library has its named entry in the licence register (slice LR1; the owner's ruling of 20 November 2026,
slice D answers, addition 4).

`oidc-client-ts` is a run-time dependency of `apps/workspace` (the Glass's OpenID Connect sign-in, `auth/userManager.ts`
and `auth/oidcConfig.ts`), so it ships in the workspace bundle. `auth/userManager.ts` says `spec/00_ARCHITECTURE.md`
section 7 is its allowlist for what it relies on rather than hand-rolls, and section 7 had no entry for it. A named entry
is a row of a table in section 7, as `graphology` and `zustand` have (ADR-152 decision 6, slice C): the package in
backticks, its range, its licence as the package's own metadata gives it, why it is used, and where it ships.

Which test fails if the invariant is broken (rule 12):

* `oidc-client-ts` is declared by `apps/workspace/package.json` and section 7 has no table row naming it (the entry
  deleted, or only mentioned in prose, which names no licence): `test_oidc_client_ts_has_a_named_entry`;
* the row's licence is not the licence the lockfile records for the installed package, or its range is not the range the
  workspace declares (the entry written from memory, or left behind by an upgrade):
  `test_the_entry_states_the_licence_and_range_the_package_has`;
* the row does not say what it is used for, where it ships and why it was named, with the date and the owner's name:
  `test_the_entry_says_what_it_is_for_where_it_ships_and_why_it_was_named`.

Each rule is shown red on a plant in the shape the real call site reads (rule 15): the real register's text and the real
`package.json`'s text, with the one row removed, or turned into prose, or its licence changed. Each case first shows the
same text clean and then asserts the one finding the case is about, so a plant that some other rule also catches proves
nothing here.

**The folders and files this test reads** (the conductor's scan-map row): `OspreyFlow_Build/spec/00_ARCHITECTURE.md`,
`OspreyFlow_Core/apps/workspace/package.json` and `OspreyFlow_Core/package-lock.json`. It walks no folder, and reads no
installed package (`node_modules`), because the lockfile records the licence of the version it pins.

**Proposed, not built (the count is the reason).** The general rule, "every run-time dependency of `apps/workspace` has a
named entry in section 7", is counted here by one definition only: this file's `named_entry()`, a section-7 table row whose
first cell is the package in backticks. `apps/workspace/package.json` declares 23 run-time dependencies; three have a named
entry (`graphology`, `zustand` and, from this slice, `oidc-client-ts`), so the rule would fail for **20**: 19 third-party
packages and the in-house `@ospreyflow/glass-shared`. The 20, in two groups:

* mentioned in section 7's prose by package name, with a licence, but in no table row (2): `@superset-ui/embedded-sdk` and
  `govuk-frontend`;
* with no table row and no mention by package name (18): `@fontsource/atkinson-hyperlegible-next` and
  `@fontsource/ibm-plex-mono` (the families are named in prose, not the packages), `@ospreyflow/glass-shared` (in-house),
  `@sigma/export-image`, `@sigma/node-border`, `@sigma/node-image`, `comlink`, `d3-polygon`, `echarts` ("Apache ECharts" in
  the rejected-alternatives table), `graphology-communities-louvain`, `graphology-metrics`, `graphology-types`, `immer`,
  `maplibre-gl` ("MapLibre GL JS" in the same table), `pmtiles`, `react`, `react-dom` and `sigma`.

That list is too long for a test with a stated reason and date on each, so this test holds to `oidc-client-ts` alone and the
owner decides whether the rest are named (the slice's report says so).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTER = REPO / "OspreyFlow_Build" / "spec" / "00_ARCHITECTURE.md"
WORKSPACE_PACKAGE = REPO / "OspreyFlow_Core" / "apps" / "workspace" / "package.json"
LOCKFILE = REPO / "OspreyFlow_Core" / "package-lock.json"

PACKAGE = "oidc-client-ts"
REGISTER_HEADING = "## 7. Licence register"
NEXT_HEADING = "## 8. "


def _section_7(register_text: str) -> str:
    start = register_text.index(REGISTER_HEADING)
    end = register_text.index(NEXT_HEADING, start)
    return register_text[start:end]


def named_entry(register_text: str, package: str) -> list[str] | None:
    """The cells of the table row in section 7 whose first cell is exactly `package` in backticks, or None.
    A mention in prose, or in a later cell of another row, is not a named entry."""
    for line in _section_7(register_text).splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] == f"`{package}`":
            return cells
    return None


def declared_range(package_json_text: str, package: str) -> str | None:
    return json.loads(package_json_text).get("dependencies", {}).get(package)


def locked_licence(lock_text: str, package: str) -> str | None:
    return json.loads(lock_text)["packages"].get(f"node_modules/{package}", {}).get("license")


def findings(register_text: str, package_json_text: str, lock_text: str) -> list[str]:
    """What is wrong with the package's entry, one sentence each; nothing if it is sound."""
    declared = declared_range(package_json_text, PACKAGE)
    if declared is None:
        return []  # not a dependency of the workspace: no entry is owed
    row = named_entry(register_text, PACKAGE)
    if row is None:
        return [f"{PACKAGE} is a run-time dependency of apps/workspace and section 7 has no named entry for it"]
    out: list[str] = []
    if len(row) != 5:
        out.append(f"the {PACKAGE} row has {len(row)} cells, not the five of the table's shape")
        return out
    _, rng, licence, why, where = row
    if rng != f"`{declared}`":
        out.append(f"the entry's range {rng} is not the declared range `{declared}`")
    locked = locked_licence(lock_text, PACKAGE)
    if locked is None:
        out.append(f"the lockfile records no licence for {PACKAGE}")
    elif licence != locked:
        out.append(f"the entry's licence {licence!r} is not the lockfile's {locked!r}")
    for needle, label in (
        ("auth/userManager.ts", "the sign-in code it serves"),
        ("auth/oidcConfig.ts", "the sign-in configuration it serves"),
    ):
        if needle not in why:
            out.append(f"the entry's reason does not name {label} ({needle})")
    if "workspace bundle" not in where:
        out.append("the entry does not say it ships in the workspace bundle")
    if "the owner, 20 November 2026" not in where + why:
        out.append("the entry does not say why it was named: 'the owner, 20 November 2026'")
    return out


def _real() -> tuple[str, str, str]:
    return (
        REGISTER.read_text(encoding="utf-8"),
        WORKSPACE_PACKAGE.read_text(encoding="utf-8"),
        LOCKFILE.read_text(encoding="utf-8"),
    )


def _without_the_row(register_text: str) -> str:
    kept = [ln for ln in register_text.splitlines(keepends=True) if not ln.startswith(f"| `{PACKAGE}` |")]
    assert len(kept) < len(register_text.splitlines(keepends=True)), "the plant removed nothing: no row to remove"
    return "".join(kept)


def test_oidc_client_ts_has_a_named_entry() -> None:
    register, package_json, lock = _real()
    assert declared_range(package_json, PACKAGE) is not None, (
        f"{PACKAGE} is no longer a dependency of apps/workspace: retire this test, with the owner's word"
    )
    assert named_entry(register, PACKAGE) is not None, (
        f"{PACKAGE} ships in the workspace bundle and section 7 of spec/00_ARCHITECTURE.md has no table row naming it"
    )
    assert findings(register, package_json, lock) == []


def test_the_entry_states_the_licence_and_range_the_package_has() -> None:
    register, package_json, lock = _real()
    row = named_entry(register, PACKAGE)
    assert row is not None
    assert row[2] == locked_licence(lock, PACKAGE)
    assert row[1] == f"`{declared_range(package_json, PACKAGE)}`"


def test_the_entry_says_what_it_is_for_where_it_ships_and_why_it_was_named() -> None:
    register, package_json, lock = _real()
    row = named_entry(register, PACKAGE)
    assert row is not None
    assert findings(register, package_json, lock) == []
    assert "workspace bundle" in row[4]


# --- the plants (rule 15): the real texts, with one thing changed --------------------------------------------------


def test_a_register_without_the_row_is_flagged() -> None:
    """The plant: the real register with the new row deleted, which is the state of main before this slice."""
    register, package_json, lock = _real()
    assert findings(register, package_json, lock) == []  # the same text, clean
    got = findings(_without_the_row(register), package_json, lock)
    assert got == [f"{PACKAGE} is a run-time dependency of apps/workspace and section 7 has no named entry for it"]


def test_a_mention_in_prose_is_not_a_named_entry() -> None:
    """The plant: the row replaced by a sentence naming the package in backticks, which states no licence."""
    register, package_json, lock = _real()
    prose = f"The sign-in library `{PACKAGE}` is used by the Glass.\n"
    planted = "".join(
        prose if ln.startswith(f"| `{PACKAGE}` |") else ln for ln in register.splitlines(keepends=True)
    )
    assert planted != register
    assert findings(planted, package_json, lock) == [
        f"{PACKAGE} is a run-time dependency of apps/workspace and section 7 has no named entry for it"
    ]


def test_an_entry_with_the_wrong_licence_is_flagged() -> None:
    """The plant: the row written from memory with another licence than the lockfile records."""
    register, package_json, lock = _real()
    assert findings(register, package_json, lock) == []
    row = named_entry(register, PACKAGE)
    assert row is not None
    lines = register.splitlines(keepends=True)
    at = next(i for i, ln in enumerate(lines) if ln.startswith(f"| `{PACKAGE}` |"))
    assert row[2] != "MIT"
    lines[at] = lines[at].replace(f"| {row[2]} |", "| MIT |", 1)
    planted = "".join(lines)
    assert planted != register
    got = findings(planted, package_json, lock)
    assert got == [f"the entry's licence 'MIT' is not the lockfile's {row[2]!r}"]


def test_an_entry_left_behind_by_an_upgrade_is_flagged() -> None:
    """The plant: the workspace declares another range than the row records."""
    register, package_json, lock = _real()
    declared = declared_range(package_json, PACKAGE)
    assert declared is not None
    planted_json = package_json.replace(f'"{PACKAGE}": "{declared}"', f'"{PACKAGE}": "^9.0.0"')
    assert planted_json != package_json
    assert findings(register, planted_json, lock) == [
        f"the entry's range `{declared}` is not the declared range `^9.0.0`"
    ]


def _with_the_row_changed(register: str, old: str, new: str) -> str:
    """The real register with `old` replaced by `new` inside the package's row alone, and nowhere else."""
    lines = register.splitlines(keepends=True)
    at = next(i for i, ln in enumerate(lines) if ln.startswith(f"| `{PACKAGE}` |"))
    assert old in lines[at], f"the plant found nothing to change in the row: {old!r}"
    lines[at] = lines[at].replace(old, new)
    planted = "".join(lines)
    assert planted != register
    return planted


def test_a_reason_that_stops_naming_a_sign_in_file_is_flagged() -> None:
    """The plants: the row loses `auth/userManager.ts`, then `auth/oidcConfig.ts`, each on its own."""
    register, package_json, lock = _real()
    assert findings(register, package_json, lock) == []  # the same text, clean
    for needle, label in (
        ("auth/userManager.ts", "the sign-in code it serves"),
        ("auth/oidcConfig.ts", "the sign-in configuration it serves"),
    ):
        planted = _with_the_row_changed(register, needle, "auth/elsewhere.ts")
        assert findings(planted, package_json, lock) == [
            f"the entry's reason does not name {label} ({needle})"
        ]


def test_an_entry_that_does_not_say_it_ships_in_the_workspace_bundle_is_flagged() -> None:
    """The plant: the row's 'workspace bundle' replaced by another place."""
    register, package_json, lock = _real()
    assert findings(register, package_json, lock) == []
    planted = _with_the_row_changed(register, "workspace bundle", "somewhere")
    assert findings(planted, package_json, lock) == ["the entry does not say it ships in the workspace bundle"]


def test_an_entry_that_does_not_say_who_named_it_and_when_is_flagged() -> None:
    """The plant: the row's 'the owner, 20 November 2026' replaced by an unattributed, undated phrase."""
    register, package_json, lock = _real()
    assert findings(register, package_json, lock) == []
    planted = _with_the_row_changed(register, "the owner, 20 November 2026", "someone, once")
    assert findings(planted, package_json, lock) == [
        "the entry does not say why it was named: 'the owner, 20 November 2026'"
    ]


def test_a_row_of_the_wrong_shape_is_flagged() -> None:
    """The plant: the row loses its last cell, so it has four cells, not the table's five."""
    register, package_json, lock = _real()
    assert findings(register, package_json, lock) == []
    row = named_entry(register, PACKAGE)
    assert row is not None and len(row) == 5
    lines = register.splitlines(keepends=True)
    at = next(i for i, ln in enumerate(lines) if ln.startswith(f"| `{PACKAGE}` |"))
    lines[at] = "| " + " | ".join(row[:4]) + " |\n"
    assert findings("".join(lines), package_json, lock) == [f"the {PACKAGE} row has 4 cells, not the five of the table's shape"]


def test_a_lockfile_with_no_licence_for_the_package_is_flagged() -> None:
    """The plant: the real lockfile with the package's `license` field removed."""
    register, package_json, lock = _real()
    assert findings(register, package_json, lock) == []
    data = json.loads(lock)
    del data["packages"][f"node_modules/{PACKAGE}"]["license"]
    assert findings(register, package_json, json.dumps(data)) == [f"the lockfile records no licence for {PACKAGE}"]


def test_a_new_dependency_is_not_swept_in_by_the_plant_rule() -> None:
    """The rule is about this package alone (the general rule is a proposal, see the docstring): a register with
    no row is clean when the workspace does not declare the package."""
    register, package_json, lock = _real()
    without = re.sub(rf'\s*"{re.escape(PACKAGE)}": "[^"]*",?', "", package_json)
    assert declared_range(without, PACKAGE) is None
    assert findings(_without_the_row(register), without, lock) == []
