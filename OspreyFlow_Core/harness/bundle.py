"""A release in one file, for a deployment that cannot reach GitHub or a registry (ADR-114
Amendment 8 point 10, the owner's ruling: full signatures carried).

`ospreyflow update --make-bundle FILE [--to vX.Y.Z]`, on a machine that reaches them, verifies the
release online and writes: the release's notes, its lock and the lock's signature; the tag's source
(`git bundle`); and every image twice — as `cosign save` keeps it (with its signatures and their
transparency-log proofs) and as `docker save` writes it.

`ospreyflow update --from FILE` verifies it with no network at all: the lock against its signature,
each owned image against the release workflow's identity, and for every image the chain from the
signed lock to what Docker loads — the saved manifest's hash is the digest the lock names, the
manifest names a configuration, and the loaded image's ID must be that configuration's digest. Only
then is anything loaded into the deployment.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import yaml

from harness.signatures import OWNED_SERVICES, Cosign, Identity

BUNDLE_FORMAT = 1
Run = Callable[[Sequence[str]], tuple[int, str]]


class BundleRefused(Exception):
    """A bundle that may not be applied, and why."""


def _need(run: Run, argv: Sequence[str], what: str) -> str:
    code, said = run(argv)
    if code != 0:
        last = [line for line in said.splitlines() if line.strip()]
        raise BundleRefused(f"{what}: {last[-1] if last else f'exit {code}'}")
    return said


def _entries(lock_text: str) -> list[dict[str, Any]]:
    return [e for e in (yaml.safe_load(lock_text) or {}).get("images") or [] if isinstance(e, dict)]


def make_bundle(
    out: Path, release: dict[str, str], repo: Path, run: Run, cosign: Cosign,
    *, staging: Path | None = None,
) -> Path:  # fmt: skip
    """Writes the bundle for a release already verified online (`update --make-bundle` does that
    first)."""
    tag = release["tag"]
    root = staging or Path(tempfile.mkdtemp(prefix="ospreyflow-bundle-", dir=out.parent))
    root.mkdir(parents=True, exist_ok=True)
    try:
        (root / "release.json").write_text(
            json.dumps({"format": BUNDLE_FORMAT, "tag": tag, "notes": release["notes"]}),
            encoding="utf-8",
        )
        (root / "versions.lock").write_text(release["lock"], encoding="utf-8")
        (root / "versions.lock.sigstore.json").write_text(
            release["lock_signature"], encoding="utf-8"
        )
        _need(run, ["git", "-C", str(repo), "fetch", "--tags", "origin"], "fetch the release's tag")
        _need(run, ["git", "-C", str(repo), "bundle", "create", str(root / "source.bundle"), tag],
              "bundle the release's source")  # fmt: skip
        (root / "saved").mkdir(exist_ok=True)
        (root / "images").mkdir(exist_ok=True)
        manifest = []
        for index, entry in enumerate(_entries(release["lock"])):
            repository, digest = str(entry["repository"]), str(entry["digest"])
            ref, local = f"{repository}@{digest}", f"{repository}:ospreyflow-{tag}"
            saved, said = cosign.save(ref, root / "saved" / str(index))
            if not saved:
                raise BundleRefused(f"save {ref} with its signatures: {said}")
            _need(run, ["docker", "pull", ref], f"pull {ref}")
            _need(run, ["docker", "tag", ref, local], f"name {ref}")
            _need(run, ["docker", "save", "-o", str(root / "images" / f"{index}.tar"), local],
                  f"save {ref}")  # fmt: skip
            manifest.append({
                "service": entry.get("service"), "repository": repository, "digest": digest,
                "saved": f"saved/{index}", "tar": f"images/{index}.tar", "local": local,
            })  # fmt: skip
        (root / "manifest.json").write_text(json.dumps({"images": manifest}), encoding="utf-8")
        with tarfile.open(out, "w") as bundle:
            bundle.add(root, arcname=".")
    finally:
        if staging is None:
            shutil.rmtree(root, ignore_errors=True)
    return out


def open_bundle(path: Path, into: Path) -> dict[str, Any]:
    """Unpacks a bundle into `into`, refusing any member that would land outside it."""
    into.mkdir(parents=True, exist_ok=True)
    base = into.resolve()
    try:
        with tarfile.open(path) as bundle:
            for member in bundle.getmembers():
                target = (into / member.name).resolve()
                if member.issym() or member.islnk() or not target.is_relative_to(base):
                    raise BundleRefused(
                        f"{path.name} holds {member.name!r}, which would land outside the folder "
                        "it is opened in; it is not a bundle this command made"
                    )
            bundle.extractall(into, filter="data")
    except (OSError, tarfile.TarError) as unreadable:
        raise BundleRefused(f"{path.name} is not a readable bundle ({unreadable})") from None
    try:
        release = json.loads((into / "release.json").read_text(encoding="utf-8"))
        lock = (into / "versions.lock").read_text(encoding="utf-8")
        signature = (into / "versions.lock.sigstore.json").read_text(encoding="utf-8")
    except (OSError, ValueError) as missing:
        raise BundleRefused(f"{path.name} is not a complete bundle ({missing})") from None
    if release.get("format") != BUNDLE_FORMAT:
        raise BundleRefused(f"{path.name} is a bundle of another format ({release.get('format')})")
    return {"tag": str(release["tag"]), "notes": str(release.get("notes") or ""), "lock": lock,
            "lock_signature": signature, "root": into}  # fmt: skip


def _hashed_blob(layout: Path, digest: str, repository: str) -> dict[str, Any]:
    """A saved blob, refused unless its content hashes to its name."""
    path = layout / "blobs" / "sha256" / digest.split(":", 1)[1]
    try:
        blob = path.read_bytes()
    except OSError:
        raise BundleRefused(
            f"{repository}@{digest}: the image the signed lock names is not in the bundle"
        ) from None
    if "sha256:" + hashlib.sha256(blob).hexdigest() != digest:
        raise BundleRefused(f"{repository}: its saved manifest does not match its digest")
    loaded: dict[str, Any] = json.loads(blob)
    return loaded


def _manifest_config(layout: Path, digest: str, repository: str, platform: str) -> str:
    """The configuration digest the saved manifest `digest` names, each hash checked. An image
    published for several platforms is locked by its index: followed to this machine's platform."""
    try:
        index = json.loads((layout / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = {"manifests": []}
    if digest not in {m.get("digest") for m in index.get("manifests") or []}:
        raise BundleRefused(
            f"{repository}@{digest}: the image the signed lock names is not in the bundle"
        )
    manifest = _hashed_blob(layout, digest, repository)
    if "config" not in manifest:  # an index: this platform's manifest, by the index's own list
        os_name, _, arch = platform.partition("/")
        children = [
            m for m in manifest.get("manifests") or []
            if (m.get("platform") or {}).get("os") == os_name
            and (m.get("platform") or {}).get("architecture") == arch
        ]  # fmt: skip
        if not children:
            raise BundleRefused(f"{repository}: the release has no image for {platform}")
        manifest = _hashed_blob(layout, str(children[0]["digest"]), repository)
    return str(manifest["config"]["digest"])


def check_bundle(
    root: Path, identity: Identity, cosign: Cosign, run: Run
) -> dict[str, tuple[str, str]]:
    """Verifies an opened bundle with no network and loads its images: repository → (the local
    reference to run, the image ID it must have)."""
    cosign.verify_blob(
        root / "versions.lock", root / "versions.lock.sigstore.json", identity, offline=True
    )
    lock = (root / "versions.lock").read_text(encoding="utf-8")
    platform = _need(
        run, ["docker", "version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"], "ask Docker"
    ).strip()
    listed = json.loads((root / "manifest.json").read_text(encoding="utf-8")).get("images") or []
    by_ref = {(str(m["repository"]), str(m["digest"])): m for m in listed}
    chosen: list[tuple[dict[str, Any], str]] = []
    for entry in _entries(lock):
        repository, digest = str(entry["repository"]), str(entry["digest"])
        item = by_ref.get((repository, digest))
        if item is None:
            raise BundleRefused(
                f"{repository}@{digest}: the image the signed lock names is not in the bundle"
            )
        layout = root / str(item["saved"])
        config = _manifest_config(layout, digest, repository, platform)
        if entry.get("service") in OWNED_SERVICES:
            ok, said = cosign.verify_local(layout, identity)
            if not ok:
                last = said.splitlines()[-1] if said else "no answer"
                raise BundleRefused(
                    f"{repository}@{digest} is not signed by {identity.describe()} ({last})"
                )
        chosen.append((item, config))
    images: dict[str, tuple[str, str]] = {}
    for item, config in chosen:
        local = str(item["local"])
        _need(run, ["docker", "load", "-i", str(root / str(item["tar"]))], f"load {local}")
        loaded = _need(run, ["docker", "image", "inspect", "--format", "{{.Id}}", local],
                       f"look at {local}").strip()  # fmt: skip
        if loaded != config:
            raise BundleRefused(
                f"{item['repository']}: its image file loaded as another image than the signed "
                f"manifest names ({loaded}, not {config})"
            )
        images[str(item["repository"])] = (local, config)
    return images
