"""The claims part of a set (ADR-148 Amendment 7, the poc shape's `ospreyflow-ingest`): a second
CronJob, on the shared claims' node, streams each claim into the same set as the main run, against
the S3 stand-in.

Both runs name the set **from the schedule slot they share** (the Job name the CronJob gives, its
scheduled minute), never by looking for an open set, so a slow or overlapping run can never join
another slot's set. The main run waits, bounded, for the claims part and writes the manifest last;
without the claims part the set stays unfinished, the run fails in words, and nothing restores from it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import Any

import pytest
from services.api import platform_backup as pb

from tests.cloud_platform_backup.conftest import BUCKET, KEY_ARN, Running, _deny_kms, _objects

# 11 November 2026, 02:15 UTC, as minutes since the epoch: the name a CronJob gives that slot's Job.
SLOT = 29_906_055
NEXT = SLOT + 1440


def _job(name: str, slot: int) -> str:
    return f"{name}-{slot}"


class Clock:
    """A monotonic clock moved on only by `sleep`, which may first run something (a second pod)."""

    def __init__(self) -> None:
        self.now = 0.0
        self.on_sleep: list[Any] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        if self.on_sleep:
            self.on_sleep.pop(0)()
        self.now += seconds


@pytest.fixture
def claims(tmp_path: Path) -> Path:
    """The claims as the claims run mounts them: `ingest` holding uploads and a drop folder, and
    the file system's own lost+found at its root."""
    root = tmp_path / "claims"
    ingest = root / "ingest"
    (ingest / "ingest" / "uploads" / "case-1").mkdir(parents=True)
    (ingest / "ingest" / "drop" / "nightly").mkdir(parents=True)
    (ingest / "ingest" / "uploads" / "case-1" / "witness statement.pdf").write_bytes(b"%PDF synthetic" * 500)
    (ingest / "ingest" / "drop" / "nightly" / "people.csv").write_text("id,name\n1,Synthetic Person\n")
    (ingest / "lost+found").mkdir()
    (ingest / "lost+found" / "#1234").write_bytes(b"fsck's, not ours")
    return root


def _with_claims(settings: pb.Settings, claims: Path, job: str, wait: float = 600) -> pb.Settings:
    return pb.Settings(**{**settings.__dict__, "claims": ("ingest",), "claims_folder": claims,
                          "job_name": job, "claims_wait": wait})  # fmt: skip


def test_both_runs_of_one_slot_name_the_same_set() -> None:
    assert pb.set_of(_job("ospreyflow-backup", SLOT)) == pb.set_of(_job("ospreyflow-backup-claims", SLOT))
    assert pb.set_of(_job("ospreyflow-backup", SLOT)) == "20261111T021500Z"
    assert pb.set_of(_job("ospreyflow-backup", NEXT)) == "20261112T021500Z"


@pytest.mark.parametrize("name", ["ospreyflow-backup", "last-backup", "ospreyflow-backup-x29906055", ""])
def test_a_job_name_naming_no_slot_is_refused_in_words(name: str) -> None:
    with pytest.raises(pb.BackupRefused) as refused:
        pb.set_of(name)
    assert "slot" in refused.value.reason and "minute" in refused.value.reason


def test_a_set_with_claims_holds_them_and_is_finished_only_with_them(
    aws: Running, run: Any, claims: Path
) -> None:
    settings, bucket, stores, _ = run
    main = _with_claims(settings, claims, _job("ospreyflow-backup", SLOT))
    other = _with_claims(settings, claims, _job("ospreyflow-backup-claims", SLOT))
    clock = Clock()
    # The claims run finishes while the main run waits for it.
    clock.on_sleep.append(lambda: pb.take_claims(other, pb.Bucket(other)))
    manifest = pb.take(main, bucket, stores, clock=clock, sleep=clock.sleep)
    assert manifest["set"] == "20261111T021500Z"
    part = manifest["claims"]["ingest"]
    key = f"sets/{manifest['set']}/claims/ingest.tar.gz"
    assert part["key"] == key and key in _objects(aws)
    assert aws.stand_in.meta(BUCKET, key)["kms_key"] == KEY_ARN
    with tarfile.open(fileobj=io.BytesIO(aws.stand_in.read(BUCKET, key)), mode="r:gz") as tar:
        names = tar.getnames()
    assert "ingest/uploads/case-1/witness statement.pdf" in names
    assert "ingest/drop/nightly/people.csv" in names
    assert not any(n.startswith("lost+found") for n in names), "the file system's folder is not ours"
    assert [s.set_id for s in pb.sets(bucket) if s.complete] == [manifest["set"]]


