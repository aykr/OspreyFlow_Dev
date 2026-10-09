"""`scripts.fetch_basemap_glyphs`: the map's place-name glyphs, kept with the basemap.

9 October 2026: every map drew without a single name, because no glyph files existed and
nothing in the build fetched them. CI never reaches the network, so the download is injected out
and the checks are made against a zip built here in the release's own layout.
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest
from scripts.fetch_basemap_glyphs import STYLE_FONTS, GlyphFetchError, install_glyphs


def _release(tmp_path: Path) -> tuple[Path, str]:
    archive = tmp_path / "fonts.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for font in (*STYLE_FONTS, "Open Sans Bold"):
            zf.writestr(f"{font}/0-255.pbf", b"glyphs")
            zf.writestr(f"{font}/256-511.pbf", b"glyphs")
        zf.writestr("../escape.pbf", b"no")
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_it_installs_only_the_fonts_the_style_names_into_the_tiles_folder(tmp_path: Path) -> None:
    archive, digest = _release(tmp_path)
    tiles = tmp_path / "basemap"
    installed = install_glyphs(archive, tiles, expected_sha256=digest)
    assert (tiles / "fonts" / "Noto Sans Regular" / "0-255.pbf").read_bytes() == b"glyphs"
    assert not (tiles / "fonts" / "Open Sans Bold").exists()
    assert not (tmp_path / "escape.pbf").exists()
    assert installed == 2


def test_a_release_whose_checksum_differs_is_refused_and_installs_nothing(tmp_path: Path) -> None:
    archive, _ = _release(tmp_path)
    tiles = tmp_path / "basemap"
    with pytest.raises(GlyphFetchError, match="checksum"):
        install_glyphs(archive, tiles, expected_sha256="0" * 64)
    assert not (tiles / "fonts").exists()


def test_a_release_without_the_styles_font_is_refused(tmp_path: Path) -> None:
    archive = tmp_path / "other.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Open Sans Bold/0-255.pbf", b"glyphs")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(GlyphFetchError, match="Noto Sans Regular"):
        install_glyphs(archive, tmp_path / "basemap", expected_sha256=digest)


def test_the_font_matches_the_one_the_bundled_style_asks_for() -> None:
    style = (
        Path(__file__).resolve().parents[2]
        / "OspreyFlow_Core" / "apps" / "workspace" / "src" / "map" / "style.ts"
    ).read_text(encoding="utf-8")
    for font in STYLE_FONTS:
        assert f'"text-font": ["{font}"]' in style
