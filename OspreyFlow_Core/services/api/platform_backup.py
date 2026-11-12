"""The `cloud-platform` profile's backups (`spec/06_DECISIONS.md` ADR-148 decision 13, as built in
Amendment 7): ArcadeDB's `BACKUP DATABASE` and ClickHouse's `BACKUP … TO S3`, into the deployment's
backups bucket, encrypted by its own KMS key, by the namespace's IAM role (IRSA) — no stored key.

Run by the chart's CronJob (`templates/backups.yaml`) in the Conduit's image, which has botocore:

    python -m services.api.platform_backup backup
    python -m services.api.platform_backup sets
    python -m services.api.platform_backup fetch-graph --set <id> --to <folder>   # a restore's 1st
    python -m services.api.platform_backup restore-analytics --set <id>

**A set** is `sets/<UTC stamp>/` in the bucket: `arcadedb/<database>.zip`, ClickHouse's own backup
under `clickhouse/`, and `manifest.json`, written **last**, so a set without one is a backup that
did not finish and is never restored from.

**ArcadeDB** writes its zip into the server's own `backups` folder; on this profile that folder is a
claim of its own (`backups-arcadedb-0`), which the CronJob's pod mounts on the same node, so the zip
is read from it, uploaded and removed. The request goes to that pod by name (`arcadedb-0`), never
the Service, which would hand it to whichever copy answered.

**ClickHouse** writes its backup to S3 itself, **as the backup role, by its own pod's web identity**
(IRSA: the render gives its pod the role's service account and AWS_DEFAULT_REGION), and the
statement names only the region's own address,
`S3('https://s3.<region>.amazonaws.com/<bucket>/…')`. No key, secret or token is ever in a
statement or ClickHouse's query log. ClickHouse 25.8's `S3()` takes a
URL or a URL and a static key pair, never a session token (Code 42, measured on kind), so the role's
temporary credentials cannot be handed to it; and its web identity client asks STS in the region
AWS_DEFAULT_REGION names (without it, us-east-1, which the platform's egress does not reach).

Every refusal is reported in words naming the store, the step and S3's own code and message, and
the run exits non-zero, so a refused backup is never a quiet one (the CronJob's failed Job).
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: A part of a multipart upload: S3's own minimum is 5 MiB; a part this size keeps a
#: hundred-gigabyte zip under S3's ten-thousand-part limit.
PART_SIZE = 64 * 1024 * 1024
MANIFEST = "manifest.json"
#: How long the main run waits for the claims part before leaving the set unfinished, unless
#: `OSPREY_BACKUP_CLAIMS_WAIT` says otherwise; and how often it looks.
CLAIMS_WAIT = 3 * 3600
CLAIMS_POLL = 15.0
#: The file system's own folder at a claim's root: never backed up, never replaced.
LOST_FOUND = "lost+found"


class BackupRefused(RuntimeError):
    """A step that did not happen, in words: which store, which step, and why."""

    def __init__(self, store: str, step: str, reason: str) -> None:
        super().__init__(f"{store}: {step}: {reason}")
        self.store, self.step, self.reason = store, step, reason


@dataclass(frozen=True)
class Settings:
    """What the CronJob's environment gives the runner (the chart renders every name)."""

    bucket: str
    kms_key: str
    region: str
    arcadedb_url: str
    arcadedb_user: str
    arcadedb_password: str
    arcadedb_database: str
    arcadedb_folder: Path
    clickhouse_url: str
    clickhouse_user: str
    clickhouse_password: str
    clickhouse_database: str
    clickhouse_cluster: str | None
    #: The address ClickHouse reaches S3 by (path style, the bucket after it); S3's own for the
    #: region unless `AWS_ENDPOINT_URL_S3` points elsewhere (the stand-in).
    s3_endpoint: str | None
    #: The poc shape's claims of their own (`storage.claims`, e.g. `ingest`), each mounted at
    #: `claims_folder/<name>` by the claims run; none in the standard shape.
    claims: tuple[str, ...] = ()
    claims_folder: Path = Path("/claims")
    #: The Job's name, `<cronjob>-<scheduled minute>`, which names the set (`set_of`).
    job_name: str | None = None
    claims_wait: float = CLAIMS_WAIT
    #: The workloads a restore refuses to run beside (`app.kubernetes.io/name`), by the restore's
    #: own service account's right to list pods; none given, none asked (the offline tests).
    writers: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ if env is None else env)
        missing = [
            n
            for n in ("OSPREY_BACKUP_BUCKET", "OSPREY_BACKUP_KMS_KEY", "AWS_REGION")
            if not env.get(n)
        ]
        if missing:
            raise BackupRefused("backup", "settings", f"not set: {', '.join(missing)}")
        return cls(
            bucket=env["OSPREY_BACKUP_BUCKET"],
            kms_key=env["OSPREY_BACKUP_KMS_KEY"],
            region=env["AWS_REGION"],
            arcadedb_url="http://{}:{}".format(
                env.get("OSPREY_BACKUP_ARCADEDB_HOST") or env.get("ARCADEDB_HOST", "arcadedb"),
                env.get("ARCADEDB_HTTP_PORT", "2480"),
            ),
            arcadedb_user=env.get("ARCADEDB_USERNAME", "root"),
            arcadedb_password=env.get("ARCADEDB_ROOT_PASSWORD", ""),
            arcadedb_database=env.get("ARCADEDB_DATABASE", "ospreyflow"),
            arcadedb_folder=Path(env.get("OSPREY_BACKUP_ARCADEDB_FOLDER", "/arcadedb-backups")),
            clickhouse_url="http://{}:{}".format(
                env.get("CLICKHOUSE_HOST", "clickhouse"), env.get("CLICKHOUSE_HTTP_PORT", "8123")
            ),
            clickhouse_user=env.get("CLICKHOUSE_USER", "default"),
            clickhouse_password=env.get("CLICKHOUSE_PASSWORD", ""),
            clickhouse_database=env.get("CLICKHOUSE_DATABASE", "ospreyflow"),
            clickhouse_cluster=env.get("CLICKHOUSE_CLUSTER") or None,
            s3_endpoint=env.get("AWS_ENDPOINT_URL_S3") or env.get("AWS_ENDPOINT_URL") or None,
            claims=tuple(n for n in env.get("OSPREY_BACKUP_CLAIMS", "").split(",") if n),
            claims_folder=Path(env.get("OSPREY_BACKUP_CLAIMS_FOLDER", "/claims")),
            job_name=env.get("OSPREY_BACKUP_JOB") or None,
            claims_wait=float(env.get("OSPREY_BACKUP_CLAIMS_WAIT", str(CLAIMS_WAIT))),
            writers=tuple(n for n in env.get("OSPREY_BACKUP_WRITERS", "").split(",") if n),
        )

    @property
    def s3_base(self) -> str:
        """The bucket as ClickHouse reaches it: the region's own address, path style, whatever
        this pod's own S3 client is pointed at (on kind, ClickHouse's pod resolves it to the
        stand-in)."""
        return f"https://s3.{self.region}.amazonaws.com/{self.bucket}"


