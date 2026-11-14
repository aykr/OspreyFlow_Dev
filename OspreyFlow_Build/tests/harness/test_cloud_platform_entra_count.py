"""How many app registrations the client's Entra administrator makes, said in INSTALL.md as the
deployment needs them (ADR-148 Amendments 8, 9 and 10): the Glass and the API always, Superset's
own where reporting renders Superset, and the report sync's where it renders the sync. Held to the
poc manifest's own Entra list (`harness/cloud_platform/poc_manifest.yaml`'s `entra`), so a
registration added there, or reporting switched on, cannot leave the words saying two."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig

_MANIFEST = (
    Path(__file__).resolve().parents[3] / "OspreyFlow_Core/harness/cloud_platform/poc_manifest.yaml"
)
_WORDS = {2: "two", 3: "three", 4: "four"}


def _install(superset: bool, sync: bool) -> str:
    raw: dict[str, Any] = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    raw["reporting"] = {"superset": superset, "sync": sync}
    if superset:
        raw["cloud_platform"]["claims"]["superset_client_id"] = (
            "cccccccc-dddd-4eee-8fff-000000000001"
        )
    text = render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts["INSTALL.md"]
    return re.sub(r"\s+", " ", text)


def _needed(superset: bool, sync: bool) -> list[str]:
    """The manifest's registrations this deployment needs: its Entra list, less reporting's where
    reporting does not render them."""
    entra = yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))["entra"]
    off = {"superset": not superset, "report-sync": not sync}
    return [name for name in entra if not off.get(name, False)]


@pytest.mark.parametrize(("superset", "sync"), [(False, False), (True, False), (True, True)])
def test_install_says_as_many_app_registrations_as_the_manifest_lists_for_it(
    superset: bool, sync: bool
) -> None:
    text = _install(superset, sync)
    count = _WORDS[len(_needed(superset, sync))]
    before_step_5 = text[text.index("**Before step 5") : text.index("## 1.")]
    sign_in = text[text.index("## 6. Sign-in") : text.index("## 7.")]
    assert f"{count} app registrations" in before_step_5, before_step_5[:400]
    assert f"{count} app registrations" in sign_in
    wrong = [w for n, w in _WORDS.items() if w != count]
    assert not any(f"{w} app registrations" in before_step_5 + sign_in for w in wrong)


def test_with_reporting_on_the_manifest_lists_four() -> None:
    assert _needed(True, True) == ["glass", "api", "superset", "report-sync"]
