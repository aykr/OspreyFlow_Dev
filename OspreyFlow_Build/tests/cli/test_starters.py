"""Starters: `ospreyflow install --starter <theme>-<domain>` (ADR-138 decision 1).

What a mistake would do, and the case that catches it (rule 12):
- a starter that sets something other than its brand, or loads the wrong demo packs —
  `test_each_starters_osprey_yaml_carries_its_brand_and_demo_packs_and_nothing_else_differs`;
- the demo cases left with the seeds' own domains instead of the starter's —
  `test_each_starters_demo_packs_are_seeded_with_its_case_domains`;
- `blank` making a demo case or a demo account — `test_blank_makes_no_demo_case_and_no_demo_account`;
- a GOV.UK service installed with no name for its page title —
  `test_a_govuk_starter_without_a_service_name_is_refused_in_words`;
- a default service name that names one demo case (step 9d finding 3) —
  `test_the_service_name_offered_names_the_deployment_not_a_demo_case`;
- the starter recorded as a setting something reads — `test_the_starter_is_a_comment_not_a_setting`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ospreyflow import starters
from ospreyflow.answers import load_answers, osprey_config

from .conftest import BASE_CONFIG, Rig

ALL_PACKS = (
    "hmp\nfixture-corp\noperation-ledger\npaysim\nenron\nprison-intelligence\ncyber-intrusion\n"
    "prison-intelligence-scale\n"
)
SERVICE = "Analyse intelligence for a test"


def _offering_every_pack(rig: Rig) -> Rig:
    rig.responses["--ids"] = [(0, ALL_PACKS)]
    return rig


def _install(rig: Rig, name: str, *extra: str) -> int:
    govuk = ["--service-name", SERVICE] if name.startswith("govuk-") else []
    return rig("install", "--mode", "lite", "--starter", name, "--yes", "--force", *govuk, *extra)


def _seeds(rig: Rig) -> list[list[str]]:
    return [c.argv for c in rig.runner.with_word("scripts.seed_internal")]


@pytest.mark.parametrize("name", starters.names())
def test_each_starters_osprey_yaml_carries_its_brand_and_demo_packs_and_nothing_else_differs(
    rig: Rig, name: str
) -> None:
    _offering_every_pack(rig)
    starter = starters.parse(name)
    assert _install(rig, name) == 0
    text = (rig.product / "osprey.yaml").read_text(encoding="utf-8")
    written = yaml.safe_load(text)
    plain = osprey_config(load_answers({"mode": "lite"}, packs=ALL_PACKS.split()), BASE_CONFIG)
    # Nothing but the look differs from an install without a starter.
    assert {k: v for k, v in written.items() if k != "appearance"} == plain
    assert written["appearance"]["brand"] == starter.theme
    if starter.govuk:
        assert written["appearance"]["service_name"] == SERVICE
        assert written["appearance"]["phase"] == starters.DEFAULT_PHASE
    # Its demo packs: recorded in the comment, and seeded in order under their own keys.
    packs = ", ".join(starter.domain.demo_packs) or "none"
    assert text.startswith(f"# Starter: {name} ")
    assert f"demo packs: {packs}." in text.splitlines()[1]
    seeded = [argv[argv.index("scripts.seed_internal") + 1] for argv in _seeds(rig)]
    expected = {"hmp": "hmp", "prison-intelligence": "prison-intelligence",
                "operation-ledger": "ledger", "fixture-corp": "fixture-corp",
                "cyber-intrusion": "cyber-intrusion"}  # fmt: skip
    assert seeded == [expected[p] for p in starter.domain.demo_packs]


@pytest.mark.parametrize(
    ("domain", "case_domains"),
    [("crime", "niem"), ("aml", "fibo"), ("fraud", "fibo"), ("cyber", "stix")],
)
def test_each_starters_demo_packs_are_seeded_with_its_case_domains(
    rig: Rig, domain: str, case_domains: str
) -> None:
    """ADR-138's table: the domain sets the demo case's `domains` — so the HMP case of a crime
    starter is `niem`, not the seed's own `fibo, niem`, and Fixture Corp's is `fibo`, not POLE."""
    _offering_every_pack(rig)
    assert _install(rig, f"ospreyflow-{domain}") == 0
    seeds = _seeds(rig)
    assert seeds
    for argv in seeds:
        assert argv[argv.index("--case-domains") + 1] == case_domains


def test_blank_makes_no_demo_case_and_no_demo_account(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    _offering_every_pack(rig)
    assert _install(rig, "ospreyflow-blank") == 0
    (apply,) = rig.runner.argvs()
    assert "harness.apply" in apply and "--demo-analyst" not in apply
    assert not rig.runner.with_word("harness.register_sign_in")
    assert _seeds(rig) == []
    said = capsys.readouterr().out
    assert "No demo case and no demo accounts were made" in said
    assert "Sign in with the accounts" not in said


def test_blank_with_govuk_still_needs_the_service_name(rig: Rig) -> None:
    _offering_every_pack(rig)
    assert rig("install", "--mode", "lite", "--starter", "govuk-blank", "--yes", "--force") == 1
    assert rig.runner.calls == []


@pytest.mark.parametrize("name", [n for n in starters.names() if n.startswith("govuk-")])
def test_a_govuk_starter_without_a_service_name_is_refused_in_words(
    rig: Rig, name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _offering_every_pack(rig)
    before = (rig.product / "osprey.yaml").read_text(encoding="utf-8")
    assert rig("install", "--mode", "lite", "--starter", name, "--yes", "--force") == 1
    err = capsys.readouterr().err
    assert "no service name was given" in err and "--service-name" in err
    assert "Nothing was installed" in err
    assert rig.runner.calls == []
    assert (rig.product / "osprey.yaml").read_text(encoding="utf-8") == before


def test_a_govuk_starter_asks_for_the_name_organisation_and_phase(rig: Rig) -> None:
    _offering_every_pack(rig)
    rig.replies = ["", "Test Department", "alpha"]  # the name offered is taken as it stands
    assert rig("install", "--mode", "lite", "--starter", "govuk-aml", "--force") == 0
    asked = " | ".join(rig.questions)
    assert "service's name" in asked and "organisation" in asked and "phase" in asked
    appearance = rig.config()["appearance"]
    assert appearance == {
        "brand": "govuk",
        "service_name": "Investigate money laundering",
        "organisation": "Test Department",
        "phase": "alpha",
    }


def test_the_service_name_offered_names_the_deployment_not_a_demo_case() -> None:
    """Step 9d finding 3: "Prison Intelligence" showed in the header of every case, the Ledger's
    included. No starter offers a demo case's or pack's name."""
    case_words = ("prison", "ledger", "fixture", "hmp", "operation", "tidewater", "intrusion")
    for domain in starters.DOMAINS.values():
        if domain.service_name is None:
            continue
        assert not any(word in domain.service_name.lower() for word in case_words)


def test_an_answers_file_can_name_the_starter(rig: Rig, tmp_path: Path) -> None:
    """The guided page writes `starter:` into `install.yaml` and runs the install from it."""
    _offering_every_pack(rig)
    answers = tmp_path / "install.yaml"
    answers.write_text(
        yaml.safe_dump(
            {"mode": "lite", "starter": "govuk-cyber",
             "appearance": {"service_name": SERVICE, "organisation": "Org", "phase": "beta"}}
        ),
        encoding="utf-8",
    )  # fmt: skip
    assert rig("install", "--mode", "lite", "--config", str(answers), "--force") == 0
    assert rig.config()["appearance"]["brand"] == "govuk"
    assert [a[a.index("scripts.seed_internal") + 1] for a in _seeds(rig)] == ["cyber-intrusion"]


def test_a_starter_answer_can_still_be_changed(rig: Rig, tmp_path: Path) -> None:
    """Pre-filled, never fixed: an answers file's own demo packs replace the starter's."""
    _offering_every_pack(rig)
    answers = tmp_path / "install.yaml"
    answers.write_text(
        yaml.safe_dump({"mode": "lite", "starter": "ospreyflow-crime", "demo_packs": ["hmp"]}),
        encoding="utf-8",
    )
    assert rig("install", "--mode", "lite", "--config", str(answers), "--force") == 0
    assert [a[a.index("scripts.seed_internal") + 1] for a in _seeds(rig)] == ["hmp"]


def test_the_starter_is_a_comment_not_a_setting(rig: Rig) -> None:
    _offering_every_pack(rig)
    assert _install(rig, "ospreyflow-aml") == 0
    assert "starter" not in rig.config()


def test_an_unknown_starter_is_refused_naming_the_starters(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("install", "--mode", "lite", "--starter", "ospreyflow-weather", "--yes") == 1
    err = capsys.readouterr().err
    assert "ospreyflow-weather" in err and "govuk-crime" in err
    assert rig.runner.calls == []


def test_a_cyber_starter_on_a_checkout_without_its_pack_says_so(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR-138's table: until `cyber-intrusion` exists the cyber starter loads no demo case and
    says so — still true of an older checkout."""
    assert _install(rig, "ospreyflow-cyber") == 0
    assert _seeds(rig) == []
    assert "no cyber-intrusion demo pack" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [("starters",), ("install", "--list-starters")])
