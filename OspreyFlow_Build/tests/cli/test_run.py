"""The command's runner and its redaction (ADR-114 decision 4: the install ends by saying where the
sign-in details are kept, "never a password").

What a mistake would do, and the case that catches it:
- a secret on the screen because the redaction missed a spelling —
  `test_every_line_naming_a_secret_is_hidden_whatever_its_case`;
- ordinary output lost — `test_other_lines_pass_through_untouched`;
- the real runner returning the wrong exit code or not streaming through the redactor —
  `test_the_real_runner_streams_redacted_lines_and_returns_the_exit_code`;
- the Compose prefix drifting from the harness's own (`harness.apply._compose`) —
  `test_compose_matches_the_harness_prefix`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from ospreyflow.run import Redactor, SubprocessRunner, compose


def test_every_line_naming_a_secret_is_hidden_whatever_its_case() -> None:
    redact = Redactor("/d/deployment.env")
    for line in (
        "OSPREY_KEYCLOAK_ADMIN_PASSWORD=hunter2",
        "client_secret: abc",
        "Authorization: Bearer TOKEN-abc",
        "the Password is x",
        "  secret",
    ):
        shown = redact(line)
        assert "hunter2" not in shown and "abc" not in shown and "is x" not in shown
        assert "a line naming a secret was hidden" in shown
        assert "/d/deployment.env" in shown


def test_other_lines_pass_through_untouched() -> None:
    redact = Redactor("/d/deployment.env")
    assert redact("Container glass  Started") == "Container glass  Started"
    assert redact("") == ""


def test_the_real_runner_streams_redacted_lines_and_returns_the_exit_code(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    runner = SubprocessRunner(Redactor("/d/deployment.env"))
    code = runner(
        [
            sys.executable,
            "-c",
            ("import os,sys; print('one'); print('PASSWORD=zzz'); print(os.getcwd()); "
             "print(os.environ['OSP_TEST']); sys.exit(4)"),
        ],
        env={"OSP_TEST": "kept"},
        cwd=tmp_path,
    )  # fmt: skip
    out = capsys.readouterr().out
    assert code == 4
    assert "one" in out and "zzz" not in out
    assert tmp_path.name in out
    assert "kept" in out


def test_compose_matches_the_harness_prefix(tmp_path: Path) -> None:
    from harness.apply import _compose

    directory = tmp_path / "gen"
    mine = compose(directory)
    assert mine[:2] == ["docker", "compose"]
    assert mine[2:4] == ["--env-file", str(directory / "deployment.env")]
    assert mine[4:] == ["-f", str(directory / "compose.yaml")]
    theirs = _compose(directory / "compose.yaml")
    assert mine == [str(x) for x in theirs]


def test_naming_the_github_variable_is_not_a_secret_but_its_value_still_is() -> None:
    """Found running `ospreyflow update --check` live: its advice for a private repository names
    `GITHUB_TOKEN`, and the redactor hid the whole line. A variable's name with no value is shown;
    any value, and any other line with the words, is still hidden."""
    from ospreyflow.run import Redactor

    redact = Redactor("/x/deployment.env")
    advice = "or it is private: set GITHUB_TOKEN to a token that can read it"
    assert redact(advice.replace("a token", "one")) == advice.replace("a token", "one")
    assert redact("set GH_TOKEN first") == "set GH_TOKEN first"
    for leaking in ("GITHUB_TOKEN=ghp_abc123", "GH_TOKEN: ghp_abc", "token ghp_abc",
                    "set GITHUB_TOKEN and the client secret"):  # fmt: skip
        assert redact(leaking) != leaking, leaking
