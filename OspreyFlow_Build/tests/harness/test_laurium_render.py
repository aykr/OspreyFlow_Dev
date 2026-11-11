"""Laurium in the `cloud-platform` render (`06_DECISIONS.md` ADR-135 Amendments 5 and 6, P12 part 2;
the orchestrator's rulings of 11 November).

- **Not chosen** (`models.extraction_engine: deep_read`, the default and the pack's preset): nothing
  of Laurium in any artefact: no workload, no image to push, no policy.
- **Chosen**: its own workload from its own image (`services/laurium/Dockerfile`, pushed by
  `ospreyflow images push` from `images.yaml`), and the gateway rendered with it, since every call
  Laurium makes goes through the gateway.
- **The master key never in Laurium's pod** (decision 8): every other owned service reads the whole
  deployment Secret (`envFrom`), which holds the gateway's master key; Laurium's pod reads none of
  it. Its environment is its gateway's address alone, the gateway's in-namespace name and port.
- **No way out of the namespace**: Laurium's pod carries no egress label.

The policies that hold its traffic to the gateway are read from Helm's own output in
`tests/harness/test_laurium_network_policy.py` (it needs Docker).
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from harness.render import load_config, render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig

GATEWAY_URL = "http://litellm:4000/v1"


def _config(name: str, engine: str | None) -> OspreyConfig:
    raw: dict[str, Any] = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text("utf-8"))
    if engine is not None:
        raw["models"] = {**raw.get("models", {}), "extraction_engine": engine}
    return OspreyConfig.model_validate(raw)


def _artefacts(config: OspreyConfig) -> dict[str, str]:
    return render(config, resolver=_resolver).artefacts


def _workloads(artefacts: dict[str, str]) -> dict[str, dict[str, Any]]:
    values = yaml.safe_load(artefacts["values.yaml"])
    return {w["name"]: w for w in values["workloads"]}


FIXTURE_NAMES = ["development", "production"]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
@pytest.mark.parametrize("engine", [None, "deep_read"])
def test_nothing_of_laurium_is_rendered_unless_chosen(name: str, engine: str | None) -> None:
    artefacts = _artefacts(_config(name, engine))
    for path, text in artefacts.items():
        assert "laurium" not in text.lower(), f"{path} names Laurium, which was not chosen"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_laurium_chosen_renders_its_workload_its_image_and_the_gateway(name: str) -> None:
    artefacts = _artefacts(_config(name, "laurium"))
    workloads = _workloads(artefacts)
    assert "laurium" in workloads
    assert "litellm" in workloads, "Laurium is chosen but its gateway is not rendered"
    pushed = yaml.safe_load(artefacts["images.yaml"])["images"]
    assert any("laurium" in str(image) for image in pushed), "Laurium's image is not pushed"
    assert workloads["laurium"]["image"].split("/")[-1].startswith("laurium")


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_lauriums_pod_reads_no_secret_and_only_its_gateway(name: str) -> None:
    """Decision 8: the master key never crosses into Laurium's container. Every owned service but
    Laurium reads the deployment's whole Secret (`envFrom`), the gateway's master key with it."""
    artefacts = _artefacts(_config(name, "laurium"))
    laurium = _workloads(artefacts)["laurium"]
    assert not laurium.get("envFrom"), "Laurium's pod reads the deployment's Secret"
    assert "initContainers" not in laurium
    env = {e["name"]: e.get("value") for e in laurium.get("env", [])}
    assert env == {"OSPREY_LAURIUM_GATEWAY_URL": GATEWAY_URL}
    assert not any("valueFrom" in e for e in laurium.get("env", []))
    values = yaml.safe_load(artefacts["values.yaml"])
    # The Secret Laurium's pod does not read holds the gateway's master key.
    assert "OSPREY_LITELLM_MASTER_SECRET" in values["secrets"]["keys"]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_lauriums_pod_has_no_way_out_and_its_resources_named(name: str) -> None:
    laurium = _workloads(_artefacts(_config(name, "laurium")))["laurium"]
    assert not laurium.get("egress"), "Laurium's pod is labelled to leave the namespace"
    assert not laurium.get("public")
    resources = laurium.get("resources") or {}
    assert resources.get("limits", {}).get("memory"), "Laurium's memory is not limited"


@pytest.mark.parametrize("profile_fixture", ["lite", "small"])
def test_every_other_profile_is_unchanged(profile_fixture: str) -> None:
    """Laurium is refused off cloud-platform (`test_extraction_engine_setting.py`); a deployment
    that names `deep_read` renders exactly what one that names nothing does."""
    from tests.services.api.test_model_engines import _config as engines_config

    base = engines_config()
    raw = base.model_dump(mode="json", exclude_none=True)
    raw["profile"] = "local-lite" if profile_fixture == "lite" else "small"
    if raw["profile"] == "small":
        raw["network"] = {**raw.get("network", {}), "public_origin": "https://osprey.example.org"}
    plain = OspreyConfig.model_validate(raw)
    named = OspreyConfig.model_validate(
        {**raw, "models": {**raw.get("models", {}), "extraction_engine": "deep_read"}}
    )
    assert _artefacts(plain) == _artefacts(named)


def test_the_fixture_loader_is_the_renders_own() -> None:
    assert load_config(FIXTURES / "development.yaml").models.extraction_engine == "deep_read"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_the_conduit_is_told_the_choice_and_lauriums_address(name: str) -> None:
    """The Conduit reads the choice from its environment (`adapters.extract_laurium.composed`):
    the engine and Laurium's address inside the deployment, and nothing that is a key."""
    values = yaml.safe_load(_artefacts(_config(name, "laurium"))["values.yaml"])
    environment = values["environment"]
    assert environment["OSPREY_EXTRACTION_ENGINE"] == "laurium"
    assert environment["OSPREY_LAURIUM_URL"] == "http://laurium:8000"
