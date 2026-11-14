"""The user guide's §5.2 on the cap's third choice (ADR-151), held to the code: the view's limits are
the working set's own figures, and each claim the guide makes about the job is one the code keeps.
Red with the guide's old sentence (reduce, or save a smaller view, and nothing of a batch job), and
with either figure changed in the code."""

from __future__ import annotations

import re
from pathlib import Path

from services.api import batch_expansion
from services.api.working_set.models import MAX_EDGES, MAX_NODES

GUIDE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core" / "docs" / "user-guide.md"


def _section_5_2() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index("### 5.2 The graph")
    return text[start : text.index("\n### ", start + 1)]


def test_section_5_2_offers_the_batch_job_at_the_cap() -> None:
    section = _section_5_2()
    flat = re.sub(r"\s+", " ", section)
    # The cap prompt's button, exactly (case's canvas/CapRefusalPrompt.tsx).
    assert "**Run as a batch job**" in flat
    assert "saves what it finds as a private view of the case" in flat
    assert "nothing is added to the case's own graph" in flat
    assert "its result opens as your private view" in flat
    assert "One batch job of yours runs in a case at a time" in flat
    # The Glass panel's own sentence, quoted whole (case-b's BatchExpansion.tsx, after its review):
    # the Conduit's 409 follows the reader's running batch in the case, and only while it runs.
    assert (
        '"Closing this does not stop the job. While it runs, asking for a batch expansion in this '
        'case again follows it."' in flat
    )


def test_the_guides_figures_are_the_views_limits() -> None:
    flat = re.sub(r"\s+", " ", _section_5_2())
    assert f"more than **{MAX_NODES:,}** nodes or **{MAX_EDGES:,}** links" in flat
    assert (batch_expansion.MAX_NODES, batch_expansion.MAX_EDGES) == (MAX_NODES, MAX_EDGES)
    # "narrow it by link type, depth or dates": the refusal's own advice.
    assert "Narrow it by link type, depth or dates" in batch_expansion._NARROW  # noqa: SLF001
    assert "narrow it by link type, depth or dates" in flat