def test_a_missing_claims_part_leaves_the_set_unfinished_and_unrestorable(
    aws: Running, run: Any, claims: Path, tmp_path: Path
) -> None:
    settings, bucket, stores, _ = run
    main = _with_claims(settings, claims, _job("ospreyflow-backup", SLOT), wait=900)
    clock = Clock()
    with pytest.raises(pb.BackupRefused) as refused:
        pb.take(main, bucket, stores, clock=clock, sleep=clock.sleep)
    assert refused.value.store == "claims"
    assert "20261111T021500Z" in str(refused.value) and "unfinished" in refused.value.reason
    assert "ospreyflow-backup-claims" in refused.value.reason
    assert 900 <= clock.now < 900 + pb.CLAIMS_POLL + 1, "bounded: waits its time and no longer"
    assert not any(k.endswith("/manifest.json") and "/claims/" not in k for k in _objects(aws))
    for restore in (lambda: pb.fetch_graph(bucket, "20261111T021500Z", tmp_path / "r"),
                    lambda: pb.fetch_claims(bucket, "20261111T021500Z", tmp_path / "c")):  # fmt: skip
        with pytest.raises(pb.BackupRefused, match="no finished set"):
            restore()
    with pytest.raises(pb.BackupRefused, match="no finished set"):
        pb.latest(bucket)


def test_an_overlapping_second_run_never_joins_the_first_runs_set(aws: Running, run: Any, claims: Path) -> None:
    """The first slot's main run is still waiting when the next slot's claims run starts: that
    claims part is the next slot's, so the first set stays unfinished, never completed by it."""
    settings, bucket, stores, _ = run
    first = _with_claims(settings, claims, _job("ospreyflow-backup", SLOT), wait=600)
    late = _with_claims(settings, claims, _job("ospreyflow-backup-claims", NEXT))
    clock = Clock()
    clock.on_sleep.append(lambda: pb.take_claims(late, pb.Bucket(late)))
    with pytest.raises(pb.BackupRefused):
        pb.take(first, bucket, stores, clock=clock, sleep=clock.sleep)
    keys = _objects(aws)
    assert "sets/20261112T021500Z/claims/ingest.tar.gz" in keys
    assert not any(k.startswith("sets/20261111T021500Z/claims/") for k in keys)
    assert not [s for s in pb.sets(bucket) if s.complete]


def test_a_claims_run_never_adds_to_a_finished_set(aws: Running, run: Any, claims: Path) -> None:
    settings, bucket, stores, _ = run
    plain = pb.take(settings, bucket, stores, now=dt.datetime(2026, 11, 11, 2, 15, tzinfo=dt.UTC))
    assert plain["set"] == "20261111T021500Z"
    late = _with_claims(settings, claims, _job("ospreyflow-backup-claims", SLOT))
    with pytest.raises(pb.BackupRefused, match="already finished"):
        pb.take_claims(late, pb.Bucket(late))
    assert not any("/claims/" in k for k in _objects(aws))


def test_a_claims_run_refused_by_kms_says_so_and_writes_no_part(aws: Running, run: Any, claims: Path) -> None:
    settings, _, _, _ = run
    _deny_kms(aws, "kms:Decrypt")
    late = _with_claims(settings, claims, _job("ospreyflow-backup-claims", SLOT))
    with pytest.raises(pb.BackupRefused) as refused:
        pb.take_claims(late, pb.Bucket(late))
    assert refused.value.store == "claims"
    assert "AccessDenied" in refused.value.reason and "kms:GenerateDataKey" in refused.value.reason
    assert not any(k.endswith("claims/manifest.json") for k in _objects(aws))


