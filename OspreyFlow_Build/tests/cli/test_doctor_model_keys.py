"""`ospreyflow doctor` names a model key the gateway no longer holds (`06_DECISIONS.md` ADR-135
Amendment 2 decision 9): after a restore from another deployment, or a changed encryption key, the
gateway drops every stored key with only a warning in its own log (measured), so the doctor says
which engines lost theirs and how to put them back. Through the real verb, with the installed
deployment's answer stood in by the probes (nothing reaches a deployment)."""

from __future__ import annotations

import pytest
from ospreyflow.doctor import SystemProbes, model_key_checks

from .conftest import Rig


def test_the_doctor_names_each_lost_key_as_a_warning(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.probes.model_key_states = lambda: {"gemini": "lost", "openai": "set", "mistral": "lost"}  # type: ignore[attr-defined]
    rig("doctor")
    out = capsys.readouterr().out
    assert "no longer holds the key of gemini, mistral" in out
    assert "ospreyflow models key <name>" in out


def test_every_key_held_is_said_and_no_deployment_says_nothing() -> None:
    (held,) = model_key_checks({"gemini": "set", "openai": "none"})
    assert held.ok
    assert model_key_checks(None) == []
    assert SystemProbes(None).model_key_states() is None


def test_a_lost_key_warns_and_does_not_stop_an_install() -> None:
    (lost,) = model_key_checks({"gemini": "lost"})
    assert not lost.ok and lost.warn
    assert "that engine is offered to no analyst" in lost.says
