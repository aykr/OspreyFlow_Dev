"""The extraction-engine setting (`06_DECISIONS.md` ADR-135 Amendments 5 and 6; P12 part 2, the
orchestrator's rulings of 11 November): `models.extraction_engine`, `deep_read` or `laurium`.

- **Left unset, the profile's preset**: `laurium` on `cloud-platform` (ADR-135 Amendment 5
  decision 2, the owner's: "the `cloud-platform` profile's pack presets Laurium"; read as this
  profile default, Amendment 9, a rule 11 gap closed) and `deep_read` on every other profile.
  Naming `deep_read` opts out.
- **`laurium` on the `cloud-platform` profile alone**, as P11's engine kinds are (Amendment 7
  decision 1): on every other profile it is refused in words naming the profile; its cluster
  translation (`ENGINES_AS`) carries it, so the render does not refuse what it renders.
- **Any other value refused**, never read as the default.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from tools.cp_policy_check import FIXTURES

from schemas.deployment import ENGINES_AS, OspreyConfig
from tests.harness.test_cluster_render import cluster_config
from tests.services.api.test_model_engines import _config as engines_config

CLOUD = "cloud-platform"


def _cloud_raw() -> dict[str, Any]:
    """The cloud-platform fixture with the engine left unset (the fixture itself names
    `deep_read`, so platform's tests keep their meaning)."""
    raw: dict[str, Any] = yaml.safe_load((FIXTURES / "development.yaml").read_text("utf-8"))
    raw.setdefault("models", {}).pop("extraction_engine", None)
    return raw


def _raw(profile: str) -> dict[str, Any]:
    if profile == CLOUD:
        return _cloud_raw()
    base = cluster_config() if profile == "cluster" else engines_config()
    raw = base.model_dump(mode="json", exclude_none=True)
    raw["profile"] = profile
    return raw


def _with_engine(raw: dict[str, Any], engine: Any) -> dict[str, Any]:
    raw["models"] = {**raw.get("models", {}), "extraction_engine": engine}
    return raw


@pytest.mark.parametrize(
    ("profile", "preset"),
    [
        (CLOUD, "laurium"),
        ("local-lite", "deep_read"),
        ("small", "deep_read"),
        ("cluster", "deep_read"),
    ],
)
def test_left_unset_it_is_the_profiles_preset(profile: str, preset: str) -> None:
    raw = _raw(profile)
    raw.get("models", {}).pop("extraction_engine", None)
    assert OspreyConfig.model_validate(raw).models.extraction_engine == preset


def test_naming_deep_read_on_cloud_platform_opts_out() -> None:
    assert (
        OspreyConfig.model_validate(
            _with_engine(_cloud_raw(), "deep_read")
        ).models.extraction_engine
        == "deep_read"
    )


def test_a_cluster_translation_keeps_what_cloud_platform_chose() -> None:
    """The translation is validated as `profile: cluster`, where unset means `deep_read`: the
    cloud-platform choice must arrive named, not be re-derived there."""
    chosen = OspreyConfig.model_validate(_cloud_raw()).models.model_dump(mode="json")
    assert chosen["extraction_engine"] == "laurium"


def test_laurium_is_taken_on_cloud_platform() -> None:
    config = OspreyConfig.model_validate(_with_engine(_cloud_raw(), "laurium"))
    assert config.models.extraction_engine == "laurium"


@pytest.mark.parametrize("profile", ["local-lite", "small", "cluster"])
def test_laurium_is_refused_on_every_other_profile_in_words(profile: str) -> None:
    refused = r"extraction_engine: laurium is for profile: cloud-platform"
    with pytest.raises(ValidationError, match=refused):
        OspreyConfig.model_validate(_with_engine(_raw(profile), "laurium"))


def test_a_cloud_platform_cluster_translation_carries_laurium() -> None:
    """`harness.cloud_platform._as_cluster` validates its translation as `profile: cluster` with
    `ENGINES_AS`: Laurium, held to cloud-platform's rules already, is carried, not refused."""
    raw = _with_engine(_raw("cluster"), "laurium")
    assert (
        OspreyConfig.model_validate(raw, context={ENGINES_AS: CLOUD}).models.extraction_engine
        == "laurium"
    )
    with pytest.raises(ValidationError, match="profile: cloud-platform"):
        OspreyConfig.model_validate(raw, context={ENGINES_AS: "small"})


#: `None` is not among them: written out, null is the field left unset, so the profile's preset.
@pytest.mark.parametrize("value", ["Laurium", "deep-read", "", "local", 1])
def test_any_other_value_is_refused(value: Any) -> None:
    """Refused as a value outside the two, not as an unknown field (before the setting existed,
    `extra="forbid"` refused the field itself, which a bare match on its name would also take)."""
    with pytest.raises(ValidationError, match="Input should be 'deep_read' or 'laurium'"):
        OspreyConfig.model_validate(_with_engine(_cloud_raw(), value))
