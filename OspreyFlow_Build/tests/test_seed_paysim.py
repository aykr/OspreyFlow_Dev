"""ADR-055 §5: the seed refuses without the file, and from anything that is not a checkout."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.seed_paysim import FILE_NAME, NotProvisionedError, resolve_source


def test_the_seed_refuses_when_the_file_is_not_there(tmp_path: Path) -> None:
    with pytest.raises(NotProvisionedError, match="dataset not provisioned"):
        resolve_source(tmp_path, is_checkout=True)


def test_the_seed_refuses_from_a_bundle_even_when_the_file_is_there(tmp_path: Path) -> None:
    folder = tmp_path / "PaySIM_Dataset"
    folder.mkdir()
    (folder / FILE_NAME).write_text("x", encoding="utf-8")

    with pytest.raises(NotProvisionedError, match="checkout"):
        resolve_source(tmp_path, is_checkout=False)


def test_the_seed_finds_the_file_under_the_data_folder_from_a_checkout(tmp_path: Path) -> None:
    folder = tmp_path / "PaySIM_Dataset"
    folder.mkdir()
    (folder / FILE_NAME).write_text("x", encoding="utf-8")

    assert resolve_source(tmp_path, is_checkout=True) == folder / FILE_NAME