def test_the_starters_are_listed_with_one_command_each(
    rig: Rig, argv: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig(*argv) == 0
    said = capsys.readouterr().out
    for name in starters.names():
        assert f"--starter {name}" in said
    assert rig.runner.calls == []


def test_install_without_a_mode_is_refused_in_words(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("install", "--starter", "ospreyflow-crime", "--yes") == 1
    assert "--mode lite" in capsys.readouterr().err


def test_the_guided_pages_draft_gets_the_starters_look(rig: Rig, tmp_path: Path) -> None:
    """The guided page installs from its draft `osprey.yaml` (`config:`); the look chosen on its
    Mode screen is an answer, so it is written over the draft."""
    _offering_every_pack(rig)
    draft = tmp_path / "osprey.draft.yaml"
    draft.write_text(yaml.safe_dump(BASE_CONFIG), encoding="utf-8")
    answers = tmp_path / "install.yaml"
    answers.write_text(
        yaml.safe_dump({"mode": "lite", "config": str(draft), "starter": "govuk-crime",
                        "appearance": {"service_name": SERVICE}}),
        encoding="utf-8",
    )  # fmt: skip
    assert rig("install", "--mode", "lite", "--config", str(answers), "--yes", "--force") == 0
    assert rig.config()["appearance"] == {"brand": "govuk", "service_name": SERVICE, "phase": "beta"}
    assert (rig.product / "osprey.yaml").read_text(encoding="utf-8").startswith(
        "# Starter: govuk-crime"
    )
