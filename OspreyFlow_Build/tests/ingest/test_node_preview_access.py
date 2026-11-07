"""Rule 4 for phase 6's *Preview* (ADR-140 decision 14; redesign brief §8): a Preview of a node reads
with the person's own principal and never shows a row the person could not read.

*Preview* adds no route. The drawer's `NodePreview.tsx` composes two that exist: a source or a
profile node reads the Map sample rows, from row 0 until `is_last_row` or `PREVIEW_ROWS` rows; a
Map or a Load node reads the dry run (`verify`). So the read path to prove is that sequence, as the
drawer makes it, through the real modules, for a reader cleared for the source's OFFICIAL and not for
the SECRET row a bound marking column gives it. What a mistake would do, and the case that catches
it:

- a source Preview's table showing the SECRET row's cells
  (`test_a_source_preview_never_shows_a_row_the_reader_may_not_read`);
- a Map or Load Preview's graph or rejections showing them
  (`test_a_map_preview_never_shows_a_row_the_reader_may_not_read`);
- either path masking for the cleared reader too, which would make the two cases above pass
  vacuously (`test_a_cleared_reader_sees_the_row_in_both_previews`)."""

from __future__ import annotations

import pytest
from services.api import studio_map, studio_profile, studio_verify
from services.api.studio_map import get_sample_row
from services.api.studio_verify import run_verify

from schemas.domain import Principal
from tests.ingest.recipe_test_support import ValidatingGraph
from tests.ingest.test_handling_from_columns import ONTOLOGY, SCHEME
from tests.ingest.test_handling_read_paths import CLEARED, OFFICIAL, ROWS, _draft

#: The drawer's own cap (`NodePreview.tsx`'s `PREVIEW_ROWS`): a Preview reads at most this many.
PREVIEW_ROWS = 10
HIDDEN = "Hidden report"


@pytest.fixture(autouse=True)
def _rows(monkeypatch: pytest.MonkeyPatch) -> None:
    for module, name in (
        (studio_verify, "_read_recipe_rows"),
        (studio_map, "_read_recipe_rows"),
        (studio_profile, "_read_rows"),
    ):
        monkeypatch.setattr(module, name, lambda draft: [dict(r) for r in ROWS])


async def _source_preview(principal: Principal) -> list[str]:
    """The rows a source node's Preview reads, in the drawer's own order and stopping rule."""
    shown: list[str] = []
    for index in range(PREVIEW_ROWS):
        row = await get_sample_row(_draft(binds=True), principal, SCHEME, index)
        shown.append(row.model_dump_json())
        if row.is_last_row:
            break
    return shown


async def _map_preview(principal: Principal) -> str:
    report = await run_verify(
        _draft(binds=True),
        principal,
        SCHEME,
        ValidatingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ONTOLOGY,
    )
    return report.model_dump_json()


async def test_a_source_preview_never_shows_a_row_the_reader_may_not_read() -> None:
    shown = await _source_preview(OFFICIAL)
    assert len(shown) == len(ROWS)  # it read every row of the sample, and stopped at the last
    assert all(HIDDEN not in row for row in shown)


async def test_a_map_preview_never_shows_a_row_the_reader_may_not_read() -> None:
    assert HIDDEN not in await _map_preview(OFFICIAL)


async def test_a_cleared_reader_sees_the_row_in_both_previews() -> None:
    assert any(HIDDEN in row for row in await _source_preview(CLEARED))
    assert HIDDEN in await _map_preview(CLEARED)
