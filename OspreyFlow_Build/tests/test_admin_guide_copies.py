"""The administration guide's two copies are one text (ADR-114 decision 5, and Amendment 15's "section
numbers kept equal"): the specification's (`spec/10_ADMINISTRATION_GUIDE.md`) and the install package's
(`docs/administration-guide.md`). The shipped guide opens on its own (document control, how OspreyFlow
is built) and shows screenshots the specification's folder does not hold; from section 1 to its end,
everything else is the same. Without this case the specification's copy drifted for versions while
`test_admin_guide.py` passed on both (it reads the schema's settings and the commands, not the prose):
§1a, the HTTP or HTTPS rules and 1.94's corrections were missing from it on 14 November 2026 (rule 12).
"""

from __future__ import annotations

import re
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
SHIPPED = (BUILD.parent / "OspreyFlow_Core" / "docs" / "administration-guide.md").read_text(encoding="utf-8")
SPEC = (BUILD / "spec" / "10_ADMINISTRATION_GUIDE.md").read_text(encoding="utf-8")
FIRST = "## 1. Choosing a mode\n"
#: A screenshot on a line of its own, and the blank line after it: the shipped guide's alone.
SCREENSHOT = re.compile(r"^!\[[^\n]*\]\(images/[^)\n]*\)\n\n?", re.MULTILINE)


def numbered(text: str) -> str:
    assert text.count(FIRST) == 1, "section 1's heading, once"
    return text[text.index(FIRST) :]


def test_the_specification_s_copy_is_the_shipped_guide_from_section_1() -> None:
    shipped = SCREENSHOT.sub("", numbered(SHIPPED))
    spec = numbered(SPEC)
    if spec != shipped:
        a, b = spec.splitlines(), shipped.splitlines()
        first = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), min(len(a), len(b)))
        raise AssertionError(
            f"spec/10 differs from the shipped guide at section 1's line {first + 1}:\n"
            f"  spec:    {a[first] if first < len(a) else '<end>'}\n"
            f"  shipped: {b[first] if first < len(b) else '<end>'}"
        )


def test_the_specification_s_copy_shows_no_screenshot_and_keeps_no_document_control() -> None:
    assert not SCREENSHOT.search(SPEC), "a screenshot in spec/, where images/ is not"
    assert "<!-- document-control:begin -->" not in SPEC
