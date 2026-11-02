"""A public dataset of the administrator's choosing (ADR-138 decision 3): the manifest, the check
and the placing (`scripts.public_dataset`), and the seed that loads it (`scripts.seed_internal
public`). Synthetic files only: no VAST data is downloaded, committed or read here (rule 9).

What a mistake would do, and the case that catches it (rule 12):
- a file whose checksum differs loaded anyway — `test_a_checksum_that_differs_is_refused_before_anything_is_placed`;
- real personal data placed without the acceptance — `test_real_personal_data_is_refused_without_the_acceptance`;
- a catalogue entry nobody has hashed trusted blindly — `test_an_unpinned_catalogue_entry_is_refused_until_pinned`;
- a manifest that says nothing of its terms — `test_every_catalogue_manifest_states_its_terms`;
- a public dataset seeded into the wrong folder, case or domains —
  `test_the_seed_mounts_the_staged_dataset_and_names_its_case_from_the_manifest`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from scripts import public_dataset, seed_internal

from schemas.public_dataset import PublicDatasetManifest

ROWS = "From,To,Datetime,Duration,Cell Tower\n200,201,20060601 0815,94,12\n201,202,20060601 0930,15,3\n"


def _manifest(folder: Path, file: Path, **overrides: object) -> Path:
    raw: dict[str, object] = {
        "id": "test-calls",
        "name": "Test calls (synthetic)",
        "source_page": "https://example.org/test-calls",
        "licence": "No licence stated on the source page.",
        "redistribution": "not_stated",
        "commercial_use": "not_stated",
        "fictional": True,
        "real_personal_data": False,
        "file": {"name": file.name, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()},
        "recipe": "vast_2008_mc3_calls_recipe.yaml",
        "domains": ["niem"],
    }
    raw.update(overrides)
    path = folder / "test.dataset.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def calls(tmp_path: Path) -> Path:
    path = tmp_path / "download" / "cell-phone-calls.csv"
    path.parent.mkdir()
    path.write_text(ROWS, encoding="utf-8")
    return path


def test_a_matching_file_is_verified_and_placed_with_its_manifest_and_recipe(
    tmp_path: Path, calls: Path
) -> None:
    manifest = _manifest(tmp_path, calls)
    folder = public_dataset.stage(str(manifest), calls, tmp_path / "data", accepted=False)
    assert folder == tmp_path / "data" / "public" / "test-calls"
    assert sorted(p.name for p in folder.iterdir()) == [
        "cell-phone-calls.csv", "dataset.yaml", "recipe.yaml",
    ]  # fmt: skip


def test_a_checksum_that_differs_is_refused_before_anything_is_placed(
    tmp_path: Path, calls: Path
) -> None:
    manifest = _manifest(tmp_path, calls)
    calls.write_text(ROWS + "202,200,20060602 1000,30,4\n", encoding="utf-8")  # changed since
    with pytest.raises(public_dataset.DatasetRefused, match="SHA-256 checksum") as refused:
        public_dataset.stage(str(manifest), calls, tmp_path / "data", accepted=True)
    assert "Nothing was loaded" in str(refused.value)
    assert not (tmp_path / "data").exists()
    assert public_dataset.main(["verify", "--manifest", str(manifest), "--file", str(calls)]) == 1


def test_real_personal_data_is_refused_without_the_acceptance(tmp_path: Path, calls: Path) -> None:
    manifest = _manifest(tmp_path, calls, fictional=False, real_personal_data=True)
    with pytest.raises(public_dataset.DatasetRefused, match="real personal data"):
        public_dataset.stage(str(manifest), calls, tmp_path / "data", accepted=False)
    assert not (tmp_path / "data").exists()
    folder = public_dataset.stage(str(manifest), calls, tmp_path / "data", accepted=True)
    record = json.loads((folder / "ACCEPTED_REAL_DATA.json").read_text(encoding="utf-8"))
    assert record["accepted"] is True and record["dataset"] == "test-calls"


def test_an_unpinned_catalogue_entry_is_refused_until_pinned(tmp_path: Path) -> None:
    """OspreyFlow never downloads VAST data, so no catalogue entry carries a checksum; the
    administrator pins the file they downloaded, into a manifest of their own."""
    synthetic = tmp_path / "Firewall-04072012.csv"
    synthetic.write_text("Date/time,Source IP\n", encoding="utf-8")
    with pytest.raises(public_dataset.DatasetRefused, match="records no checksum yet"):
        public_dataset.verify("vast-2012-mc2", synthetic)
    pinned = public_dataset.pin("vast-2012-mc2", synthetic, tmp_path / "mine" / "vast.yaml")
    manifest, _m, recipe = public_dataset.verify(str(pinned), synthetic)
    assert manifest.file.sha256 == hashlib.sha256(synthetic.read_bytes()).hexdigest()
    assert recipe.parent == pinned.parent  # the recipe travels with the pinned copy


def test_a_manifest_that_is_fictional_and_holds_real_people_is_refused(
    tmp_path: Path, calls: Path
) -> None:
    with pytest.raises(public_dataset.DatasetRefused, match="cannot be fictional"):
        public_dataset.load_manifest(_manifest(tmp_path, calls, real_personal_data=True))


def test_an_unknown_manifest_key_is_refused_by_name() -> None:
    with pytest.raises(ValidationError, match="licence_text"):
        PublicDatasetManifest.model_validate({"licence_text": "x"})


def test_every_catalogue_manifest_states_its_terms() -> None:
    """Each VAST entry says where it comes from, what its terms are (no licence is stated, so no
    right to redistribute is granted), that it is fictional and holds no real people, and names a
    recipe that is valid."""
    entries = public_dataset.catalogue()
    assert {p.name for p in entries} == {"vast-2012-mc2.dataset.yaml", "vast-2008-mc3.dataset.yaml"}
    for path in entries:
        manifest = public_dataset.load_manifest(path)
        assert manifest.fictional and not manifest.real_personal_data
        assert manifest.redistribution == manifest.commercial_use == "not_stated"
        assert "No licence" in manifest.licence and "redistribute" in manifest.licence
        assert manifest.file.sha256 is None
        public_dataset.load_recipe(public_dataset.recipe_path(manifest, path))
    cyber = public_dataset.load_manifest(public_dataset.find_manifest("vast-2012-mc2"))
    assert cyber.domains == ["stix"]


def test_the_command_reads_the_verify_summary_and_refusal_from_standard_output(
    tmp_path: Path, calls: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _manifest(tmp_path, calls)
    argv = ["verify", "--manifest", str(manifest), "--file", str(calls), "--json"]
    assert public_dataset.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "test-calls"
    calls.write_text("changed\n", encoding="utf-8")
    assert public_dataset.main(argv) == 1
    assert "SHA-256 checksum" in capsys.readouterr().out


# --- the seed ------------------------------------------------------------------------------------


class Runner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> str:
        self.calls.append(list(argv))
        return "Loaded.\n" if "run" in argv else ""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    core = tmp_path / "OspreyFlow_Core"
    out = core / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text("X=1\n", encoding="utf-8")
    return core


def _seed(repo: Path, **kwargs: object) -> list[str]:
    runner = Runner()
    seed_internal.seed_internal(
        "public", repo, run=runner,
        lookup_subs=lambda directory: {"osprey-demo-admin": "a", "osprey-demo-analyst": "b"},
        api_running=lambda compose: False, permitted=lambda name, use: False,
        **kwargs,  # type: ignore[arg-type]
    )  # fmt: skip
    (call,) = [c for c in runner.calls if "run" in c]
    return call


def test_the_seed_mounts_the_staged_dataset_and_names_its_case_from_the_manifest(
    repo: Path, tmp_path: Path, calls: Path
) -> None:
    data = repo.parent / "OspreyFlow_Data"
    public_dataset.stage(str(_manifest(tmp_path, calls)), calls, data, accepted=False)
    call = _seed(repo, public_id="test-calls")
    assert call[call.index("-m") + 1] == "scripts.seed_public"
    assert f"{data}:/internal-data:ro" in call
    assert call[call.index("--case-name") + 1] == "Test calls (synthetic) (public dataset)"
    assert call[call.index("--dataset-id") + 1] == "test-calls"
    assert call[call.index("--case-domains") + 1] == "niem"


def test_the_seed_refuses_a_dataset_not_placed(repo: Path) -> None:
    with pytest.raises(seed_internal.SeedRefused, match="not placed"):
        _seed(repo, public_id="never-added")


def test_the_seed_refuses_real_data_whose_acceptance_is_missing(
    repo: Path, tmp_path: Path, calls: Path
) -> None:
    data = repo.parent / "OspreyFlow_Data"
    manifest = _manifest(tmp_path, calls, fictional=False, real_personal_data=True)
    folder = public_dataset.stage(str(manifest), calls, data, accepted=True)
    (folder / "ACCEPTED_REAL_DATA.json").unlink()
    with pytest.raises(seed_internal.SeedRefused, match="has not been accepted"):
        _seed(repo, public_id="test-calls")


def test_a_starters_case_domains_reach_the_seed(repo: Path) -> None:
    """ADR-138: `--case-domains` from the install goes to the seed in the container, which sets the
    case's packs while nobody has chosen (`scripts/case_seed.py`)."""
    runner = Runner()
    seed_internal.seed_internal(
        "hmp", repo, run=runner,
        lookup_subs=lambda directory: {"osprey-demo-admin": "a", "osprey-demo-analyst": "b"},
        api_running=lambda compose: False, case_domains=["niem"],
    )  # fmt: skip
    (call,) = [c for c in runner.calls if "run" in c]
    assert call[call.index("--case-domains") + 1] == "niem"
