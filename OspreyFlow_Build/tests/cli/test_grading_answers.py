"""`install.yaml`'s `grading.scheme` (`06_DECISIONS.md` ADR-143 decision 11): chosen at install and
written into `osprey.yaml`'s `grading` section, validated by the deployment's own schema; a scheme
that is not one is refused in words, never silently the default."""

from __future__ import annotations

from pathlib import Path

import pytest
from ospreyflow.answers import AnswersRefused, load_answers, osprey_config

from pydantic import ValidationError

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


def test_a_scheme_file_is_passed_on_as_named(tmp_path: Path) -> None:
    chosen = _config({"mode": "lite", "grading": {"scheme": "force-grades.yaml"}}, tmp_path)
    assert chosen.grading.scheme == "force-grades.yaml"


@pytest.mark.parametrize("given", ["5x5", "3X5X2"])
def test_a_scheme_that_is_not_one_is_refused_by_the_deployment_schema_naming_it(
    tmp_path: Path, given: str
) -> None:
    """The answers pass the name on; the deployment's schema, whose list of schemes is the one
    list (`GRADING_PARTS`), refuses it, naming it, when the result is checked."""
    with pytest.raises(ValidationError, match=f"{given!r} is neither a grading scheme"):
        _config({"mode": "lite", "grading": {"scheme": given}}, tmp_path)


def test_a_scheme_that_is_not_a_name_or_a_key_that_is_not_one_is_refused(tmp_path: Path) -> None:
    with pytest.raises(AnswersRefused, match="grading.scheme"):
        load_answers({"mode": "lite", "grading": {"scheme": 552}}, packs=PACKS, home=tmp_path)
    with pytest.raises(AnswersRefused, match="schem"):
        load_answers({"mode": "lite", "grading": {"schem": "3x5x2"}}, packs=PACKS, home=tmp_path)
