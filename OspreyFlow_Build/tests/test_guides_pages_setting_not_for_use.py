"""No document the release ships says the pages setting is turned on, enabled for a deployment, or for use.

The owner's condition 1 of 23 November 2026 (a release blocker, PL7f): until PL7f has merged and he has said so, no guide
or release note describes `pages.enabled` as available. PL7f's own round 7 found one sentence left behind: Appendix A's row
for the `pages` section said the setting was "off, and turned on for one deployment at a time by the owner", directly above
the reworded `pages.enabled` row. Nothing read the documents against the condition; this does (rule 12).

Walks: `OspreyFlow_Core/docs/*.md` (the four guides) and `OspreyFlow_Core/CHANGELOG.md` (the release notes), and the
administration guide's copy under `OspreyFlow_Build/spec/`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "OspreyFlow_Core"
SHIPPED = (
    *sorted((CORE / "docs").glob("*.md")),
    CORE / "CHANGELOG.md",
    ROOT / "OspreyFlow_Build" / "spec" / "10_ADMINISTRATION_GUIDE.md",
)

# A sentence is about the setting when it names it, or names the page service, or is the Appendix A row of the `pages` section.
ABOUT = re.compile(r"`pages\.enabled`|`pages`|page service|pages service|server-rendered pages", re.IGNORECASE)
# What turns the setting on, hands it to a deployment, or calls it usable.
AVAILABLE = re.compile(
    r"turned on|turns? (?:it|the page service|the pages service|the setting) on|switched on|enabled for|"
    r"(?:is|are|now) (?:enabled|available|on)\b|(?<!not )(?<!no )for use|available|in use",
    re.IGNORECASE,
)
# The sentence that says the opposite, in the words the release uses.
NOT_AVAILABLE = re.compile(
    r"\bnot for use|nothing (?:else )?(?:is |turns )|not yet in any deployment|is off\b|not available",
    re.IGNORECASE,
)


def sentences(text: str) -> list[str]:
    """Paragraphs (a bullet's wrapped lines joined) split at a full stop, a semicolon-free clause; a table row is one cell
    at a time."""
    out: list[str] = []
    for line in re.sub(r"\n(?=  \S)", " ", text).splitlines():
        for cell in line.split("|") if line.startswith("|") else [line]:
            out += [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`*])", cell.strip()) if s]
    return out


def says_the_setting_is_available(text: str) -> list[str]:
    return [s for s in sentences(text) if ABOUT.search(s) and AVAILABLE.search(s) and not NOT_AVAILABLE.search(s)]


def test_no_shipped_document_says_the_pages_setting_is_turned_on_or_for_use() -> None:
    found = {p.name: says_the_setting_is_available(p.read_text(encoding="utf-8")) for p in SHIPPED}
    assert {k: v for k, v in found.items() if v} == {}


def test_the_scan_reads_every_shipped_document() -> None:
    assert [p.name for p in SHIPPED[:-2]] == [
        "administration-guide.md",
        "architecture-guide.md",
        "developer-guide.md",
        "user-guide.md",
    ]
    assert all(p.is_file() for p in SHIPPED)


def test_appendix_a_s_pages_row_as_it_was_is_flagged() -> None:
    """The row as the guide carried it at round 7, the shape the scan really reads (a table line)."""
    row = (
        "| `pages` | section | — | Whether the deployment runs the page service (the server-rendered pages): off, "
        "and turned on for one deployment at a time by the owner. |\n"
    )
    assert len(says_the_setting_is_available(row)) == 1


def test_the_revision_row_as_it_was_is_flagged() -> None:
    row = (
        "| 2.35 | 2026-11-22 | Appendix A: `pages.enabled`, whether the deployment runs the page service (the "
        "server-rendered pages), from the schema (ADR-152 Amendment 3): false by default, turned on for one deployment at "
        "a time by the owner, and nothing reads it yet. |\n"
    )
    assert len(says_the_setting_is_available(row)) == 1


def test_other_ways_of_saying_it_is_available_are_flagged() -> None:
    for said in (
        "The page service is available on the Small shape.\n",
        "- Set `pages.enabled: true` to turn it on; the page service is then in use.\n",
        "`pages.enabled` is enabled for the demo deployment.\n",
        "The page service is now on for this deployment.\n",
    ):
        assert says_the_setting_is_available(said), said


def test_the_reworded_sentences_are_not_flagged() -> None:
    for said in (
        "| `pages` | section | — | The page service (the server-rendered pages): the setting exists and is off; it is not "
        "for use yet. |\n",
        "| `pages.enabled` | bool | false | Whether this deployment runs the page service, the server-rendered pages. The "
        "setting exists and is off; it is not for use yet, and nothing is switched on by it for a deployment you run. "
        "true or false, nothing else. |\n",
        "- **`pages.enabled` exists in `osprey.yaml`, and is off. It is not for use yet.**\n",
    ):
        assert says_the_setting_is_available(said) == [], said
