"""Every guide's header names the release it describes: the CHANGELOG's latest release (the docs lane's step 5 sweep,
§2; rule 12). The headers said "For OspreyFlow v0.5.0" through v0.5.1 and up to v0.5.2's cut, because nothing read
them against the release; this does, so a cut that leaves a header behind is red.
"""

from __future__ import annotations

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
GUIDES = ("user", "administration", "developer", "architecture")
HEADER = re.compile(r"^\*\*Version \d+\.\d+\*\* · \d{4}-\d{2}-\d{2} · For OspreyFlow (v\d+\.\d+\.\d+) · Issued$", re.MULTILINE)


def latest_release(changelog: str) -> str:
    m = re.search(r"^## (v\d+\.\d+\.\d+) — \d{4}-\d{2}-\d{2}$", changelog, re.MULTILINE)
    assert m, "no released version in the CHANGELOG"
    return m.group(1)


def headers_behind(texts: dict[str, str], release: str) -> list[str]:
    found = []
    for name, text in texts.items():
        named = HEADER.findall(text)
        if named != [release]:
            found.append(f"{name}: {named or 'no header'}")
    return found


def test_every_guide_s_header_names_the_latest_release() -> None:
    release = latest_release((CORE / "CHANGELOG.md").read_text(encoding="utf-8"))
    texts = {g: (CORE / "docs" / f"{g}-guide.md").read_text(encoding="utf-8") for g in GUIDES}
    assert headers_behind(texts, release) == []


def test_a_header_left_behind_is_flagged() -> None:
    """v0.5.1's headers, against v0.5.2's CHANGELOG."""
    log = "# Changelog\n\n## Unreleased\n\n## v0.5.2 — 2026-11-15\n\n- x\n\n## v0.5.1 — 2026-11-14\n"
    old = {"user": "**Version 1.65** · 2026-11-14 · For OspreyFlow v0.5.0 · Issued\n", "developer": "no header here\n"}
    assert headers_behind(old, latest_release(log)) == ["user: ['v0.5.0']", "developer: no header"]
