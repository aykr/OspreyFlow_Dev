"""ADR-114 Amendment 1 (stage B0): the demo packs. What each test catches is named in its own
docstring; together they hold the pack list to the registry, and a download to its own size and
checksum."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
from pathlib import Path

import pytest
from scripts import demo_packs
from scripts.demo_packs import DemoPack, PackDownload, PackRefused
from scripts.demo_registry import REGISTRY, shipped_manifests

from tools.layout import CORE

_EXPECTED_IDS = {"hmp", "fixture-corp", "operation-ledger", "paysim"}
_LICENCE_SHA256 = "28a9529c7d0bb4dc51f4bf5c116a3d16ef247a052f7591466768ddf563fd1cf5"
_REFUSAL = (
    "There is no demo pack called '{}'. "
    "The packs are: hmp, fixture-corp, operation-ledger, paysim."
)


def _refusal_for(pack_id: str) -> str:
    with pytest.raises(PackRefused) as caught:
        demo_packs.pack(pack_id)
    return str(caught.value)


def test_an_unregistered_pack_and_an_internal_demo_are_refused_in_the_same_words() -> None:
    """An internal demo (`enron`) must not be distinguishable from one that does not exist, or the
    refusal itself would confirm the internal demo is there."""
    assert _refusal_for("nonesuch") == _REFUSAL.format("nonesuch")
    assert _refusal_for("enron") == _REFUSAL.format("enron")


def test_every_shipped_demo_is_a_pack_and_no_internal_one_is() -> None:
    """The pack list is derived from the registry's shipped entries, not kept beside it."""
    ids = {p.id for p in demo_packs.packs()}

    assert ids == _EXPECTED_IDS
    assert ids == {m.id for m in shipped_manifests(REGISTRY)}


def test_a_misspelled_distribution_offers_no_pack() -> None:
    """The registry fails closed; a pack list built from it must too."""
    misspelt = tuple(
        dataclasses.replace(m, distribution="Shipped") if m.id == "paysim" else m for m in REGISTRY
    )

    assert "paysim" not in {p.id for p in demo_packs.packs(misspelt)}
    with pytest.raises(PackRefused):
        demo_packs.pack("paysim", misspelt)


def _small_pack(path: Path, data: bytes) -> DemoPack:
    return DemoPack(
        id="small",
        title="Small",
        shows="A tiny file.",
        delivery="download",
        seed_module=None,
        licence="CC-BY-SA-4.0",
        attribution="Someone",
        download=PackDownload(
            filename=path.name,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            source_page="https://example.invalid/small",
            release_asset=None,
            licence_file="x/LICENSE.txt",
            attribution_file="x/ATTRIBUTION.md",
        ),
    )


def test_a_download_with_the_wrong_size_or_checksum_is_refused(tmp_path: Path) -> None:
    """A truncated or altered file must be refused, each for its own stated reason."""
    data = b"abcdefghij" * 100
    target = tmp_path / "small.csv"
    target.write_bytes(data)
    pack = _small_pack(target, data)

    demo_packs.verify_download(target, pack)  # the correct file passes

    altered = bytearray(data)
    altered[5] ^= 0x01
    target.write_bytes(bytes(altered))
    with pytest.raises(PackRefused, match="does not match") as checksum:
        demo_packs.verify_download(target, pack)
    assert "downloaded again" in str(checksum.value)

    target.write_bytes(data[:-1])
    with pytest.raises(PackRefused, match="1,000") as size:
        demo_packs.verify_download(target, pack)
    assert "999" in str(size.value)

    with pytest.raises(PackRefused, match="no file"):
        demo_packs.verify_download(tmp_path / "absent.csv", pack)


def test_a_seeded_pack_has_nothing_to_download(tmp_path: Path) -> None:
    """A seeded pack has no download to verify; asking is refused in words."""
    seeded = demo_packs.pack("hmp")

    assert seeded.download is None
    with pytest.raises(PackRefused, match="nothing to download"):
        demo_packs.verify_download(tmp_path / "anything", seeded)


def test_paysim_carries_its_licence_and_attribution() -> None:
    """Share-alike data is only redistributable with its licence and credit beside it."""
    pack = demo_packs.pack("paysim")
    assert pack.licence == "CC-BY-SA-4.0"
    assert pack.attribution is not None
    for needle in ("Lopez-Rojas", "Elmir", "Axelsson", "EMSS 2016"):
        assert needle in pack.attribution

    download = pack.download
    assert download is not None
    licence = CORE / download.licence_file
    attribution = CORE / download.attribution_file
    assert licence.is_file()
    assert attribution.is_file()
    assert hashlib.sha256(licence.read_bytes()).hexdigest() == _LICENCE_SHA256
    assert licence.read_text(encoding="utf-8").startswith("Attribution-ShareAlike 4.0 International")
    text = attribution.read_text(encoding="utf-8")
    assert "https://www.kaggle.com/datasets/ealaxi/paysim1" in text
    assert "CC BY-SA 4.0" in text
    assert download.size_bytes == 493534783
    assert download.sha256 == "16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b"
    assert download.release_asset is None


def test_each_seeded_pack_names_a_seed_module_that_exists() -> None:
    """A pack whose seed module cannot be found would fail only when someone tried to use it."""
    seeded = [p for p in demo_packs.packs() if p.delivery == "seed"]

    assert {p.id for p in seeded} == {"hmp", "fixture-corp", "operation-ledger"}
    for pack in seeded:
        assert pack.seed_module is not None
        assert importlib.util.find_spec(pack.seed_module) is not None, pack.seed_module