def _finished_with_claims(run: Any, claims: Path) -> tuple[pb.Settings, pb.Bucket, str]:
    settings, bucket, stores, _ = run
    main = _with_claims(settings, claims, _job("ospreyflow-backup", SLOT))
    other = _with_claims(settings, claims, _job("ospreyflow-backup-claims", SLOT))
    clock = Clock()
    clock.on_sleep.append(lambda: pb.take_claims(other, pb.Bucket(other)))
    return main, bucket, pb.take(main, bucket, stores, clock=clock, sleep=clock.sleep)["set"]


def test_a_restore_puts_each_claim_back_as_it_was(aws: Running, run: Any, claims: Path, tmp_path: Path) -> None:
    _, bucket, set_id = _finished_with_claims(run, claims)
    target = tmp_path / "restored"
    (target / "ingest" / "ingest" / "uploads").mkdir(parents=True)
    (target / "ingest" / "ingest" / "uploads" / "written after the set.txt").write_text("not in the set")
    (target / "ingest" / "lost+found").mkdir()
    (target / "ingest" / "lost+found" / "#9").write_text("kept: the file system's")
    restored = pb.fetch_claims(bucket, set_id, target)
    assert restored == ["ingest"]
    root = target / "ingest"
    assert (root / "ingest/uploads/case-1/witness statement.pdf").read_bytes() == (
        claims / "ingest/ingest/uploads/case-1/witness statement.pdf"
    ).read_bytes()
    assert (root / "ingest/drop/nightly/people.csv").exists()
    assert not (root / "ingest/uploads/written after the set.txt").exists(), "the claim is the set's, nothing else"
    assert (root / "lost+found/#9").exists(), "the file system's own folder is left alone"


def test_a_claims_part_that_does_not_match_its_manifest_is_never_restored(
    aws: Running, run: Any, claims: Path, tmp_path: Path
) -> None:
    _, bucket, set_id = _finished_with_claims(run, claims)
    key = f"sets/{set_id}/claims/ingest.tar.gz"
    aws.stand_in.put(BUCKET, key, b"\x1f\x8b not the set's", KEY_ARN)
    target = tmp_path / "restored"
    (target / "ingest").mkdir(parents=True)
    (target / "ingest" / "kept.txt").write_text("untouched by a refused restore")
    with pytest.raises(pb.BackupRefused, match="manifest says"):
        pb.fetch_claims(bucket, set_id, target)
    assert (target / "ingest" / "kept.txt").exists(), "nothing removed before the part is checked"


def test_a_part_reaching_outside_its_claim_is_refused(aws: Running, run: Any, claims: Path, tmp_path: Path) -> None:
    """A tar member naming `../` is refused by the extraction's own filter, not written."""
    settings, bucket, set_id = _finished_with_claims(run, claims)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("../outside.txt")
        info.size = 4
        tar.addfile(info, io.BytesIO(b"evil"))
    data = buffer.getvalue()
    key = f"sets/{set_id}/claims/ingest.tar.gz"
    aws.stand_in.put(BUCKET, key, data, KEY_ARN)
    manifest = pb.manifest_of(bucket, set_id)
    manifest["claims"]["ingest"].update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    aws.stand_in.put(BUCKET, f"sets/{set_id}/manifest.json", json.dumps(manifest).encode(), KEY_ARN)
    with pytest.raises(pb.BackupRefused, match="outside"):
        pb.fetch_claims(bucket, set_id, tmp_path / "restored")
    # A `../` entry unpacked from the claim's staging folder would land inside the claim itself, or
    # beside it: neither, nor anywhere else under the test's folder.
    assert not list(tmp_path.rglob("outside.txt"))


