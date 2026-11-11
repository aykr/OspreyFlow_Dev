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

**ClickHouse** is given no role and no key: the backup role's temporary credentials travel in the
`BACKUP` statement, so ClickHouse writes as the role does, under the bucket's policy and its key,
and an expired session is refused as S3 refuses one. ClickHouse masks the credentials in its
query log.

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
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: A part of a multipart upload: S3's own minimum is 5 MiB; a part this size keeps a
#: hundred-gigabyte zip under S3's ten-thousand-part limit.
PART_SIZE = 64 * 1024 * 1024
#: Sets kept unless `OSPREY_BACKUP_KEEP` says otherwise.
KEEP = 14
MANIFEST = "manifest.json"


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
    keep: int = KEEP

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
            keep=int(env.get("OSPREY_BACKUP_KEEP", str(KEEP))),
        )

    @property
    def s3_base(self) -> str:
        endpoint = self.s3_endpoint or f"https://s3.{self.region}.amazonaws.com"
        return f"{endpoint.rstrip('/')}/{self.bucket}"


# ---------------------------------------------------------------------------------------------
# S3, by the role's credentials
# ---------------------------------------------------------------------------------------------


def _said(error: Exception) -> str:
    """S3's own code and words for a refusal (botocore's `ClientError`), or the error's."""
    response = getattr(error, "response", None)
    if isinstance(response, dict) and "Error" in response:
        found = response["Error"]
        return f"S3 refused it ({found.get('Code')}: {found.get('Message')})"
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

    def credentials(self) -> tuple[str, str, str | None]:
        """The role's credentials now, as ClickHouse is handed them (frozen: never refreshed)."""
        if self.session is None:
            raise BackupRefused("clickhouse", "credentials", "no session to take them from")
        found = self.session.get_credentials()
        if found is None:
            raise BackupRefused(
                "clickhouse",
                "credentials",
                "the role gave no credentials (is the pod's service account the backup role's?)",
            )
        frozen = found.get_frozen_credentials()
        return frozen.access_key, frozen.secret_key, frozen.token

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

    def delete(self, keys: list[str]) -> None:
        for start in range(0, len(keys), 1000):
            chunk = keys[start : start + 1000]
            self.client.delete_objects(
                Bucket=self.settings.bucket,
                Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
            )


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


def _s3_function(url: str, credentials: tuple[str, str, str | None]) -> str:
    key, secret, token = credentials
    words = [_quoted(url), _quoted(key), _quoted(secret)]
    if token:
        words.append(_quoted(token))
    return f"S3({', '.join(words)})"


@dataclass
class Stores:
    """ArcadeDB's and ClickHouse's own HTTP APIs, as the backup asks them."""

    settings: Settings
    http: Http = field(default=_http)
    #: Long enough for a large database's backup; the CronJob's own deadline is the bound.
    timeout: float = 6 * 3600

    def arcadedb_backup(self) -> Path:
        """ArcadeDB's `BACKUP DATABASE`; the zip it wrote, in the mounted folder."""
        s = self.settings
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

    def clickhouse(self, statement: str, step: str, secrets: tuple[str | None, ...] = ()) -> str:
        """`statement` run; a refusal reported with `secrets` (the role's) never in its words:
        ClickHouse's error may quote the statement back."""
        s = self.settings
        request = _request(
            f"{s.clickhouse_url}/",
            statement.encode(),
            {"X-ClickHouse-User": s.clickhouse_user, "X-ClickHouse-Key": s.clickhouse_password},
        )
        try:
            return self.http(request, self.timeout).decode()
        except Exception as error:  # noqa: BLE001 - reported in words
            raise BackupRefused("clickhouse", step, _scrub(_http_said(error), secrets)) from None

    def _on_cluster(self) -> str:
        cluster = self.settings.clickhouse_cluster
        return f" ON CLUSTER {_identifier(cluster)}" if cluster else ""

    def clickhouse_backup(self, url: str, credentials: tuple[str, str, str | None]) -> str:
        database = _identifier(self.settings.clickhouse_database)
        answer = self.clickhouse(
            f"BACKUP DATABASE {database}{self._on_cluster()} TO {_s3_function(url, credentials)}",
            "BACKUP … TO S3",
            credentials[1:],
        )
        if "BACKUP_CREATED" not in answer:
            raise BackupRefused(
                "clickhouse", "BACKUP … TO S3", f"ClickHouse answered {answer.strip()[:300]!r}"
            )
        return answer.split("\t", 1)[0].strip()

    def clickhouse_restore(self, url: str, credentials: tuple[str, str, str | None]) -> None:
        database = _identifier(self.settings.clickhouse_database)
        self.clickhouse(
            f"DROP DATABASE IF EXISTS {database}{self._on_cluster()} SYNC", "DROP DATABASE"
        )
        source = _s3_function(url, credentials)
        answer = self.clickhouse(
            f"RESTORE DATABASE {database}{self._on_cluster()} FROM {source}",
            "RESTORE … FROM S3",
            credentials[1:],
        )
        if "RESTORED" not in answer:
            raise BackupRefused(
                "clickhouse", "RESTORE … FROM S3", f"ClickHouse answered {answer.strip()[:300]!r}"
            )


