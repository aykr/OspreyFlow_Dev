"""`ospreyflow repair-sign-in` (ADR-114 Amendment 22): the deployment's sign-in registered again —
`harness.register_sign_in` for the deployment's own profile — in place of `make register-sign-in`.

What a mistake would do, and the case that catches it:
- the wrong deployment's realm touched — `test_it_registers_the_sign_in_of_the_installed_deployment`;
- demo accounts made on an install that has none — `test_no_demo_accounts_is_passed_on`;
- a repair attempted with nothing installed — `test_with_nothing_installed_it_says_so_and_runs_nothing`.
"""

from __future__ import annotations

import pytest

from .conftest import Rig


def test_it_registers_the_sign_in_of_the_installed_deployment(rig: Rig) -> None:
    rig.install_deployment()
    assert rig("repair-sign-in") == 0
    python = str(rig.product / ".venv" / "bin" / "python")
    (step,) = rig.runner.argvs()
    assert step == [python, "-m", "harness.register_sign_in", "--profile", "local-lite"]


def test_no_demo_accounts_is_passed_on(rig: Rig) -> None:
    rig.install_deployment()
    assert rig("repair-sign-in", "--no-demo-accounts") == 0
    (step,) = rig.runner.argvs()
    assert step[-1] == "--no-demo-accounts"


def test_with_nothing_installed_it_says_so_and_runs_nothing(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("repair-sign-in") == 1
    assert "install" in capsys.readouterr().err
    assert rig.runner.calls == []
