"""The install answers file (`06_DECISIONS.md` ADR-114 Amendment 3 decision 5): what every question
writes and what `--config` reads, so the guided page, the prompts and CI install the same way — and
the `osprey.yaml` it becomes, validated by the deployment's own schema.

What a mistake would do, and the case that catches it:
- a typo in the file silently ignored — `test_an_unknown_key_is_refused_naming_it`;
- a mode or demo pack nobody built accepted — `test_an_unknown_mode_or_pack_is_refused`;
- the dashboards lost, as the hand-edited deployment showed they would be —
  `test_dashboards_are_on_by_default_and_reach_osprey_yaml`;
- the ingest or tiles folder left at a path that does not exist on a laptop —
  `test_the_folders_reach_storage_as_absolute_host_paths`;
- a generated `osprey.yaml` the renderer would refuse — every case validates it with `OspreyConfig`;
- the owner's own `osprey.yaml` rewritten when they asked for it to be used as it is —
  `test_a_named_config_is_used_as_it_is`;
- a cloud mode's answers dropped before B6/B7 can use them — `test_a_cloud_modes_answers_are_kept`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ospreyflow.answers import AnswersRefused, load_answers, osprey_config
from schemas.deployment import OspreyConfig


PACKS = ("hmp", "fixture-corp", "operation-ledger", "paysim")


def _base() -> dict[str, object]:
    """The product's committed defaults — what a fresh checkout's `osprey.yaml` holds."""
    import subprocess

    from tools.layout import ROOT

    text = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:OspreyFlow_Core/osprey.yaml"],
                          capture_output=True, text=True, check=True).stdout  # fmt: skip
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict)
    return loaded


def _config(raw: dict[str, object], home: Path) -> OspreyConfig:
    answers = load_answers(raw, packs=PACKS, home=home)
    return OspreyConfig.model_validate(osprey_config(answers, _base()))


def test_the_smallest_file_is_a_valid_lite_install(tmp_path: Path) -> None:
    config = _config({"mode": "lite"}, tmp_path)
    assert config.profile.value == "local-lite"


def test_an_unknown_key_is_refused_naming_it(tmp_path: Path) -> None:
    with pytest.raises(AnswersRefused, match="dashbords"):
        load_answers({"mode": "lite", "components": {"dashbords": False}}, packs=PACKS, home=tmp_path)
    with pytest.raises(AnswersRefused, match="colour"):
        load_answers({"mode": "lite", "colour": "blue"}, packs=PACKS, home=tmp_path)


def test_an_unknown_mode_or_pack_is_refused(tmp_path: Path) -> None:
    with pytest.raises(AnswersRefused, match="medium"):
        load_answers({"mode": "medium"}, packs=PACKS, home=tmp_path)
    with pytest.raises(AnswersRefused, match="enron"):
        load_answers({"mode": "lite", "demo_packs": ["hmp", "enron"]}, packs=PACKS, home=tmp_path)


def test_dashboards_are_on_by_default_and_reach_osprey_yaml(tmp_path: Path) -> None:
    on = _config({"mode": "lite"}, tmp_path)
    assert on.reporting.sync and on.reporting.superset
    off = _config({"mode": "lite", "components": {"dashboards": False}}, tmp_path)
    assert not off.reporting.sync and not off.reporting.superset


def test_the_folders_reach_storage_as_absolute_host_paths(tmp_path: Path) -> None:
    default = _config({"mode": "lite"}, tmp_path)
    assert default.components.storage.ingest == str(tmp_path / "OspreyFlow" / "ingest")
    assert default.components.storage.tiles == str(tmp_path / "OspreyFlow" / "basemap")
    chosen = _config({"mode": "lite", "folders": {"ingest": "~/evidence", "tiles": str(tmp_path / "maps")}},
                     tmp_path)  # fmt: skip
    assert chosen.components.storage.ingest == str(tmp_path / "evidence")
    assert chosen.components.storage.tiles == str(tmp_path / "maps")
    with pytest.raises(AnswersRefused, match="relative"):
        load_answers({"mode": "lite", "folders": {"ingest": "evidence"}}, packs=PACKS, home=tmp_path)


def test_models_stay_on_the_machine_unless_said_otherwise(tmp_path: Path) -> None:
    assert _config({"mode": "lite"}, tmp_path).models.local_only is True
    assert _config({"mode": "lite", "models": {"local_only": False}}, tmp_path).models.local_only is False


def test_the_demo_packs_and_paysims_file_are_kept(tmp_path: Path) -> None:
    answers = load_answers({"mode": "lite", "demo_packs": ["operation-ledger", "paysim"],
                            "paysim_file": "~/Downloads/paysim.csv"}, packs=PACKS, home=tmp_path)  # fmt: skip
    assert answers.demo_packs == ("operation-ledger", "paysim")
    assert answers.paysim_file == tmp_path / "Downloads" / "paysim.csv"
    with pytest.raises(AnswersRefused, match="paysim_file"):
        load_answers({"mode": "lite", "paysim_file": "/x.csv"}, packs=PACKS, home=tmp_path)


def test_a_named_config_is_used_as_it_is(tmp_path: Path) -> None:
    own = tmp_path / "osprey.yaml"
    own.write_text("profile: local-lite\nreporting:\n  sync: true\n  superset: false\n", encoding="utf-8")
    answers = load_answers({"mode": "lite", "config": str(own)}, packs=PACKS, home=tmp_path)
    assert osprey_config(answers, _base()) == yaml.safe_load(own.read_text(encoding="utf-8"))
    with pytest.raises(AnswersRefused, match="either"):
        load_answers({"mode": "lite", "config": str(own), "components": {"dashboards": False}},
                     packs=PACKS, home=tmp_path)  # fmt: skip


def test_a_cloud_modes_answers_are_kept(tmp_path: Path) -> None:
    answers = load_answers({"mode": "small", "cloud": {"provider": "azure", "region": "uksouth",
                            "domain": "osprey.example.org"}}, packs=PACKS, home=tmp_path)  # fmt: skip
    assert answers.cloud == {"provider": "azure", "region": "uksouth", "domain": "osprey.example.org"}
    with pytest.raises(AnswersRefused, match="gcp"):
        load_answers({"mode": "small", "cloud": {"provider": "gcp"}}, packs=PACKS, home=tmp_path)
    with pytest.raises(AnswersRefused, match="cloud"):
        load_answers({"mode": "lite", "cloud": {"provider": "aws"}}, packs=PACKS, home=tmp_path)
