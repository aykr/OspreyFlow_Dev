"""The real keeper of a list's versions, `ParquetListRows`, against the leased stack's object store
(`06_DECISIONS.md` ADR-140 Amendment 13; the lane review of L1.6, item 7; rule 15). The offline
tests run its twin, `InMemoryListRows`; this proves the twin keeps what the real one keeps and
refuses what it refuses. A bucket of the run's own, removed after (L1.4's `storage` fixture:
skipped, never run, without a lease's `MINIO_ENDPOINT` and `OSPREY_LANE`).

What a mistake would do, and the case that catches it:
- an unchanged own list with a blank cell kept as a new version on every import, because the file's
  `""` and the kept `None` differ —
  `test_an_unchanged_own_list_with_blank_cells_keeps_no_new_version`;
- a version's rows replaced, or a list's rows read as another's —
  `test_a_version_is_never_replaced_and_never_read_as_another_list`;
- a scheduled deployment list's change, or a version file never applied, wedging its imports —
  `test_a_deployment_list_imports_through_the_real_keeper`.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.fs as pa_fs
import pytest
from services.api.list_connector import (
    InMemoryListRows,
    InMemoryListStore,
    ListConnectorRefused,
    ParquetListRows,
    deployment_reference,
    import_list,
    import_own_list,
)
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import StagingError

from schemas.dataset_model import ReferenceList
from schemas.list_connector import BlankListMapping, DeploymentListInput
from schemas.monitoring import ListSchedule
from tests.ingest.test_phase7_exit_live import _answers


@pytest.fixture
def storage() -> Iterator[ObjectStorageConfig]:
    """A bucket of the run's own on the object store a lease pins, or CI's own (the live job's
    `MINIO_ENDPOINT`, `CI=true`); skipped otherwise, never the default store on 9000 (rule 14). Run
    in CI's live job (the orchestrator's second review of L1.6, item 14)."""
    endpoint = os.environ.get("MINIO_ENDPOINT", "")
    on_record = bool(os.environ.get("OSPREY_LANE")) or os.environ.get("CI") == "true"
    if not endpoint or not on_record or not _answers(endpoint):
        pytest.skip("live: run under a lease, or in CI's live job, with its MINIO_ENDPOINT")
    config = dataclasses.replace(
        ObjectStorageConfig.from_env(), bucket=f"studio-b-l16-{uuid.uuid4().hex[:12]}"
    )
    yield config
    fs = pa_fs.S3FileSystem(
        endpoint_override=config.endpoint, access_key=config.access_key,
        secret_key=config.secret_key, scheme="https" if config.use_ssl else "http",
        allow_bucket_deletion=True,
    )  # fmt: skip
    if fs.get_file_info(config.bucket).type != pa_fs.FileType.NotFound:
        fs.delete_dir(config.bucket)

GOLDEN = Path(__file__).parents[2] / "connectors" / "golden"
BODY = b"estab_id,estab_name,region\nE1,HMP Synthetic One,\nE2,HMP Synthetic Two, \n"


def test_an_unchanged_own_list_with_blank_cells_keeps_no_new_version(
    storage: ObjectStorageConfig,
) -> None:
    for rows in (ParquetListRows(storage), InMemoryListRows()):
        first, _ = import_own_list("ds-a", "rl-a", BODY, rows_kept=rows, named=["rl-a"],
                                   name="establishments", key_column="estab_id")  # fmt: skip
        again, outcome = import_own_list("ds-a", "rl-a", BODY, rows_kept=rows, named=["rl-a"])
        assert (again.version, outcome) == (1, "unchanged"), type(rows).__name__
        assert rows.read(first) == [
            {"estab_id": "E1", "estab_name": "HMP Synthetic One", "region": None},
            {"estab_id": "E2", "estab_name": "HMP Synthetic Two", "region": None},
        ], type(rows).__name__
        assert [r.id for r in rows.kept("ds-a")] == ["rl-a"]


def test_a_version_is_never_replaced_and_never_read_as_another_list(
    storage: ObjectStorageConfig,
) -> None:
    reference = ReferenceList(id="rl-a", dataset_id="ds-a", name="establishments",
                              kind="reference", key_column="estab_id", version=1)  # fmt: skip
    for rows in (ParquetListRows(storage), InMemoryListRows()):
        rows.write(reference, [{"estab_id": "E1", "estab_name": "One"}])
        rows.write(reference, [{"estab_id": "E1", "estab_name": "One"}])  # the same: no change
        with pytest.raises(StagingError):
            rows.write(reference, [{"estab_id": "E1", "estab_name": "Other"}])
        with pytest.raises(StagingError, match="another list"):
            rows.read(reference.model_copy(update={"id": "rl-other"}))
        with pytest.raises(ListConnectorRefused, match="key"):
            import_own_list("ds-a", "rl-b", b"k,v\nX,1\nX,2\n", rows_kept=rows, named=["rl-b"],
                            name="dupes", key_column="k")  # fmt: skip


async def test_a_deployment_list_imports_through_the_real_keeper(
    storage: ObjectStorageConfig,
    tmp_path: Path,
) -> None:
    shutil.copy(GOLDEN / "blank_client_list.csv", tmp_path / "client.csv")
    mapping = BlankListMapping.model_validate_json(
        (GOLDEN / "blank_client_list.mapping.json").read_text()
    )
    store, rows = InMemoryListStore(), ParquetListRows(storage)
    made = await store.add(
        DeploymentListInput(name="Client list", template="blank", location="client.csv",
                            mapping=mapping),
        "admin-1",
    )  # fmt: skip

    async def run() -> object:
        import hashlib

        known = {hashlib.sha256((tmp_path / "client.csv").read_bytes()).hexdigest()}
        return await import_list(made.id, store=store, rows_kept=rows, root=tmp_path, known=known)

    first, again = await run(), await run()
    assert (first.outcome, first.version, again.outcome) == ("updated", 1, "unchanged")  # type: ignore[attr-defined]
    await store.set_schedule(made.id, ListSchedule(every="daily", hour=5), "admin-1",
                             datetime(2026, 11, 8, tzinfo=UTC))  # fmt: skip
    record = await store.get(made.id)
    never_live = {"ref": "ORPHAN", "primary_name": "Never live", "aliases": None,
                  "date_of_birth": None, "nationality": None, "identifiers": None,
                  "programme": None, "listing": "sanction", "entity_type": "Person"}  # fmt: skip
    rows.write(deployment_reference(record, 2), [never_live])
    (tmp_path / "client.csv").write_text((tmp_path / "client.csv").read_text().replace("XB", "XC"))
    changed = await run()
    assert (changed.outcome, changed.version, changed.changed) == ("updated", 3, 1)  # type: ignore[attr-defined]
    assert [(r.id, r.version) for r in rows.kept("deployment")] == [(made.id, 3)]
