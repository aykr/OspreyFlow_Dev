"""The guided install page's built front end, present and current before `ospreyflow install --gui`
serves it (`06_DECISIONS.md` ADR-114 Amendment 11).

The page (`apps/harness`) is built by the release and shipped beside it, signed; a checkout of a
developer builds it with `npm run build`. Its build writes `dist/source.sha256`, the hash of the
sources it was built from (`apps/harness/scripts/stamp.mjs`); this computes the same hash, so:

- built from these sources — served;
- otherwise, on a release tag — the release's own page fetched, its signature checked against the
  release workflow's identity, and unpacked;
- otherwise — refused in words, naming the command that builds it.

    python -m harness.install_page_build --product <checkout>
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import sys
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

#: As `apps/harness/scripts/stamp.mjs` names them — `tests/harness/test_install_page_build.py`
#: holds the two hashes equal.
SOURCES = (
    "apps/harness/src",
    "apps/harness/index.html",
    "apps/harness/package.json",
    "apps/workspace/src/design",
    "apps/workspace/src/theme",
)
DIST = Path("apps/harness/dist")
STAMP = "source.sha256"
ASSET = "install-page.tar.gz"
SIGNATURE = "install-page.tar.gz.sigstore.json"
BUILD = "cd apps/harness && npm ci && npm run build"


class InstallPageMissing(Exception):
    """No current page to serve, and none could be fetched; the message says what to do."""


def _skipped(name: str) -> bool:
    return name.startswith(".") or name == "node_modules" or name == "Icon\r"


def _files(product: Path, path: str) -> list[str]:
    full = product / path
    if full.is_file():
        return [path]
    if not full.is_dir():
        return []
    return [
        found
        for child in sorted(full.iterdir())
        if not _skipped(child.name)
        for found in _files(product, f"{path}/{child.name}")
    ]


def source_hash(product: Path) -> str:
    paths = sorted(p for source in SOURCES for p in _files(product, source))
    whole = hashlib.sha256()
    for path in paths:
        digest = hashlib.sha256((product / path).read_bytes()).hexdigest()
        whole.update(f"{path}\n{digest}\n".encode())
    return whole.hexdigest()


def is_current(product: Path) -> bool:
    stamp = product / DIST / STAMP
    if not (product / DIST / "index.html").is_file() or not stamp.is_file():
        return False
    return stamp.read_text(encoding="utf-8").strip() == source_hash(product)


def unpack(product: Path, archive: bytes) -> None:
    """The release's page in place of whatever was there; Python's own safe extraction, so a member
    naming a path outside the folder is refused rather than written."""
    with tempfile.TemporaryDirectory(prefix="ospreyflow-page-") as folder:
        staging = Path(folder) / "dist"
        staging.mkdir()
        try:
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
                tar.extractall(staging, filter="data")
        except (tarfile.TarError, OSError) as unsafe:
            raise InstallPageMissing(
                f"the release's install page could not be unpacked safely ({unsafe}); nothing was "
                "changed"
            ) from None
        if not (staging / "index.html").is_file():
            raise InstallPageMissing("the release's install page holds no index.html")
        target = product / DIST
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(staging, target)


#: `(tag) -> (archive, signature)`: the release's page and its bundle, from its GitHub release.
Fetch = Callable[[str], tuple[bytes, bytes]]
#: `(tag, archive path, signature path)`: raises when the signature is not the release's own.
Verify = Callable[[str, Path, Path], None]


def ensure(product: Path, *, release_tag: str | None, fetch: Fetch, verify: Verify) -> str:
    """Says how the page is ready, or raises `InstallPageMissing` in words."""
    if is_current(product):
        return "The install page is built from this checkout."
    if release_tag is None:
        raise InstallPageMissing(
            "The guided install page is not built in this checkout (or is older than its sources). "
            f"Build it: {BUILD} — or install from a release, which ships it built."
        )
    try:
        archive, signature = fetch(release_tag)
    except Exception as failed:  # noqa: BLE001 - said in words
        raise InstallPageMissing(
            f"{release_tag}'s install page could not be fetched ({failed})."
        ) from None
    with tempfile.TemporaryDirectory(prefix="ospreyflow-page-") as folder:
        archive_path, signature_path = Path(folder) / ASSET, Path(folder) / SIGNATURE
        archive_path.write_bytes(archive)
        signature_path.write_bytes(signature)
        try:
            verify(release_tag, archive_path, signature_path)
        except Exception as refused:  # noqa: BLE001 - nothing is unpacked; said in words
            raise InstallPageMissing(
                f"{release_tag}'s install page is not signed by its release ({refused}); "
                "nothing was unpacked."
            ) from None
    unpack(product, archive)
    return f"The install page of {release_tag} is in place, its signature checked."


def _real(product: Path) -> tuple[str | None, Fetch, Verify]:
    from harness.release import github_repository, origin_url, release_assets
    from harness.signatures import Cosign, Keyless

    tags = _tags_at_head(product)
    tag = tags[0] if tags else None
    owner, repo = github_repository(origin_url(product)) if tag else ("", "")

    def fetch(release: str) -> tuple[bytes, bytes]:
        found = release_assets((owner, repo), release, (ASSET, SIGNATURE))
        return found[ASSET], found[SIGNATURE]

    def verify(release: str, archive: Path, signature: Path) -> None:
        Cosign().verify_blob(archive, signature, Keyless(owner, repo, release))

    return tag, fetch, verify


def _tags_at_head(product: Path) -> list[str]:
    """The release tags at the checkout's HEAD, newest first."""
    from harness.release import _git, _parts, is_version

    said = _git(product, "tag", "--points-at", "HEAD") or ""
    return sorted((t for t in said.split() if is_version(t)), key=_parts, reverse=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness.install_page_build", description=__doc__)
    parser.add_argument("--product", type=Path, required=True)
    args = parser.parse_args(argv)
    tag, fetch, verify = _real(args.product)
    try:
        print(ensure(args.product, release_tag=tag, fetch=fetch, verify=verify))
    except InstallPageMissing as missing:
        print(str(missing), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
