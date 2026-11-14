"""A drawn dataset merged into another, as the developer guide §7.8 and the architecture guide §5 give it, held to the
Ingest Studio's screen (`ingest/runs/drawnMerge.tsx`), the Conduit's routes and `services/api/drawn_merge.py`
(ADR-143 Amendment 2 decisions 6 and 7, Amendment 3, Amendment 7). Both guides called it "Coming" while it was on
main, screen and all; the docs lane's step 5 sweep read the code before writing it as built (rule 12).
"""

from __future__ import annotations

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
SCREEN = re.sub(r"\s+", " ", (CORE / "apps/workspace/src/ingest/runs/drawnMerge.tsx").read_text(encoding="utf-8"))
SERVICE = re.sub(r"\s+", " ", (CORE / "services/api/drawn_merge.py").read_text(encoding="utf-8"))
ROUTES = (CORE / "services/api/app.py").read_text(encoding="utf-8")


def guide(name: str) -> str:
    return re.sub(r"\s+", " ", (CORE / "docs" / f"{name}-guide.md").read_text(encoding="utf-8"))


def merge_paragraph() -> str:
    m = re.search(r"\*\*Merging a drawn dataset into another\.\*\*.*?(?= A waiting promotion grows overdue)", guide("developer"))
    assert m, "developer guide §7.8's merge"
    return m.group(0)


def test_no_guide_calls_the_merge_coming() -> None:
    assert [g for g in ("developer", "architecture") if re.search(r"\*\*Coming:\*\* merging a drawn dataset", guide(g))] == []


def test_section_7_8_names_the_four_steps_as_the_screen_heads_them() -> None:
    steps = re.findall(r'"label"\}>(\d\. [A-Z][a-z ]+)</h5>', SCREEN)
    assert steps == ["1. Map the models", "2. Match", "3. Dry run"]
    assert '{sheet.policy === "author_promotes" ? "4. Merge" : "4. Send for review"}' in SCREEN
    text = merge_paragraph()
    assert all(f"**{step}**" in text for step in steps)
    assert "**4. Merge**, or **4. Send for review** where the target's policy asks for a second person" in text
    assert "> Merge into a dataset… </" in SCREEN and "In **4 Runs**, *Merge into a dataset…*" in text


def test_section_7_8_says_who_may_merge_as_the_routes_and_service_do() -> None:
    assert "`merge_datasets` on every route" in ROUTES
    assert "an Author of the **target** dataset" in SERVICE and "who holds `merge_datasets`" in SERVICE
    assert "an Author of the target dataset holding `merge_datasets`" in merge_paragraph()


def test_the_guides_say_a_match_is_proposed_never_merged_in_storage() -> None:
    assert "a scored, `inferred` `SAME_AS` (rule 5)" in SERVICE and "nothing is collapsed in storage (rule 6)" in SERVICE
    assert "each chosen one written as a proposed match (inferred and scored) that a person confirms later" in merge_paragraph()
    assert "proposed as scored links for a person to confirm (never merged in storage)" in guide("architecture")


def test_section_7_8_says_what_follows_the_merge_as_the_service_does() -> None:
    for code in ("the drawing's home case reads the target, and its drawn dataset read-only",
                 "each of its boards becomes a view", "read through each reader's own handling"):  # fmt: skip
        assert code in SERVICE, code
    text = merge_paragraph()
    assert "Afterwards the drawing's home case reads the target, and the drawn dataset read-only" in text
    assert "each of its boards becomes a view" in text


# ---------------------------------------------------------------- developer guide §7.5's writers that read in full


def writers_reading_in_full() -> list[str]:
    """Every module in `services/` that enters `sources_in_full()` (packages/ontology/handling.py)."""
    return sorted(
        str(p.relative_to(CORE)) for p in (CORE / "services").rglob("*.py")
        if "test" not in p.name and "with sources_in_full()" in p.read_text(encoding="utf-8")
    )  # fmt: skip


def named_writers(text: str) -> list[str]:
    m = re.search(r"The writers that do this today are (.*?)\. The working set", text)
    assert m, "developer guide §7.5's writers"
    return sorted(re.findall(r"`(services/[^`]+\.py)`", m.group(1)))


def test_section_7_5_names_every_writer_that_reads_in_full() -> None:
    assert named_writers(guide("developer")) == writers_reading_in_full()


def test_the_writers_check_flags_one_left_out() -> None:
    """The guide's own list before this sweep: three writers missing."""
    old = ("The writers that do this today are `services/api/link_changes.py`, `services/api/entity_pictures.py`, "
           "`services/extract/writer.py`, `services/resolve/trigger.py`, `services/api/pipeline_run.py` and "
           "`services/api/alert_queue.py`. The working set")  # fmt: skip
    missing = sorted(set(writers_reading_in_full()) - set(named_writers(old)))
    assert missing == ["services/api/case_gazetteers.py", "services/api/drawn_merge.py", "services/api/grading.py"]