def _scrub(text: str, secrets: tuple[str | None, ...]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[the role's secret]")
    return text


def _identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise BackupRefused("clickhouse", "settings", f"{name!r} is not a plain name")
    return name


# ---------------------------------------------------------------------------------------------
# A set
# ---------------------------------------------------------------------------------------------


def stamp(now: dt.datetime | None = None) -> str:
    return (now or dt.datetime.now(dt.UTC)).strftime("%Y%m%dT%H%M%SZ")


def take(settings: Settings, bucket: Bucket, stores: Stores, *, now: dt.datetime | None = None,
         clock: Callable[[], float] | None = None) -> dict[str, Any]:  # fmt: skip
    """One set: ArcadeDB's zip, ClickHouse's backup, then the manifest. Returns the manifest."""
    import time

    tick = clock or time.monotonic
    started = tick()
    set_id = stamp(now)
    prefix = f"sets/{set_id}/"
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
    backup_id = stores.clickhouse_backup(url, bucket.credentials())
    manifest["clickhouse"] = {
        "database": settings.clickhouse_database,
        "prefix": f"{prefix}clickhouse/",
        "backup_id": backup_id,
        "cluster": settings.clickhouse_cluster,
        "seconds": round(tick() - analytics_started, 1),
    }
    manifest["seconds"] = round(tick() - started, 1)
    try:
        bucket.put_bytes(prefix + MANIFEST, json.dumps(manifest, indent=2).encode())
    except Exception as error:  # noqa: BLE001 - reported in words
        raise BackupRefused("backup", "write the manifest", _said(error)) from error
    return manifest


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


def prune(bucket: Bucket, keep: int) -> list[str]:
    """The finished sets beyond the newest `keep` removed, and every unfinished set older than
    the oldest one kept. Returns the sets removed. Never removes the newest finished set."""
    found = sets(bucket)
    finished = [s.set_id for s in found if s.complete]
    kept = finished[-max(keep, 1) :]
    if not kept:
        return []
    oldest_kept = kept[0]
    removed = [s.set_id for s in found if s.set_id not in kept and s.set_id < oldest_kept]
    for set_id in removed:
        bucket.delete(list(bucket.keys(f"sets/{set_id}/")))
    return removed


def manifest_of(bucket: Bucket, set_id: str) -> dict[str, Any]:
    try:
        manifest: dict[str, Any] = json.loads(bucket.get_bytes(f"sets/{set_id}/{MANIFEST}"))
    except Exception as error:  # noqa: BLE001 - reported in words
        raise BackupRefused(
            "restore", f"read set {set_id}", f"no finished set by that name ({_said(error)})"
        ) from error
    return manifest


def latest(bucket: Bucket) -> str:
    finished = [s.set_id for s in sets(bucket) if s.complete]
    if not finished:
        raise BackupRefused("restore", "find a set", "the bucket holds no finished set")
    return finished[-1]


def fetch_graph(bucket: Bucket, set_id: str, folder: Path) -> Path:
    """The set's ArcadeDB zip into `folder`, checked against its manifest before it is used."""
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


def restore_analytics(settings: Settings, bucket: Bucket, stores: Stores, set_id: str) -> None:
    manifest = manifest_of(bucket, set_id)
    url = f"{settings.s3_base}/{manifest['clickhouse']['prefix']}"
    stores.clickhouse_restore(url, bucket.credentials())


# ---------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="platform_backup", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup", help="take a set, then remove the sets beyond the kept number")
    commands.add_parser("sets", help="list the sets, newest last")
    fetch = commands.add_parser("fetch-graph", help="a set's ArcadeDB zip into a folder, checked")
    fetch.add_argument("--set", default="latest")
    fetch.add_argument("--to", type=Path, required=True)
    analytics = commands.add_parser("restore-analytics", help="ClickHouse's RESTORE from a set")
    analytics.add_argument("--set", default="latest")
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
            removed = prune(bucket, settings.keep)
            if removed:
                print(f"backup: removed {len(removed)} older set(s): {', '.join(removed)}")
        elif args.command == "sets":
            for found in sets(bucket):
                print(f"{found.set_id}\t{'finished' if found.complete else 'unfinished'}")
        elif args.command == "fetch-graph":
            set_id = latest(bucket) if args.set == "latest" else args.set
            path = fetch_graph(bucket, set_id, args.to)
            print(f"restore: set {set_id}'s ArcadeDB zip at {path}, checked against its manifest")
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
