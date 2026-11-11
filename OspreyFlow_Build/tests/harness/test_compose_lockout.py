"""A compose file naming a required value `deployment.env` does not hold no longer locks the
operator out of `apply` in silence (CARRIES, the v0.5.0 upgrade rehearsal, 10 November 2026):
`apply`'s own port lookup (`compose ps`) failed, preflight then refused the deployment's own 8090
and 2500 as taken, and nothing said why. It now refuses before Compose is asked, naming the value.

What Compose refuses is what this reads (`harness.compose_env.unset_required`), and the CLI's own
copy (`ospreyflow stop`'s, which cannot import the harness) answers the same:
`${X:?}` unset or empty, `${X?}` unset only; `${X}`, `${X:-d}` and `$${X:?}` never; a value from the
shell or an `export X=v` line held.
- `test_applys_own_port_lookup_names_the_missing_value`
- `test_what_compose_refuses_is_read_the_same_by_both_copies`
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
    ],
)  # fmt: skip
def test_what_compose_refuses_is_read_the_same_by_both_copies(
    tmp_path: Path, env: str, shell: dict[str, str], missing: list[str]
) -> None:
    folder = _deployment(tmp_path, env)
    assert compose_env.unset_required(folder, shell) == missing
    assert cli_run.unset_required(folder, shell) == missing


def test_applys_own_port_lookup_names_the_missing_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _deployment(tmp_path, "HELD=1\n")
    asked: list[list[str]] = []
    monkeypatch.setattr(apply, "_run", lambda args, **_: asked.append(args) or "")
    with pytest.raises(apply.ApplyFailed) as refused:
        apply.own_published_ports(folder / "compose.yaml")
    words = refused.value.detail
    assert "REQUIRED_EMPTY_REFUSED" in words and "backup set" in words, words
    assert "label=com.docker.compose.project=osprey-upg" in words
    assert asked == []  # Compose was never asked
