"""ADR-135 decisions 1 and 2: several model engines, each with its own key.

What a mistake would do, and the case that catches it (rule 12):
- two providers sharing one key, or one provider's key read by another's entry —
  `test_two_providers_render_two_entries_each_reading_its_own_key`;
- a key written into `litellm.yaml`, `compose.yaml` or any generated file —
  `test_no_generated_file_holds_any_providers_key`;
- the Conduit given a key: its `env_file` is the whole `deployment.env`, so a key there reaches it
  unless its own environment blanks it — `test_no_service_but_the_gateway_is_given_a_key`;
- the Conduit not told which engines exist, which has a key, and each role's default —
  `test_the_conduit_is_told_the_engines_the_defaults_and_key_presence_never_a_key`;
- today's single `provider` no longer read, or read under a new key name, so an existing install
  loses its key — `test_the_single_provider_is_still_read_with_its_old_key_name`;
- both `provider` and `providers` named, a default naming an engine that is not enabled, two
  providers with one name — `test_settings_that_cannot_be_right_are_refused_in_words`;
- an enabled provider installed without its key — `test_an_enabled_provider_without_its_key_
  stops_the_install_in_words`;
- a second apply losing a key it was not given again — `test_a_second_apply_keeps_both_keys`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from harness.apply import ApplyFailed, keep_existing_secrets, provider_secret_lines
from harness.render import load_config, render, render_litellm_config
from pydantic import ValidationError
from tools.layout import CORE

from schemas.deployment import ModelProviderConfig, ModelsConfig, OspreyConfig
from tests.harness.test_render import FIXTURE_CONFIG, _fake_resolver

GEMINI_KEY = "AIza-gemini-THIS-MUST-NEVER-APPEAR"
OPENAI_KEY = "sk-openai-THIS-MUST-NEVER-APPEAR"

GEMINI = ModelProviderConfig(name="gemini", roles={"extraction": "gemini-2.5-flash"})
OPENAI = ModelProviderConfig(name="openai", roles={"extraction": "gpt-4o-mini", "vision": "gpt-4o"})
TWO = ModelsConfig(
    local_only=False,
    providers=[GEMINI, OPENAI],
    defaults={"extraction": "gemini"},
    sendable_handling_codes=["P"],
)


def _config(tmp_path: Path, models: ModelsConfig) -> OspreyConfig:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    return loaded.model_copy(
        update={
            "models": models,
            "components": loaded.components.model_copy(update={"source_path": str(CORE)}),
        }
    )


def _env_lines(text: str) -> dict[str, str]:
    return {
        name: value
        for name, _, value in (line.partition("=") for line in text.splitlines())
        if name and not name.startswith("#")
    }


# --- settings ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "words"),
    [
        (
            {"local_only": False, "provider": {"name": "gemini", "roles": {"extraction": "m"}},
             "providers": [{"name": "openai", "roles": {"extraction": "m"}}]},
            "both models.provider and models.providers",
        ),
        (
            {"local_only": False, "providers": [{"name": "gemini", "roles": {"extraction": "m"}},
                                                {"name": "gemini", "roles": {"vision": "v"}}]},
            "gemini is named twice",
        ),
        (
            {"local_only": False, "providers": [{"name": "gemini", "roles": {"extraction": "m"}}],
             "defaults": {"extraction": "openai"}},
            "not an enabled engine",
        ),
        (
            {"local_only": False, "providers": [{"name": "gemini", "roles": {"extraction": "m"}}],
             "defaults": {"vision": "gemini"}},
            "gemini takes no vision model",
        ),
        (
            {"local_only": True, "providers": [{"name": "gemini", "roles": {"extraction": "m"}}]},
            "local_only",
        ),
        (
            {"local_only": False, "providers": [{"name": "gemini", "roles": {"extraction": "m"},
                                                 "api_base": "http://insecure.example"}]},
            "https",
        ),
    ],
)  # fmt: skip
def test_settings_that_cannot_be_right_are_refused_in_words(
    fields: dict[str, object], words: str
) -> None:
    with pytest.raises(ValidationError, match=words):
        ModelsConfig.model_validate(fields)


def test_each_provider_has_a_label_analysts_see() -> None:
    assert GEMINI.label == "Gemini"
    assert OPENAI.label == "OpenAI"
    assert ModelProviderConfig(name="anthropic", roles={"extraction": "m"}).label == "Anthropic"
    named = ModelProviderConfig(name="gemini", roles={"extraction": "m"}, label="Google Gemini")
    assert named.label == "Google Gemini"


def test_the_single_provider_reads_as_a_one_entry_list_and_round_trips() -> None:
    legacy = ModelsConfig(local_only=False, provider=OPENAI, sendable_handling_codes=["P"])
    assert [p.name for p in legacy.enabled_providers] == ["openai"]
    # Its roles default to it, as Amendment 6's one provider did.
    assert legacy.role_defaults == {"extraction": "openai", "vision": "openai"}
    # The guided install dumps and re-validates the file: the one-entry form must survive that.
    again = ModelsConfig.model_validate(legacy.model_dump(mode="json", exclude_none=True))
    assert again.provider is not None and again.providers == []
    assert TWO.role_defaults == {"extraction": "gemini"}


# --- the model table and the compose file --------------------------------------------------------


def test_hosted_engines_are_not_rendered_but_held_in_the_gateway_s_database(
    tmp_path: Path,
) -> None:
    """ADR-135 Amendment 2 decision 3 (superseding ADR-135's rendered entries): the rendered table
    keeps the local models alone, the gateway stores models in its own database, and its master key
    is read from its environment, minted per deployment."""
    table = yaml.safe_load(render_litellm_config(_config(tmp_path, TWO)))
    routed = {m["model_name"] for m in table["model_list"]}
    assert "qwen2.5:7b-instruct" in routed  # the local engine stays
    assert not any(name.startswith(("gemini/", "openai/")) for name in routed)
    assert table["general_settings"] == {
        "master_key": "os.environ/LITELLM_MASTER_KEY",
        "store_model_in_db": True,
    }
    compose = yaml.safe_load(render(_config(tmp_path, TWO), resolver=_fake_resolver)
                             .artefacts["compose.yaml"])  # fmt: skip
    gateway = compose["services"]["litellm"]["environment"]
    assert (
        gateway["LITELLM_SALT_KEY"]
        == "${OSPREY_LITELLM_SALT_SECRET:?set in the deployment env file}"
    )
    assert gateway["DATABASE_URL"].startswith("postgresql://litellm:${OSPREY_LITELLM_DB_PASSWORD:")
    assert gateway["DATABASE_URL"].endswith("@postgres:5432/litellm")
    assert gateway["LITELLM_LOCAL_MODEL_COST_MAP"] == "True"
    assert compose["services"]["litellm"]["depends_on"]["litellm-db"] == {
        "condition": "service_completed_successfully"
    }


def test_no_service_but_the_gateway_is_given_a_key(tmp_path: Path) -> None:
    """Every owned service reads the whole `deployment.env` (`env_file`), where the keys are kept;
    its own environment, which Compose and Kubernetes both put above the file, blanks each one."""
    compose = yaml.safe_load(render(_config(tmp_path, TWO), resolver=_fake_resolver)
                             .artefacts["compose.yaml"])  # fmt: skip
    readers = [n for n, s in compose["services"].items() if "env_file" in s]
    assert "api" in readers and "litellm" not in readers
    for name in readers:
        environment = compose["services"][name].get("environment") or {}
        for key in ("OSPREY_MODEL_KEY_GEMINI", "OSPREY_MODEL_KEY_OPENAI"):
            assert environment.get(key) == "", (name, key)
    for name, service in compose["services"].items():
        if name == "litellm":
            continue
        for key, value in (service.get("environment") or {}).items():
            if key.startswith("OSPREY_MODEL_KEY_PRESENT_"):
                continue
            assert "OSPREY_MODEL_KEY_" not in str(value), (name, key)


def test_the_conduit_is_told_the_engines_the_defaults_and_key_presence_never_a_key(
    tmp_path: Path,
) -> None:
    rendered = render(_config(tmp_path, TWO), resolver=_fake_resolver)
    env = _env_lines(rendered.artefacts["deployment.env"])
    engines = json.loads(env["OSPREY_MODEL_ENGINES"])
    # ADR-136: each with its contract mark (none here) and no reference; ADR-135 Amendment 2: and
    # its base, since the Conduit makes the gateway's entries.
    assert engines == [
        {"name": "gemini", "label": "Gemini", "roles": {"extraction": "gemini/gemini-2.5-flash"},
         "privacy_contract": False, "contract_reference": None, "api_base": None},
        {"name": "openai", "label": "OpenAI",
         "roles": {"extraction": "openai/gpt-4o-mini", "vision": "openai/gpt-4o"},
         "privacy_contract": False, "contract_reference": None, "api_base": None},
    ]  # fmt: skip
    assert json.loads(env["OSPREY_MODEL_DEFAULTS"]) == {"extraction": "gemini"}
    assert env["OSPREY_SENDABLE_HANDLING_CODES"] == "P"
    api = yaml.safe_load(rendered.artefacts["compose.yaml"])["services"]["api"]
    environment = api["environment"]
    # Whether each key is present, resolved by Compose from the env file: "yes" or empty — read only
    # until the keys are moved into the gateway, after which the models file says.
    assert environment["OSPREY_MODEL_KEY_PRESENT_GEMINI"] == "${OSPREY_MODEL_KEY_GEMINI:+yes}"
    assert environment["OSPREY_MODEL_SETTINGS_DIR"] == "/run/osprey/model-settings"
    assert "model-settings:/run/osprey/model-settings" in api["volumes"]
    assert environment["LITELLM_API_KEY"].startswith("${OSPREY_LITELLM_MASTER_SECRET:?")


def test_no_generated_file_holds_any_providers_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OSPREY_MODEL_KEY_GEMINI", GEMINI_KEY)
    monkeypatch.setenv("OSPREY_MODEL_KEY_OPENAI", OPENAI_KEY)
    config = _config(tmp_path, TWO)
    rendered = render(config, resolver=_fake_resolver)
    for name, text in {**rendered.artefacts, "litellm.yaml": render_litellm_config(config)}.items():
        assert GEMINI_KEY not in text, name
        assert OPENAI_KEY not in text, name


def test_the_single_provider_is_still_read_with_its_old_key_name(tmp_path: Path) -> None:
    """The single provider's `OSPREY_MODEL_PROVIDER_KEY` is moved into the gateway under its name
    (ADR-135 Amendment 2 decision 3)."""
    from harness.apply import model_keys_to_move

    legacy = ModelsConfig(local_only=False, provider=OPENAI, sendable_handling_codes=["P"])
    env = render(_config(tmp_path, legacy), resolver=_fake_resolver).artefacts["deployment.env"]
    assert model_keys_to_move(env + f"OSPREY_MODEL_PROVIDER_KEY={OPENAI_KEY}\n") == {
        "openai": OPENAI_KEY
    }


def test_an_enabled_provider_without_its_key_stops_the_install_in_words(tmp_path: Path) -> None:
    config = _config(tmp_path, TWO)
    with pytest.raises(ApplyFailed, match="OSPREY_MODEL_KEY_OPENAI is not set"):
        provider_secret_lines(config, {"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY})
    both = {"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY, "OSPREY_MODEL_KEY_OPENAI": OPENAI_KEY}
    assert _env_lines(provider_secret_lines(config, both)) == both


def test_a_second_apply_keeps_both_keys(tmp_path: Path) -> None:
    """ADR-132 ruling 6, as `apply` runs it: the earlier `deployment.env` is read first; a key it
    holds is not asked for again, and the earlier value is the one kept."""
    config = _config(tmp_path, TWO)
    first = provider_secret_lines(
        config, {"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY, "OSPREY_MODEL_KEY_OPENAI": OPENAI_KEY}
    )
    previous = "OSPREY_OIDC_CLIENT_SECRET=s\n" + first
    # The second run's terminal has neither key: it does not stop, and both are kept.
    second = provider_secret_lines(config, {}, previous=previous)
    kept = _env_lines(keep_existing_secrets("X=1\n" + second, previous))
    assert kept["OSPREY_MODEL_KEY_GEMINI"] == GEMINI_KEY
    assert kept["OSPREY_MODEL_KEY_OPENAI"] == OPENAI_KEY
    # A key only the earlier file held (written by `ospreyflow models key`) is carried over too.
    carried = _env_lines(keep_existing_secrets("X=1\n", previous))
    assert carried["OSPREY_MODEL_KEY_GEMINI"] == GEMINI_KEY


def test_no_service_but_the_gateway_reads_its_encryption_key_or_database_password(
    tmp_path: Path,
) -> None:
    """ADR-135 Amendment 2 decision 3: every service reading `deployment.env` whole has the
    gateway's encryption key and database password blanked; the master key reaches the Conduit
    too."""
    compose = yaml.safe_load(render(_config(tmp_path, TWO), resolver=_fake_resolver)
                             .artefacts["compose.yaml"])  # fmt: skip
    readers = [n for n, s in compose["services"].items() if "env_file" in s]
    assert "api" in readers and "litellm" not in readers
    for name in readers:
        environment = compose["services"][name].get("environment") or {}
        assert environment.get("OSPREY_LITELLM_SALT_SECRET") == "", name
        assert environment.get("OSPREY_LITELLM_DB_PASSWORD") == "", name
        if name != "api":
            assert environment.get("OSPREY_LITELLM_MASTER_SECRET") == "", name


def test_the_gateway_s_secrets_are_minted_once_and_kept_by_every_apply() -> None:
    """A different encryption key silently drops every key the gateway holds (measured), so the
    one minted at install must survive every later render: `keep_existing_secrets` keeps it."""
    from harness.apply import _env_pairs, gateway_secret_lines, keep_existing_secrets

    first = keep_existing_secrets(gateway_secret_lines(), "")
    second = keep_existing_secrets(gateway_secret_lines(), first)
    for name in ("OSPREY_LITELLM_SALT_SECRET", "OSPREY_LITELLM_MASTER_SECRET",
                 "OSPREY_LITELLM_DB_PASSWORD"):  # fmt: skip
        assert _env_pairs(second)[name] == _env_pairs(first)[name], name
        assert _env_pairs(first)[name]
