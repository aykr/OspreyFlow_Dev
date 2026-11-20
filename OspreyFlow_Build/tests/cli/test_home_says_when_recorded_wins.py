"""The command says so when the recorded home wins over a different product in the current folder
(`06_DECISIONS.md` ADR-114 Amendment 50, point 1; the resolution order itself is Amendment 3
decision 3 and does not change: `OSPREYFLOW_HOME`, then the recorded folder, then the walk up).

The fault (N05): a person standing in a fresh checkout B, with the bootstrap's recorded home A
pointing at another deployment's folder, had every command act on A without a word; and after a
repoint or a reinstall the recorded home went stale and nothing said so.

Rule 12, which test fails if the fault returns:
- the warning dropped, or never printed on standard error, or printed after the command has
  already acted — `test_the_recorded_home_winning_over_another_product_is_said_before_it_acts`
  (the call is the real entry, `ospreyflow.main.main`, with the runner and the streams captured);
- the warning naming only one of the two folders, or not how to choose the other —
  the same test (both folders and `OSPREYFLOW_HOME=<folder>` are asserted in the one line);
- the warning on a day when there is nothing to say — the same folder, a symlink to it, the
  developer layout found from inside its own product, no product in the current folder,
  `OSPREYFLOW_HOME` set, or the recorded home gone — `test_no_line_when_there_is_nothing_to_choose`
  (one case each, and each asserts what the command did, so a case cannot pass by the command
  failing);
- the order changed, so the current folder beats the recorded one (the other reading, which is an
  amendment to three accepted texts) — the first test asserts the command acted on the recorded
  folder, and `test_the_walk_up_still_wins_when_the_recorded_home_is_gone` that the walk up
  still serves when it is gone;
- the exit code changed by the warning — the first test asserts it is 0.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from ospreyflow.main import main

from .conftest import FakeProbes, FakeRunner


def _make_product(root: Path) -> Path:
    """What `tests/cli/test_home.py` plants, plus the rendered deployment `stop` acts on."""
    (root / "harness").mkdir(parents=True)
    (root / "harness" / "__init__.py").write_text("", encoding="utf-8")
    (root / "osprey.yaml").write_text(yaml.safe_dump({"profile": "local-lite"}), encoding="utf-8")
    out = root / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text("X=1\n", encoding="utf-8")
    return root


class _Run:
    def __init__(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self.tmp_path = tmp_path
        self.capsys = capsys
        #: What standard error held at the moment the command first ran something.
        self.before_acting = ""
        self.runner = FakeRunner()
        inner = self.runner.__call__

        def spy(argv: Sequence[str], **kwargs: Any) -> int:
            self.before_acting += capsys.readouterr().err
            return inner(argv, **kwargs)

        self.spy = spy

    def __call__(
        self, start: Path, *, recorded: Path | None, home: str | None = None
    ) -> tuple[int, list[str]]:
        """`ospreyflow stop`, run from `start` with `recorded` as the bootstrap's home."""
        env = {"HOME": str(self.tmp_path / "home")}
        if home is not None:
            env["OSPREYFLOW_HOME"] = home
        self.capsys.readouterr()
        self.before_acting = ""
        code = main(
            ["stop"],
            runner=self.spy,
            probes=FakeProbes(),
            home_env=env,
            recorded_home=lambda: recorded,
            start=start,
        )
        return code, (self.before_acting + self.capsys.readouterr().err).splitlines()

    def acted_on(self) -> Path:
        """The product whose rendered deployment the command ran Compose against."""
        (call,) = self.runner.calls
        compose = Path(call.argv[call.argv.index("-f") + 1])
        return compose.parents[3]


@pytest.fixture
def run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> _Run:
    return _Run(tmp_path, capsys)


def test_the_recorded_home_winning_over_another_product_is_said_before_it_acts(
    run: _Run, tmp_path: Path
) -> None:
    a = _make_product(tmp_path / "recorded-a")
    b = _make_product(tmp_path / "checkout-b")
    inside_b = b / "scripts"
    inside_b.mkdir()

    code, lines = run(inside_b, recorded=a)

    assert code == 0, lines
    assert run.acted_on() == a  # the order is unchanged: the recorded home wins
    (said,) = lines  # one line, and nothing else on standard error
    assert str(a) in said and str(b) in said
    assert "recorded" in said
    assert f"OSPREYFLOW_HOME={b}" in said
    assert said in run.before_acting  # said before the command ran anything, not after


def test_no_line_when_there_is_nothing_to_choose(run: _Run, tmp_path: Path) -> None:
    a = _make_product(tmp_path / "recorded-a")
    sub = a / "scripts"
    sub.mkdir()
    # The same folder.
    code, lines = run(sub, recorded=a)
    assert (code, lines, run.acted_on()) == (0, [], a)

    # The same folder, recorded through a link to it.
    run.runner.calls.clear()
    link = tmp_path / "link-to-a"
    link.symlink_to(a, target_is_directory=True)
    code, lines = run(sub, recorded=link)
    assert (code, lines, run.acted_on()) == (0, [], link)

    # No product in the current folder.
    run.runner.calls.clear()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    code, lines = run(elsewhere, recorded=a)
    assert (code, lines, run.acted_on()) == (0, [], a)

    # `OSPREYFLOW_HOME` set: the person chose, so there is nothing to say, even over a third product.
    run.runner.calls.clear()
    b = _make_product(tmp_path / "checkout-b")
    c = _make_product(tmp_path / "chosen-c")
    code, lines = run(b, recorded=a, home=str(c))
    assert (code, lines, run.acted_on()) == (0, [], c)


def test_the_developer_layout_is_compared_by_its_product_folder(run: _Run, tmp_path: Path) -> None:
    """The walk up finds `OspreyFlow_Core` from the repository root: that is the other folder."""
    a = _make_product(tmp_path / "recorded-a")
    core = _make_product(tmp_path / "dev" / "OspreyFlow_Core")
    (tmp_path / "dev" / "OspreyFlow_Build").mkdir()
    code, lines = run(tmp_path / "dev", recorded=a)
    assert code == 0 and run.acted_on() == a
    (said,) = lines
    assert str(core) in said and f"OSPREYFLOW_HOME={core}" in said

    # Run from inside that product, with it recorded: the same folder, nothing to say.
    run.runner.calls.clear()
    code, lines = run(core / "harness", recorded=core)
    assert (code, lines, run.acted_on()) == (0, [], core)


def test_the_walk_up_still_wins_when_the_recorded_home_is_gone(run: _Run, tmp_path: Path) -> None:
    b = _make_product(tmp_path / "checkout-b")
    code, lines = run(b, recorded=tmp_path / "gone")
    assert (code, lines, run.acted_on()) == (0, [], b)
