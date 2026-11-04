"""The Prison Intelligence pack and post-ingest resolution (build order step 25 (c); ADR-127
Amendment 46, which completes Amendments 33–35).

With `components.post_ingest_resolution` on, a live load in the demonstration queues resolution,
whose worker writes a `SAME_AS` link for every candidate pair across the corpus (about 39 resting on
the one man chapter 4 adds), and every rehearsal reset then refuses. The setting is the whole
deployment's: nothing in the specification scopes resolution to a case or a dataset, so the pack
cannot turn it off for itself alone. Instead `ospreyflow demo add prison-intelligence` refuses, in
words, while it is on; and an install whose answers choose the pack writes it off, so a fresh
install (the crime starter's one command among them) never turns it back on under the pack.

What a mistake would do, and the case that catches it (rule 12):
- the pack loaded onto a deployment whose Conduit queues resolution —
  `test_adding_the_pack_is_refused_in_words_while_resolution_is_on`, with the switch rendered on
  and with a deployment rendered before the switch existed (no line: on, as the Conduit reads it);
- the refusal firing where the switch is off — `test_the_pack_loads_once_resolution_is_off`;
- a fresh install with the pack turning resolution back on —
  `test_an_install_that_chooses_the_pack_turns_resolution_off`, read through the real renderer
  into the `deployment.env` the refusal reads, so the install's pack step is never refused;
- an install without the pack changing the setting — the same case's second half;
- a hand-written `osprey.yaml` (`config:`) that says resolution is on, with the pack chosen,
  silently overridden or installed to fail at the last step —
  `test_a_config_that_turns_resolution_on_with_the_pack_is_refused_before_anything_runs`.

The deployment's `deployment.env` is written by `harness.render`, as `harness.apply` writes it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness.render import _render_env

from schemas.deployment import OspreyConfig

from .conftest import BASE_CONFIG, Rig

ALL_PACKS = (
    # The prison fixture's own pack is left out: this is a PID-named file, and the naming gate
    # (`tools/pid_naming_check.py`) bans its name here. The starter loads what is offered.
    "fixture-corp\noperation-ledger\npaysim\nenron\nprison-intelligence\ncyber-intrusion\n"
    "prison-intelligence-scale\n"
)
SWITCH = "OSPREY_POST_INGEST_RESOLUTION"


def _deployment(rig: Rig) -> Path:
    return rig.product / "deploy" / "generated" / "local-lite"


def _render(rig: Rig, settings: dict[str, object]) -> str:
    """The deployment's `deployment.env`, rendered from `settings` by the real renderer."""
    env = _render_env(OspreyConfig.model_validate(settings))
    folder = _deployment(rig)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (folder / "deployment.env").write_text(env, encoding="utf-8")
    return env


def _seeds(rig: Rig) -> list[list[str]]:
    return [c.argv for c in rig.runner.with_word("scripts.seed_internal")]


@pytest.mark.parametrize("rendered", ["on", "absent"])
def test_adding_the_pack_is_refused_in_words_while_resolution_is_on(
    rig: Rig, capsys: pytest.CaptureFixture[str], rendered: str
) -> None:
    env = _render(rig, BASE_CONFIG)
    assert f"{SWITCH}=on" in env  # the default, as the renderer writes it
    if rendered == "absent":
        # A deployment rendered before ADR-127 Amendment 33: the Conduit takes the default, on.
        lines = [line for line in env.splitlines() if not line.startswith(f"{SWITCH}=")]
        (_deployment(rig) / "deployment.env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert rig("demo", "add", "prison-intelligence") == 1
    assert _seeds(rig) == []
    words = capsys.readouterr().err
    assert "post_ingest_resolution: false" in words and "components:" in words
    assert "ospreyflow apply" in words
    assert str(rig.product / "osprey.yaml") in words
    assert "Nothing was added" in words


def test_the_pack_loads_once_resolution_is_off(rig: Rig) -> None:
    off = {**BASE_CONFIG, "components": {**BASE_CONFIG["components"],  # type: ignore[dict-item]
                                         "post_ingest_resolution": False}}  # fmt: skip
    assert f"{SWITCH}=off" in _render(rig, off)
    assert rig("demo", "add", "prison-intelligence") == 0
    (argv,) = _seeds(rig)
    assert argv[argv.index("scripts.seed_internal") + 1 :] == ["prison-intelligence", "--stop-api"]


def test_other_packs_are_not_refused_while_resolution_is_on(rig: Rig) -> None:
    _render(rig, BASE_CONFIG)
    assert rig("demo", "add", "operation-ledger") == 0
    assert len(_seeds(rig)) == 1


def test_an_install_that_chooses_the_pack_turns_resolution_off(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.responses["--ids"] = [(0, ALL_PACKS)]
    assert (
        rig("install", "--mode", "lite", "--starter", "ospreyflow-crime", "--yes", "--force") == 0
    )
    written = rig.config()
    assert written["components"]["post_ingest_resolution"] is False  # type: ignore[index]
    assert "post_ingest_resolution" in capsys.readouterr().out
    # What `harness.apply` renders from it is what the pack's refusal reads: off, so `demo add` goes
    # ahead after the install as it did during it.
    assert f"{SWITCH}=off" in _render(rig, written)
    rig.runner.calls.clear()
    assert rig("demo", "add", "prison-intelligence") == 0
    # An install without the pack leaves the setting as the checkout has it (the checkout's own
    # osprey.yaml put back first: an install starts from what is there).
    (rig.product / "osprey.yaml").write_text(yaml.safe_dump(BASE_CONFIG), encoding="utf-8")
    rig.runner.calls.clear()
    assert rig("install", "--mode", "lite", "--starter", "ospreyflow-aml", "--yes", "--force") == 0
    assert "post_ingest_resolution" not in (rig.config().get("components") or {})


def test_a_config_that_turns_resolution_on_with_the_pack_is_refused_before_anything_runs(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.responses["--ids"] = [(0, ALL_PACKS)]
    own = tmp_path / "osprey.own.yaml"
    on = {**BASE_CONFIG, "components": {"post_ingest_resolution": True}}
    own.write_text(yaml.safe_dump(on), encoding="utf-8")
    answers = tmp_path / "install.yaml"
    answers.write_text(
        yaml.safe_dump({"mode": "lite", "config": str(own), "demo_packs": ["prison-intelligence"]}),
        encoding="utf-8",
    )
    assert rig("install", "--mode", "lite", "--config", str(answers), "--yes", "--force") == 1
    assert not any("harness.apply" in c.argv for c in rig.runner.calls)
    words = capsys.readouterr().err
    assert "post_ingest_resolution" in words and "prison-intelligence" in words
