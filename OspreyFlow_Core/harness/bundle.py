"""A release in one file, for a deployment that cannot reach GitHub or a registry (ADR-114
Amendment 8 point 10, the owner's ruling: full signatures carried).

`ospreyflow update --make-bundle FILE [--to vX.Y.Z] [--platform OS/ARCH]`, on a machine that
reaches them, verifies the release online and writes: the release's notes, its lock and the lock's
signature; the tag's source (`git bundle`); and every image twice — as `cosign save` keeps it (with
its signatures and their transparency-log proofs) and as `docker save` writes it, for one platform.

`ospreyflow update --from FILE` verifies it with no network at all: the lock against its signature,
each owned image against the release workflow's identity, and for every image the chain from the
signed lock to what Docker loads — the saved manifest's hash is the digest the lock names, the
manifest names a configuration, and the loaded image's ID must be that configuration's digest. Only
then is anything loaded into the deployment.

**cosign travels in the bundle too** (build order step 20a, ADR-114 Amendment 34): the checks above
run cosign from its image, and a machine with no network that never pulled it could run none of
them. The bundle carries that image (`docker save`, pulled by the digest `harness.signatures` pins);
`--from` loads it first and runs it only if its ID is the one pinned in the code for this machine's
platform, so a bundle cannot bring its own verifier. A bundle from before carries none: the
machine's own cosign image is used, as before.

**For another platform than the machine's** (build order step 29, the owner's ruling of 4
November): `--platform` (default `linux/amd64`, the platform a release is run on) names the
platform whose images the bundle carries, from any machine. Every image a release names is an index
over several platforms and is signed and locked by the index's digest, so `cosign save` keeps the
whole index, signed. The image Docker saves is pulled by the manifest digest that saved index names
for the platform (each hash checked), never by the index: a Mac's daemon answers a pull of the
index with the arm64 image it already holds under that reference, `--platform` or not. Docker is
then asked the named image's platform before it is saved. cosign's own image is pulled the same
way, by the digest `harness.signatures` pins for the platform. `--from` reads the platform the
bundle names and refuses, in words, a bundle for another than the machine's.
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

from harness.signatures import (
    COSIGN_IMAGE_IDS,
    COSIGN_PLATFORM_IMAGES,
    SIGNED_SERVICES,
    Cosign,
    Identity,
)

BUNDLE_FORMAT = 1
#: What the bundle's cosign image is named once loaded; it is run by its checked ID, not this name.
COSIGN_LOCAL = "ghcr.io/sigstore/cosign/cosign:ospreyflow-bundle"
#: The platforms `release.yml` builds the owned images for (`--platform`), so the only ones a
#: bundle can be made for; a test holds the two to each other. The first is the default.
RELEASE_PLATFORMS = ("linux/amd64", "linux/arm64")
DEFAULT_PLATFORM = RELEASE_PLATFORMS[0]
Run = Callable[[Sequence[str]], tuple[int, str]]


class BundleRefused(Exception):
    """A bundle that may not be applied, and why."""


def bundle_platform(platform: str) -> str:
    """`platform`, if a release is built for it; refused in words before anything is fetched."""
    if platform not in RELEASE_PLATFORMS or platform not in COSIGN_PLATFORM_IMAGES:
        raise BundleRefused(
            f"a release's images are built for {' and '.join(RELEASE_PLATFORMS)} only, so no "
            f"bundle can be made for {platform}"
        )
    return platform


def _platforms_of(index: dict[str, Any]) -> list[str]:
    """The platforms an index holds images for (an attestation manifest is none)."""
    named = []
    for child in index.get("manifests") or []:
        found = child.get("platform") or {}
        if found.get("os") not in (None, "unknown"):
            named.append(f"{found.get('os')}/{found.get('architecture')}")
    return named


def _child_for(index: dict[str, Any], platform: str, repository: str) -> str:
    """The digest of `platform`'s manifest in `index`; refused naming the platforms it has."""
    os_name, _, arch = platform.partition("/")
    for child in index.get("manifests") or []:
        found = child.get("platform") or {}
        if found.get("os") == os_name and found.get("architecture") == arch:
            return str(child["digest"])
    has = ", ".join(_platforms_of(index)) or "none"
    raise BundleRefused(f"{repository}: the release has no image for {platform} (it has {has})")


def _image_to_pull(layout: Path, digest: str, repository: str, platform: str) -> str:
    """What to pull for `platform`: the manifest the saved, signed index names for it (each hash
    checked), or `digest` itself when the lock names one platform's manifest."""
    _in_layout(layout, digest, repository)
    manifest = _hashed_blob(layout, digest, repository)
    if "config" in manifest:
        return digest
    child = _child_for(manifest, platform, repository)
    _hashed_blob(layout, child, repository)
    return child


