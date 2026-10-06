"""ADR-095 decision 1: the system administrator chooses the deployment's models on the setup
harness's Models screen, from the list of pinned models, the shipped default chosen to begin with.
What a mistake would do, and the case that catches it: the screen offering a model with no pin, or
a second hand-kept list drifting from the config's (`test_the_choices_are_the_configs_own_list`);
a model off the list saved (`test_a_model_off_the_list_is_not_saved`); the choice not reaching
`osprey.yaml` (`test_a_chosen_model_is_saved`); the route open in console mode (the boundary
`test_webapp_mode.py` holds for every setup route)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from harness.webapp import create_app

from schemas.deployment import (
    EMBEDDING_MODELS,
    EXTRACTION_MODELS,
    TRANSCRIPTION_MODELS,
    VISION_MODELS,
)


def _client(tmp_path: Path, mode: str = "setup") -> TestClient:
    return TestClient(
        create_app(config_path=tmp_path / "osprey.yaml", mode=mode), client=("127.0.0.1", 51000)
    )


def test_the_choices_are_the_configs_own_list(tmp_path: Path) -> None:
    choices = _client(tmp_path).get("/api/model-choices").json()
    assert [c["name"] for c in choices["extraction"]] == list(EXTRACTION_MODELS)
    assert [c["name"] for c in choices["vision"]] == list(VISION_MODELS)
    assert [c["name"] for c in choices["transcription"]] == list(TRANSCRIPTION_MODELS)
    assert [c["name"] for c in choices["embedding"]] == list(EMBEDDING_MODELS)
    assert choices["defaults"]["extraction"] == "qwen2.5:7b-instruct"


def test_a_chosen_model_is_saved(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.put("/api/config", json={"profile": "local-lite"})
    saved = client.put("/api/config", json={"models": {"extraction": "qwen2.5:14b-instruct"}})
    assert saved.status_code == 200, saved.text
    written = yaml.safe_load((tmp_path / "osprey.yaml").read_text())
    assert written["models"]["extraction"] == "qwen2.5:14b-instruct"


def test_a_model_off_the_list_is_not_saved(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.put("/api/config", json={"profile": "local-lite"})
    refused = client.put("/api/config", json={"models": {"extraction": "qwen2.5:0.5b-instruct"}})
    assert refused.status_code == 422


def test_console_mode_does_not_serve_the_choices(tmp_path: Path) -> None:
    assert _client(tmp_path, mode="console").get("/api/model-choices").status_code == 404
