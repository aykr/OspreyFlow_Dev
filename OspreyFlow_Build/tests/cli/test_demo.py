"""`ospreyflow demo list | add` (ADR-114 decision 5; Amendment 3 decision 4): a pack seeded through
the product's own `scripts.seed_internal`, a PaySim file checked before anything starts.

What a mistake would do, and the case that catches it:
- PaySim started without its file, or with a file nobody checked —
  `test_paysim_without_a_file_is_refused_naming_b5_and_the_source_page` and
  `test_a_wrong_checksum_is_refused_before_any_seed_runs`;
- the file copied or the seed started before the check — the same case asserts the order;
- the pack ids and the seed's dataset keys drifting apart — `test_each_pack_maps_to_its_seed_key`;
- the CLI's copy of PaySim's source page going stale —
  `test_the_source_page_the_command_names_is_the_packs_own`;
- an unknown id accepted, or refused without saying which exist — `test_an_unknown_pack_is_refused_with_the_list`;
- the seed not told where the data is — `test_the_demo_data_folder_reaches_the_seed`;
- the demo-data root chosen differently from `scripts.seed_internal`'s —
  `test_the_demo_data_root_follows_the_environment_then_the_sibling_then_the_home_folder`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from ospreyflow.demo import PACK_KEYS, PAYSIM_SOURCE_PAGE, demo_data_root
from scripts import demo_packs

from .conftest import FakeRunner, Rig


class VerifyingRunner(FakeRunner):
    """Records every command, and runs the real `scripts.demo_packs verify` for that one."""

    def __call__(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
    ) -> int:
        code = super().__call__(argv, env=env, cwd=cwd)
        if "scripts.demo_packs" in argv and "verify" in argv:
            return demo_packs.main(list(argv[argv.index("verify") :]))
        return code


def _seed_calls(rig: Rig) -> list[list[str]]:
    return [c.argv for c in rig.runner.with_word("scripts.seed_internal")]


def test_demo_list_runs_the_products_pack_listing(rig: Rig) -> None:
    assert rig("demo", "list") == 0
    (call,) = rig.runner.calls
    assert call.argv == [str(rig.product / ".venv" / "bin" / "python"), "-m", "scripts.demo_packs"]
    assert call.cwd == rig.product


def test_each_pack_maps_to_its_seed_key(rig: Rig, tmp_path: Path) -> None:
    assert PACK_KEYS == {
        "hmp": "hmp",
        "fixture-corp": "fixture-corp",
        "operation-ledger": "ledger",
        "paysim": "paysim",
        "enron": "enron",
    }
    assert rig("demo", "add", "operation-ledger") == 0
    (argv,) = _seed_calls(rig)
    assert argv[argv.index("scripts.seed_internal") + 1 :] == ["ledger", "--stop-api"]


def test_an_unknown_pack_is_refused_with_the_list(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("demo", "add", "vast") == 1
    err = capsys.readouterr().err
    assert "vast" in err
    for known in PACK_KEYS:
        assert known in err
    assert rig.runner.calls == []


def test_paysim_without_a_file_is_refused_naming_b5_and_the_source_page(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("demo", "add", "paysim") == 1
    err = capsys.readouterr().err
    assert "B5" in err and "--file" in err
    assert PAYSIM_SOURCE_PAGE in err
    assert rig.runner.calls == []


def test_the_source_page_the_command_names_is_the_packs_own() -> None:
    download = demo_packs.pack("paysim").download
    assert download is not None
    assert PAYSIM_SOURCE_PAGE == download.source_page


def test_a_wrong_checksum_is_refused_before_any_seed_runs(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A small real file, a pack that expects its size but another checksum, and the real verifier:
    the refusal must come first, and neither the copy nor the seed may follow it."""
    import dataclasses
    import hashlib

    download = demo_packs._DESCRIPTIONS["paysim"].download
    assert download is not None
    wrong = tmp_path / "PS_wrong.csv"
    wrong.write_text("the 0riginal\n", encoding="utf-8")
    pinned = dataclasses.replace(
        download,
        size_bytes=wrong.stat().st_size,
        sha256=hashlib.sha256(b"the original\n").hexdigest(),
    )
    monkeypatch.setitem(
        demo_packs._DESCRIPTIONS,
        "paysim",
        dataclasses.replace(demo_packs._DESCRIPTIONS["paysim"], download=pinned),
    )
    rig.runner = VerifyingRunner()
    assert rig("demo", "add", "paysim", "--file", str(wrong)) == 1
    argvs = rig.runner.argvs()
    assert len(argvs) == 1 and "verify" in argvs[0]  # the check was the only thing that ran
    assert argvs[0][-3:] == ["verify", "paysim", str(wrong)]
    assert not (tmp_path / "demo-data").exists()  # nothing was copied
    shown = capsys.readouterr()
    assert "checksum" in shown.out + shown.err

    # The same file made right is copied, and only then seeded.
    good = tmp_path / "PS_good.csv"
    good.write_text("the original\n", encoding="utf-8")
    assert rig("demo", "add", "paysim", "--file", str(good)) == 0
    *_, verify, seed = rig.runner.argvs()
    assert verify[-3:] == ["verify", "paysim", str(good)]
    assert seed[seed.index("scripts.seed_internal") + 1] == "paysim"
    assert (tmp_path / "demo-data" / "PaySIM_Dataset" / "PS_good.csv").read_text(
        encoding="utf-8"
    ) == "the original\n"


def test_a_file_already_in_place_is_not_copied_again(rig: Rig, tmp_path: Path) -> None:
    root = tmp_path / "demo-data" / "PaySIM_Dataset"
    root.mkdir(parents=True)
    source = tmp_path / "PS.csv"
    source.write_text("same\n", encoding="utf-8")
    (root / "PS.csv").write_text("same\n", encoding="utf-8")
    placed = (root / "PS.csv").stat().st_mtime_ns
    assert rig("demo", "add", "paysim", "--file", str(source)) == 0
    assert (root / "PS.csv").stat().st_mtime_ns == placed
    source.write_text("different\n", encoding="utf-8")
    assert rig("demo", "add", "paysim", "--file", str(source)) == 0
    assert (root / "PS.csv").read_text(encoding="utf-8") == "different\n"


def test_the_demo_data_folder_reaches_the_seed(rig: Rig, tmp_path: Path) -> None:
    assert rig("demo", "add", "hmp") == 0
    (call,) = rig.runner.with_word("scripts.seed_internal")
    assert call.env is not None
    assert call.env["OSPREYFLOW_DEMO_DATA"] == str(tmp_path / "demo-data")
    assert call.cwd == rig.product


def test_the_demo_data_root_follows_the_environment_then_the_sibling_then_the_home_folder(
    tmp_path: Path,
) -> None:
    product = tmp_path / "repo" / "OspreyFlow_Core"
    product.mkdir(parents=True)
    home = tmp_path / "home"
    assert demo_data_root(product, {"OSPREYFLOW_DEMO_DATA": "/chosen"}, home=home) == Path(
        "/chosen"
    )
    assert demo_data_root(product, {}, home=home) == home / "OspreyFlow" / "demo-data"
    (tmp_path / "repo" / "OspreyFlow_Data").mkdir()
    assert demo_data_root(product, {}, home=home) == tmp_path / "repo" / "OspreyFlow_Data"
