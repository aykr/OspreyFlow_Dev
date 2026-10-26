"""ADR-127 Amendment 33: `OSPREY_POST_INGEST_RESOLUTION` (`on`, the default, or `off`) is a
deployment setting. What a mistake would do, and the case that catches it:

- the setting read wrongly, or an unrecognised value taken as on, so a typo leaves the worker
  writing `SAME_AS` links onto the demo's people
  (`test_the_conduit_reads_the_setting_and_refuses_a_value_it_does_not_know`);
- `osprey.yaml` unable to say it, or saying it and the deployment's environment file not carrying it
  (`test_a_deployment_that_turns_resolution_off_renders_it_and_the_default_renders_on`);
- the run not passing the setting to the hook, so the hook's own test passes and nothing is ever off
  (`test_both_runs_of_a_recipe_pass_the_setting_to_the_hook`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from harness.render import load_config, render
from services.api.config import ApiConfig
from tools.layout import CORE

from tests.harness.test_render import FIXTURE_CONFIG, _fake_resolver


def _environment(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    monkeypatch.setenv("OIDC_JWKS_URL", "http://localhost:9/jwks")
    if value is None:
        monkeypatch.delenv("OSPREY_POST_INGEST_RESOLUTION", raising=False)
    else:
        monkeypatch.setenv("OSPREY_POST_INGEST_RESOLUTION", value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, True), ("", True), ("on", True), ("ON", True), ("off", False), (" Off ", False)],
)
def test_the_conduit_reads_the_setting_and_refuses_a_value_it_does_not_know(
    monkeypatch: pytest.MonkeyPatch, value: str | None, expected: bool
) -> None:
    _environment(monkeypatch, value)
    assert ApiConfig.from_env().post_ingest_resolution is expected


@pytest.mark.parametrize("value", ["false", "0", "no", "of", "disabled"])
def test_an_unrecognised_value_is_refused_not_taken_as_on(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _environment(monkeypatch, value)
    with pytest.raises(ValueError, match="OSPREY_POST_INGEST_RESOLUTION"):
        ApiConfig.from_env()


def _env_file(tmp_path: Path, *, off: bool | None) -> str:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    update: dict[str, object] = {"source_path": str(CORE)}
    if off is not None:
        update["post_ingest_resolution"] = not off
    config = loaded.model_copy(update={"components": loaded.components.model_copy(update=update)})
    return render(config, resolver=_fake_resolver).artefacts["deployment.env"]


def test_a_deployment_that_turns_resolution_off_renders_it_and_the_default_renders_on(
    tmp_path: Path,
) -> None:
    assert "OSPREY_POST_INGEST_RESOLUTION=off" in _env_file(tmp_path, off=True).splitlines()
    assert "OSPREY_POST_INGEST_RESOLUTION=on" in _env_file(tmp_path, off=None).splitlines()
    assert "OSPREY_POST_INGEST_RESOLUTION=on" in _env_file(tmp_path, off=False).splitlines()


def test_osprey_yaml_can_say_it(tmp_path: Path) -> None:
    path = tmp_path / "osprey.yaml"
    text = FIXTURE_CONFIG.replace(
        "components:\n", "components:\n  post_ingest_resolution: false\n", 1
    )
    path.write_text(text, encoding="utf-8")
    assert load_config(path).components.post_ingest_resolution is False
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    assert load_config(path).components.post_ingest_resolution is True


def test_both_runs_of_a_recipe_pass_the_setting_to_the_hook() -> None:
    text = (CORE / "services/api/recipe_run.py").read_text(encoding="utf-8")
    assert text.count("submit_post_ingest_resolution_jobs(") == 2
    assert text.count("enabled=deps.config.post_ingest_resolution") == 2
