"""CO1, item 1: a Studio read of a source's first rows stops reading at the limit (ADR-140
Amendment 12 item 5; the owner's word of 21 November 2026, file 009 answer 4: a bounded reader,
first N rows, stop reading, N = 10 for the Preview).

Before this, `studio_profile._read_rows` read a source file whole and its callers sliced the list,
so a large file was read in full on every Preview click, Profile and Map sample. The invariant:
**a read that needs the first N rows consumes about N rows of the file, however large the file is.**

Which "N" is which (read ADR-140 Amendment 12 and `09_INGEST_STUDIO.md` §3 and §4):

- the step's live sample (the Preview): `studio_staging.PREVIEW_ROWS` = 10, "each source's first ten
  rows" (Amendment 12 item 5, Q4);
- Profile and the Map sample row: `profiler.DEFAULT_SAMPLE_SIZE` = 10,000, "10,000 rows or the whole
  file, whichever is smaller" (§3), which Profile also needs one row past, to say whether the
  sample is the whole source. **Not changed here**: the decision text gives 10 only for the step's
  sample; the Map and Load graph preview's own limit is Test's (`DEFAULT_SAMPLE_SIZE + 1`) and is
  not read here at all.

What each case proves, and the planted fault that shows it red (rule 15). A plant takes the shape
the code had on main: the caller's own alias for `_read_rows` put back to a whole read, which the
caller then slices (`rows = _read_rows(reader)`; `rows = rows[:limit]`).

- `test_the_reader_stops_at_the_limit`: the reader's own bound. Plant: the whole read
  (`read_csv`), measured with the same counter, consumes every line.
- `test_a_preview_reads_ten_rows_of_a_large_source` (the route), `..._source_tables_...`,
  `test_profile_reads_its_sample_and_one_row_more`, `test_the_map_sample_row_...`,
  `test_the_map_save_reads_the_header_only`: each call site consumes only its bound. Plants
  (`test_each_site_is_shown_red_when_the_whole_read_is_put_back`): the whole read put back at that
  one site alone makes that site's check fail, and no other site's.
- the refusals keep their words: a missing file, a file that is not text in the declared encoding,
  a file outside the ingest folder (`test_the_refusals_keep_their_words`).
- a read with no limit still reads every row (a run and Test read whole sources).

The test walks no repository folder: its files are in `tmp_path`, and it reads no source of the
repository, so it needs no scan row.
"""

from __future__ import annotations

import asyncio
import csv
import pathlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import studio_map, studio_profile, studio_staging
from services.api.studio_map import get_sample_row, source_column_names
from services.api.studio_profile import (
    SourceUnreadableError,
    _read_rows,
    profile_recipe_source,
)
from services.api.studio_staging import PREVIEW_ROWS, source_tables
from services.ingest.connectors import csv_connector
from services.ingest.connectors.csv_connector import read_csv

from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal
from schemas.ingest import (
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    StudioRecipeDraft,
    StudioRecipeStatus,
)
from tests.services.api import test_studio_staging_routes as routes
from tests.services.api.test_studio_staging_routes import (  # noqa: F401  (fixtures)
    staged,
    store,
)
from tests.services.api.test_studio_verify_routes import (  # noqa: F401  (fixtures)
    client,
    graph_client,
)

# ruff: noqa: F811  (the imported fixtures are every test's own same-named parameters)

SCHEME = load_uk_le_scheme()
READER = Principal(id="reader-1", clearance="OFFICIAL", org_unit="unit-1")
HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}
#: Far larger than any bound below: a whole read is easy to tell from a bounded one.
BIG = 30_000
FIRST = {"id": "r0", "name": "Alpha", "value": "0"}


