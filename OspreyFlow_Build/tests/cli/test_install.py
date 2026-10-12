"""`ospreyflow install` (ADR-114 Amendment 3 decision 4): doctor first, then the answers become
`osprey.yaml`, then `harness.apply`, the sign-in, and the chosen demo packs, each step stopping the
install if it fails.

What a mistake would do, and the case that catches it:
- an install that carries on past a failed prerequisite —
  `test_a_failing_doctor_stops_the_install_before_anything_runs`;
- the owner's own `osprey.yaml` overwritten — `test_an_existing_different_osprey_yaml_is_refused_without_force`
  and `test_a_config_naming_the_products_own_osprey_yaml_writes_nothing`;
- answers that never reach the deployment — `test_the_answers_reach_osprey_yaml`;
- the apply run without the build or the demo analyst, or the sign-in skipped —
  `test_apply_is_built_with_the_demo_analyst_then_the_sign_in_is_registered`, and
  `test_no_demo_accounts_drops_both`;
- a password on the screen — `test_a_line_naming_a_password_from_a_step_is_hidden`;
- demo packs out of order or under the wrong key — `test_the_chosen_demo_packs_run_in_order_with_their_seed_keys`;
- a failed step reported as success — `test_a_failing_step_stops_the_install_and_names_it`;
- Small or Enterprise pretending to install — `test_small_mode_saves_the_answers_and_runs_nothing`;
- the prompts not being the answers' other door — `test_without_yes_or_config_the_prompts_make_the_answers`;
- the guided page — `test_install_gui.py` has its own cases.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from .conftest import Rig, make_python_stub


def test_a_failing_doctor_stops_the_install_before_anything_runs(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.probes.missing.add("git")
    before = (rig.product / "osprey.yaml").read_text(encoding="utf-8")
    assert rig("install", "--mode", "lite", "--yes") == 1
    assert rig.runner.calls == []
    assert (rig.product / "osprey.yaml").read_text(encoding="utf-8") == before
    assert "Git is not installed" in capsys.readouterr().out


def test_an_existing_different_osprey_yaml_is_refused_without_force(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    (rig.product / "osprey.yaml").write_text("profile: local-lite\nmodels:\n  local_only: false\n",
                                             encoding="utf-8")  # fmt: skip
    mine = (rig.product / "osprey.yaml").read_text(encoding="utf-8")
    assert rig("install", "--mode", "lite", "--yes") == 1
    assert rig.runner.calls == []
    assert (rig.product / "osprey.yaml").read_text(encoding="utf-8") == mine
    err = capsys.readouterr().err
    assert "osprey.yaml" in err and "--force" in err
    assert rig("install", "--mode", "lite", "--yes", "--force") == 0
    assert rig.config()["models"]["local_only"] is True  # type: ignore[index]


def test_a_config_naming_the_products_own_osprey_yaml_writes_nothing(rig: Rig) -> None:
    own = rig.product / "osprey.yaml"
    own.write_text("# mine\nprofile: local-lite\nreporting:\n  sync: false\n  superset: false\n",
                   encoding="utf-8")  # fmt: skip
    before = own.read_text(encoding="utf-8")
    answers = rig.product / "install.yaml"
    answers.write_text(yaml.safe_dump({"mode": "lite", "config": str(own)}), encoding="utf-8")
    assert rig("install", "--mode", "lite", "--config", str(answers), "--yes") == 0
    assert own.read_text(encoding="utf-8") == before  # byte for byte, comment included
    assert rig.runner.with_word("harness.apply")


def test_the_answers_reach_osprey_yaml(rig: Rig, tmp_path: Path) -> None:
    ingest, tiles = tmp_path / "evidence", tmp_path / "maps"
    answers = tmp_path / "answers.yaml"
    answers.write_text(
        yaml.safe_dump(
            {
                "mode": "lite",
                "components": {"dashboards": False},
                "folders": {"ingest": str(ingest), "tiles": str(tiles)},
            }
        ),
        encoding="utf-8",
    )
    assert rig("install", "--mode", "lite", "--config", str(answers), "--force") == 0
    config = rig.config()
    assert config["reporting"] == {"sync": False, "superset": False}
    storage = config["components"]["storage"]  # type: ignore[index]
    assert storage["ingest"] == str(ingest) and storage["tiles"] == str(tiles)
    assert storage["data"] == "/var/lib/osprey/data"  # the product's own defaults are kept


def test_apply_is_built_with_the_demo_analyst_then_the_sign_in_is_registered(rig: Rig) -> None:
    assert rig("install", "--mode", "lite", "--yes", "--force") == 0
    python = str(rig.product / ".venv" / "bin" / "python")
    apply, sign_in = rig.runner.argvs()
    assert apply == [python, "-m", "harness.apply", "--build", "--demo-analyst"]
    assert sign_in == [python, "-m", "harness.register_sign_in"]
    assert all(c.cwd == rig.product for c in rig.runner.calls)


def test_no_demo_accounts_drops_both(rig: Rig) -> None:
    assert rig("install", "--mode", "lite", "--yes", "--force", "--no-demo-accounts") == 0
    (apply,) = rig.runner.argvs()
    assert "--build" in apply
    assert "--demo-analyst" not in apply
    assert not rig.runner.with_word("harness.register_sign_in")


@pytest.mark.skipif(os.name == "nt", reason="the interpreter is stubbed with a shell script")
def test_a_line_naming_a_password_from_a_step_is_hidden(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    """Runs through the real runner, so the redaction is the one a person's screen gets."""
    make_python_stub(
        rig.product,
        'echo "building"; echo "OSPREY_KEYCLOAK_ADMIN_PASSWORD=hunter2-not-real"; '
        'echo "client_secret: abc"; echo "done"',
    )
    rig.use_real_runner = True
    assert rig("install", "--mode", "lite", "--yes", "--force", "--no-demo-accounts") == 0
    out = capsys.readouterr().out
    assert "building" in out and "done" in out
    assert "hunter2" not in out and "abc" not in out
    assert "a line naming a secret was hidden" in out
    assert "deployment.env" in out


