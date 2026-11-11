"""A compose file naming a required value `deployment.env` does not hold no longer locks the
operator out of `apply` (CARRIES, the v0.5.0 upgrade rehearsal, 10 November 2026): `apply`'s own port
lookup (`compose ps`) failed, preflight then refused the deployment's own 8090 and 2500 as taken, and
nothing said why. Now it asks Docker by the project's label, which needs no compose file, and goes on
to render the file again, which is the way out (ADR-114 Amendment 39 decision 1). It never refuses
there, so no words of it are hidden by the command's redactor either (the lane review, items 2, 3).

What Compose refuses is what this reads (`harness.compose_env.unset_required`), and the CLI's own copy
(`ospreyflow stop`'s, which cannot import the harness) answers the same: `${X:?}` unset or empty,
`${X?}` unset only; `${X}`, `${X:-d}` and `$${X:?}` never; a value from the shell (an empty one too)
before the file; an `export X=v` line, one pair of quotes, an unquoted ` #` comment, as Compose reads
them.
- `test_what_compose_refuses_is_read_the_same_by_both_copies`
- `test_applys_own_port_lookup_asks_docker_by_label_and_never_refuses`
- `test_the_words_name_the_values_never_hold_one_and_point_to_apply`
"""

from __future__ import annotations

from pathlib import Path

import pytest
from harness import apply, compose_env
from ospreyflow import run as cli_run

COMPOSE = """name: osprey-upg
services:
  api:
    environment:
      A: ${REQUIRED_EMPTY_REFUSED:?set it}
      B: ${REQUIRED_UNSET_ONLY?set it}
      C: ${PLAIN}
      D: ${DEFAULTED:-x}
      E: $${ESCAPED:?not a variable}
      F: ${FROM_THE_SHELL:?set it}
      G: ${FROM_AN_EXPORT:?set it}
      H: ${HELD:?set it}
"""


def _deployment(tmp_path: Path, env: str) -> Path:
    folder = tmp_path / "osprey-upg"
    folder.mkdir()
    (folder / "compose.yaml").write_text(COMPOSE, encoding="utf-8")
    (folder / "deployment.env").write_text(env, encoding="utf-8")
    return folder


@pytest.mark.parametrize(
    ("env", "shell", "missing"),
    [
        ("HELD=1\nexport FROM_AN_EXPORT=2\n", {"FROM_THE_SHELL": "3"},
         ["REQUIRED_EMPTY_REFUSED", "REQUIRED_UNSET_ONLY"]),
        ("HELD=1\nexport FROM_AN_EXPORT=2\nREQUIRED_EMPTY_REFUSED=\nREQUIRED_UNSET_ONLY=\n",
         {"FROM_THE_SHELL": "3"}, ["REQUIRED_EMPTY_REFUSED"]),
        ("REQUIRED_EMPTY_REFUSED=a\nREQUIRED_UNSET_ONLY=b\n", {},
         ["FROM_AN_EXPORT", "FROM_THE_SHELL", "HELD"]),
        # One pair of quotes taken whole; an unquoted ` #` comment is no value.
        ('HELD="1"\nFROM_AN_EXPORT=\'2\'\nREQUIRED_EMPTY_REFUSED= # note\nREQUIRED_UNSET_ONLY=b\n',
         {"FROM_THE_SHELL": "3"}, ["REQUIRED_EMPTY_REFUSED"]),
        # An empty value in the shell is taken before the file's.
        ("HELD=1\nFROM_AN_EXPORT=2\nREQUIRED_EMPTY_REFUSED=a\nREQUIRED_UNSET_ONLY=b\n",
         {"FROM_THE_SHELL": "3", "REQUIRED_EMPTY_REFUSED": "", "REQUIRED_UNSET_ONLY": ""},
         ["REQUIRED_EMPTY_REFUSED"]),
    ],
)  # fmt: skip
def test_what_compose_refuses_is_read_the_same_by_both_copies(
    tmp_path: Path, env: str, shell: dict[str, str], missing: list[str]
) -> None:
    folder = _deployment(tmp_path, env)
    assert compose_env.unset_required(folder, shell) == missing
    assert cli_run.unset_required(folder, shell) == missing


def test_applys_own_port_lookup_asks_docker_by_label_and_never_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _deployment(tmp_path, "HELD=1\n")
    asked: list[list[str]] = []

    def run(args: list[str], **_: object) -> str:
        asked.append(args)
        return "0.0.0.0:8090->8090/tcp, :::8090->8090/tcp\n127.0.0.1:2500->2480/tcp\n"

    monkeypatch.setattr(apply, "_run", run)
    assert apply.own_published_ports(folder / "compose.yaml") == {8090, 2500}
    assert asked == [["docker", "ps", "--filter", "label=com.docker.compose.project=osprey-upg",
                      "--format", "{{.Ports}}"]]  # fmt: skip
    assert not any("compose" == a for args in asked for a in args)  # Compose was never asked


def test_the_words_name_the_values_never_hold_one_and_point_to_apply(tmp_path: Path) -> None:
    folder = _deployment(tmp_path, "HELD=held-secret-value-Q7Z4\nREQUIRED_UNSET_ONLY=\n")
    missing = compose_env.unset_required(folder, {})
    for words in (compose_env.locked_out(folder, missing), cli_run.locked_out(folder, missing)):
        assert "REQUIRED_EMPTY_REFUSED" in words and "ospreyflow apply" in words
        assert "label=com.docker.compose.project=osprey-upg" in words
        assert "Q7Z4" not in words and "backup set's" not in words
    assert compose_env.locked_out(folder, missing) == cli_run.locked_out(folder, missing)
