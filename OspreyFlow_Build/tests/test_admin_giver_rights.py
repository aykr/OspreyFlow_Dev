"""Route A2 (v0.5.2): the Glass offers a role only when the giver may give it, by the same list of administration
rights the Conduit's giver rule reads (`schemas.rights.ADMINISTRATION_RIGHTS`, `custom_roles.giver_may_give`, ADR-145
Amendment 5). People.tsx keeps its own copy of the list, so the two are held together here: a right made an
administration right in one place and not the other would offer a role the Conduit refuses, or withhold one it
allows. Rule 15: the copy is read from the file the Glass builds, by its own name."""

from __future__ import annotations

import re
from pathlib import Path

from schemas.rights import ADMINISTRATION_RIGHTS

PEOPLE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core/apps/workspace/src/admin/sections/People.tsx"


def glass_list(source: str) -> list[str]:
    m = re.search(r"export const ADMINISTRATION_RIGHTS = \[(.*?)\] as const", source, re.S)
    assert m, "People.tsx no longer has ADMINISTRATION_RIGHTS"
    return re.findall(r'"([a-z_]+)"', m.group(1))


def test_the_glass_withholds_by_the_conduit_s_administration_rights() -> None:
    glass = glass_list(PEOPLE.read_text(encoding="utf-8"))
    assert len(glass) == len(set(glass))
    assert set(glass) == {r.value for r in ADMINISTRATION_RIGHTS}


def test_the_check_sees_a_right_missing_from_the_glass_s_copy() -> None:
    source = PEOPLE.read_text(encoding="utf-8").replace('"read_audit", ', "", 1)
    assert {r.value for r in ADMINISTRATION_RIGHTS} - set(glass_list(source)) == {"read_audit"}