def test_the_chosen_demo_packs_run_in_order_with_their_seed_keys(rig: Rig, tmp_path: Path) -> None:
    csv = tmp_path / "paysim.csv"
    csv.write_text("x\n", encoding="utf-8")
    answers = tmp_path / "answers.yaml"
    answers.write_text(
        yaml.safe_dump(
            {
                "mode": "lite",
                "demo_packs": ["operation-ledger", "hmp", "fixture-corp"],
            }
        ),
        encoding="utf-8",
    )
    assert rig("install", "--mode", "lite", "--config", str(answers), "--force") == 0
    seeds = [c.argv[c.argv.index("scripts.seed_internal") + 1] for c in
             rig.runner.with_word("scripts.seed_internal")]  # fmt: skip
    assert seeds == ["ledger", "hmp", "fixture-corp"]
    # They come after the apply and the sign-in, never before.
    names = [" ".join(a) for a in rig.runner.argvs()]
    assert names.index(next(n for n in names if "harness.apply" in n)) == 0
    assert names.index(next(n for n in names if "seed_internal" in n)) == 2


def test_a_failing_step_stops_the_install_and_names_it(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.runner.fail["harness.apply"] = 3
    assert rig("install", "--mode", "lite", "--yes", "--force") == 1
    assert len(rig.runner.calls) == 1  # the sign-in was not attempted
    err = capsys.readouterr().err
    assert "build and start the deployment" in err and "exit 3" in err

    rig.runner.calls.clear()
    rig.runner.fail = {"harness.register_sign_in": 2}
    assert rig("install", "--mode", "lite", "--yes", "--force") == 1
    assert "register the sign-in" in capsys.readouterr().err


def test_a_finished_install_says_the_address_and_where_the_sign_in_details_are(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("install", "--mode", "lite", "--yes", "--force") == 0
    out = capsys.readouterr().out
    assert "http://localhost:8080" in out
    assert "deployment.env" in out
    assert "ospreyflow status" in out and "ospreyflow open" in out


def test_small_mode_saves_the_answers_and_runs_nothing(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = tmp_path / "answers.yaml"
    answers.write_text(
        yaml.safe_dump({"mode": "small", "cloud": {"provider": "aws", "region": "eu-west-2"}}),
        encoding="utf-8",
    )
    before = (rig.product / "osprey.yaml").read_text(encoding="utf-8")
    assert rig("install", "--mode", "small", "--config", str(answers)) == 0
    assert rig.runner.calls == []
    assert (rig.product / "osprey.yaml").read_text(encoding="utf-8") == before
    saved = yaml.safe_load((rig.product / "install.yaml").read_text(encoding="utf-8"))
    assert saved["mode"] == "small" and saved["cloud"]["region"] == "eu-west-2"
    assert "B6" in capsys.readouterr().out
    assert rig("install", "--mode", "enterprise", "--yes") == 0
    assert "B7" in capsys.readouterr().out
    assert rig.runner.calls == []


def test_the_mode_flag_and_the_answers_file_must_agree(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = tmp_path / "answers.yaml"
    answers.write_text(yaml.safe_dump({"mode": "small"}), encoding="utf-8")
    assert rig("install", "--mode", "lite", "--config", str(answers)) == 1
    assert "small" in capsys.readouterr().err
    assert rig.runner.calls == []


def test_without_yes_or_config_the_prompts_make_the_answers(rig: Rig, tmp_path: Path) -> None:
    rig.replies = ["n", str(tmp_path / "in"), str(tmp_path / "tiles"), "hmp"]
    assert rig("install", "--mode", "lite", "--force") == 0
    assert len(rig.questions) == 4
    config = rig.config()
    assert config["reporting"] == {"sync": False, "superset": False}
    assert config["components"]["storage"]["ingest"] == str(tmp_path / "in")  # type: ignore[index]
    assert rig.runner.with_word("scripts.seed_internal")[0].argv[-2:] == ["hmp", "--stop-api"]
    # --yes never asks.
    rig.questions.clear()
    assert rig("install", "--mode", "lite", "--yes", "--force") == 0
    assert rig.questions == []


def test_the_install_alias_is_accepted(rig: Rig) -> None:
    assert rig("--install", "--mode", "lite", "--yes", "--force", "--no-demo-accounts") == 0
    assert rig.runner.with_word("harness.apply")
