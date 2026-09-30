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


# --- running inside the deployment (ADR-055 Amendment 2) ---

from scripts.seed_paysim import _parse_args, scope_and_source  # noqa: E402


def test_the_seed_needs_either_a_case_to_make_or_a_scope_to_write_into() -> None:
    with pytest.raises(SystemExit):
        _parse_args([])
    assert _parse_args(["--investigation-scope", "abc"]).investigation_scope == "abc"
    assert _parse_args(["--case-name", "PaySim"]).case_name == "PaySim"


def test_grants_and_the_attestation_are_read_from_the_command_line() -> None:
    args = _parse_args(
        [
            "--case-name",
            "PaySim",
            "--grant",
            "a=author",
            "--grant",
            "b=editor",
            "--attested-checkout",
        ]
    )
    assert args.grant == ["a=author", "b=editor"]
    assert args.attested_checkout is True
    assert _parse_args(["--case-name", "x"]).attested_checkout is False


def test_a_seed_run_inside_a_container_refuses_without_the_hosts_attestation(
    tmp_path: Path,
) -> None:
    """The container has no `.git`, so the seed cannot tell a checkout from a bundle itself. The
    host-side command checks and says so with `--attested-checkout`; without it the container's own
    answer stands: not a checkout, refuse (ADR-035 §C1)."""
    folder = tmp_path / "PaySIM_Dataset"
    folder.mkdir()
    (folder / FILE_NAME).write_text("x", encoding="utf-8")

    with pytest.raises(NotProvisionedError, match="checkout"):
        scope_and_source(
            _parse_args(["--case-name", "x", "--data-dir", str(tmp_path)]), in_checkout=False
        )
    assert (
        scope_and_source(
            _parse_args(["--case-name", "x", "--data-dir", str(tmp_path), "--attested-checkout"]),
            in_checkout=False,
        )
        == folder / FILE_NAME
    )
