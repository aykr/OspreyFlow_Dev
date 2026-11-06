"""ADR-110 Amendment 6 point 1, an incremental refresh: only the rows past the kept watermark are
read, a row at or below it is counted, and the watermark the run reaches is the highest value it
read. `services/ingest/watermark.read_past` decides; nothing here touches a store.

What a mistake would do, and the case that catches it:

- a row at or below the watermark read again (`test_only_rows_past_the_watermark_are_read`);
- numbers compared as text, so "10" sorts below "9"
  (`test_numbers_are_compared_as_numbers`);
- times compared as text, so a later time with another offset sorts first
  (`test_times_are_compared_as_instants`);
- the watermark moved back by a file whose rows all lie below it
  (`test_the_watermark_never_moves_back`);
- a row with no watermark value lost (`test_a_row_with_no_value_is_read_and_counted`);
- a value that cannot be compared with the kept one compared anyway, or named by its content
  (`test_a_value_of_another_kind_than_the_kept_one_is_refused_by_its_row`);
- a missing column read as no watermark at all (`test_a_file_without_the_column_is_refused`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from services.ingest.watermark import WatermarkRefused, read_past

from schemas.ingest import SourceWatermark
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)


def _rows(column: str, *values: str) -> list[dict[str, str]]:
    return [{"id": f"r{i}", column: v} for i, v in enumerate(values)]


def _kept(value: str, kind: str = "number", column: str = "seq") -> SourceWatermark:
    return SourceWatermark(source_id="src-1", column=column, kind=kind, value=value)  # type: ignore[arg-type]


def test_a_first_read_reads_every_row_and_reaches_the_highest() -> None:
    read = read_past(_rows("seq", "3", "1", "2"), source_id="src-1", column="seq", kept=None)
    assert [r["id"] for r in read.rows] == ["r0", "r1", "r2"]
    assert read.row_numbers == [0, 1, 2]
    assert (read.below, read.without) == (0, 0)
    assert read.reached == _kept("3")
    assert read.notes == []


def test_only_rows_past_the_watermark_are_read() -> None:
    read = read_past(
        _rows("seq", "1", "2", "3", "4"), source_id="src-1", column="seq", kept=_kept("2")
    )
    assert [r["id"] for r in read.rows] == ["r2", "r3"]
    assert read.row_numbers == [2, 3], "the file's own row numbers, for the report"
    assert read.below == 2, "a row at the watermark is not past it"
    assert read.reached == _kept("4")
    assert read.notes == ["2 rows at or below the watermark (seq) were not read"]


def test_numbers_are_compared_as_numbers() -> None:
    read = read_past(_rows("seq", "9", "10", "8.5"), source_id="src-1", column="seq", kept=None)
    assert read.reached == _kept("10")
    again = read_past(
        _rows("seq", "9", "10", "11"), source_id="src-1", column="seq", kept=_kept("9.5")
    )
    assert [r["seq"] for r in again.rows] == ["10", "11"]


def test_times_are_compared_as_instants() -> None:
    rows = _rows("at", "2026-11-01T10:00:00+01:00", "2026-11-01T09:30:00+00:00")
    read = read_past(rows, source_id="src-1", column="at", kept=None)
    assert read.reached == _kept("2026-11-01T09:30:00+00:00", "time", "at")
    kept = _kept("2026-11-01T09:15:00Z", "time", "at")
    again = read_past(rows, source_id="src-1", column="at", kept=kept)
    assert [r["id"] for r in again.rows] == ["r1"], "10:00 at +01:00 is 09:00 UTC, below 09:15"


def test_text_is_compared_as_text_when_the_values_are_neither() -> None:
    read = read_past(_rows("batch", "b-07", "b-10"), source_id="src-1", column="batch", kept=None)
    assert read.reached == _kept("b-10", "text", "batch")


def test_the_watermark_never_moves_back() -> None:
    read = read_past(_rows("seq", "1", "2"), source_id="src-1", column="seq", kept=_kept("5"))
    assert read.rows == [] and read.below == 2
    assert read.reached == _kept("5")


def test_a_row_with_no_value_is_read_and_counted() -> None:
    read = read_past(_rows("seq", "", "3", "  "), source_id="src-1", column="seq", kept=_kept("2"))
    assert [r["id"] for r in read.rows] == ["r0", "r1", "r2"]
    assert read.without == 2
    assert read.reached == _kept("3")
    assert read.notes == [
        "2 rows had no value in the watermark column (seq) and were read; their deduplication key "
        "keeps them from loading twice"
    ]


def test_a_value_of_another_kind_than_the_kept_one_is_refused_by_its_row() -> None:
    with pytest.raises(WatermarkRefused) as refused:
        read_past(
            _rows("seq", "4", "SECRET-NAME"), source_id="src-1", column="seq", kept=_kept("2")
        )
    words = str(refused.value)
    assert "row 2" in words and "numbers" in words
    assert "SECRET-NAME" not in words, "a refusal names the row, never its content"


def test_a_changed_column_reads_the_whole_file_and_says_so() -> None:
    read = read_past(_rows("at", "1", "2"), source_id="src-1", column="at", kept=_kept("9"))
    assert len(read.rows) == 2 and read.below == 0
    assert read.reached == _kept("2", column="at")
    assert read.notes == ["the watermark column changed from seq to at, so every row was read"]


def test_a_file_without_the_column_is_refused() -> None:
    with pytest.raises(WatermarkRefused) as refused:
        read_past([{"id": "r0"}], source_id="src-1", column="seq", kept=None)
    assert "seq" in str(refused.value)
    # An empty file has no header to judge: nothing is read and the watermark stays.
    empty = read_past([], source_id="src-1", column="seq", kept=_kept("2"))
    assert empty.rows == [] and empty.reached == _kept("2")


# --- the run's own refusals (ADR-110 Amendment 6 point 2) ---------------------------------------


async def test_an_incremental_read_with_no_ledger_or_no_key_is_refused_before_anything_loads(
    tmp_path: Path,
) -> None:
    """A watermark is asked of the ledger and kept with the record, and a row with no watermark
    value is kept from loading twice by its key: without either the run is refused, in words."""
    from services.api.studio_publish import run_published_recipe
    from services.ingest.recipe_rules import RecipeRuleError
    from services.ingest.watermark import RefreshRead

    from adapters.media_objectstore.testing import InMemoryMediaStore
    from tests.ingest.recipe_test_support import MergingGraph
    from tests.ingest.test_row_keys import LOADER, ONTOLOGY, SCHEME, _published_draft

    repo, draft = _published_draft(tmp_path)
    graph = MergingGraph(ONTOLOGY)
    with pytest.raises(RecipeRuleError, match="deduplication key"):
        await run_published_recipe(
            draft, LOADER, graph=graph, ontology=ONTOLOGY, load_id="load-1",  # type: ignore[arg-type]
            investigation_scope="case-1", repo_root=repo, media=InMemoryMediaStore(),
            scheme=SCHEME, sink=None,
            refresh=RefreshRead(source_id="src-1", mode="incremental", watermark_column="paid_at"),
        )  # fmt: skip
    assert not graph.committed_nodes, "nothing loaded"


def test_a_route_never_answers_the_watermark_and_withholds_its_counts_below_the_rows_marking() -> (
    None
):
    """Rules 3, 4 and 7: the watermark is a value of the loader's own source, for the ledger alone;
    its counts are a read, withheld from a reader who may not view a row's marking."""
    from services.api.load_records import report_view

    from schemas.domain import Handling, Principal
    from schemas.ingest import LoadReport
    from tests.ingest.test_row_keys import SCHEME

    secret = Handling(
        classification="SECRET", handling_code="P", owning_unit="unit-1", originator="unit-1"
    )
    report = LoadReport(
        load_id="load-1", recipe_id="r", recipe_version=1, rows_read=1, rows_below_watermark=3,
        rows_without_watermark=1, watermark=_kept("2026-11-01T09:00:00+00:00", "time"),
        markings=[secret],
    )  # fmt: skip
    cleared = Principal(id="a", clearance="SECRET", org_unit="unit-1")
    below = Principal(id="b", clearance="OFFICIAL", org_unit="unit-1")

    shown = report_view(report, cleared, SCHEME)
    assert (shown.rows_below_watermark, shown.rows_without_watermark) == (3, 1)
    assert "2026-11-01" not in shown.model_dump_json(), "never the watermark's value"
    withheld = report_view(report, below, SCHEME)
    assert withheld.withheld and (withheld.rows_below_watermark, withheld.rows_read) == (0, 0)
