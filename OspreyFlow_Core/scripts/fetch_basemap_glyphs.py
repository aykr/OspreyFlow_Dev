"""The map's place-name glyphs, kept with the basemap — the part of the tier-1 local basemap
`scripts/build_local_basemap.py` does not build (`spec/02_GLASS_FRONTEND.md` §3.4).

The bundled MapLibre style asks the Glass's origin for `/fonts/{fontstack}/{range}.pbf`; the
workspace's nginx serves them from the tiles folder's `fonts/`, mounted read-only by the renderer
(`harness/render.py`, `GLYPHS_CONTAINER_PATH`). Without them the Glass draws the map unlabelled
(`glyphsServed`). Found 9 October 2026, when every map in the deck had no names on it.

The glyphs come from the OpenMapTiles fonts release, pinned by version and SHA-256, and only the
fonts the style names are installed. Noto Sans is under the SIL Open Font License 1.1 (the licence
register, `spec/00_ARCHITECTURE.md`). Self-hosted, never a CDN: the deployment serves them itself.

    python -m scripts.fetch_basemap_glyphs --tiles-root ../OspreyFlow_Data/basemap
    python -m scripts.fetch_basemap_glyphs --tiles-root <dir> --from-zip <downloaded v2.0.zip>
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

#: The OpenMapTiles fonts release, pinned. Checked when installed; a different file is refused.
RELEASE_URL = "https://github.com/openmaptiles/fonts/releases/download/v2.0/v2.0.zip"
RELEASE_SHA256 = "3a7a6c2dcd940a840aa6ffac8f39758252a667a0b329945b071fb44bf00e7f47"

#: The fonts the bundled style names in its `text-font` (`apps/workspace/src/map/style.ts`).
STYLE_FONTS: tuple[str, ...] = ("Noto Sans Regular",)


class GlyphFetchError(Exception):
    """The glyphs could not be installed; nothing was written."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_glyphs(
    archive: Path, tiles_root: Path, *, expected_sha256: str = RELEASE_SHA256
) -> int:
    """Install the style's fonts from `archive` into `<tiles_root>/fonts`; the number of glyph
    files installed. The archive's checksum is checked first, each member must lie inside its
    font's folder, and the fonts are written beside the destination and moved into place only
    when complete, so a refused or broken release leaves nothing behind."""
    if _sha256(archive) != expected_sha256:
        raise GlyphFetchError(f"{archive.name}: checksum does not match the pinned release")
    with zipfile.ZipFile(archive) as zf:
        members = {
            font: [
                name
                for name in zf.namelist()
                if PurePosixPath(name).parts[:1] == (font,)
                and len(PurePosixPath(name).parts) == 2
                and name.endswith(".pbf")
            ]
            for font in STYLE_FONTS
        }
        missing = [font for font, names in members.items() if not names]
        if missing:
            raise GlyphFetchError(f"the release has no glyphs for {', '.join(missing)}")
        destination = tiles_root / "fonts"
        tiles_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".fonts-", dir=tiles_root))
        try:
            installed = 0
            for font, names in members.items():
                (staging / font).mkdir()
                for name in names:
                    target = staging / font / PurePosixPath(name).name
                    target.write_bytes(zf.read(name))
                    installed += 1
            destination.mkdir(exist_ok=True)
            for font in STYLE_FONTS:
                shutil.rmtree(destination / font, ignore_errors=True)
                (staging / font).rename(destination / font)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return installed


def download_release(directory: Path) -> Path:
    """The pinned release, downloaded into `directory`."""
    target = directory / "openmaptiles-fonts-v2.0.zip"
    with urllib.request.urlopen(RELEASE_URL) as response, target.open("wb") as out:  # noqa: S310
        shutil.copyfileobj(response, out)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tiles-root", type=Path, required=True,
                        help="the deployment's tiles folder (components.storage.tiles)")
    parser.add_argument("--from-zip", type=Path, help="a release zip already downloaded")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        archive = args.from_zip or download_release(Path(tmp))
        count = install_glyphs(archive, args.tiles_root)
    print(f"installed {count} glyph files into {args.tiles_root / 'fonts'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
