"""The local engine on an NVIDIA GPU (`06_DECISIONS.md` ADR-135 Amendment 1): `resources.gpu` in
`osprey.yaml`, and what the render does with it.

What a mistake would do, and the case that catches it:
- a GPU accepted for a cloud's server, which ADR-114 sizes without one —
  `test_a_gpu_is_refused_in_words_for_a_cloud`;
- a GPU refused on Lite, which may set it on a Linux computer, because `resources` is otherwise
  Small's alone — `test_a_gpu_is_taken_on_lite_and_on_a_small_of_your_own`;
- a misspelt GPU silently meaning none — `test_a_gpu_other_than_nvidia_is_refused`;
- the GPU given to a service other than `ollama`, or to none —
  `test_with_nvidia_the_ollama_service_alone_reserves_every_gpu`;
- the 14b default overriding a model the administrator named, or reaching a deployment without a
  GPU — `test_the_extraction_model_is_the_14b_on_a_gpu_unless_one_is_named`;
- the pull, the routing table and the Conduit's model disagreeing on a GPU, so the Conduit asks for
  a model nobody pulled — `test_the_pull_the_route_and_the_conduit_all_take_the_14b_on_a_gpu`,
  and the same through `start --build`'s own update of them,
  `test_start_build_brings_the_14b_to_a_gpu_deployment`;
- a deployment without a GPU rendered differently from before —
  `test_gpu_none_renders_byte_for_byte_as_no_setting`;
- the 14b at 32k context left 15%/85% split between CPU and GPU because its KV cache is held at
  full precision (measured on the first server, 4 November 2026: 18 GB, 9–11 s an answer, against
  14 GB, 100% GPU, 3.3–3.6 s with the two settings) —
  `test_on_a_gpu_the_model_server_quantises_its_kv_cache_with_flash_attention`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.render import render, render_litellm_config, render_ollama_pull_script
from pydantic import ValidationError

from schemas.deployment import EXTRACTION_MODELS, OspreyConfig

OWN_SERVER: dict[str, Any] = {
    "profile": "small",
    "network": {"public_origin": "https://osprey.example.internal"},
}
CLOUD_SMALL: dict[str, Any] = {
    "profile": "small",
    "network": {"public_origin": "https://osprey.example.org"},
    "external": {"postgres": {"host": "db.example.org"}},
}
CLUSTER: dict[str, Any] = {
    "profile": "cluster",
    "network": {"public_origin": "https://osprey.example.org"},
    "components": {"storage": {"ingest": "/srv/ingest", "tiles": "/srv/tiles"}},
    "cluster": {"shared_storage_class": "efs-sc"},
    "external": {
        "postgres": {"host": "db.example.org"},
        "valkey": {"host": "cache.example.org"},
        "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2"},
    },
}


def _with_gpu(raw: dict[str, Any], gpu: str = "nvidia") -> OspreyConfig:
    return OspreyConfig.model_validate({**raw, "resources": {"gpu": gpu}})


def test_no_gpu_is_the_default() -> None:
    assert OspreyConfig().resources.gpu == "none"
    assert OspreyConfig.model_validate(CLUSTER).resources.gpu == "none"


def test_a_gpu_is_taken_on_lite_and_on_a_small_of_your_own() -> None:
    assert _with_gpu({}).resources.gpu == "nvidia"
    assert _with_gpu(OWN_SERVER).resources.gpu == "nvidia"
    # It sizes nothing, so it is not "the stores sized to the server" that Lite is refused.
    assert not _with_gpu({}).resources.any


@pytest.mark.parametrize("raw", [CLOUD_SMALL, CLUSTER], ids=["small-in-a-cloud", "enterprise"])
def test_a_gpu_is_refused_in_words_for_a_cloud(raw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError) as refused:
        _with_gpu(raw)
    said = str(refused.value)
    assert "resources.gpu" in said
    assert "without a GPU" in said


def test_a_gpu_other_than_nvidia_is_refused() -> None:
    # Refused as a value of the field, not as a key the schema does not know.
    with pytest.raises(ValidationError, match="'none' or 'nvidia'"):
        _with_gpu({}, "amd")


# ---- unit 2: the render --------------------------------------------------------------------------

NVIDIA_RESERVATION = {
    "resources": {
        "reservations": {"devices": [{"driver": "nvidia", "count": "all", "capabilities": ["gpu"]}]}
    }
}


def _artefacts(config: OspreyConfig) -> dict[str, str]:
    return render(config, resolver=lambda _image: "sha256:" + "0" * 64).artefacts


def _services(config: OspreyConfig) -> dict[str, Any]:
    return yaml.safe_load(_artefacts(config)["compose.yaml"])["services"]


@pytest.mark.parametrize("raw", [{}, OWN_SERVER], ids=["lite", "small-of-your-own"])
def test_with_nvidia_the_ollama_service_alone_reserves_every_gpu(raw: dict[str, Any]) -> None:
    services = _services(_with_gpu(raw))
    assert services["ollama"]["deploy"] == NVIDIA_RESERVATION
    # Not the step that downloads the weights, nor any other service.
    assert [name for name, service in services.items() if "deploy" in service] == ["ollama"]
    without = _services(OspreyConfig.model_validate(raw))
    assert not any("deploy" in service for service in without.values())


def test_on_a_gpu_the_model_server_quantises_its_kv_cache_with_flash_attention() -> None:
    """ADR-135 Amendment 1, as measured 4 November 2026: on the GPU the `ollama` server keeps the
    KV cache at q8_0 with flash attention (which q8_0 needs), and so fits the 14b at 32k context on
    a 16 GB card. Without a GPU its environment is what it was; `ollama-models` never has them."""
    for raw in ({}, OWN_SERVER):
        services = _services(_with_gpu(raw))
        assert services["ollama"]["environment"] == {
            "OLLAMA_NOPRUNE": "1",
            "OLLAMA_FLASH_ATTENTION": "1",
            "OLLAMA_KV_CACHE_TYPE": "q8_0",
        }
        assert "environment" not in services["ollama-models"]
        without = _services(OspreyConfig.model_validate(raw))
        assert without["ollama"]["environment"] == {"OLLAMA_NOPRUNE": "1"}


def _named(extraction: str, gpu: str = "nvidia") -> OspreyConfig:
    """As `osprey.yaml` is read: from the file's own text, so "named" is what the file says."""
    return OspreyConfig.model_validate(
        yaml.safe_load(f"models:\n  extraction: {extraction}\nresources:\n  gpu: {gpu}\n")
    )


