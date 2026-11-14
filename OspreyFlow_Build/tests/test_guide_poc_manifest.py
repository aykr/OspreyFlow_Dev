"""The administration guide §6a.2's poc tables are the poc manifest's own, as `python -m harness.cloud_platform.manifest
tables` prints them (ROUTE_052 rules: the manifest is the one source; part one's D5). The block between the guide's
`manifest:begin` and `manifest:end` markers is that output, its headings set under §6a.2 and its title line left out
(the guide names its own release). `--write` puts it in (rule 12: a hand-kept copy of the manifest drifts)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
GUIDE = BUILD.parent / "OspreyFlow_Core" / "docs" / "administration-guide.md"
BEGIN, END = "<!-- manifest:begin -->", "<!-- manifest:end -->"


def expected() -> str:
    from harness.cloud_platform import manifest

    lines = manifest.tables().splitlines()
    assert lines and lines[0].startswith("# OspreyFlow "), "the tables' title line"
    body = "\n".join(re.sub(r"^## ", "#### ", line) for line in lines[1:]).strip("\n")
    return f"{BEGIN}\n\n{body}\n\n{END}"


def in_guide(text: str) -> str:
    m = re.search(rf"{re.escape(BEGIN)}.*?{re.escape(END)}", text, re.DOTALL)
    assert m, "the guide's manifest block"
    return m.group(0)


def test_section_6a2_s_poc_tables_are_the_manifest_s() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert text.index("### 6a.2 ") < text.index(BEGIN) < text.index("### 6a.3 "), "in §6a.2"
    assert in_guide(text) == expected(), "run `python -m tests.test_guide_poc_manifest --write` and read what changed"


def test_a_table_kept_by_hand_is_flagged() -> None:
    planted = GUIDE.read_text(encoding="utf-8").replace("| api | Deployment | 1 |", "| api | Deployment | 2 |", 1)
    assert in_guide(planted) != expected()


if __name__ == "__main__" and sys.argv[1:] == ["--write"]:
    core = BUILD.parent / "OspreyFlow_Core"
    sys.path[:0] = [str(core), str(core / "packages")]  # as pytest.ini's pythonpath gives them
    text = GUIDE.read_text(encoding="utf-8")
    GUIDE.write_text(text.replace(in_guide(text), expected()), encoding="utf-8")
    print("administration-guide.md §6a.2: the poc tables written from the manifest")
