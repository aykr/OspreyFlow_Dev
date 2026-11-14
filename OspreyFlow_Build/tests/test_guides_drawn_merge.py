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


def merge_routes() -> dict[str, str]:
    """Each route on a drawing's merge (`/v1/datasets/{dataset_id}/merge…`): its decorator's arguments and its
    signature, as `app.py` declares them."""
    found = {}
    for m in re.finditer(r'@app\.(?:get|post|put|delete)\(\s*"(/v1/datasets/\{dataset_id\}/merge[^"]*)"(.*?)\)\s*\nasync def \w+\((.*?)\)', ROUTES, re.DOTALL):
        found[m.group(1)] = m.group(2) + " | " + m.group(3)
    return found


def test_section_7_8_says_who_may_merge_as_the_routes_and_service_do() -> None:
    """The right on every route; the dataset read as the Studio's (a case of the reader's that reads it); the target
    of the drawing's own unit, offered and checked again at the merge."""
    assert "_MERGES = [Depends(require_right(Right.MERGE_DATASETS))]" in ROUTES
    routes = merge_routes()
    assert len(routes) >= 4, routes
    assert [p for p, args in routes.items() if "dependencies=_MERGES" not in args or "StudioDatasetDep" not in args] == []
    assert "or dataset.owning_unit != drawn.owning_unit" in SERVICE and "or target.owning_unit != drawing.owning_unit" in SERVICE
    text = merge_paragraph()
    assert "an Author of the target dataset holding `merge_datasets`, who reads the drawing through its home case" in text
    assert "It is merged only into a dataset of the drawing's unit." in text


def test_the_guides_say_a_match_is_proposed_never_merged_in_storage() -> None:
    """Each match the merge writes is a `SAME_AS` whose provenance `_inferred` makes `INFERRED` (rule 5): a link, so
    nothing is merged in storage (rule 6)."""
    inferred = re.search(r"def _inferred\(.*?\) -> Provenance: .*? return Provenance\( state=ProvenanceState\.(\w+),", SERVICE)
    assert inferred and inferred.group(1) == "INFERRED"
    # The match's own link, the chosen pair's (not only the retyped copy's): a SAME_AS made by `_inferred`.
    assert 'provenance=self._inferred(record, f"{r.drawn}:{r.loaded}", r.score, now),' in SERVICE
    assert "each chosen one written as a proposed match (inferred and scored) that a person confirms later" in merge_paragraph()
    assert "proposed as scored links for a person to confirm (never merged in storage)" in guide("architecture")


def test_section_7_8_says_what_follows_the_merge_as_the_service_does() -> None:
    assert "await self.datasets.merge_drawn(" in SERVICE, "the home case reads the target, the drawn dataset read-only"
    assert "await self.views.merge_boards(record.case_id, record.load_id, drawn)" in SERVICE, "its boards become views"
    assert "async def view_annotations(" in SERVICE
    text = merge_paragraph()
    assert "Afterwards the drawing's home case reads the target, and the drawn dataset read-only" in text
    assert "each of its boards becomes a view" in text


def writers_reading_in_full() -> list[str]:
    """Every module in `services/` and `scripts/` that enters `sources_in_full()` (packages/ontology/handling.py)."""
    return sorted(
        str(p.relative_to(CORE)) for root in ("services", "scripts") for p in (CORE / root).rglob("*.py")
        if "test" not in p.name and "with sources_in_full()" in p.read_text(encoding="utf-8")
    )  # fmt: skip


def named_writers(text: str) -> list[str]:
    m = re.search(r"The writers that do this today are (.*?)\. The working set", text)
    assert m, "developer guide §7.5's writers"
    return sorted(re.findall(r"`((?:services|scripts)/[^`]+\.py)`", m.group(1)))


def test_section_7_5_names_every_writer_that_reads_in_full() -> None:
    assert named_writers(guide("developer")) == writers_reading_in_full()


def test_the_writers_check_flags_one_left_out() -> None:
    """The guide's own list before this sweep: three writers missing."""
    old = ("The writers that do this today are `services/api/link_changes.py`, `services/api/entity_pictures.py`, "
           "`services/extract/writer.py`, `services/resolve/trigger.py`, `services/api/pipeline_run.py` and "
           "`services/api/alert_queue.py`. The working set")  # fmt: skip
    missing = sorted(set(writers_reading_in_full()) - set(named_writers(old)))
    assert missing == ["scripts/build_local_basemap.py", "services/api/case_gazetteers.py", "services/api/drawn_merge.py",
                       "services/api/grading.py"]  # fmt: skip
