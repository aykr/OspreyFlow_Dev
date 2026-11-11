"""`ospreyflow models` and an engine signed in by the namespace's IAM role (`06_DECISIONS.md`
ADR-135 Amendment 4, P11 part 1): it is listed as keeping no key, and `models key` and `models
remove-key` refuse it before any key is read, so none is ever typed or handed over for it.

What a mistake would do, and the case that catches it (rule 12):
- the engine hidden from `ospreyflow models` as if removed in *Admin › Models* —
  `test_an_iam_role_engine_is_listed_as_keeping_no_key`;
- a key asked for, read from the terminal or passed into the Conduit's container for it —
  `test_models_key_and_remove_key_refuse_an_iam_role_engine_before_reading_a_key`.
"""

from __future__ import annotations

import pytest

from .conftest import Rig
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


def test_an_iam_role_engine_is_listed_as_keeping_no_key(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    _installed(rig, models=BEDROCK_MODELS, status=STATUS)
    assert rig("models") == 0
    out = capsys.readouterr().out
    said = (
        "bedrock (Bedrock (London)): key present: none kept: signs in by the namespace's IAM role"
    )
    assert said in out


@pytest.mark.parametrize("action", ["key", "remove-key"])
def test_models_key_and_remove_key_refuse_an_iam_role_engine_before_reading_a_key(
    rig: Rig, capsys: pytest.CaptureFixture[str], action: str
) -> None:
    _installed(rig, models=BEDROCK_MODELS, status=STATUS)
    rig.env["OSPREY_MODEL_KEY_BEDROCK"] = PLANTED
    assert rig("models", action, "bedrock") == 1
    out = capsys.readouterr()
    assert "IAM role" in out.err and PLANTED not in out.out + out.err
    # Only the status was asked; nothing handed to the Conduit's key path.
    assert rig.runner.calls == []
    assert PLANTED not in _every_argv_word(rig)
