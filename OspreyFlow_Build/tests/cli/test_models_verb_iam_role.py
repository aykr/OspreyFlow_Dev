"""`ospreyflow models` and an engine signed in by the gateway's own IAM role (`06_DECISIONS.md`
ADR-135 Amendment 4; as built, Amendment 7, P11 part 1): it is listed as keeping no key, and `models
key` and `models remove-key` refuse it before any key is read, so none is ever typed or handed over
for it — **even when the Conduit does not answer `status`** (the review's item 8).

What a mistake would do, and the case that catches it (rule 12):
- the engine hidden from `ospreyflow models` as if removed in *Admin › Models* —
  `test_an_iam_role_engine_is_listed_as_keeping_no_key`;
- a key asked for, read from the terminal or passed into the Conduit's container for it —
  `test_models_key_and_remove_key_refuse_an_iam_role_engine_before_reading_a_key`;
- the same with the Conduit silent, for a declared Bedrock engine and for any engine on the
  `cloud-platform` profile (one added in *Admin › Models* is not in `osprey.yaml`) —
  `test_with_the_conduit_silent_no_key_is_read_where_the_engine_may_keep_none`;
- every other profile asked for a key as before when the Conduit is silent —
  `test_with_the_conduit_silent_another_profile_s_key_is_read_as_before`.
"""

from __future__ import annotations

import pytest
import yaml
from ospreyflow import models as engine_keys

from schemas.deployment import MODEL_ROUTE_PROFILE

from .conftest import BASE_CONFIG, Rig
from .test_models_verb import _every_argv_word, _installed

BEDROCK_MODELS = {
    "local_only": False,
    "sendable_handling_codes": ["P"],
    "providers": [
        {"name": "gemini", "roles": {"extraction": "gemini-2.5-flash"}},
        {"name": "bedrock", "label": "Bedrock (London)", "kind": "bedrock",
         "roles": {"extraction": "anthropic.claude-3-haiku-20240307-v1:0"}},
    ],
}  # fmt: skip
STATUS = "gemini set\nbedrock iam_role\n"
PLANTED = "bedrock-PLANTED-key-Q7Z4"


def _on_cloud_platform(rig: Rig, models: dict[str, object] = BEDROCK_MODELS) -> None:
    """Installed with the `cloud-platform` profile in the deployment's own copy of `osprey.yaml`
    (what is running, which the command line reads first); the rig finds its deployment by the
    product's."""
    _installed(rig, models=models, status=STATUS)
    config = {**BASE_CONFIG, "profile": MODEL_ROUTE_PROFILE, "models": models}
    (rig.deployment / "osprey.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


def test_an_iam_role_engine_is_listed_as_keeping_no_key(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    _on_cloud_platform(rig)
    assert rig("models") == 0
    out = capsys.readouterr().out
    said = (
        "bedrock (Bedrock (London)): key present: none kept: signs in by the gateway's own IAM role"
    )
    assert said in out


@pytest.mark.parametrize("action", ["key", "remove-key"])
def test_models_key_and_remove_key_refuse_an_iam_role_engine_before_reading_a_key(
    rig: Rig, capsys: pytest.CaptureFixture[str], action: str
) -> None:
    _on_cloud_platform(rig)
    rig.env["OSPREY_MODEL_KEY_BEDROCK"] = PLANTED
    assert rig("models", action, "bedrock") == 1
    out = capsys.readouterr()
    assert "IAM role" in out.err and PLANTED not in out.out + out.err
    # Only the status was asked; nothing handed to the Conduit's key path.
    assert rig.runner.calls == []
    assert PLANTED not in _every_argv_word(rig)


@pytest.mark.parametrize("action", ["key", "remove-key"])
@pytest.mark.parametrize(
    "engine",
    ["bedrock", "acme_added_in_admin_models"],
    ids=["declared-bedrock", "added-in-admin-models"],
)
def test_with_the_conduit_silent_no_key_is_read_where_the_engine_may_keep_none(
    rig: Rig, capsys: pytest.CaptureFixture[str], action: str, engine: str
) -> None:
    _on_cloud_platform(rig)
    rig.responses["status"] = [(1, "service \"api\" is not running")]
    rig.env[f"OSPREY_MODEL_KEY_{engine.upper()}"] = PLANTED
    rig.secret_replies.append(PLANTED)
    assert rig("models", action, engine) == 1
    out = capsys.readouterr()
    assert "IAM role" in out.err and "no key was read" in out.err
    assert rig.secret_prompts == []
    assert rig.runner.calls == []
    assert PLANTED not in _every_argv_word(rig) + out.out + out.err


def test_with_the_conduit_silent_another_profile_s_key_is_read_as_before(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    # local-lite (the rig's own profile), a plain provider: as before Amendment 4, the key is read
    # and handed on, and the hand-over is what fails or not.
    _installed(rig, models={**BEDROCK_MODELS, "providers": BEDROCK_MODELS["providers"][:1]})
    rig.responses["status"] = [(1, "service \"api\" is not running")]
    rig.secret_replies.append("g-key-typed")
    rig("models", "key", "gemini")
    assert rig.secret_prompts == ["Key for Gemini (OSPREY_MODEL_KEY_GEMINI; not shown): "]


def test_the_command_line_names_the_profile_as_the_schema_does() -> None:
    assert engine_keys.MODEL_ROUTE_PROFILE == MODEL_ROUTE_PROFILE