class _Counting:
    """The open source file as the csv reader sees it, counting what it is given. A read that stops
    consumes few lines and few characters; a whole read consumes every line of the file."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle
        self.lines = 0
        self.characters = 0

    def __enter__(self) -> _Counting:
        return self

    def __exit__(self, *exc: object) -> None:
        self._handle.close()

    def __iter__(self) -> _Counting:
        return self

    def __next__(self) -> str:
        line = next(self._handle)
        self.lines += 1
        self.characters += len(line)
        return str(line)

    def read(self, *args: Any) -> str:
        data = self._handle.read(*args)
        self.characters += len(data)
        return str(data)

    def readline(self, *args: Any) -> str:
        line = self._handle.readline(*args)
        self.lines += 1
        self.characters += len(line)
        return str(line)

    def close(self) -> None:
        self._handle.close()

    @property
    def closed(self) -> bool:
        return bool(self._handle.closed)


@contextmanager
def counting(source: Path) -> Iterator[list[_Counting]]:
    """Every open of `source` for reading text, wrapped to count; the wrappers are yielded."""
    opened: list[_Counting] = []
    real = pathlib.Path.open
    target = source.resolve()

    def wrapped(self: Path, *args: Any, **kwargs: Any) -> Any:
        handle = real(self, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        if self.resolve() == target and "b" not in mode and "w" not in mode:
            counted = _Counting(handle)
            opened.append(counted)
            return counted
        return handle

    pathlib.Path.open = wrapped  # type: ignore[method-assign,assignment]
    try:
        yield opened
    finally:
        pathlib.Path.open = real  # type: ignore[method-assign]


def _consumed(opened: list[_Counting]) -> int:
    assert opened, "the source was never opened: the measure saw nothing"
    return sum(c.lines for c in opened)


def _write_big(path: Path, rows: int = BIG) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIRST))
        writer.writeheader()
        for n in range(rows):
            writer.writerow({"id": f"r{n}", "name": f"Name {n}", "value": str(n)})
    return path


@pytest.fixture
def ingest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "ingest"
    root.mkdir()
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(root))
    return root


@pytest.fixture
def big(ingest: Path) -> Path:
    return _write_big(ingest / "big.csv")


def _draft(location: Path | str) -> StudioRecipeDraft:
    return StudioRecipeDraft(
        recipe_id="r-bounded",
        version=1,
        status=StudioRecipeStatus.DRAFT,
        label="bounded",
        connector_profile="generic-csv",
        source_location=str(location),
        handling=dict(HANDLING),
        legal_basis="test",
        owning_unit="unit-1",
        created_by="tester",
        created_at=datetime(2026, 11, 21, tzinfo=UTC),
        ready_for_profile=True,
    )


def _one_source() -> PipelineGraph:
    return PipelineGraph(
        nodes=[PipelineNode(id="src", kind=PipelineNodeKind.SOURCE, label="Source")], edges=[]
    )


# --- the reader's own bound ----------------------------------------------------------------------


def test_the_reader_stops_at_the_limit(big: Path) -> None:
    with counting(big) as opened:
        rows = csv_connector.read_csv_head(big, limit=10)
    assert [r["id"] for r in rows] == [f"r{n}" for n in range(10)]
    # The header and the ten rows; one line more would be a reader that looks ahead, which is
    # still not a whole read, so a little slack is allowed.
    assert _consumed(opened) <= 10 + 1 + 1
    assert opened[0].characters < 1_000, "it read far more of the file than ten rows"
    assert opened[0].closed, "the file is closed the moment the reader stops"


def test_the_measure_sees_a_whole_read(big: Path) -> None:
    """The plant: `read_csv` as `_read_rows` called it on main (every row, then sliced). The same
    counter, which `test_the_reader_stops_at_the_limit` passes, reads every line of the file."""
    with counting(big) as opened:
        rows = list(read_csv(big))[:10]
    assert len(rows) == 10
    assert _consumed(opened) == BIG + 1
    assert _consumed(opened) > 10 + 1 + 1


def test_a_limit_larger_than_the_file_reads_all_of_it(ingest: Path) -> None:
    small = _write_big(ingest / "small.csv", rows=7)
    assert len(csv_connector.read_csv_head(small, limit=10)) == 7
    assert csv_connector.read_csv_head(small, limit=0) == []


def test_no_limit_reads_every_row(ingest: Path) -> None:
    """A run and Test read whole sources: `limit=None` is the whole read, not a default bound."""
    source = _write_big(ingest / "all.csv", rows=250)
    assert len(_read_rows(_draft(source))) == 250
    assert len(_read_rows(_draft(source), limit=None)) == 250
    assert len(_read_rows(_draft(source), limit=40)) == 40


# --- each call site -------------------------------------------------------------------------------
# Each check is a function so the plant below can run the very same check against a site with the
# whole read put back, and see it fail.


def check_source_tables(big: Path) -> None:
    """The step sample's own call (`source_tables(limit=PREVIEW_ROWS)`)."""
    with counting(big) as opened:
        read = source_tables(_draft(big), _one_source(), load_id="p", limit=PREVIEW_ROWS)
    assert len(read.raw["src"]) == PREVIEW_ROWS
    assert _consumed(opened) <= PREVIEW_ROWS + 2, "the sample read more than its ten rows"