def _is_platform(run: Run, ref: str, platform: str, what: str) -> None:
    """Docker's own answer to which platform `ref` is; refused before it is saved otherwise."""
    held = _need(run, ["docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}",
                       ref], f"look at {what}").strip()  # fmt: skip
    if held != platform:
        raise BundleRefused(
            f"{what}: Docker holds it as {held}, not {platform}; no bundle was written"
        )


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
    *, staging: Path | None = None, platform: str = DEFAULT_PLATFORM,
) -> Path:  # fmt: skip
    """Writes the bundle of `platform`'s images for a release already verified online (`update
    --make-bundle` does that first)."""
    bundle_platform(platform)
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
        pinned = COSIGN_PLATFORM_IMAGES[platform]
        _need(run, ["docker", "pull", "--platform", platform, pinned],
              f"pull the pinned cosign image {pinned}")  # fmt: skip
        _need(run, ["docker", "tag", pinned, COSIGN_LOCAL], "name the cosign image")
        _is_platform(run, COSIGN_LOCAL, platform, f"the cosign image {pinned}")
        _need(run, ["docker", "save", "-o", str(root / "cosign.tar"), COSIGN_LOCAL],
              "save the cosign image")  # fmt: skip
        (root / "saved").mkdir(exist_ok=True)
        (root / "images").mkdir(exist_ok=True)
        manifest = []
        for index, entry in enumerate(_entries(release["lock"])):
            repository, digest = str(entry["repository"]), str(entry["digest"])
            ref, local = f"{repository}@{digest}", f"{repository}:ospreyflow-{tag}"
            saved, said = cosign.save(ref, root / "saved" / str(index))
            if not saved:
                raise BundleRefused(f"save {ref} with its signatures: {said}")
            # This platform's own manifest, as the signed index just saved names it: never the
            # index, which a daemon answers with whatever platform it already holds under it.
            child = _image_to_pull(root / "saved" / str(index), digest, repository, platform)
            pull = f"{repository}@{child}"
            _need(run, ["docker", "pull", "--platform", platform, pull], f"pull {pull}")
            _need(run, ["docker", "tag", pull, local], f"name {pull}")
            _is_platform(run, local, platform, ref)
            _need(run, ["docker", "save", "-o", str(root / "images" / f"{index}.tar"), local],
                  f"save {ref}")  # fmt: skip
            manifest.append({
                "service": entry.get("service"), "repository": repository, "digest": digest,
                "saved": f"saved/{index}", "tar": f"images/{index}.tar", "local": local,
            })  # fmt: skip
        (root / "manifest.json").write_text(
            json.dumps(
                {"images": manifest, "cosign": {"tar": "cosign.tar", "local": COSIGN_LOCAL},
                 "platform": platform}
            ),
            encoding="utf-8",
        )
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


def _in_layout(layout: Path, digest: str, repository: str) -> None:
    """Refused unless the saved layout's own index lists `digest` (what `cosign save` saved)."""
    try:
        index = json.loads((layout / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = {"manifests": []}
    if digest not in {m.get("digest") for m in index.get("manifests") or []}:
        raise BundleRefused(
            f"{repository}@{digest}: the image the signed lock names is not in the bundle"
        )


def _manifest_config(layout: Path, digest: str, repository: str, platform: str) -> str:
    """The configuration digest the saved manifest `digest` names, each hash checked. An image
    published for several platforms is locked by its index: followed to this machine's platform."""
    _in_layout(layout, digest, repository)
    manifest = _hashed_blob(layout, digest, repository)
    if "config" not in manifest:  # an index: this platform's manifest, by the index's own list
        manifest = _hashed_blob(layout, _child_for(manifest, platform, repository), repository)
    return str(manifest["config"]["digest"])


def _bundled_cosign(
    root: Path, carried: dict[str, Any] | None, platform: str, cosign: Cosign, run: Run
) -> Cosign:
    """The cosign the bundle carries, loaded and run by its ID once that ID is the one pinned for
    this platform — refused before it runs otherwise. A bundle carrying none: `cosign` as given."""
    if carried is None:
        return cosign
    pinned = COSIGN_IMAGE_IDS.get(platform)
    if pinned is None:
        raise BundleRefused(f"no cosign image is pinned for {platform}; nothing can be verified")
    local = str(carried["local"])
    _need(run, ["docker", "load", "-i", str(root / str(carried["tar"]))], "load the cosign image")
    loaded = _need(run, ["docker", "image", "inspect", "--format", "{{.Id}}", local],
                   "look at the cosign image").strip()  # fmt: skip
    if loaded != pinned:
        raise BundleRefused(
            f"the bundle's cosign image is not the one pinned for {platform} ({loaded}, not "
            f"{pinned}); it was not run, and nothing was verified or loaded"
        )
    return cosign.from_image(loaded)


def check_bundle(
    root: Path, identity: Identity, cosign: Cosign, run: Run
) -> dict[str, tuple[str, str]]:
    """Verifies an opened bundle with no network and loads its images: repository → (the local
    reference to run, the image ID it must have)."""
    platform = _need(
        run, ["docker", "version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"], "ask Docker"
    ).strip()
    contents = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    carried = contents.get("platform")  # a bundle from before step 29 names none
    if carried is not None and carried != platform:
        raise BundleRefused(
            f"this bundle carries the images for {carried}, and this machine is {platform}; "
            "nothing was verified or loaded. Make one for it on any machine that reaches the "
            f"release: ospreyflow update --make-bundle FILE --platform {platform}"
        )
    cosign = _bundled_cosign(root, contents.get("cosign"), platform, cosign, run)
    cosign.verify_blob(
        root / "versions.lock", root / "versions.lock.sigstore.json", identity, offline=True
    )
    lock = (root / "versions.lock").read_text(encoding="utf-8")
    listed = contents.get("images") or []
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
        if entry.get("service") in SIGNED_SERVICES:
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
