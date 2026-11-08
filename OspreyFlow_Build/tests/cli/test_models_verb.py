"""`ospreyflow models` (`06_DECISIONS.md` ADR-135 decision 3, Amendment 2 decision 8): the engines,
each role's default and each key's state; `models key <name>` sets or rotates a key; `models
remove-key <name>` removes it — through the Conduit's own key path inside its container, so the
gateway, the models file and the audit are *Admin › Models*' own. Nothing is restarted.

What a mistake would do, and the case that catches it (rule 12):
- a key printed, or passed on a command line where `ps` shows it —
  `test_models_lists_engines_defaults_and_states_and_never_a_key`,
  `test_models_key_hands_the_key_over_by_name_and_restarts_nothing`;
- `deployment.env` written, or a service restarted —
  `test_models_key_hands_the_key_over_by_name_and_restarts_nothing`;
- the key asked for where everyone can see it — `test_with_no_key_in_the_terminal_it_is_asked_
  for_hidden`;
- a key sent for an engine the deployment does not enable — `test_an_unknown_provider_is_refused_
  in_words`;
- `remove-key` not reaching the gateway — `test_remove_key_asks_the_conduit_to_remove_it`;
- an engine added in *Admin › Models* unknown to the command — `test_an_engine_added_in_admin_is_
  listed_and_takes_a_key`;
- a key lost after a restore shown as present — `test_a_lost_key_is_shown_lost`;
- the command and the harness disagreeing on where a key is kept —
  `test_the_command_names_each_key_as_the_harness_does`;
- the privacy-contract mark (ADR-136) not shown, or shown without its reference —
  `test_models_shows_each_providers_privacy_contract_mark_and_its_reference`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ospreyflow.models import key_variable

from schemas.deployment import ModelsConfig

from .conftest import BASE_CONFIG, Rig

GEMINI_KEY = "AIza-gemini-NEVER-PRINTED-0123456789"
OPENAI_KEY = "sk-openai-NEVER-PRINTED"

MODELS = {
    "local_only": False,
    "sendable_handling_codes": ["P"],
    "providers": [
        {"name": "gemini", "roles": {"extraction": "gemini-2.5-flash"}},
        {"name": "openai", "label": "OpenAI", "roles": {"extraction": "gpt-4o-mini"}},
    ],
    "defaults": {"extraction": "gemini"},
}
ENV_FILE = (
    "# Generated\n"
    "OSPREY_OIDC_CLIENT_SECRET=client-secret-value\n"
    "OSPREY_MODEL_KEYS_IN_GATEWAY=yes\n"
    "OSPREY_MODEL_ENGINES=[]\n"
)
STATUS = "gemini none\nopenai set\n"
KEY_PATH = ["python", "-m", "services.api.model_keys"]


def _compose(rig: Rig) -> list[str]:
    return [
        "docker", "compose",
        "--env-file", str(rig.deployment / "deployment.env"),
        "-f", str(rig.deployment / "compose.yaml"),
    ]  # fmt: skip


def _installed(
    rig: Rig, models: dict[str, object] = MODELS, env: str = ENV_FILE, status: str = STATUS
) -> Path:
    (rig.product / "osprey.yaml").write_text(
        yaml.safe_dump({**BASE_CONFIG, "models": models}), encoding="utf-8"
    )
    rig.install_deployment()
    env_file = rig.deployment / "deployment.env"
    env_file.write_text(env, encoding="utf-8")
    env_file.chmod(0o600)
    rig.responses["status"] = [(0, status)]
    return env_file


def _every_argv_word(rig: Rig) -> str:
    return " ".join([*(w for c in rig.runner.calls for w in c.argv),
                     *(w for c in rig.captured for w in c)])  # fmt: skip


def test_models_lists_engines_defaults_and_states_and_never_a_key(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    _installed(rig)
    rig.env["OSPREY_MODEL_KEY_GEMINI"] = GEMINI_KEY  # in the terminal, not the deployment
    assert rig("models") == 0
    out = capsys.readouterr()
    text = out.out + out.err
    assert GEMINI_KEY not in text and "client-secret-value" not in text
    assert "gemini (Gemini): key present: no" in text
    assert "openai (OpenAI): key present: yes" in text
    assert "extraction: gemini" in text and "vision: local" in text
    assert rig.captured == [[*_compose(rig), "exec", "-T", "api", *KEY_PATH, "status"]]
    assert rig.runner.calls == []


def test_before_the_keys_move_presence_is_read_from_deployment_env(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    _installed(rig, env=f"OSPREY_MODEL_KEY_OPENAI={OPENAI_KEY}\n")
    rig.responses["status"] = [(1, "no such service")]
    assert rig("models") == 0
    text = capsys.readouterr().out
    assert "openai (OpenAI): key present: yes" in text and OPENAI_KEY not in text


def test_models_shows_each_providers_privacy_contract_mark_and_its_reference(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR-136 decision 1: the mark is shown, "no" by default, with the reference where there is
    one — and still never a key."""
    marked = {**MODELS, "providers": [
        {"name": "gemini", "roles": {"extraction": "gemini-2.5-flash"}},
        {"name": "openai", "label": "OpenAI", "roles": {"extraction": "gpt-4o-mini"},
         "privacy_contract": True, "contract_reference": "DPA 2026/07"},
    ]}  # fmt: skip
    _installed(rig, marked)
    assert rig("models") == 0
    text = capsys.readouterr().out
    assert "gemini (Gemini): key present: no; privacy contract: no" in text
    assert "openai (OpenAI): key present: yes; privacy contract: yes (DPA 2026/07)" in text


