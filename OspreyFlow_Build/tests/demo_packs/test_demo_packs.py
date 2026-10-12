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
        case_name="Small (test)",
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


def test_ids_prints_the_pack_ids_one_per_line_and_nothing_else(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The `ospreyflow` command reads this to know which packs a checkout offers (stage B2b)."""
    assert demo_packs.main(["--ids"]) == 0
    assert capsys.readouterr().out.splitlines() == [p.id for p in demo_packs.packs()]
    assert demo_packs.main([]) == 0
    assert "shows:" in capsys.readouterr().out  # a plain run still lists


def _small_paysim(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: bytes) -> Path:
    """PaySim expecting `content` exactly, so a real file small enough to write can be checked."""
    download = demo_packs.pack("paysim").download
    assert download is not None
    file = tmp_path / "PS.csv"
    file.write_bytes(content)
    pinned = dataclasses.replace(
        download, size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest()
    )
    monkeypatch.setitem(
        demo_packs._DESCRIPTIONS,
        "paysim",
        dataclasses.replace(demo_packs._DESCRIPTIONS["paysim"], download=pinned),
    )
    return file


def test_verify_accepts_the_right_file_and_refuses_each_wrong_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 0 for the pack's own file; exit 1 and the refusal's words for a file with the right size
    but another checksum, a file that is missing, and a pack that has nothing to download."""
    file = _small_paysim(monkeypatch, tmp_path, b"original\n")
    assert demo_packs.main(["verify", "paysim", str(file)]) == 0
    file.write_bytes(b"tampered\n")  # the same size, so only the checksum can tell
    assert demo_packs.main(["verify", "paysim", str(file)]) == 1
    assert "checksum" in capsys.readouterr().err
    assert demo_packs.main(["verify", "paysim", str(tmp_path / "gone.csv")]) == 1
    assert "no file" in capsys.readouterr().err.lower()
    assert demo_packs.main(["verify", "hmp", str(file)]) == 1
    assert "nothing to download" in capsys.readouterr().err
    assert demo_packs.main(["verify", "enron", str(file)]) == 1
    assert "no demo pack called 'enron'" in capsys.readouterr().err.lower()


def test_verify_without_its_arguments_is_a_usage_error() -> None:
    assert demo_packs.main(["verify", "paysim"]) == 2


def test_each_pack_names_the_case_its_seed_makes() -> None:
    """ADR-114 Amendment 5 (B4d): the Admin area's Demo packs tab says whether a pack is loaded by
    the case it lands in. The Conduit cannot import the seed runner (it needs the harness), so the
    pack carries the name — and must carry the seed's own."""
    from ospreyflow.demo import PACK_KEYS
    from scripts.seed_internal import DATASETS

    for each in demo_packs.packs():
        assert each.case_name == DATASETS[PACK_KEYS[each.id]].case_name, each.id
