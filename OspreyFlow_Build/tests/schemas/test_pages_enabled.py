"""ADR-152 Amendment 3 (21 November 2026): the page service in a deployment is a deployment
setting, off by default.

`pages.enabled` in `osprey.yaml` is a boolean whose default is `false`; a value that is not `true`
or `false` is refused in words by the same settings validation that refuses an unknown
`appearance.brand`; a file that omits it validates and is off; an unknown sibling still fails as it
does for every other section. Slice IS5a adds the entry and reads nothing from it: the renderers
that will (PL7a2b) and the release switch (PL7d) are theirs.

Which test fails if the invariant is broken (rule 12):

* the default turned on -> `test_the_setting_exists_and_defaults_to_off`, and the same check is
  shown red against a planted default of true (`test_a_default_of_true_is_caught`)
* a file that omits it read as on -> `test_a_file_that_omits_it_validates_and_is_off`
* a value that is not a boolean read as one ("yes", "true" in quotes, 1)
  -> `test_a_value_that_is_not_true_or_false_is_refused_in_words`
* YAML 1.1's other spellings (`yes`, `on`, ...) read as true by the loader the deployment's real
  call sites use -> `test_the_plain_loader_reads_yes_as_true_and_the_validator_cannot_tell`
  (the fault, on record), `test_the_deployment_loader_refuses_yes_and_on_in_words` (the fix, on
  the YAML text, the shape `harness/render.py` loads), and
  `test_render_load_config_refuses_yes` (strict xfail until the renderer's own loader is the
  deployment loader: that file is the owner's)
* an unknown sibling taken in -> `test_an_unknown_sibling_still_fails`
* the setting read by anything yet -> `test_nothing_reads_the_setting_yet`
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from schemas.deployment import OspreyConfig, PagesConfig

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"


def default_is_off(model: type[BaseModel]) -> bool:
    """What the Amendment asks of the default: built with nothing, `enabled` is exactly `False`."""
    return getattr(model(), "enabled", None) is False


def test_the_setting_exists_and_defaults_to_off() -> None:
    assert "pages" in OspreyConfig.model_fields
    assert default_is_off(PagesConfig)
    assert OspreyConfig().pages.enabled is False


def test_a_default_of_true_is_caught() -> None:
    """The check above, run on the shape the field would take with the default on (rule 15)."""

    class Planted(BaseModel):
        model_config = ConfigDict(extra="forbid")
        enabled: bool = Field(default=True)

    assert not default_is_off(Planted)


def test_a_file_that_omits_it_validates_and_is_off() -> None:
    raws: list[dict[str, Any]] = [
        {},
        {"profile": "local-lite"},
        {"appearance": {"brand": "govuk"}},
        {"pages": {}},
    ]
    for raw in raws:
        assert OspreyConfig.model_validate(raw).pages.enabled is False, raw


def test_a_deployment_can_turn_it_on_and_off_in_its_own_file() -> None:
    assert OspreyConfig.model_validate({"pages": {"enabled": True}}).pages.enabled is True
    assert OspreyConfig.model_validate({"pages": {"enabled": False}}).pages.enabled is False


@pytest.mark.parametrize("value", ["yes", "true", "True", "on", 1, 0, None, [], {}, "false"])
def test_a_value_that_is_not_true_or_false_is_refused_in_words(value: Any) -> None:
    with pytest.raises(ValidationError, match=r"pages\.enabled must be true or false"):
        OspreyConfig.model_validate({"pages": {"enabled": value}})


# What PyYAML's own bool resolver reads as a boolean besides true and false.
SPELLINGS_YAML_1_1 = ["yes", "Yes", "YES", "on", "On", "ON", "no", "No", "NO", "off", "Off", "OFF"]


def _file(value: str) -> str:
    """An `osprey.yaml` as a person writes it: the value unquoted, as YAML 1.1 reads it."""
    return f"pages:\n  enabled: {value}\n"


@pytest.mark.parametrize("value", SPELLINGS_YAML_1_1)
def test_the_plain_loader_reads_yes_as_true_and_the_validator_cannot_tell(value: str) -> None:
    """The fault, on record (rule 15: the planted value takes the shape the real call site
    receives). `yaml.safe_load`, which `harness/render.py`, `site.py` and `install_page.py` call,
    follows YAML 1.1: an unquoted `yes` arrives as the Python bool, so no validator behind it can
    refuse it. The fix is in the loader, not the validator."""
    loaded = yaml.safe_load(_file(value))
    assert isinstance(loaded["pages"]["enabled"], bool)
    OspreyConfig.model_validate(loaded)  # passes: the validator is shown a real bool


@pytest.mark.parametrize("value", SPELLINGS_YAML_1_1)
def test_the_deployment_loader_refuses_yes_and_on_in_words(value: str) -> None:
    from schemas.deployment import load_osprey_yaml

    with pytest.raises(ValidationError, match=r"pages\.enabled must be true or false"):
        OspreyConfig.model_validate(load_osprey_yaml(_file(value)))


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("True", True), ("TRUE", True), ("false", False), ("False", False)],
)
def test_the_deployment_loader_still_reads_true_and_false(value: str, expected: bool) -> None:
    from schemas.deployment import load_osprey_yaml

    config = OspreyConfig.model_validate(load_osprey_yaml(_file(value)))
    assert config.pages.enabled is expected


def test_the_deployment_loader_reads_the_rest_of_a_file_as_the_plain_one_does() -> None:
    """Only the boolean spellings differ: the committed root file, an empty file and a file
    with strings and numbers load to the same thing."""
    from schemas.deployment import load_osprey_yaml

    texts = [
        (CORE / "osprey.yaml").read_text(encoding="utf-8"),
        "",
        "profile: small\nnetwork:\n  hostname: example.test\npages:\n  enabled: true\n",
    ]
    for text in texts:
        assert load_osprey_yaml(text) == (yaml.safe_load(text) or {}), text


@pytest.mark.xfail(
    strict=True,
    reason=(
        "harness/render.py is the owner's file and still calls yaml.safe_load: wiring "
        "schemas.deployment.load_osprey_yaml in is the diff the slice's report hands over. "
        "When it lands this passes, the strict xfail fails, and this marker comes off."
    ),
)
def test_render_load_config_refuses_yes(tmp_path: Path) -> None:
    from harness.render import load_config

    path = tmp_path / "osprey.yaml"
    path.write_text(_file("yes"), encoding="utf-8")
    with pytest.raises(ValidationError, match=r"pages\.enabled must be true or false"):
        load_config(path)


@pytest.mark.parametrize(
    "raw",
    [
        {"pages": {"enabled": False, "tree": "govuk"}},
        {"pages": {"enabled": True, "port": 8090}},
        {"pages": {"enable": True}},
        {"page": {"enabled": True}},
        {"bogus": 1},
    ],
)
def test_an_unknown_sibling_still_fails(raw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OspreyConfig.model_validate(raw)


def test_nothing_reads_the_setting_yet() -> None:
    """The renderers are PL7a2's: until they read it, no file in `harness/` names the setting,
    so a render cannot differ."""
    for path in sorted((CORE / "harness").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert ".pages.enabled" not in text and "config.pages" not in text, path.name