def check_profile(big: Path) -> None:
    sample = studio_profile.DEFAULT_SAMPLE_SIZE
    with counting(big) as opened:
        profile = asyncio.run(profile_recipe_source(_draft(big), READER, SCHEME))
    assert profile.rows_sampled == sample
    assert profile.sample_is_whole_source is False
    # The sample, and the one row more that says whether the sample is the whole source.
    assert _consumed(opened) <= sample + 1 + 2, "Profile read past its sample"


def check_map_sample_row(big: Path) -> None:
    sample = studio_map.DEFAULT_SAMPLE_SIZE
    with counting(big) as opened:
        row = asyncio.run(get_sample_row(_draft(big), READER, SCHEME, 0))
    assert row.values["id"] == "r0"
    assert row.is_last_row is False
    assert _consumed(opened) <= sample + 2, "the Map sample read past its sample"


def check_map_header(big: Path) -> None:
    """Map's save wants the source's columns alone: the header."""
    with counting(big) as opened:
        columns = source_column_names(_draft(big))
    assert columns == list(FIRST)
    assert _consumed(opened) <= 3, "the columns were read by reading the file"


def test_the_step_sample_reads_ten_rows_of_a_large_source(big: Path) -> None:
    assert PREVIEW_ROWS == 10
    check_source_tables(big)


def test_profile_reads_its_sample_and_one_row_more(big: Path) -> None:
    check_profile(big)


def test_the_map_sample_row_reads_its_sample_only(big: Path) -> None:
    check_map_sample_row(big)


def test_the_map_save_reads_the_header_only(big: Path) -> None:
    check_map_header(big)


def test_profile_still_says_whether_its_sample_is_the_whole_source(ingest: Path) -> None:
    """Behaviour kept (green on main too, by design): the row past the sample is what
    `sample_is_whole_source` is judged by, so it is right at the sample's edge, where a reader that
    stopped at the sample would say "whole" of a file one row longer."""
    sample = studio_profile.DEFAULT_SAMPLE_SIZE
    for rows, whole in ((sample - 1, True), (sample, True), (sample + 1, False)):
        source = _write_big(ingest / f"edge-{rows}.csv", rows=rows)
        profile = asyncio.run(profile_recipe_source(_draft(source), READER, SCHEME))
        assert (profile.sample_is_whole_source, profile.rows_sampled) == (
            whole,
            min(rows, sample),
        ), rows


def test_a_preview_reads_ten_rows_of_a_large_source(staged: TestClient, tmp_path: Path) -> None:
    """The route itself (`POST …/staging-preview`) over the exit's pipeline, its bookings file made
    large: ten rows of each source, as Amendment 12 item 5 says, however large the file."""
    source = Path(routes._draft(staged).source_location)
    with source.open(newline="", encoding="utf-8") as handle:
        original = list(csv.DictReader(handle))
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(original[0]))
        writer.writeheader()
        for n in range(BIG):
            writer.writerow(original[n % len(original)])
    with counting(source) as opened:
        response = routes._preview(staged, "with_owner")
    assert response.status_code == 200, response.text
    assert response.json()["problems"] == []
    assert _consumed(opened) <= PREVIEW_ROWS + 2, "the Preview read past its ten rows"


