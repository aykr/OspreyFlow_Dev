"""`install.yaml`'s `grading.scheme` (`06_DECISIONS.md` ADR-143 decision 11): chosen at install and
written into `osprey.yaml`'s `grading` section, validated by the deployment's own schema; a scheme
that is not one is refused in words, never silently the default."""

from __future__ import annotations

from pathlib import Path

import pytest
from ospreyflow.answers import AnswersRefused, load_answers, osprey_config

from schemas.deployment import OspreyConfig

from .test_answers import PACKS, _base


def _config(raw: dict[str, object], home: Path) -> OspreyConfig:
    answers = load_answers(raw, packs=PACKS, home=home)
    return OspreyConfig.model_validate(osprey_config(answers, _base()))


def test_the_grading_scheme_is_5x5x5_unless_the_answers_choose_another(tmp_path: Path) -> None:
    assert _config({"mode": "lite"}, tmp_path).grading.scheme == "5x5x5"
    chosen = _config({"mode": "lite", "grading": {"scheme": "3x5x2"}}, tmp_path)
    assert chosen.grading.scheme == "3x5x2"


def test_a_named_config_gains_the_chosen_scheme_and_keeps_the_rest(tmp_path: Path) -> None:
    own = tmp_path / "osprey.yaml"
    own.write_text("profile: local-lite\n", encoding="utf-8")
    answers = load_answers(
        {"mode": "lite", "config": str(own), "grading": {"scheme": "3x5x2"}}, packs=PACKS,
        home=tmp_path,
    )  # fmt: skip
    config = OspreyConfig.model_validate(osprey_config(answers, _base()))
    assert config.grading.scheme == "3x5x2" and config.profile.value == "local-lite"


@pytest.mark.parametrize("given", ["5x5", "3X5X2", 552])
def test_a_scheme_that_is_not_one_is_refused_naming_it(tmp_path: Path, given: object) -> None:
    with pytest.raises(AnswersRefused, match="grading.scheme"):
        load_answers({"mode": "lite", "grading": {"scheme": given}}, packs=PACKS, home=tmp_path)
    with pytest.raises(AnswersRefused, match="schem"):
        load_answers({"mode": "lite", "grading": {"schem": "3x5x2"}}, packs=PACKS, home=tmp_path)
