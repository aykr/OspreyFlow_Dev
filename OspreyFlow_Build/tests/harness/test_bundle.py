"""`ospreyflow update --make-bundle` and `update --from` (ADR-114 Amendment 8 point 10, the owner's
ruling: full signatures carried).

The image layouts here are real OCI layouts with real hashes, so an altered blob really fails its
hash; only Docker's `load` and `image inspect` are stood in for, and they answer as Docker does — a
loaded image's ID is its configuration's digest. cosign is a fake that refuses an image it was not
told is signed. The real tools are exercised by the live proof (`07_BUILD_PLAN.md`, the B5d row).
"""

from __future__ import annotations

import hashlib
import json
import tarfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.bundle import BundleRefused, check_bundle, make_bundle, open_bundle
from harness.signatures import Cosign, PublicKey, SignatureRefused

KEY = PublicKey(Path("/k/cosign.pub"))
REG = "localhost:5055/acme"
SERVICES = ("workspace", "api", "ingest", "ner", "arcadedb")


def _blob(layout: Path, data: bytes) -> str:
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    path = layout / "blobs" / "sha256" / digest.split(":")[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return digest


def _layout(layout: Path, service: str) -> tuple[str, str]:
    """A saved image: its manifest's digest and the configuration digest the manifest names."""
    config = _blob(layout, json.dumps({"service": service}).encode())
    manifest = _blob(
        layout, json.dumps({"schemaVersion": 2, "config": {"digest": config}}).encode()
    )
    (layout / "oci-layout").write_text('{"imageLayoutVersion": "1.0.0"}')
    (layout / "index.json").write_text(json.dumps({"manifests": [
        {"digest": manifest, "annotations": {"kind": "dev.cosignproject.cosign/image"}},
        {"digest": "sha256:" + "0" * 64, "annotations": {"kind": "dev.cosignproject.cosign/sigs"}},
    ]}))  # fmt: skip
    return manifest, config


def _repository(service: str) -> str:
    return "arcadedata/arcadedb" if service == "arcadedb" else f"{REG}/{service}"


class _Docker:
    """`docker load` and `docker image inspect` as Docker answers them."""

    def __init__(self) -> None:
        self.loaded: dict[str, str] = {}  # local reference -> image id
        self.asked: list[list[str]] = []
        self.tars: dict[str, str] = {}  # tar path -> (reference, id) as JSON

    def run(self, argv: Sequence[str]) -> tuple[int, str]:
        argv = list(argv)
        self.asked.append(argv)
        if argv[:2] == ["docker", "load"]:
            reference, image_id = json.loads(Path(argv[-1]).read_text())
            self.loaded[reference] = image_id
            return 0, f"Loaded image: {reference}"
        if argv[:2] == ["docker", "version"]:
            return 0, "linux/arm64"
        if argv[:3] == ["docker", "image", "inspect"]:
            reference = argv[-1]
            return (0, self.loaded[reference]) if reference in self.loaded else (1, "No such image")
        raise AssertionError(argv)


def _bundle(tmp: Path, *, tag: str = "v0.5.0") -> tuple[Path, dict[str, tuple[str, str]]]:
    """An opened bundle, by hand: each image's layout, and its 'docker save' (what it loads as)."""
    root = tmp / "opened"
    rows, digests, entries = [], {}, []
    for index, service in enumerate(SERVICES):
        manifest, config = _layout(root / "saved" / str(index), service)
        digests[service] = (manifest, config)
        repository = _repository(service)
        local = f"{repository}:ospreyflow-{tag}"
        tar = root / "images" / f"{index}.tar"
        tar.parent.mkdir(parents=True, exist_ok=True)
        tar.write_text(json.dumps([local, config]))
        rows.append({"service": service, "repository": repository, "tag": "x", "digest": manifest,
                     "source": "registry"})  # fmt: skip
        entries.append({"service": service, "repository": repository, "digest": manifest,
                        "saved": f"saved/{index}", "tar": f"images/{index}.tar",
                        "local": local})  # fmt: skip
    (root / "versions.lock").write_text(
        "# GENERATED\n" + yaml.safe_dump({"images": rows}, sort_keys=False)
    )
    (root / "versions.lock.sigstore.json").write_text("{}")
    (root / "release.json").write_text(json.dumps({"format": 1, "tag": tag, "notes": "- new"}))
    (root / "manifest.json").write_text(json.dumps({"images": entries}))
    (root / "source.bundle").write_text("git bundle")
    return root, digests


def _cosign(signed: set[str] | None = None, lock_ok: bool = True) -> tuple[Cosign, list[list[str]]]:
    asked: list[list[str]] = []

    def run(argv: Sequence[str]) -> tuple[int, str]:
        asked.append(list(argv))
        if "verify-blob" in argv:
            return (0, "Verified OK") if lock_ok else (1, "invalid signature")
        saved = argv[-1]
        ok = signed is None or Path(saved).name in signed or saved.rsplit("/", 1)[-1] in signed
        return (0, "verified") if ok else (1, "no signatures found")

    return Cosign(run), asked


# --- checking an opened bundle -------------------------------------------------------------------


def test_a_good_bundle_is_verified_offline_loaded_and_names_what_to_run(tmp_path: Path) -> None:
    root, digests = _bundle(tmp_path)
    docker = _Docker()
    cosign, asked = _cosign()
    images = check_bundle(root, KEY, cosign, docker.run)
    assert images[f"{REG}/api"] == (f"{REG}/api:ospreyflow-v0.5.0", digests["api"][1])
    assert images["arcadedata/arcadedb"] == (
        "arcadedata/arcadedb:ospreyflow-v0.5.0", digests["arcadedb"][1],
    )  # fmt: skip
    # The lock first, then each owned image, all with no network; the third party is not signed.
    assert "verify-blob" in asked[0] and "--offline" in asked[0]
    owned_checks = [a for a in asked if "verify-blob" not in a]
    assert len(owned_checks) == 4 and all("--offline" in a for a in owned_checks)
    assert all(["--network", "none"] == a[3:5] for a in asked)
    assert len(docker.loaded) == 5


def test_a_lock_that_does_not_verify_refuses_before_anything_is_loaded(tmp_path: Path) -> None:
    root, _ = _bundle(tmp_path)
    docker = _Docker()
    with pytest.raises(SignatureRefused, match="versions.lock is not signed"):
        check_bundle(root, KEY, _cosign(lock_ok=False)[0], docker.run)
    assert docker.loaded == {}


def test_an_owned_image_whose_signature_does_not_verify_refuses_naming_it(tmp_path: Path) -> None:
    root, _ = _bundle(tmp_path)
    docker = _Docker()
    with pytest.raises(BundleRefused, match=f"{REG}/ner"):
        check_bundle(root, KEY, _cosign(signed={"0", "1", "2"})[0], docker.run)
    assert docker.loaded == {}


def test_an_altered_manifest_fails_its_own_hash(tmp_path: Path) -> None:
    root, digests = _bundle(tmp_path)
    manifest_blob = root / "saved" / "1" / "blobs" / "sha256" / digests["api"][0].split(":")[1]
    manifest_blob.write_bytes(
        manifest_blob.read_bytes().replace(b"schemaVersion", b"schemaVersiom")
    )
    with pytest.raises(BundleRefused, match="api.*does not match its digest"):
        check_bundle(root, KEY, _cosign()[0], _Docker().run)


def test_a_saved_image_that_is_not_the_lock_s_is_refused(tmp_path: Path) -> None:
    """A layout swapped for another image's: its manifest is not the digest the lock names."""
    root, _ = _bundle(tmp_path)
    _layout(root / "saved" / "4", "something-else")  # arcadedb's layout replaced
    (root / "saved" / "4" / "index.json").write_text(json.dumps({"manifests": [
        {"digest": _layout(tmp_path / "other", "x")[0]}]}))  # fmt: skip
    with pytest.raises(BundleRefused, match="arcadedata/arcadedb.*not in the bundle"):
        check_bundle(root, KEY, _cosign()[0], _Docker().run)


def test_an_image_file_that_loads_as_something_else_is_refused(tmp_path: Path) -> None:
    """The chain's last link: the loaded image's ID must be the configuration the manifest names."""
    root, digests = _bundle(tmp_path)
    tar = root / "images" / "1.tar"
    reference, _ = json.loads(tar.read_text())
    tar.write_text(json.dumps([reference, "sha256:" + "e" * 64]))
    with pytest.raises(BundleRefused, match=f"{REG}/api.*loaded as another image"):
        check_bundle(root, KEY, _cosign()[0], _Docker().run)


def test_a_bundle_missing_a_lock_image_is_refused(tmp_path: Path) -> None:
    root, _ = _bundle(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["images"] = manifest["images"][:-1]
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(BundleRefused, match="arcadedata/arcadedb"):
        check_bundle(root, KEY, _cosign()[0], _Docker().run)


# --- making and opening one --------------------------------------------------------------------


class _Connected:
    """A machine that reaches the registry: cosign save and docker save write their files."""

    def __init__(self) -> None:
        self.asked: list[list[str]] = []
        self.configs: dict[str, str] = {}

    def run(self, argv: Sequence[str]) -> tuple[int, str]:
        argv = list(argv)
        self.asked.append(argv)
        if "save" in argv and "--dir" in argv:  # cosign save
            out = Path(argv[argv.index("--dir") + 1].replace("/out", str(self.out)))
            service = argv[-1].split("@")[0].rsplit("/", 1)[1]
            manifest, config = _layout(out, service)
            self.configs[argv[-1]] = config
            return 0, ""
        if argv[:2] == ["docker", "save"]:
            Path(argv[argv.index("-o") + 1]).write_text(json.dumps([argv[-1], "id"]))
            return 0, ""
        if argv[:2] in (["docker", "pull"], ["docker", "tag"]):
            return 0, ""
        if argv[0] == "git":
            if "bundle" in argv:
                Path(argv[-2]).write_text("git bundle")
            return 0, ""
        raise AssertionError(argv)


def test_a_bundle_holds_the_release_its_source_and_every_image_twice(tmp_path: Path) -> None:
    connected = _Connected()
    lock = "# GENERATED\n" + yaml.safe_dump({"images": [
        {"service": s, "repository": _repository(s), "tag": "x", "digest": "sha256:" + str(i) * 64,
         "source": "registry"} for i, s in enumerate(SERVICES, 1)]}, sort_keys=False)  # fmt: skip
    release = {"tag": "v0.5.0", "notes": "- new", "lock": lock, "lock_signature": "{}"}
    out = tmp_path / "ospreyflow-v0.5.0.tar"

    def run(argv: Sequence[str]) -> tuple[int, str]:
        return connected.run(argv)

    connected.out = tmp_path / "staging" / "saved"  # type: ignore[attr-defined]
    make_bundle(out, release, tmp_path / "repo", run, Cosign(run), staging=tmp_path / "staging")
    with tarfile.open(out) as bundle:
        names = set(bundle.getnames())
    assert {"./release.json", "./versions.lock", "./versions.lock.sigstore.json",
            "./source.bundle", "./manifest.json"} <= names  # fmt: skip
    assert {f"./images/{i}.tar" for i in range(5)} <= names
    assert {f"./saved/{i}/index.json" for i in range(5)} <= names
    git = [a for a in connected.asked if a[0] == "git"]
    assert ["bundle", "create"] == git[-1][3:5] and git[-1][-1] == "v0.5.0"
    opened = open_bundle(out, tmp_path / "opened")
    assert opened["tag"] == "v0.5.0" and opened["lock"] == lock


def test_a_bundle_cannot_write_outside_the_folder_it_is_opened_in(tmp_path: Path) -> None:
    evil = tmp_path / "evil.tar"
    with tarfile.open(evil, "w") as bundle:
        data = b"x"
        info = tarfile.TarInfo("../escaped.txt")
        info.size = len(data)
        import io

        bundle.addfile(info, io.BytesIO(data))
    with pytest.raises(BundleRefused, match="outside"):
        open_bundle(evil, tmp_path / "opened")
    assert not (tmp_path / "escaped.txt").exists()


def _unused(*_: Any) -> None:
    pass


# --- an image locked by its multi-platform index (found by the live proof) ----------------------


def _index_layout(layout: Path, service: str, platforms: list[tuple[str, str]]) -> tuple[str, str]:
    """An image published for several platforms: the index's digest, and the arm64 configuration."""
    children, arm_config = [], ""
    for os_name, arch in platforms:
        config = _blob(layout, json.dumps({"service": service, "arch": arch}).encode())
        body = {"schemaVersion": 2, "config": {"digest": config}}
        manifest = _blob(layout, json.dumps(body).encode())
        children.append({"digest": manifest, "platform": {"os": os_name, "architecture": arch}})
        if arch == "arm64":
            arm_config = config
    index = _blob(layout, json.dumps({
        "mediaType": "application/vnd.oci.image.index.v1+json", "manifests": children}).encode())
    (layout / "oci-layout").write_text('{"imageLayoutVersion": "1.0.0"}')
    (layout / "index.json").write_text(json.dumps({"manifests": [{"digest": index}]}))
    return index, arm_config


def _with_index(tmp_path: Path, platforms: list[tuple[str, str]]) -> tuple[Path, str]:
    root, _ = _bundle(tmp_path)
    layout = root / "saved" / "4"  # arcadedb
    import shutil

    shutil.rmtree(layout)
    index, config = _index_layout(layout, "arcadedb", platforms)
    lock = yaml.safe_load((root / "versions.lock").read_text())
    lock["images"][4]["digest"] = index
    (root / "versions.lock").write_text(yaml.safe_dump(lock, sort_keys=False))
    listed = json.loads((root / "manifest.json").read_text())
    listed["images"][4]["digest"] = index
    (root / "manifest.json").write_text(json.dumps(listed))
    tar = root / "images" / "4.tar"
    tar.write_text(json.dumps(["arcadedata/arcadedb:ospreyflow-v0.5.0", config]))
    return root, config


def test_an_image_locked_by_its_index_is_followed_to_this_machines_platform(tmp_path: Path) -> None:
    root, config = _with_index(tmp_path, [("linux", "amd64"), ("linux", "arm64")])
    images = check_bundle(root, KEY, _cosign()[0], _Docker().run)
    assert images["arcadedata/arcadedb"][1] == config


def test_an_index_with_nothing_for_this_platform_is_refused(tmp_path: Path) -> None:
    root, _ = _with_index(tmp_path, [("linux", "amd64")])
    with pytest.raises(BundleRefused, match="arcadedata/arcadedb.*linux/arm64"):
        check_bundle(root, KEY, _cosign()[0], _Docker().run)


def test_an_altered_platform_manifest_inside_an_index_fails_its_hash(tmp_path: Path) -> None:
    root, _ = _with_index(tmp_path, [("linux", "amd64"), ("linux", "arm64")])
    layout = root / "saved" / "4"
    index_digest = json.loads((layout / "index.json").read_text())["manifests"][0]["digest"]
    index = json.loads((layout / "blobs" / "sha256" / index_digest.split(":")[1]).read_text())
    arm = next(m for m in index["manifests"] if m["platform"]["architecture"] == "arm64")
    blob = layout / "blobs" / "sha256" / arm["digest"].split(":")[1]
    blob.write_bytes(blob.read_bytes().replace(b"schemaVersion", b"schemaVersiom"))
    with pytest.raises(BundleRefused, match="does not match its digest"):
        check_bundle(root, KEY, _cosign()[0], _Docker().run)



# --- the cosign image travels in the bundle (build order step 20a, ADR-114 Amendment 34) --------
#
# `update --from` verifies with cosign run from its image. A machine with no network that never
# pulled that image could verify nothing: Docker, asked to run an image it does not hold, tries to
# pull it, and with no network the pull fails. These two machines answer as Docker does — the
# offline one refuses every pull, and a reference by digest is only found if it was *pulled* by
# that digest (`docker load` of a `docker save` file records no repository digest), so naming the
# image by digest after a load would still try to pull.

#: The real cosign v2.4.1, measured 3 November 2026 (`docker buildx imagetools inspect`): its
#: multi-platform index, and the ID Docker gives its linux/arm64 image (its configuration's digest).
_REAL_COSIGN_INDEX = "sha256:b03690aa52bfe94054187142fba24dc54137650682810633901767d8a3e15b31"
_REAL_COSIGN_ARM64_ID = "sha256:6793dd4d518a6b556385e3dee81d02554900a3f386f8b50bbd29bdb4ac6d8829"
_COSIGN_REPOSITORY = "ghcr.io/sigstore/cosign/cosign"
#: Docker's own words when a pull cannot reach the registry (exit 125 from `docker run`).
_NO_NETWORK = (
    'docker: Error response from daemon: Get "https://ghcr.io/v2/": dial tcp: lookup ghcr.io: '
    "no such host\n\nRun 'docker run --help' for more information"
)


class _Machine:
    """Docker, and cosign inside its image, on one machine. `online`: a pull reaches `registry`
    (reference -> the image ID it gives); offline, every pull fails as Docker's does."""

    def __init__(
        self, *, online: bool, registry: dict[str, str] | None = None,
        platform: str = "linux/arm64", layouts: dict[str, str] | None = None,
    ) -> None:  # fmt: skip
        self.online = online
        self.registry = registry or {}
        self.platform = platform
        self.layouts = layouts or {}  # repository@digest -> the service its saved layout holds
        self.images: dict[str, str] = {}  # a reference Docker resolves locally -> image ID
        self.ran: list[list[str]] = []  # every `docker run`, as asked

    def _pull(self, ref: str) -> tuple[int, str]:
        if not self.online or ref not in self.registry:
            return 1, _NO_NETWORK.replace("docker: ", "")
        self.images[ref] = self.registry[ref]
        return 0, f"Status: Downloaded newer image for {ref}"

    def _local(self, ref: str) -> str | None:
        if ref.startswith("sha256:"):
            return ref if ref in self.images.values() else None
        return self.images.get(ref)

    def run(self, argv: Sequence[str]) -> tuple[int, str]:
        argv = list(argv)
        if argv[:2] == ["docker", "version"]:
            return 0, self.platform
        if argv[:2] == ["docker", "pull"]:
            return self._pull(argv[-1])
        if argv[:2] == ["docker", "tag"]:
            found = self._local(argv[2])
            if found is None:
                return 1, f"Error response from daemon: No such image: {argv[2]}"
            self.images[argv[3]] = found
            return 0, ""
        if argv[:2] == ["docker", "save"]:
            found = self._local(argv[-1])
            if found is None:
                return 1, f"Error response from daemon: reference does not exist: {argv[-1]}"
            Path(argv[argv.index("-o") + 1]).write_text(json.dumps([argv[-1], found]))
            return 0, ""
        if argv[:2] == ["docker", "load"]:
            reference, image_id = json.loads(Path(argv[-1]).read_text())
            self.images[reference] = image_id
            return 0, f"Loaded image: {reference}"
        if argv[:3] == ["docker", "image", "inspect"]:
            found = self._local(argv[-1])
            return (0, found) if found else (1, f"Error: No such image: {argv[-1]}")
        if argv[:2] == ["docker", "run"]:
            self.ran.append(argv)
            return self._cosign(argv)
        if argv[0] == "git":
            if "bundle" in argv:
                Path(argv[-2]).write_text("git bundle")
            return 0, ""
        raise AssertionError(argv)

    def _cosign(self, argv: list[str]) -> tuple[int, str]:
        at, mounts = 2, {}
        while argv[at].startswith("-"):
            if argv[at] == "--rm":
                at += 1
                continue
            if argv[at] == "-v":
                host, inside = argv[at + 1].split(":")[:2]
                mounts[inside] = host
            at += 2
        image = argv[at]
        if self._local(image) is None:
            code, said = self._pull(image)
            if code != 0:
                return 125, f"Unable to find image '{image}' locally\n{_NO_NETWORK}"
        verb = argv[at + 1]
        if verb == "save":
            dest = argv[argv.index("--dir") + 1]
            for inside, host in mounts.items():
                dest = dest.replace(inside, host, 1) if dest.startswith(inside) else dest
            _layout(Path(dest), self.layouts[argv[-1]])
            return 0, ""
        return 0, "Verified OK"


def _release_on_the_registry(tmp: Path) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    """A release as the registry holds it: its lock, and what each reference pulls as."""
    registry, layouts, rows = {}, {}, []
    for service in SERVICES:
        manifest, config = _layout(tmp / "registry" / service, service)
        ref = f"{_repository(service)}@{manifest}"
        registry[ref], layouts[ref] = config, service
        rows.append({"service": service, "repository": _repository(service), "tag": "x",
                     "digest": manifest, "source": "registry"})  # fmt: skip
    for ref in (f"{_COSIGN_REPOSITORY}:v2.4.1", f"{_COSIGN_REPOSITORY}@{_REAL_COSIGN_INDEX}",
                f"{_COSIGN_REPOSITORY}:v2.4.1@{_REAL_COSIGN_INDEX}"):  # fmt: skip
        registry[ref] = _REAL_COSIGN_ARM64_ID
    lock = "# GENERATED\n" + yaml.safe_dump({"images": rows}, sort_keys=False)
    release = {"tag": "v0.5.0", "notes": "- new", "lock": lock, "lock_signature": "{}"}
    return release, registry, layouts


def _made_on_a_connected_machine(tmp: Path) -> Path:
    release, registry, layouts = _release_on_the_registry(tmp)
    connected = _Machine(online=True, registry=registry, layouts=layouts)
    out = tmp / "ospreyflow-v0.5.0.tar"
    make_bundle(out, release, tmp / "repo", connected.run, Cosign(connected.run),
                staging=tmp / "staging")  # fmt: skip
    return out


def test_update_from_verifies_on_a_machine_with_no_cosign_image_and_no_network(
    tmp_path: Path,
) -> None:
    """Red before step 20a: the bundle carried no cosign, so the first check (the lock's
    signature) asked Docker to run an image it did not have, and the pull failed."""
    out = _made_on_a_connected_machine(tmp_path)
    offline = _Machine(online=False)
    opened = open_bundle(out, tmp_path / "opened")
    images = check_bundle(Path(opened["root"]), KEY, Cosign(offline.run), offline.run)
    assert set(images) == {_repository(s) for s in SERVICES}
    # Every check ran from the image the bundle carried, by its ID, with no network.
    assert offline.ran and all(_REAL_COSIGN_ARM64_ID in argv for argv in offline.ran)
    assert all(["--network", "none"] == argv[3:5] for argv in offline.ran)


def test_a_bundle_whose_cosign_is_another_image_is_refused_before_it_runs(
    tmp_path: Path,
) -> None:
    """The pin is in the code, not the bundle: a cosign image swapped for another is refused
    before it is run, so nothing is ever 'verified' by it."""
    out = _made_on_a_connected_machine(tmp_path)
    opened = Path(open_bundle(out, tmp_path / "opened")["root"])
    listed = json.loads((opened / "manifest.json").read_text())
    tar = opened / listed["cosign"]["tar"]
    reference, _ = json.loads(tar.read_text())
    tar.write_text(json.dumps([reference, "sha256:" + "e" * 64]))
    offline = _Machine(online=False)
    with pytest.raises(BundleRefused, match="cosign"):
        check_bundle(opened, KEY, Cosign(offline.run), offline.run)
    assert offline.ran == []


def test_a_bundle_is_not_made_without_the_pinned_cosign_image(tmp_path: Path) -> None:
    """A connected machine that cannot pull cosign by its pinned digest writes no bundle."""
    release, registry, layouts = _release_on_the_registry(tmp_path)
    del registry[f"{_COSIGN_REPOSITORY}:v2.4.1@{_REAL_COSIGN_INDEX}"]
    del registry[f"{_COSIGN_REPOSITORY}@{_REAL_COSIGN_INDEX}"]
    connected = _Machine(online=True, registry=registry, layouts=layouts)
    connected.images[f"{_COSIGN_REPOSITORY}:v2.4.1"] = _REAL_COSIGN_ARM64_ID  # by tag only
    out = tmp_path / "ospreyflow-v0.5.0.tar"
    with pytest.raises(BundleRefused, match="cosign"):
        make_bundle(out, release, tmp_path / "repo", connected.run, Cosign(connected.run),
                    staging=tmp_path / "staging")  # fmt: skip
    assert not out.exists()