# --- the plants: the whole read put back at one site ---------------------------------------------


def _whole_read(original: Callable[..., Any]) -> Callable[..., Any]:
    """`_read_rows` as it was on main: the file read whole, the limit ignored. The caller's own
    slice (`rows[:limit]`) is gone from the sites, so the sites see every row."""

    def whole(recipe: Any, limit: int | None = None) -> Any:
        del limit
        return original(recipe)

    return whole


SITES: list[tuple[str, Any, str, Callable[[Path], None]]] = [
    ("staging", studio_staging, "_read_rows", check_source_tables),
    ("profile", studio_profile, "_read_rows", check_profile),
    ("map sample row", studio_map, "_read_recipe_rows", check_map_sample_row),
    ("map header", studio_map, "_read_recipe_rows", check_map_header),
]


@pytest.mark.parametrize(("name", "module", "alias", "check"), SITES, ids=[s[0] for s in SITES])
def test_each_site_is_shown_red_when_the_whole_read_is_put_back(
    name: str,
    module: Any,
    alias: str,
    check: Callable[[Path], None],
    big: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, alias, _whole_read(_read_rows))
    with pytest.raises(AssertionError):
        check(big)


def test_a_plant_at_one_site_leaves_the_others_green(
    big: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plants are about their own site: put the whole read back in Map and the step sample's
    check still passes, so a site that stops calling the reader is named by its own check alone."""
    monkeypatch.setattr(studio_map, "_read_recipe_rows", _whole_read(_read_rows))
    check_source_tables(big)


# --- the refusals keep their words ----------------------------------------------------------------


def test_the_refusals_keep_their_words(ingest: Path, tmp_path: Path) -> None:
    missing = ingest / "no-such-file.csv"
    with pytest.raises(SourceUnreadableError, match="No such file"):
        _read_rows(_draft(missing), limit=10)
    with pytest.raises(SourceUnreadableError, match="No such file"):
        _read_rows(_draft(missing))

    # Not text in the declared encoding, in the rows the reader reads.
    binary = ingest / "binary.csv"
    binary.write_bytes(b"id,name\n1,\xff\xfe\xfa\n")
    with pytest.raises(SourceUnreadableError, match="codec can't decode"):
        _read_rows(_draft(binary), limit=10)

    outside = tmp_path / "outside.csv"
    outside.write_text("a,b\n1,2\n")
    with pytest.raises(SourceUnreadableError, match="not in the ingest folder"):
        _read_rows(_draft(outside), limit=10)
    # The same refusal at every site that reads (the confinement is the reader's, not the caller's).
    with pytest.raises(SourceUnreadableError, match="not in the ingest folder"):
        source_tables(_draft(outside), _one_source(), load_id="p", limit=PREVIEW_ROWS)
    assert source_column_names(_draft(outside)) is None


def test_a_file_with_a_bad_row_after_the_limit_is_not_read_that_far(ingest: Path) -> None:
    """The one change in what a read can refuse: a limit of ten reads ten rows, so a byte that is
    not text in row 5,000 is not met by a read of the first ten. A read with no limit still meets
    it, and refuses in the same words."""
    path = ingest / "late-fault.csv"
    good = "".join(f"{n},Name {n},{n}\n" for n in range(5_000)).encode()
    path.write_bytes(b"id,name,value\n" + good + b"5000,\xff\xfe,0\n")
    assert len(_read_rows(_draft(path), limit=10)) == 10
    with pytest.raises(SourceUnreadableError, match="codec can't decode"):
        _read_rows(_draft(path))
