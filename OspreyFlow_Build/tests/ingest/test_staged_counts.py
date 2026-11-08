"""ADR-140 Amendment 12: a staged load's report carries each step's counts and each rejection's
refs, and a staged row's identity is the engine's one encoding (L1.3's carried item).

What a mistake would do, and the case that catches it:

- a step's counts that are not its table's rows, so the run report says one thing and the staged
  Parquet another (`test_per_step_counts_equal_the_staged_tables`);
- a step left out of the report, or reported out of run order
  (`test_every_step_is_counted_in_run_order`);
- a staging rejection whose refs do not name the rows it refused, by table, row, load and side
  (`test_a_staging_rejection_names_its_rows_by_table_row_load_and_side`);
- a Map rejection whose refs do not lead back from the staged row to its source rows
  (`test_a_map_rejection_names_its_staged_row_and_the_source_rows_behind_it`);
- the catalogue hashing a row's key parts in an encoding of its own, so a staged row's identity
  and the engine's key for the same parts disagree
  (`test_a_staged_row_s_identity_is_the_engine_s_key_encoding`).
"""

from __future__ import annotations

from services.ingest.engine import encode_key_parts
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import read_staged_table, source_table

from schemas.ingest import RejectionRef
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_staged_run import RECIPE, load


async def test_per_step_counts_equal_the_staged_tables() -> None:
    done, _graph = await load()
    storage = ObjectStorageConfig(bucket="staging")
    for count in done.report.staging_steps:
        staged = read_staged_table(done.staged_paths[count.step], storage=storage)
        assert count.rows_out == len(staged.rows) == len(done.staging.tables[count.step].rows)
    # And as the existing test reads them: 6 bookings in, one left without an establishment;
    # 5 out of the left join (one refused on each side).
    by_step = {c.step: c for c in done.report.staging_steps}
    lookup = by_step["with_establishment"]
    assert (lookup.rows_in, lookup.unmatched) == (6, 1)
    assert (by_step["with_owner"].rejected, by_step["with_owner"].right_rows_in) == (2, 4)
    assert sum(c.rows_out for c in done.report.staging_steps) == done.rows_staged


async def test_every_step_is_counted_in_run_order() -> None:
    done, _graph = await load()
    assert RECIPE.staging
    assert [(c.step, c.kind) for c in done.report.staging_steps] == [
        (s.id, s.kind) for s in RECIPE.staging
    ]


async def test_a_staging_rejection_names_its_rows_by_table_row_load_and_side() -> None:
    done, _graph = await load()
    staged = [r for r in done.report.rejections if r.reason.startswith("staging step")]
    assert [r.refs for r in staged] == [
        [RejectionRef(table="number_owners", row_index=3, load_id="ld-no-1", side="right")],
        [
            RejectionRef(table="visit_bookings", row_index=3, load_id="ld-vb-1", side="left"),
            RejectionRef(table="reference_list:establishments@v3", row_index=1, side="left"),  # HBK
        ],
    ]


async def test_a_map_rejection_names_its_staged_row_and_the_source_rows_behind_it() -> None:
    done, _graph = await load()
    [mapped] = [r for r in done.report.rejections if r.reason.startswith("staged table")]
    assert mapped.refs[0] == RejectionRef(table="titled", row_index=4)
    behind = {(r.table, r.row_index, r.load_id) for r in mapped.refs[1:]}
    # Booking 006 is row 5 of the bookings, read by its own load.
    assert ("visit_bookings", 5, "ld-vb-1") in behind


def test_a_staged_row_s_identity_is_the_engine_s_key_encoding() -> None:
    table = source_table(
        "visit_bookings",
        [{"booking_id": "VB-001", "contact_number": "07700 900731"}],
        load_id="ld-1",
        key=["booking_id"],
    )
    assert table.rows[0].refs[0].row_key == encode_key_parts(["VB-001"])