def test_models_key_hands_the_key_over_by_name_and_restarts_nothing(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = _installed(rig)
    rig.env["OSPREY_MODEL_KEY_GEMINI"] = GEMINI_KEY
    assert rig("models", "key", "gemini") == 0
    assert env_file.read_text(encoding="utf-8") == ENV_FILE  # nothing written here
    (call,) = rig.runner.calls
    assert call.argv[: len(_compose(rig))] == _compose(rig)
    assert call.argv[len(_compose(rig)) :][:5] == [
        "exec",
        "-T",
        "-e",
        "OSPREY_MODEL_KEY_GIVEN",
        "api",
    ]
    assert call.argv[-4:-2] == ["set", "gemini"] and call.argv[-2] == "--by"
    assert call.argv[-1].startswith("cli:")
    # By name, from the Docker client's environment: never on the command line.
    assert dict(call.env or {})["OSPREY_MODEL_KEY_GIVEN"] == GEMINI_KEY
    assert GEMINI_KEY not in _every_argv_word(rig)
    assert not any("up" in c.argv for c in rig.runner.calls)
    out = capsys.readouterr()
    assert GEMINI_KEY not in out.out + out.err
    assert "The key for Gemini is set" in out.out


def test_with_no_key_in_the_terminal_it_is_asked_for_hidden(rig: Rig) -> None:
    _installed(rig)
    rig.secret_replies.append(GEMINI_KEY)
    assert rig("models", "key", "gemini") == 0
    assert rig.secret_prompts == ["Key for Gemini (OSPREY_MODEL_KEY_GEMINI; not shown): "]
    assert rig.questions == []  # never through the ordinary, visible prompt
    assert dict(rig.runner.calls[0].env or {})["OSPREY_MODEL_KEY_GIVEN"] == GEMINI_KEY


def test_an_empty_key_is_refused_and_nothing_is_sent(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    _installed(rig)
    rig.secret_replies.append("   ")
    assert rig("models", "key", "gemini") == 1
    assert "No key was given" in capsys.readouterr().err
    assert rig.runner.calls == []


def test_an_unknown_provider_is_refused_in_words(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    _installed(rig)
    rig.env["OSPREY_MODEL_KEY_ANTHROPIC"] = "sk-ant"
    assert rig("models", "key", "anthropic") == 1
    err = capsys.readouterr().err
    assert "anthropic is not a provider this deployment enables" in err
    assert "gemini, openai" in err
    assert rig("models", "remove-key", "local") == 1
    assert rig.runner.calls == []


def test_remove_key_asks_the_conduit_to_remove_it(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    _installed(rig)
    assert rig("models", "remove-key", "openai") == 0
    (call,) = rig.runner.calls
    assert call.argv[len(_compose(rig)) :][:3] == ["exec", "-T", "api"]
    assert call.argv[-4:-2] == ["remove", "openai"]
    assert "not offered to analysts" in capsys.readouterr().out
    # Removing a key that is not there changes nothing and runs nothing.
    assert rig("models", "remove-key", "gemini") == 0
    assert len(rig.runner.calls) == 1


def test_an_engine_added_in_admin_is_listed_and_takes_a_key(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    _installed(rig, status=STATUS + "mistral none\n")
    assert rig("models") == 0
    assert "mistral: added in Admin › Models; key present: no" in capsys.readouterr().out
    rig.env["OSPREY_MODEL_KEY_MISTRAL"] = "mk-123"
    assert rig("models", "key", "mistral") == 0
    assert rig.runner.calls[-1].argv[-4:-2] == ["set", "mistral"]


def test_a_lost_key_is_shown_lost(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    _installed(rig, status="gemini lost\nopenai set\n")
    assert rig("models") == 0
    assert "gemini (Gemini): key present: lost: enter it again" in capsys.readouterr().out


def test_nothing_installed_is_refused_in_words(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("models") == 1
    assert "Nothing is installed here yet" in capsys.readouterr().err


@pytest.mark.parametrize(
    "models",
    [
        MODELS,
        {"local_only": False, "provider": {"name": "openai", "roles": {"extraction": "m"}}},
        {"local_only": False, "providers": [{"name": "azure_eu", "roles": {"extraction": "m"}}]},
    ],
)
def test_the_command_names_each_key_as_the_harness_does(models: dict[str, object]) -> None:
    """The command runs outside the checkout's environment and cannot import `schemas`; this holds
    its own rule to the harness's (`ModelsConfig.key_variable`)."""
    config = ModelsConfig.model_validate(models)
    for provider in config.enabled_providers:
        assert key_variable(models, provider.name) == config.key_variable(provider.name)