# ---------------------------------------------------------------------------------------------
# S3, by the role's credentials
# ---------------------------------------------------------------------------------------------


#: The service a botocore operation belongs to, for a refusal's words (a KMS refusal reaches us as
#: S3's, since S3 asks KMS on our behalf).
_SERVICE = {"AssumeRoleWithWebIdentity": "STS"}


def _said(error: Exception) -> str:
    """The refusing service's own code and words (botocore's `ClientError`), or the error's."""
    response = getattr(error, "response", None)
    if isinstance(response, dict) and "Error" in response:
        found = response["Error"]
        service = _SERVICE.get(str(getattr(error, "operation_name", "")), "S3")
        return f"{service} refused it ({found.get('Code')}: {found.get('Message')})"
    return f"{type(error).__name__}: {error}"


@dataclass
class Bucket:
    """The backups bucket through botocore, every write encrypted by the deployment's key."""

    settings: Settings
    client: Any = None
    session: Any = None

    def __post_init__(self) -> None:
        if self.client is None:
            import botocore.session
            from botocore.config import Config

            self.session = botocore.session.get_session()
            self.client = self.session.create_client(
                "s3",
                region_name=self.settings.region,
                endpoint_url=self.settings.s3_endpoint,
                config=Config(s3={"addressing_style": "path"}, retries={"mode": "standard"}),
            )

    def _sse(self) -> dict[str, str]:
        return {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self.settings.kms_key}

    def put_bytes(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.settings.bucket, Key=key, Body=data, **self._sse())

    def put_file(self, key: str, path: Path) -> tuple[int, str]:
        """The file uploaded (in parts above one part's size); its size and SHA-256."""
        size = path.stat().st_size
        digest = hashlib.sha256()
        bucket = self.settings.bucket
        if size <= PART_SIZE:
            data = path.read_bytes()
            digest.update(data)
            self.client.put_object(Bucket=bucket, Key=key, Body=data, **self._sse())
            return size, digest.hexdigest()
        upload = self.client.create_multipart_upload(Bucket=bucket, Key=key, **self._sse())
        upload_id = upload["UploadId"]
        parts = []
        try:
            with path.open("rb") as file:
                for number, chunk in enumerate(iter(lambda: file.read(PART_SIZE), b""), start=1):
                    digest.update(chunk)
                    done = self.client.upload_part(
                        Bucket=bucket, Key=key, UploadId=upload_id, PartNumber=number, Body=chunk
                    )
                    parts.append({"PartNumber": number, "ETag": done["ETag"]})
            self.client.complete_multipart_upload(
                Bucket=bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": parts}
            )
        except Exception:
            # An upload left open is stored, and paid for, until it is aborted.
            try:
                self.client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
            except Exception:  # noqa: BLE001, S110 - the first refusal is the one reported
                pass
            raise
        return size, digest.hexdigest()

    def put_tree(self, key: str, folder: Path) -> tuple[int, str, dict[str, Any]]:
        """`folder` (its top-level lost+found left out) as a gzipped tar, streamed up in parts; its
        size, SHA-256 and what was taken. A live claim moves under it (the drop folder above all):
        a file gone before it is opened is left out and counted, and one that shrinks while read is
        kept at its new length and named, so a busy folder never fails the part."""
        bucket = self.settings.bucket
        upload_id = self.client.create_multipart_upload(Bucket=bucket, Key=key, **self._sse())[
            "UploadId"
        ]
        writer = _PartWriter(self.client, bucket, key, upload_id)
        taken: dict[str, Any] = {"entries": 0, "gone": 0}
        try:
            with tarfile.open(fileobj=writer, mode="w|gz") as tar:  # type: ignore[call-overload]
                for path in _tree(folder):
                    _add(tar, path, path.relative_to(folder).as_posix(), taken)
            writer.finish()
            self.client.complete_multipart_upload(
                Bucket=bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": writer.parts}
            )
        except Exception:
            try:
                self.client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
            except Exception:  # noqa: BLE001, S110 - the first refusal is the one reported
                pass
            raise
        return writer.size, writer.digest.hexdigest(), taken

    def listing(self, prefix: str) -> list[dict[str, Any]]:
        """Each object under `prefix`: its key, size and ETag (a part this role may list but not
        read, ClickHouse's own, is checked by these)."""
        found: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            extra = {"ContinuationToken": token} if token else {}
            page = self.client.list_objects_v2(Bucket=self.settings.bucket, Prefix=prefix, **extra)
            found += [{"key": i["Key"], "bytes": i["Size"], "etag": i["ETag"].strip('"')}
                      for i in page.get("Contents", [])]  # fmt: skip
            if not page.get("IsTruncated"):
                return found
            token = page["NextContinuationToken"]

    def digest_of(self, key: str) -> tuple[int, str]:
        """An object's size and SHA-256, read through and never written anywhere."""
        body = self.client.get_object(Bucket=self.settings.bucket, Key=key)["Body"]
        digest = hashlib.sha256()
        size = 0
        for chunk in iter(lambda: body.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
        return size, digest.hexdigest()

    def get_to(self, key: str, path: Path) -> tuple[int, str]:
        body = self.client.get_object(Bucket=self.settings.bucket, Key=key)["Body"]
        digest = hashlib.sha256()
        size = 0
        with path.open("wb") as file:
            for chunk in iter(lambda: body.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
                file.write(chunk)
        return size, digest.hexdigest()

    def get_bytes(self, key: str) -> bytes:
        return bytes(self.client.get_object(Bucket=self.settings.bucket, Key=key)["Body"].read())

    def keys(self, prefix: str) -> Iterator[str]:
        token: str | None = None
        while True:
            extra = {"ContinuationToken": token} if token else {}
            page = self.client.list_objects_v2(Bucket=self.settings.bucket, Prefix=prefix, **extra)
            for item in page.get("Contents", []):
                yield item["Key"]
            if not page.get("IsTruncated"):
                return
            token = page["NextContinuationToken"]


def _tree(folder: Path) -> Iterator[Path]:
    """Every entry under `folder`, parents first, its top-level lost+found left out; an entry gone
    while it is walked is passed over (os.walk's own way)."""
    for top in sorted(folder.iterdir()):
        if top.name == LOST_FOUND:
            continue
        yield top
        if top.is_dir() and not top.is_symlink():
            for root, dirs, files in os.walk(top):
                dirs.sort()
                for name in [*sorted(dirs), *sorted(files)]:
                    yield Path(root) / name


class FileShrank(OSError):
    """A file that grew shorter while it was read: never padded into the set (the orchestrator's
    round 2), the claims part refused instead."""


class _AtMost:
    """A file read for exactly `size` bytes; one that shrank while read is refused."""

    def __init__(self, file: Any, size: int, name: str) -> None:
        self.file, self.left, self.name = file, size, name

    def read(self, n: int = -1) -> bytes:
        want = self.left if n < 0 else min(n, self.left)
        data = self.file.read(want)
        if len(data) < want:
            raise FileShrank(f"{self.name} grew shorter while it was read")
        self.left -= len(data)
        return bytes(data)


def _add(tar: tarfile.TarFile, path: Path, name: str, taken: dict[str, Any]) -> None:
    try:
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as file:  # opened: a delete after this keeps its content
                info = tar.gettarinfo(arcname=name, fileobj=file)
                tar.addfile(info, _AtMost(file, info.size, name))
        else:
            tar.add(path, arcname=name, recursive=False)
    except FileNotFoundError:
        taken["gone"] += 1
        return
    taken["entries"] += 1


class _PartWriter:
    """A write-only file that uploads each `PART_SIZE` written as a part (the last may be less)."""

    def __init__(self, client: Any, bucket: str, key: str, upload_id: str) -> None:
        self.client, self.bucket, self.key, self.upload_id = client, bucket, key, upload_id
        self.buffer = bytearray()
        self.parts: list[dict[str, Any]] = []
        self.size = 0
        self.digest = hashlib.sha256()

    def write(self, data: bytes) -> int:
        self.buffer += data
        self.size += len(data)
        self.digest.update(data)
        while len(self.buffer) >= PART_SIZE:
            self._part(bytes(self.buffer[:PART_SIZE]))
            del self.buffer[:PART_SIZE]
        return len(data)

    def finish(self) -> None:
        if self.buffer or not self.parts:
            self._part(bytes(self.buffer))
            self.buffer.clear()

    def _part(self, chunk: bytes) -> None:
        number = len(self.parts) + 1
        done = self.client.upload_part(
            Bucket=self.bucket, Key=self.key, UploadId=self.upload_id, PartNumber=number, Body=chunk
        )
        self.parts.append({"PartNumber": number, "ETag": done["ETag"]})


# ---------------------------------------------------------------------------------------------
# The stores' own HTTP
# ---------------------------------------------------------------------------------------------


Http = Callable[[urllib.request.Request, float], bytes]


def _http(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310 - the stores' own
        return bytes(answer.read())


def _request(url: str, body: bytes, headers: dict[str, str]) -> urllib.request.Request:
    return urllib.request.Request(url, data=body, headers=headers, method="POST")


def _http_said(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        detail = error.read().decode(errors="replace")[:600]
        return f"HTTP {error.code}: {detail}"
    return f"{type(error).__name__}: {error}"


def _quoted(text: str) -> str:
    """A ClickHouse string literal."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _s3_function(url: str) -> str:
    """ClickHouse's `S3()` by its URL alone: it writes as its own pod's role."""
    return f"S3({_quoted(url)})"


@dataclass
class Stores:
    """ArcadeDB's and ClickHouse's own HTTP APIs, as the backup asks them."""

    settings: Settings
    http: Http = field(default=_http)
    #: Long enough for a large database's backup; the CronJob's own deadline is the bound.
    timeout: float = 6 * 3600

    def arcadedb_backup(self) -> Path:
        """ArcadeDB's `BACKUP DATABASE`; the zip it wrote, in the mounted folder. A zip already
        there is a run's that was killed or evicted before its own cleanup: removed first, or they
        fill the claim and every later run fails for space."""
        s = self.settings
        for stale in sorted((s.arcadedb_folder / s.arcadedb_database).glob("*.zip")):
            if stale.is_file() and not stale.is_symlink():
                stale.unlink()
        token = base64.b64encode(f"{s.arcadedb_user}:{s.arcadedb_password}".encode()).decode()
        body = json.dumps({"language": "sql", "command": "BACKUP DATABASE"}).encode()
        request = _request(
            f"{s.arcadedb_url}/api/v1/command/{urllib.parse.quote(s.arcadedb_database)}",
            body,
            {"Authorization": f"Basic {token}", "Content-Type": "application/json"},
        )
        try:
            raw = self.http(request, self.timeout)
        except Exception as error:  # noqa: BLE001 - reported in words
            raise BackupRefused("arcadedb", "BACKUP DATABASE", _http_said(error)) from error
        try:
            name = json.loads(raw)["result"][0]["backupFile"]
            if not isinstance(name, str):
                raise TypeError(name)
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise BackupRefused(
                "arcadedb", "BACKUP DATABASE", f"no backup file reported: {raw[:300]!r}"
            ) from error
        if "/" in name or name.startswith("."):
            raise BackupRefused(
                "arcadedb", "BACKUP DATABASE", f"an unexpected backup file name: {name!r}"
            )
        path = s.arcadedb_folder / s.arcadedb_database / name
        if not path.is_file():
            raise BackupRefused(
                "arcadedb",
                "read the zip",
                f"{path} is not in the mounted backups folder (is this pod on arcadedb-0's claim?)",
            )
        return path

    def clickhouse(self, statement: str, step: str) -> str:
        """`statement` run; a refusal reported in ClickHouse's own words."""
        s = self.settings
        request = _request(
            f"{s.clickhouse_url}/",
            statement.encode(),
            {"X-ClickHouse-User": s.clickhouse_user, "X-ClickHouse-Key": s.clickhouse_password},
        )
        try:
            return self.http(request, self.timeout).decode()
        except Exception as error:  # noqa: BLE001 - reported in words
            raise BackupRefused("clickhouse", step, _http_said(error)) from None

    def _on_cluster(self) -> str:
        cluster = self.settings.clickhouse_cluster
        return f" ON CLUSTER {_identifier(cluster)}" if cluster else ""

    def clickhouse_backup(self, url: str) -> str:
        database = _identifier(self.settings.clickhouse_database)
        answer = self.clickhouse(
            f"BACKUP DATABASE {database}{self._on_cluster()} TO {_s3_function(url)}",
            "BACKUP … TO S3",
        )
        if "BACKUP_CREATED" not in answer:
            raise BackupRefused(
                "clickhouse", "BACKUP … TO S3", f"ClickHouse answered {answer.strip()[:300]!r}"
            )
        return answer.split("\t", 1)[0].strip()

    def clickhouse_restore(self, url: str, set_id: str) -> None:
        """ClickHouse's database replaced by the set's, **never dropped before the restore is
        proven** (the orchestrator's ruling 5): restored into a database of its own (its own Keeper
        path, so it never meets the live one's), then the two swapped by rename, and the old dropped
        only after. A refusal leaves the live database as it was, the half-restored one removed."""
        database = _identifier(self.settings.clickhouse_database)
        stamp_ = _identifier(set_id.lower())
        restoring, old = f"{database}_restoring_{stamp_}", f"{database}_before_{stamp_}"
        # Its Keeper path is this attempt's own: a RENAME keeps the path, so the database swapped
        # in by an earlier restore of this set still holds `…_restoring_<set>`'s, and making it
        # again is refused (Code 253, kind round 4).
        attempt = uuid.uuid4().hex[:12]
        on = self._on_cluster()
        # Another set's restored copy, kept by a swap refused part-way: the set it holds is still in
        # the bucket, so it is dropped here and said, never left to pile up beside the live one.
        stale = self.clickhouse(
            f"SHOW DATABASES LIKE '{database}\\_restoring\\_%'", "find restored copies left"
        )
        for name in stale.split():
            if name != restoring and name.startswith(f"{database}_restoring_"):
                print(
                    f"restore: dropping {name}, a restored copy an earlier restore left",
                    file=sys.stderr,
                )
                self.clickhouse(
                    f"DROP DATABASE IF EXISTS {_identifier(name)}{on} SYNC", "drop a copy left"
                )
        self.clickhouse(f"DROP DATABASE IF EXISTS {restoring}{on} SYNC", "clear the restore's own")
        self.clickhouse(
            f"CREATE DATABASE {restoring}{on} ENGINE = Replicated("
            f"'/clickhouse/databases/{restoring}_{attempt}', '{{shard}}', '{{replica}}')"
            if self.settings.clickhouse_cluster
            else f"CREATE DATABASE {restoring}",
            "make the restore's own database",
        )
        try:
            answer = self.clickhouse(
                f"RESTORE DATABASE {database} AS {restoring}{on} FROM {_s3_function(url)} "
                "SETTINGS allow_different_database_def = true",
                "RESTORE … FROM S3",
            )
            if "RESTORED" not in answer:
                raise BackupRefused(
                    "clickhouse",
                    "RESTORE … FROM S3",
                    f"ClickHouse answered {answer.strip()[:300]!r}",
                )
        except BackupRefused:
            # The live database untouched; the half-restored one removed (a refusal to remove it
            # is said beside the first, never in its place).
            try:
                self.clickhouse(f"DROP DATABASE IF EXISTS {restoring}{on} SYNC", "remove the half")
            except BackupRefused:
                pass
            raise
        # The live one set aside only if it is there: after a loss (the disaster the restore is
        # for) it is not, and a RENAME of it is refused (Code 81, measured on kind in round 3).
        live = self.clickhouse(f"EXISTS DATABASE {database}", "see whether the live one is there")
        aside = live.strip() == "1"
        if aside:
            try:
                self.clickhouse(
                    f"RENAME DATABASE {database} TO {old}{on}", "set the live one aside"
                )
            except BackupRefused as refusal:
                raise BackupRefused(
                    refusal.store,
                    refusal.step,
                    f"{refusal.reason}; the live database is as it was; the set's restored copy "
                    f"is kept as {restoring}",
                ) from refusal
        try:
            self.clickhouse(
                f"RENAME DATABASE {restoring} TO {database}{on}", "put the restored one in"
            )
        except BackupRefused as refusal:
            # Between the two renames: the live one put back (or said where it is), the restored
            # one kept, both named, so ClickHouse is never left without its database unsaid.
            where = f"the set's restored database is kept as {restoring}"
            if aside:
                try:
                    self.clickhouse(
                        f"RENAME DATABASE {old} TO {database}{on}", "put the live one back"
                    )
                    where += f"; the live database was put back as {database}"
                except BackupRefused:
                    where += f"; the live database is in {old}, not put back (the recovery runbook)"
            raise BackupRefused(
                refusal.store, refusal.step, f"{refusal.reason}; {where}"
            ) from refusal
        self.clickhouse(f"DROP DATABASE IF EXISTS {old}{on} SYNC", "drop the old one")


def _identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise BackupRefused("clickhouse", "settings", f"{name!r} is not a plain name")
    return name


# ---------------------------------------------------------------------------------------------
# A set
# ---------------------------------------------------------------------------------------------


def stamp(now: dt.datetime | None = None) -> str:
    return (now or dt.datetime.now(dt.UTC)).strftime("%Y%m%dT%H%M%SZ")


_SLOT = re.compile(r"-(\d{8,})$")


def set_of(job_name: str) -> str:
    """The set a Job writes, named by its schedule slot: a CronJob names each Job
    `<cronjob>-<scheduled minute since 1970>`, so the main run and the claims run of a slot name
    the same set without looking for it; a slow or overlapping run never meets another slot's."""
    found = _SLOT.search(job_name)
    if not found:
        raise BackupRefused(
            "backup",
            "name the set",
            f"the Job's name {job_name!r} names no schedule slot: a CronJob names each Job by its "
            "scheduled minute (<cronjob>-<minutes since 1970>), and a Job made by hand is named "
            "the same way, e.g. ospreyflow-backup-$(( $(date +%s) / 60 ))",
        )
    return stamp(dt.datetime.fromtimestamp(int(found.group(1)) * 60, dt.UTC))


def take(
    settings: Settings,
    bucket: Bucket,
    stores: Stores,
    *,
    now: dt.datetime | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """One set: ArcadeDB's zip, ClickHouse's backup, the claims part (from the claims run, waited
    for, bounded), then the manifest. Returns the manifest."""
    tick = clock or time.monotonic
    started = tick()
    set_id = set_of(settings.job_name) if settings.job_name else stamp(now)
    prefix = f"sets/{set_id}/"
    try:
        finished = prefix + MANIFEST in set(bucket.keys(prefix))
    except Exception as error:  # noqa: BLE001 - reported in words
        raise BackupRefused("backup", f"read set {set_id}", _said(error)) from error
    if finished:
        # A Job of a slot run again (by hand, or its retry) never writes over a finished set.
        raise BackupRefused("backup", f"take set {set_id}", "that set is already finished")
    manifest: dict[str, Any] = {
        "set": set_id,
        "bucket": settings.bucket,
        "kms_key": settings.kms_key,
    }

    zip_path = stores.arcadedb_backup()
    graph_key = f"{prefix}arcadedb/{settings.arcadedb_database}.zip"
    try:
        size, digest = bucket.put_file(graph_key, zip_path)
    except Exception as error:  # noqa: BLE001 - reported in words
        raise BackupRefused(
            "arcadedb", f"upload to s3://{settings.bucket}/{graph_key}", _said(error)
        ) from error
    finally:
        # Never left on the claim to fill it: the next run takes another.
        zip_path.unlink(missing_ok=True)
    manifest["arcadedb"] = {
        "database": settings.arcadedb_database,
        "key": graph_key,
        "bytes": size,
        "sha256": digest,
        "seconds": round(tick() - started, 1),
    }

    analytics_started = tick()
    url = f"{settings.s3_base}/{prefix}clickhouse/"
    backup_id = stores.clickhouse_backup(url)
    try:
        # ClickHouse's own part, as its files' names, sizes and ETags (this role may list it, never
        # read it): what a restore checks before it drops anything.
        files = bucket.listing(f"{prefix}clickhouse/")
    except Exception as error:  # noqa: BLE001 - reported in words
        raise BackupRefused("clickhouse", "list its part", _said(error)) from error
    if not any(f["key"].endswith("/.backup") for f in files):
        raise BackupRefused("clickhouse", "BACKUP … TO S3", "its part holds no .backup file")
    manifest["clickhouse"] = {
        "database": settings.clickhouse_database,
        "prefix": f"{prefix}clickhouse/",
        "files": files,
        "backup_id": backup_id,
        "cluster": settings.clickhouse_cluster,
        "seconds": round(tick() - analytics_started, 1),
    }
    if settings.claims:
        manifest["claims"] = _wait_for_claims(settings, bucket, set_id, tick, sleep)
    manifest["seconds"] = round(tick() - started, 1)
    # When the set finished (UTC): the time a restore brings the managed database (RDS) back to,
    # point in time, so the stores and it agree (ADR-148 Amendment 7; the recovery runbook).
    finished_at = (
        dt.datetime.now(dt.UTC) if now is None else now + dt.timedelta(seconds=manifest["seconds"])
    )
    manifest["finished"] = finished_at.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        bucket.put_bytes(prefix + MANIFEST, json.dumps(manifest, indent=2).encode())
    except Exception as error:  # noqa: BLE001 - reported in words
        raise BackupRefused("backup", "write the manifest", _said(error)) from error
    return manifest


def _claims_part(bucket: Bucket, set_id: str) -> dict[str, Any] | None:
    key = f"sets/{set_id}/claims/{MANIFEST}"
    if key not in set(bucket.keys(f"sets/{set_id}/claims/")):
        return None
    found: dict[str, Any] = json.loads(bucket.get_bytes(key))
    return found


def _wait_for_claims(
    settings: Settings,
    bucket: Bucket,
    set_id: str,
    tick: Callable[[], float],
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    """The claims run's part of this slot's set, waited for at most `claims_wait` seconds: never a
    hang. Without it the set is left unfinished and the run fails in words."""
    deadline = tick() + settings.claims_wait
    while True:
        try:
            part = _claims_part(bucket, set_id)
        except Exception as error:  # noqa: BLE001 - reported in words
            raise BackupRefused(
                "claims", f"read set {set_id}'s claims part", _said(error)
            ) from error
        if part is not None:
            missing = [n for n in settings.claims if n not in part]
            if missing:
                raise BackupRefused(
                    "claims",
                    f"check set {set_id}'s claims part",
                    f"it lacks {', '.join(missing)}: the set is left unfinished",
                )
            return part
        left = deadline - tick()
        if left <= 0:
            raise BackupRefused(
                "claims",
                f"wait for set {set_id}'s claims part",
                f"none after {settings.claims_wait:g} s: the claims run (ospreyflow-backup-claims) "
                "for this slot failed or never ran, so the set is left unfinished and is never "
                "restored from",
            )
        sleep(min(CLAIMS_POLL, left))


def take_claims(settings: Settings, bucket: Bucket) -> dict[str, Any]:
    """The claims run: each claim streamed into its slot's set, then the part's own manifest. The
    main run writes the set's manifest once it is there."""
    if not settings.job_name:
        raise BackupRefused("claims", "name the set", "OSPREY_BACKUP_JOB is not set")
    set_id = set_of(settings.job_name)
    prefix = f"sets/{set_id}/"
    try:
        finished = prefix + MANIFEST in set(bucket.keys(prefix))
    except Exception as error:  # noqa: BLE001 - reported in words
        raise BackupRefused("claims", f"read set {set_id}", _said(error)) from error
    if finished:
        raise BackupRefused(
            "claims", f"add to set {set_id}", "that set is already finished; a part is never added"
        )
    part: dict[str, Any] = {}
    for name in settings.claims:
        folder = settings.claims_folder / name
        if not folder.is_dir():
            raise BackupRefused("claims", f"read {name}", f"{folder} is not mounted in this pod")
        key = f"{prefix}claims/{name}.tar.gz"
        try:
            size, digest, taken = bucket.put_tree(key, folder)
        except Exception as error:  # noqa: BLE001 - reported in words
            raise BackupRefused(
                "claims", f"upload {name} to s3://{settings.bucket}/{key}", _said(error)
            ) from error
        part[name] = {"key": key, "bytes": size, "sha256": digest, **taken}
    try:
        bucket.put_bytes(f"{prefix}claims/{MANIFEST}", json.dumps(part, indent=2).encode())
    except Exception as error:  # noqa: BLE001 - reported in words
        raise BackupRefused("claims", "write the claims part's manifest", _said(error)) from error
    return {"set": set_id, **part}


@dataclass(frozen=True)
class FoundSet:
    set_id: str
    complete: bool


def sets(bucket: Bucket) -> list[FoundSet]:
    """Every set in the bucket, oldest first, and whether it finished (has its manifest)."""
    seen: dict[str, bool] = {}
    for key in bucket.keys("sets/"):
        parts = key.split("/")
        if len(parts) < 3:
            continue
        seen.setdefault(parts[1], False)
        if parts[2] == MANIFEST:
            seen[parts[1]] = True
    return [FoundSet(s, c) for s, c in sorted(seen.items())]


def _malformed(manifest: Any) -> list[str]:
    """What is wrong with a manifest's shape (each part's fields and their types), in words."""
    if not isinstance(manifest, dict):
        return ["it is not an object"]
    problems: list[str] = []

    def fields(where: str, part: Any, wanted: dict[str, type]) -> None:
        if not isinstance(part, dict):
            problems.append(f"{where} is not an object")
            return
        for name, kind in wanted.items():
            if not isinstance(part.get(name), kind) or isinstance(part.get(name), bool):
                problems.append(f"{where}.{name} is not a {kind.__name__}")

    fields("arcadedb", manifest.get("arcadedb"), {"key": str, "bytes": int, "sha256": str})
    analytics = manifest.get("clickhouse")
    fields("clickhouse", analytics, {"prefix": str})
    files = analytics.get("files", []) if isinstance(analytics, dict) else []
    if not isinstance(files, list):
        problems.append("clickhouse.files is not a list")
    else:
        for index, file in enumerate(files):
            fields(f"clickhouse.files[{index}]", file, {"key": str, "bytes": int, "etag": str})
    claims = manifest.get("claims") or {}
    if not isinstance(claims, dict):
        problems.append("claims is not an object")
    else:
        for name, part in claims.items():
            fields(f"claims.{name}", part, {"key": str, "bytes": int, "sha256": str})
    return problems


def manifest_of(bucket: Bucket, set_id: str) -> dict[str, Any]:
    """The set's manifest, refused in words unless a finished set's, of a manifest's shape."""
    try:
        manifest: Any = json.loads(bucket.get_bytes(f"sets/{set_id}/{MANIFEST}"))
    except Exception as error:  # noqa: BLE001 - reported in words
        raise BackupRefused(
            "restore", f"read set {set_id}", f"no finished set by that name ({_said(error)})"
        ) from error
    if problems := _malformed(manifest):
        raise BackupRefused(
            "restore",
            f"read set {set_id}",
            "its manifest is malformed: " + "; ".join(problems) + "; nothing was touched",
        )
    found: dict[str, Any] = manifest
    return found


def latest(bucket: Bucket) -> str:
    finished = [s.set_id for s in sets(bucket) if s.complete]
    if not finished:
        raise BackupRefused("restore", "find a set", "the bucket holds no finished set")
    return finished[-1]


def verify_set(
    bucket: Bucket, set_id: str, claims: tuple[str, ...] = (), parts: tuple[str, ...] = ()
) -> dict[str, Any]:
    """**Every part of the set checked before anything is replaced** (the orchestrator's rulings 3
    and 4): the manifest there (a finished set) and **its own** (its `set` this set, every key it
    names under `sets/<set_id>/`); the deployment's claims (`claims`) each in it, so a set without
    its claims part is never restored into a deployment that has them; ArcadeDB's zip and each claim
    by size and SHA-256, read through and kept nowhere; ClickHouse's part by each file's name, size
    and ETag. `parts` narrows the check to those parts (a step re-checking its own). A part missing
    (expired, say), changed or another set's refuses the restore with nothing touched. Returns the
    manifest."""
    manifest = manifest_of(bucket, set_id)
    prefix = f"sets/{set_id}/"
    wanted = set(parts or ("arcadedb", "clickhouse", "claims"))
    problems: list[str] = []
    if manifest.get("set") != set_id:
        problems.append(f"its manifest is set {manifest.get('set')!r}'s, not {set_id}'s")
    named = [manifest["arcadedb"]["key"], manifest["clickhouse"]["prefix"],
             *(f["key"] for f in manifest["clickhouse"].get("files", [])),
             *(c["key"] for c in (manifest.get("claims") or {}).values())]  # fmt: skip
    if outside := [k for k in named if not k.startswith(prefix)]:
        problems.append(f"its manifest names objects outside the set: {', '.join(outside)}")
    if missing := [c for c in claims if c not in (manifest.get("claims") or {})]:
        problems.append(f"it holds no part for the claim {', '.join(missing)}")

    def check(what: str, key: str, size: int, sha256: str) -> None:
        try:
            found = bucket.digest_of(key)
        except Exception as error:  # noqa: BLE001 - reported in words
            problems.append(f"{what} ({key}): {_said(error)}")
            return
        if found != (size, sha256):
            problems.append(
                f"{what} ({key}) is {found[0]} bytes, SHA-256 {found[1][:12]}…; "
                f"the manifest says {size}, {sha256[:12]}…"
            )

    if "arcadedb" in wanted:
        graph = manifest["arcadedb"]
        check("ArcadeDB's zip", graph["key"], graph["bytes"], graph["sha256"])
    analytics = manifest["clickhouse"]
    if "clickhouse" in wanted and not analytics.get("files"):
        problems.append("ClickHouse's part has no file list in the manifest")
    elif "clickhouse" in wanted:
        try:
            now = {f["key"]: f for f in bucket.listing(analytics["prefix"])}
        except Exception as error:  # noqa: BLE001 - reported in words
            now = {}
            problems.append(f"ClickHouse's part ({analytics['prefix']}): {_said(error)}")
        for file in analytics["files"]:
            there = now.get(file["key"])
            if there is None:
                problems.append(f"ClickHouse's {file['key']} is missing")
                continue
            if (there["bytes"], there["etag"]) != (file["bytes"], file["etag"]):
                problems.append(f"ClickHouse's {file['key']} is not the file the set wrote")
    if "claims" in wanted:
        for name, part in sorted((manifest.get("claims") or {}).items()):
            check(f"the claim {name}", part["key"], part["bytes"], part["sha256"])
    if problems:
        raise BackupRefused(
            "restore", f"verify set {set_id}", "; ".join(problems) + "; nothing was touched"
        )
    return manifest


#: Where Kubernetes mounts a pod's own service account's token, namespace and CA.
SERVICE_ACCOUNT_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")


def _pods(selector: str) -> list[dict[str, Any]]:
    """The namespace's pods matching `selector`, by this pod's own service account (its Role: get
    and list pods, nothing else)."""
    import ssl

    account = SERVICE_ACCOUNT_DIR
    namespace = (account / "namespace").read_text().strip()
    request = urllib.request.Request(
        f"https://kubernetes.default.svc/api/v1/namespaces/{namespace}/pods?"
        + urllib.parse.urlencode({"labelSelector": selector}),
        headers={"Authorization": f"Bearer {(account / 'token').read_text().strip()}"},
    )
    context = ssl.create_default_context(cafile=str(account / "ca.crt"))
    with urllib.request.urlopen(request, timeout=30, context=context) as answer:  # noqa: S310
        items: list[dict[str, Any]] = json.loads(answer.read())["items"]
    return items


def writers_stopped(
    settings: Settings, pods: Callable[[str], list[dict[str, Any]]] | None = None
) -> None:
    """A restore refuses while anything that writes runs (the orchestrator's ruling 4): the writers
    the render names (`OSPREY_BACKUP_WRITERS`: ArcadeDB, every workload that mounts the set's claims
    or writes the stores, the backups' own runs). A pod finished (Succeeded, Failed) is not
    running. **It fails closed**: with no writers named, or the pods unlisted, it refuses; it never
    proceeds unconfirmed."""
    if not settings.writers:
        raise BackupRefused(
            "restore",
            "see what runs",
            "cannot confirm the writers are stopped: none are named to check "
            "(OSPREY_BACKUP_WRITERS); nothing was touched",
        )
    selector = f"app.kubernetes.io/name in ({','.join(settings.writers)})"
    try:
        found = (pods or _pods)(selector)
    except Exception as error:  # noqa: BLE001 - reported in words
        # Fails closed: unless the cluster's API answers this pod's own account (its egress row to
        # the API, its Role), no restore proceeds, never one that guessed.
        raise BackupRefused(
            "restore",
            "see what runs",
            f"cannot confirm the writers are stopped: the pods could not be listed "
            f"({_http_said(error)}); nothing was touched",
        ) from error
    finished = ("Succeeded", "Failed")
    running = sorted(
        p["metadata"]["name"] for p in found if (p.get("status") or {}).get("phase") not in finished
    )
    if running:
        raise BackupRefused(
            "restore",
            "see what runs",
            f"{', '.join(running)} still running: stop every writer first "
            f"({', '.join(settings.writers)}; the recovery runbook); nothing was touched",
        )


def fetch_graph(bucket: Bucket, set_id: str, folder: Path) -> Path:
    """The set's ArcadeDB zip into `folder`, checked against its manifest before it is used; the
    whole set is verified by the Job's first step (`verify`), so this checks the zip alone, as it
    downloads it."""
    manifest = manifest_of(bucket, set_id)
    graph = manifest["arcadedb"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{graph['database']}.zip"
    try:
        size, digest = bucket.get_to(graph["key"], path)
    except Exception as error:  # noqa: BLE001 - reported in words
        path.unlink(missing_ok=True)
        raise BackupRefused(
            "arcadedb", f"fetch s3://{bucket.settings.bucket}/{graph['key']}", _said(error)
        ) from error
    if (size, digest) != (graph["bytes"], graph["sha256"]):
        path.unlink(missing_ok=True)
        raise BackupRefused(
            "arcadedb",
            "check the zip",
            f"it is {size} bytes, SHA-256 {digest[:12]}…; the manifest says {graph['bytes']}, "
            f"{graph['sha256'][:12]}…",
        )
    return path


def fetch_claims(bucket: Bucket, set_id: str, folder: Path) -> list[str]:
    """Each claim of the set put back into `folder/<name>` as it was in the set: the part checked
    against the manifest, unpacked beside the claim's contents (refusing any entry outside it),
    and only then the old contents, but for lost+found, replaced. Run with every pod that mounts
    the claims stopped."""
    manifest = manifest_of(bucket, set_id)  # the whole set verified by the Job's first step
    claims = manifest.get("claims")
    if not claims:
        raise BackupRefused("claims", f"restore set {set_id}", "the set holds no claims part")
    restored = []
    for name, part in sorted(claims.items()):
        target = folder / name
        target.mkdir(parents=True, exist_ok=True)
        staging = target / ".osprey-restore"
        before = target / ".osprey-before"
        if before.exists():
            raise BackupRefused(
                "claims",
                f"restore {name}",
                f"{before} is there: a restore stopped while it replaced the claim; it holds the "
                "claim's old contents. See the recovery runbook before restoring again; nothing "
                "was touched",
            )
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        archive = target / ".osprey-restore.tar.gz"
        swapping = False
        try:
            try:
                size, digest = bucket.get_to(part["key"], archive)
            except Exception as error:  # noqa: BLE001 - reported in words
                raise BackupRefused(
                    "claims", f"fetch s3://{bucket.settings.bucket}/{part['key']}", _said(error)
                ) from error
            if (size, digest) != (part["bytes"], part["sha256"]):
                raise BackupRefused(
                    "claims",
                    f"check {name}",
                    f"it is {size} bytes, SHA-256 {digest[:12]}…; the manifest says "
                    f"{part['bytes']}, {part['sha256'][:12]}…",
                )
            try:
                with tarfile.open(archive, mode="r:gz") as tar:
                    tar.extractall(staging, filter="data")
            except (tarfile.TarError, OSError) as error:
                raise BackupRefused("claims", f"unpack {name}", str(error)) from error
            # The old contents set aside on the claim (renamed, never deleted), then the set's moved
            # in, then the old removed: a failure part-way keeps both, and says where each is.
            swapping = True
            try:
                before.mkdir()
                for entry in list(target.iterdir()):
                    if entry.name not in (LOST_FOUND, staging.name, archive.name, before.name):
                        entry.rename(before / entry.name)
                for entry in list(staging.iterdir()):
                    entry.rename(target / entry.name)
            except OSError as error:
                raise BackupRefused(
                    "claims",
                    f"put {name} in place",
                    f"{error}; the claim's old contents are in {before}, the set's not yet moved "
                    f"in are in {staging}: nothing was removed (the recovery runbook)",
                ) from error
            shutil.rmtree(before)
        finally:
            # Once the old contents are out of place, the set's are never removed here.
            if not swapping:
                shutil.rmtree(staging, ignore_errors=True)
            elif staging.exists() and not any(staging.iterdir()):
                staging.rmdir()
            archive.unlink(missing_ok=True)
        restored.append(name)
    return restored


def restore_analytics(
    settings: Settings,
    bucket: Bucket,
    stores: Stores,
    set_id: str,
    pods: Callable[[str], list[dict[str, Any]]] | None = None,
) -> None:  # fmt: skip
    """ClickHouse's database replaced from the set, only once nothing writes and the whole set is
    verified: ClickHouse is dropped only for a set it can be restored from."""
    writers_stopped(settings, pods)
    manifest = verify_set(bucket, set_id, parts=("clickhouse",))
    url = f"{settings.s3_base}/{manifest['clickhouse']['prefix']}"
    stores.clickhouse_restore(url, set_id)


# ---------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="platform_backup", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup", help="take a set (sets expire by the bucket's lifecycle rule)")
    commands.add_parser("sets", help="list the sets, newest last")
    fetch = commands.add_parser("fetch-graph", help="a set's ArcadeDB zip into a folder, checked")
    fetch.add_argument("--set", default="latest")
    fetch.add_argument("--to", type=Path, required=True)
    analytics = commands.add_parser("restore-analytics", help="ClickHouse's RESTORE from a set")
    analytics.add_argument("--set", default="latest")
    commands.add_parser("backup-claims", help="the claims run: each claim into its slot's set")
    commands.add_parser("writers", help="a restore's guard: refuses while anything writes")
    verify = commands.add_parser(
        "verify", help="a restore's first step: nothing writing, every part checked"
    )
    verify.add_argument("--set", default="latest")
    restore_claims = commands.add_parser("restore-claims", help="a set's claims put back")
    restore_claims.add_argument("--set", default="latest")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
        bucket = Bucket(settings)
        stores = Stores(settings)
        if args.command == "backup":
            manifest = take(settings, bucket, stores)
            graph, analytics = manifest["arcadedb"], manifest["clickhouse"]
            print(
                f"backup: set {manifest['set']} written in {manifest['seconds']} s "
                f"(ArcadeDB {graph['bytes']} bytes; ClickHouse {analytics['backup_id']})"
            )
        elif args.command == "sets":
            # Each set, and for a finished one when it finished (UTC): the time a restore of it
            # brings the managed database back to first (the recovery runbook).
            for found in sets(bucket):
                if not found.complete:
                    print(f"{found.set_id}\tunfinished")
                    continue
                try:
                    at = manifest_of(bucket, found.set_id).get("finished", "time not recorded")
                except BackupRefused as refusal:
                    at = f"its manifest is unreadable ({refusal.reason})"
                print(f"{found.set_id}\tfinished\t{at}")
        elif args.command == "fetch-graph":
            set_id = latest(bucket) if args.set == "latest" else args.set
            path = fetch_graph(bucket, set_id, args.to)
            print(f"restore: set {set_id}'s ArcadeDB zip at {path}, checked against its manifest")
        elif args.command == "writers":
            writers_stopped(settings)
            print("restore: nothing writing")
        elif args.command == "verify":
            set_id = latest(bucket) if args.set == "latest" else args.set
            writers_stopped(settings)
            verify_set(bucket, set_id, claims=settings.claims)
            print(f"restore: set {set_id} verified, every part; nothing writing")
        elif args.command == "backup-claims":
            part = take_claims(settings, bucket)
            print(
                f"backup-claims: set {part['set']}'s claims part written: "
                + "; ".join(f"{n} {part[n]['bytes']} bytes" for n in settings.claims)
            )
        elif args.command == "restore-claims":
            set_id = latest(bucket) if args.set == "latest" else args.set
            writers_stopped(settings)
            names = fetch_claims(bucket, set_id, settings.claims_folder)
            print(f"restore: {', '.join(names)} put back from set {set_id}")
        elif args.command == "restore-analytics":
            set_id = latest(bucket) if args.set == "latest" else args.set
            restore_analytics(settings, bucket, stores, set_id)
            print(f"restore: ClickHouse restored from set {set_id}")
    except BackupRefused as refusal:
        print(f"{args.command} refused: {refusal}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
