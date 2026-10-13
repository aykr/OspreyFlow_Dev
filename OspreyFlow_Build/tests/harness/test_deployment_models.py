"""ADR-095: a deployment's models are its own, chosen on the Models screen, never the conformance
ones. What a mistake would do, and the case that catches it:

- an extraction model nobody pinned reaching a deployment (`test_a_model_off_the_list_is_refused`);
- the product shipping with the 0.5B test model again (`test_the_shipped_default_is_the_7b`);
- the choice written to `osprey.yaml` but not pulled, routed or told to the Conduit
  (`test_the_render_pulls_routes_and_names_the_chosen_model`), or its context left at Ollama's
  small default, so a long email is cut inside the model where nobody sees it;
- the developer stack made to download the deployment's model
  (`..._is_the_developer_stacks_plus_one_line`);
- a service passing a conformance model to analysts' work again
  (`test_no_service_uses_a_conformance_model`).
"""

from __future__ import annotations

import re

import pytest
import yaml
from harness.render import (
    _OLLAMA_PULL_SCRIPT,
    render,
    render_litellm_config,
    render_ollama_pull_script,
)
from pydantic import ValidationError

from schemas.deployment import EXTRACTION_MODELS, ModelsConfig, OspreyConfig
from tools.layout import CORE


def test_the_shipped_default_is_the_7b() -> None:
    models = ModelsConfig()
    assert models.extraction == "qwen2.5:7b-instruct"
    assert models.vision == "moondream:1.8b-v2-q4_K_M"
    assert models.transcription == "Systran/faster-whisper-tiny.en"
    assert EXTRACTION_MODELS["qwen2.5:7b-instruct"] == "845dbda0ea48"
    assert EXTRACTION_MODELS["qwen2.5:14b-instruct"] == "7cdf5a0187d5"


@pytest.mark.parametrize("name", ["qwen2.5:0.5b-instruct", "llama3.1:8b", "anything"])
def test_a_model_off_the_list_is_refused(name: str) -> None:
    with pytest.raises(ValidationError):
        ModelsConfig(extraction=name)  # type: ignore[arg-type]


def _chosen(name: str = "qwen2.5:14b-instruct") -> OspreyConfig:
    return OspreyConfig(models=ModelsConfig(extraction=name))  # type: ignore[arg-type]


def test_the_render_pulls_routes_and_names_the_chosen_model() -> None:
    config = _chosen()
    rendered = render(config, allow_unpinned=True).artefacts
    compose = yaml.safe_load(rendered["compose.yaml"])
    assert (
        "pull_and_verify qwen2.5:14b-instruct 7cdf5a0187d5\n"
        in compose["services"]["ollama-models"]["command"][0]
    )
    routes = {
        m["model_name"]: m["litellm_params"]
        for m in yaml.safe_load(render_litellm_config(config))["model_list"]
    }
    assert routes["qwen2.5:14b-instruct"]["model"] == "ollama_chat/qwen2.5:14b-instruct"
    assert routes["qwen2.5:14b-instruct"]["num_ctx"] == 32768
    env = rendered["deployment.env"]
    assert "OSPREY_EXTRACTION_MODEL=qwen2.5:14b-instruct" in env
    assert "OSPREY_VISION_MODEL=moondream:1.8b-v2-q4_K_M" in env
    assert "OSPREY_TRANSCRIPTION_MODEL=Systran/faster-whisper-tiny.en" in env
    assert "OSPREY_EMBEDDING_MODEL=all-minilm:22m-l6-v2-fp16" in env


def test_the_rendered_pull_is_the_developer_stacks_plus_one_line() -> None:
    """The developer stack and CI keep pulling the small pinned models only (ADR-020); a
    deployment adds exactly its own extraction model, verified the same way."""
    script = render_ollama_pull_script(_chosen("qwen2.5:7b-instruct"))
    assert (
        script.replace("pull_and_verify qwen2.5:7b-instruct 845dbda0ea48\n", "")
        == _OLLAMA_PULL_SCRIPT
    )
    assert script.index("qwen2.5:7b-instruct") < script.index("wait\n")


_CONFORMANCE_NAMES = re.compile(
    r"\bCONFORMANCE_(?:MODEL|VISION_MODEL|TRANSCRIBE_MODEL|EMBED_MODEL)\b"
)


def test_no_service_uses_a_conformance_model() -> None:
    """`adapters/model_litellm`'s own rule: a conformance name is never a caller's outside the
    conformance suite. Shown red against `services/api/app.py` before ADR-095."""
    offenders = [
        p.relative_to(CORE).as_posix()
        for p in sorted((CORE / "services").rglob("*.py"))
        if _CONFORMANCE_NAMES.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_the_choices_and_their_pins_are_one_list() -> None:
    """A model offered on the Models screen without a pin could not be verified, and a pin with no
    choice is dead weight: the type and the table must agree."""
    from typing import get_args

    from schemas.deployment import (
        EMBEDDING_MODELS,
        TRANSCRIPTION_MODELS,
        VISION_MODELS,
        EmbeddingModel,
        ExtractionModel,
        TranscriptionModel,
        VisionModel,
    )

    assert set(get_args(ExtractionModel)) == set(EXTRACTION_MODELS)
    assert set(get_args(VisionModel)) == set(VISION_MODELS)
    assert set(get_args(TranscriptionModel)) == set(TRANSCRIPTION_MODELS)
    assert set(get_args(EmbeddingModel)) == set(EMBEDDING_MODELS)