def test_the_extraction_model_is_the_14b_on_a_gpu_unless_one_is_named() -> None:
    assert OspreyConfig().extraction_model == "qwen2.5:7b-instruct"
    assert _with_gpu({}).extraction_model == "qwen2.5:14b-instruct"
    # Named, it always wins — the 7b on a GPU, and the 14b without one.
    assert _named("qwen2.5:7b-instruct").extraction_model == "qwen2.5:7b-instruct"
    assert _named("qwen2.5:14b-instruct", "none").extraction_model == "qwen2.5:14b-instruct"


def test_the_pull_the_route_and_the_conduit_all_take_the_14b_on_a_gpu() -> None:
    for config, model in (
        (_with_gpu({}), "qwen2.5:14b-instruct"),
        (OspreyConfig(), "qwen2.5:7b-instruct"),
        (_named("qwen2.5:7b-instruct"), "qwen2.5:7b-instruct"),
    ):
        assert f"pull_and_verify {model} {EXTRACTION_MODELS[model]}\n" in (
            render_ollama_pull_script(config)
        )
        assert f"pull_and_verify {model} " in _services(config)["ollama-models"]["command"][0]
        routes = {
            entry["model_name"]: entry["litellm_params"]
            for entry in yaml.safe_load(render_litellm_config(config))["model_list"]
        }
        assert routes[model]["model"] == f"ollama_chat/{model}"
        assert routes[model]["num_ctx"] == 32768
        other = ({"qwen2.5:7b-instruct", "qwen2.5:14b-instruct"} - {model}).pop()
        assert other not in routes
        assert f"OSPREY_EXTRACTION_MODEL={model}\n" in _artefacts(config)["deployment.env"]


def test_gpu_none_renders_byte_for_byte_as_no_setting() -> None:
    for raw in ({}, OWN_SERVER):
        unset = _artefacts(OspreyConfig.model_validate(raw))
        none = _artefacts(_with_gpu(raw, "none"))
        assert none == unset


def test_start_build_brings_the_14b_to_a_gpu_deployment(tmp_path: Path) -> None:
    """`ospreyflow start --build` updates the model parts of the rendered files from the rendered
    `osprey.yaml` (`scripts/refresh.py`); on a GPU, with no model named, they take the 14b."""
    from scripts import refresh

    rendered = _artefacts(OspreyConfig())
    for name in ("compose.yaml", "deployment.env"):
        (tmp_path / name).write_text(rendered[name], encoding="utf-8")
    (tmp_path / "litellm.yaml").write_text(render_litellm_config(OspreyConfig()), encoding="utf-8")
    (tmp_path / "osprey.yaml").write_text("resources:\n  gpu: nvidia\n", encoding="utf-8")
    assert refresh._models_up_to_date(tmp_path)  # the routing table changed
    env = (tmp_path / "deployment.env").read_text(encoding="utf-8")
    assert "OSPREY_EXTRACTION_MODEL=qwen2.5:14b-instruct\n" in env
    services = yaml.safe_load((tmp_path / "compose.yaml").read_text(encoding="utf-8"))["services"]
    assert "pull_and_verify qwen2.5:14b-instruct " in services["ollama-models"]["command"][0]
    assert "qwen2.5:14b-instruct" in (tmp_path / "litellm.yaml").read_text(encoding="utf-8")
