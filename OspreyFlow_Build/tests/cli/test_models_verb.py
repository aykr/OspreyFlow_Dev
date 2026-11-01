"""`ospreyflow models` (`06_DECISIONS.md` ADR-135 decision 3): the engines, each role's default and
whether each key is present; `models key <name>` sets or rotates a key; `models remove-key <name>`
removes it. A key is never printed, never on a command line, and written to `deployment.env` alone.

What a mistake would do, and the case that catches it (rule 12):
- a key printed, or passed on a command line where `ps` shows it —
  `test_models_lists_engines_defaults_and_presence_and_never_a_key`,
  `test_models_key_writes_only_that_line_and_restarts_only_the_gateway_and_the_conduit`;
- another line of `deployment.env` changed, or the file's mode loosened —
  `test_models_key_writes_only_that_line_and_restarts_only_the_gateway_and_the_conduit`;
- a rotation leaving the old key beside the new — `test_a_rotated_key_replaces_the_line`;
- the key asked for where everyone can see it — `test_with_no_key_in_the_terminal_it_is_asked_
  for_hidden`;
- a key set for a provider the deployment does not enable — `test_an_unknown_provider_is_refused_
  in_words`;
- `remove-key` leaving the key, or restarting nothing — `test_remove_key_removes_the_line`;
- the command and the harness disagreeing on where a key is kept —
  `test_the_command_names_each_key_as_the_harness_does`.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
import yaml
from ospreyflow.models import key_variable

from schemas.deployment import ModelsConfig

from .conftest import BASE_CONFIG, Rig

GEMINI_KEY = "AIza-gemini-NEVER-PRINTED-0123456789"
OLD_KEY = "AIza-old-gemini-key-NEVER-PRINTED"
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
    f"OSPREY_MODEL_KEY_OPENAI={OPENAI_KEY}\n"
    "OSPREY_MODEL_ENGINES=[]\n"
)


def _compose(rig: Rig) -> list[str]:
    return [
        "docker", "compose",
        "--env-file", str(rig.deployment / "deployment.env"),
        "-f", str(rig.deployment / "compose.yaml"),
    ]  # fmt: skip


def _installed(rig: Rig, models: dict[str, object] = MODELS, env: str = ENV_FILE) -> Path:
    (rig.product / "osprey.yaml").write_text(
        yaml.safe_dump({**BASE_CONFIG, "models": models}), encoding="utf-8"
    )
    rig.install_deployment()
    env_file = rig.deployment / "deployment.env"
    env_file.write_text(env, encoding="utf-8")
    env_file.chmod(0o600)
    return env_file


def _every_word_the_runner_saw(rig: Rig) -> str:
    return " ".join(
        [*(w for c in rig.runner.calls for w in c.argv),
         *(f"{k}={v}" for c in rig.runner.calls for k, v in (c.env or {}).items())]
    )  # fmt: skip


def test_models_lists_engines_defaults_and_presence_and_never_a_key(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    _installed(rig)
    rig.env["OSPREY_MODEL_KEY_GEMINI"] = GEMINI_KEY  # in the terminal, not the deployment
    assert rig("models") == 0
    out = capsys.readouterr()
    text = out.out + out.err
    assert OPENAI_KEY not in text and GEMINI_KEY not in text and "client-secret-value" not in text
    assert "gemini (Gemini): key present: no" in text
    assert "openai (OpenAI): key present: yes" in text
    assert "extraction: gemini" in text and "vision: local" in text
    assert rig.runner.calls == []


def test_models_key_writes_only_that_line_and_restarts_only_the_gateway_and_the_conduit(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = _installed(rig)
    rig.env["OSPREY_MODEL_KEY_GEMINI"] = GEMINI_KEY
    assert rig("models", "key", "gemini") == 0
    written = env_file.read_text(encoding="utf-8")
    assert written == ENV_FILE + f"OSPREY_MODEL_KEY_GEMINI={GEMINI_KEY}\n"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    # The gateway reads the key; the Conduit is told whether it is present. Nothing else.
    assert rig.runner.argvs() == [
        [*_compose(rig), "up", "-d", "--no-deps", "--wait", "litellm", "api"]
    ]
    assert GEMINI_KEY not in _every_word_the_runner_saw(rig)
    out = capsys.readouterr()
    assert GEMINI_KEY not in out.out + out.err
    assert "The key for Gemini is set" in out.out


def test_a_rotated_key_replaces_the_line(rig: Rig) -> None:
    env_file = _installed(rig, env=ENV_FILE + f"OSPREY_MODEL_KEY_GEMINI={OLD_KEY}\nAFTER=1\n")
    rig.env["OSPREY_MODEL_KEY_GEMINI"] = GEMINI_KEY
    assert rig("models", "key", "gemini") == 0
    written = env_file.read_text(encoding="utf-8")
    assert OLD_KEY not in written
    assert written == ENV_FILE + f"OSPREY_MODEL_KEY_GEMINI={GEMINI_KEY}\nAFTER=1\n"


def test_with_no_key_in_the_terminal_it_is_asked_for_hidden(rig: Rig) -> None:
    env_file = _installed(rig)
    rig.secret_replies.append(GEMINI_KEY)
    assert rig("models", "key", "gemini") == 0
    assert rig.secret_prompts == ["Key for Gemini (OSPREY_MODEL_KEY_GEMINI; not shown): "]
    assert rig.questions == []  # never through the ordinary, visible prompt
    assert f"OSPREY_MODEL_KEY_GEMINI={GEMINI_KEY}\n" in env_file.read_text(encoding="utf-8")


def test_an_empty_key_is_refused_and_nothing_is_written(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = _installed(rig)
    rig.secret_replies.append("   ")
    assert rig("models", "key", "gemini") == 1
    assert "No key was given" in capsys.readouterr().err
    assert env_file.read_text(encoding="utf-8") == ENV_FILE
    assert rig.runner.calls == []


def test_an_unknown_provider_is_refused_in_words(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = _installed(rig)
    rig.env["OSPREY_MODEL_KEY_ANTHROPIC"] = "sk-ant"
    assert rig("models", "key", "anthropic") == 1
    err = capsys.readouterr().err
    assert "anthropic is not a provider this deployment enables" in err
    assert "gemini, openai" in err
    assert rig("models", "remove-key", "local") == 1
    assert env_file.read_text(encoding="utf-8") == ENV_FILE
    assert rig.runner.calls == []


def test_remove_key_removes_the_line(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    env_file = _installed(rig)
    assert rig("models", "remove-key", "openai") == 0
    written = env_file.read_text(encoding="utf-8")
    assert OPENAI_KEY not in written and "OSPREY_MODEL_KEY_OPENAI" not in written
    assert "OSPREY_OIDC_CLIENT_SECRET=client-secret-value" in written
    assert rig.runner.argvs() == [
        [*_compose(rig), "up", "-d", "--no-deps", "--wait", "litellm", "api"]
    ]
    assert "not offered to analysts" in capsys.readouterr().out
    # Removing a key that is not there changes nothing and restarts nothing.
    assert rig("models", "remove-key", "gemini") == 0
    assert len(rig.runner.calls) == 1


def test_the_single_provider_keeps_its_old_key_name(rig: Rig) -> None:
    env_file = _installed(
        rig, models={"local_only": False, "provider": {"name": "openai",
                                                       "roles": {"extraction": "gpt-4o-mini"}}},
        env="X=1\n",
    )  # fmt: skip
    rig.env["OSPREY_MODEL_KEY_OPENAI"] = OPENAI_KEY
    assert rig("models", "key", "openai") == 0
    assert env_file.read_text(encoding="utf-8") == f"X=1\nOSPREY_MODEL_PROVIDER_KEY={OPENAI_KEY}\n"


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
