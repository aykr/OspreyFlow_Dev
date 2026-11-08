"""ADR-140 Amendment 12 (Q3 (a), the orchestrator's settlement of 8 November 2026): a run reads a
dataset's reference list from the list's own version file
(`<bucket>/reference_lists/<dataset>/<name>@v<version>.parquet`, Amendment 11's place), written by
`python -m services.ingest.reference_list_import` from a synthetic file until L1.6 builds import.

What a mistake would do, and the case that catches it:

- the rows a run reads not being the rows imported (`test_imported_rows_are_the_rows_a_run_reads`);
- a run whose list has no file going ahead with an empty list, every Lookup silently unmatched
  (rule 2) (`test_a_run_whose_list_has_no_file_is_refused_in_words`);
- a file at the path holding another list's rows, or another version's, read as this one
  (`test_a_file_holding_another_list_is_refused`);
- an import replacing rows elements may already name (`test_an_import_never_replaces_other_rows`);
- an import admitting a file from outside the repository's synthetic fixtures (rule 9)
  (`test_the_import_admits_only_synthetic_fixtures`);
- a run reading a list the dataset may not read
  (`test_a_run_reads_only_lists_the_dataset_may_read`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from services.ingest.reference_list_import import (
    import_list,
    lists_for_run,
    main,
    read_list_rows,
)
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import StagingError, list_rows_path, reference_table

from schemas.dataset_model import ReferenceList
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_staged_run import ESTABLISHMENTS, FIXTURES, RECIPE, _rows

STORAGE = ObjectStorageConfig(bucket="staging")
CSV = FIXTURES / "establishments.csv"


def test_imported_rows_are_the_rows_a_run_reads() -> None:
    path = import_list(ESTABLISHMENTS, CSV, storage=STORAGE)
    assert path == list_rows_path(ESTABLISHMENTS, storage=STORAGE)
    read = read_list_rows(ESTABLISHMENTS, storage=STORAGE)
    expected = reference_table(ESTABLISHMENTS, _rows("establishments.csv"))
    assert read.columns == expected.columns
    assert [(r.cells, r.refs) for r in read.rows] == [(r.cells, r.refs) for r in expected.rows]
    assert read.reference == ESTABLISHMENTS


def test_a_run_whose_list_has_no_file_is_refused_in_words() -> None:
    assert RECIPE.staging
    with pytest.raises(StagingError) as refused:
        lists_for_run(RECIPE.staging, [ESTABLISHMENTS], dataset_id="pid", storage=STORAGE)
    assert refused.value.problems == [
        "the list 'establishments' (version 3) has no rows kept for a run to read: import its "
        "rows first; nothing was loaded"
    ]


def test_a_file_holding_another_list_is_refused() -> None:
    other = ESTABLISHMENTS.model_copy(update={"id": "rl-other"})
    import_list(other, CSV, storage=STORAGE)
    with pytest.raises(StagingError) as refused:
        read_list_rows(ESTABLISHMENTS, storage=STORAGE)
    assert refused.value.problems == [
        "the rows kept for the list 'establishments' (version 3) are another list's; nothing "
        "was loaded"
    ]


def test_an_import_never_replaces_other_rows(tmp_path: Path) -> None:
    import_list(ESTABLISHMENTS, CSV, storage=STORAGE)
    import_list(ESTABLISHMENTS, CSV, storage=STORAGE)  # the same rows again: no change
    changed = FIXTURES.parent / "visits_and_contacts" / "number_owners.csv"
    other_key = ESTABLISHMENTS.model_copy(update={"key_column": "number"})
    with pytest.raises(StagingError) as refused:
        import_list(other_key, changed, storage=STORAGE)
    assert "never replaced" in refused.value.problems[0]


def test_the_import_admits_only_synthetic_fixtures(tmp_path: Path) -> None:
    """Rule 9, by content: a file whose bytes are not a synthetic list the repository names is
    refused wherever it sits; the same bytes elsewhere are the same synthetic list."""
    other = tmp_path / "establishments.csv"
    other.write_text(CSV.read_text(encoding="utf-8") + "ZZZ,Not listed,Nowhere\n", encoding="utf-8")
    with pytest.raises(StagingError) as refused:
        import_list(ESTABLISHMENTS, other, storage=STORAGE)
    assert refused.value.problems == [
        "only a synthetic list this repository names may be imported as a list's rows "
        "(rule 9, synthetic_lists.json); this file is not one"
    ]


def test_a_run_reads_only_lists_the_dataset_may_read() -> None:
    assert RECIPE.staging
    theirs = ESTABLISHMENTS.model_copy(update={"dataset_id": "another"})
    import_list(theirs, CSV, storage=STORAGE)
    with pytest.raises(StagingError) as refused:
        lists_for_run(RECIPE.staging, [theirs], dataset_id="pid", storage=STORAGE)
    assert refused.value.problems == [
        "step 'with_establishment' looks up 'establishments', which names no list this dataset "
        "holds or subscribes to"
    ]


def test_the_command_imports_a_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "--dataset", "pid", "--list-id", "rl-est", "--name", "establishments",
            "--key", "estab_id", "--version", "3", "--bucket", "staging", str(CSV),
        ]
    )  # fmt: skip
    assert code == 0
    assert "establishments@v3" in capsys.readouterr().out
    assert read_list_rows(ESTABLISHMENTS, storage=STORAGE).rows


def test_a_list_record_of_its_own_kind_is_kept() -> None:
    screening = ReferenceList(
        id="rl-s", dataset_id="pid", name="watch", kind="reference", key_column="estab_id",
        version=1,
    )  # fmt: skip
    import_list(screening, CSV, storage=STORAGE)
    assert read_list_rows(screening, storage=STORAGE).reference == screening
