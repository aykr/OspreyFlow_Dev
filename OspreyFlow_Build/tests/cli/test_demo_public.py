"""`ospreyflow demo add public --file <path> --manifest <dataset.yaml>` (ADR-138 decision 3).

The command checks the file against its manifest first, through the checkout's own
`scripts.public_dataset verify`, and runs nothing else when that refuses; real personal data is
accepted in words or with `--accept-real-data`; then it places the dataset and seeds it.

- a checksum that differs — `test_a_file_the_manifest_does_not_describe_is_refused_before_anything_runs`;
- real personal data loaded without acceptance — `test_real_personal_data_needs_yes_typed`,
  `test_accept_real_data_accepts_in_a_scripted_run`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import Rig

SUMMARY = {
    "id": "vast-2012-mc2", "name": "VAST 2012 MC2", "source_page": "https://example.org/vast",
    "licence": "No licence stated", "real_personal_data": False,
}  # fmt: skip


def _checked(rig: Rig, summary: dict[str, object] | None, code: int = 0, said: str = "") -> None:
    rig.responses["scripts.public_dataset"] = [
        (code, json.dumps(summary) + "\n" if summary is not None else said)
    ]


def _ran(rig: Rig, word: str) -> list[list[str]]:
    return [c.argv for c in rig.runner.with_word(word)]


def test_a_file_the_manifest_does_not_describe_is_refused_before_anything_runs(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _checked(rig, None, 1, "The SHA-256 checksum of x.csv is aa, but the manifest records bb.")
    assert rig("demo", "add", "public", "--file", str(tmp_path / "x.csv"),
               "--manifest", "vast-2012-mc2") == 1  # fmt: skip
    assert "SHA-256 checksum" in capsys.readouterr().err
    assert rig.runner.calls == []


def test_a_matching_file_is_placed_then_seeded_into_its_own_case(rig: Rig, tmp_path: Path) -> None:
    _checked(rig, SUMMARY)
    assert rig("demo", "add", "public", "--file", str(tmp_path / "x.csv"),
               "--manifest", "vast-2012-mc2") == 0  # fmt: skip
    (stage,) = _ran(rig, "stage")
    assert stage[stage.index("--into") + 1] == str(tmp_path / "demo-data")
    assert "--accepted" not in stage
    (seed,) = _ran(rig, "scripts.seed_internal")
    assert seed[seed.index("scripts.seed_internal") + 1 :] == [
        "public", "--stop-api", "--public-id", "vast-2012-mc2",
    ]  # fmt: skip


def test_real_personal_data_needs_yes_typed(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _checked(rig, {**SUMMARY, "real_personal_data": True})
    rig.replies = ["no"]
    assert rig("demo", "add", "public", "--file", str(tmp_path / "x.csv"),
               "--manifest", "mine.yaml") == 0  # fmt: skip
    assert "REAL DATA" in capsys.readouterr().out
    assert rig.runner.calls == []
    rig.replies = ["yes"]
    assert rig("demo", "add", "public", "--file", str(tmp_path / "x.csv"),
               "--manifest", "mine.yaml") == 0  # fmt: skip
    (stage,) = _ran(rig, "stage")
    assert "--accepted" in stage


def test_accept_real_data_accepts_in_a_scripted_run(rig: Rig, tmp_path: Path) -> None:
    _checked(rig, {**SUMMARY, "real_personal_data": True})
    assert rig("demo", "add", "public", "--file", str(tmp_path / "x.csv"),
               "--manifest", "mine.yaml", "--accept-real-data") == 0  # fmt: skip
    assert rig.questions == []
    assert _ran(rig, "scripts.seed_internal")


def test_without_a_file_or_manifest_it_says_what_to_give(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("demo", "add", "public", "--manifest", "vast-2012-mc2") == 1
    assert "--file <the downloaded file>" in capsys.readouterr().err
    assert rig.runner.calls == []