def test_a_set_without_a_claims_part_is_refused_by_a_claims_restore(aws: Running, run: Any, tmp_path: Path) -> None:
    settings, bucket, stores, _ = run
    plain = pb.take(settings, bucket, stores)
    with pytest.raises(pb.BackupRefused, match="holds no claims"):
        pb.fetch_claims(bucket, plain["set"], tmp_path / "restored")


def test_main_runs_each_part_and_fails_the_job_on_a_missing_claims_part(
    aws: Running, run: Any, claims: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CronJob's own entry point: a missing part is a non-zero exit, in words, for P9b's alert."""
    settings, _, _, fake = run
    monkeypatch.setattr(pb, "CLAIMS_POLL", 0.01)
    for name, value in {"OSPREY_BACKUP_BUCKET": BUCKET,
                        "OSPREY_BACKUP_KMS_KEY": KEY_ARN, "AWS_REGION": "eu-west-2",
                        "AWS_ENDPOINT_URL_S3": aws.endpoint,
                        "OSPREY_BACKUP_ARCADEDB_FOLDER": str(settings.arcadedb_folder),
                        "OSPREY_BACKUP_CLAIMS": "ingest", "OSPREY_BACKUP_CLAIMS_FOLDER": str(claims),
                        "OSPREY_BACKUP_CLAIMS_WAIT": "0.05", "CLICKHOUSE_USER": "backup",
                        "OSPREY_BACKUP_JOB": _job("ospreyflow-backup", SLOT)}.items():  # fmt: skip
        monkeypatch.setenv(name, value)
    stores = pb.Stores
    monkeypatch.setattr(pb, "Stores", lambda s: stores(s, http=fake))
    assert pb.main(["backup"]) == 1
    said = capsys.readouterr().err
    assert "claims" in said and "20261111T021500Z" in said and "unfinished" in said
    monkeypatch.setenv("OSPREY_BACKUP_JOB", _job("ospreyflow-backup-claims", SLOT))
    assert pb.main(["backup-claims"]) == 0


def test_a_file_gone_before_it_is_read_is_left_out_and_counted(
    aws: Running, run: Any, claims: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drop folder moves while the part is taken: a file removed between the listing and its
    read is passed over and counted, and the part is still written."""
    settings, _, _, _ = run
    late = _with_claims(settings, claims, _job("ospreyflow-backup-claims", SLOT))
    walked = pb._tree

    def walk_then_remove(folder: Path) -> Any:
        for path in walked(folder):
            if path.name == "people.csv":
                path.unlink()
            yield path

    monkeypatch.setattr(pb, "_tree", walk_then_remove)
    part = pb.take_claims(late, pb.Bucket(late))
    assert part["ingest"]["gone"] == 1
    with tarfile.open(fileobj=io.BytesIO(aws.stand_in.read(BUCKET, part["ingest"]["key"])), mode="r:gz") as tar:
        names = tar.getnames()
    assert "ingest/drop/nightly/people.csv" not in names
    assert "ingest/uploads/case-1/witness statement.pdf" in names


def test_a_file_that_shrinks_while_read_refuses_the_part_never_padded() -> None:
    """The orchestrator's round 2: a file shorter than its header says is never padded into the set."""
    reader = pb._AtMost(io.BytesIO(b"abc"), 5, "ingest/drop/x.csv")
    with pytest.raises(pb.FileShrank, match="ingest/drop/x.csv grew shorter"):
        reader.read()


def test_the_sets_verify_refuses_a_changed_claim_before_anything(
    aws: Running, run: Any, claims: Path, tmp_path: Path
) -> None:
    """The Jobs' first step checks each claim's part by its SHA-256, before either Job replaces anything
    (the claims' own step re-checks it as it reads it)."""
    _, bucket, set_id = _finished_with_claims(run, claims)
    aws.stand_in.put(BUCKET, f"sets/{set_id}/claims/ingest.tar.gz", b"\x1f\x8b not the set's", KEY_ARN)
    with pytest.raises(pb.BackupRefused, match="the claim ingest .* the manifest says"):
        pb.verify_set(bucket, set_id, claims=("ingest",))
