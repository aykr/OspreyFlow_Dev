"""`ospreyflow install --gui` (ADR-114 Amendment 3 decision 6, stage B2c): the command copies the
product's osprey.yaml to a draft, starts the guided page behind a one-time token, opens it, and
waits for it.

What a mistake would do, and the case that catches it:
- the screens editing the product's own osprey.yaml — `test_gui_copies_osprey_yaml_to_a_draft`;
- a page started without its token or on a guessable address —
  `test_gui_starts_the_page_with_a_token_and_a_port`;
- the browser opened at a link that does not carry the token —
  `test_gui_opens_the_link_carrying_that_token`;
- the command returning before the install ends, or hiding its failure —
  `test_gui_waits_and_returns_the_pages_exit_code`;
- the doctor run before the page, where its failures could not be shown on a screen —
  `test_gui_does_not_run_the_doctor_first`;
- a secret printed — `test_gui_prints_no_secret`;
- the page started for a mode that is not an install on this machine, or a build with no
  checkout — `test_gui_on_a_missing_checkout_is_refused`;
- a page served unbuilt or stale (ADR-114 Amendment 11) —
  `test_gui_makes_the_page_ready_before_it_starts_it`, `test_with_no_page_to_serve_nothing_is_started`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from ospreyflow import main as command

from .conftest import Rig


class FakeServer:
    def __init__(self, code: int) -> None:
        self.code = code
        self.waited = False

    def wait(self) -> int:
        self.waited = True
        return self.code


class Starter:
    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.calls: list[dict[str, Any]] = []
        self.server = FakeServer(code)

    def __call__(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
    ) -> FakeServer:
        draft = Path(argv[argv.index("--draft") + 1])
        self.calls.append(
            {"argv": list(argv), "env": env, "cwd": cwd, "draft_text": draft.read_text("utf-8")}
        )
        return self.server


def gui(rig: Rig, starter: Starter, *extra: str) -> int:
    return command.main(
        ["install", "--mode", "lite", "--gui", *extra],
        runner=rig.runner,
        probes=rig.probes,
        home_env={"OSPREYFLOW_HOME": str(rig.product), **rig.env},
        recorded_home=lambda: None,
        capture=rig.capture,
        ask=rig.ask,
        open_url=rig.opened.append,
        start_server=starter,
    )


def arg(call: dict[str, Any], name: str) -> str:
    argv = call["argv"]
    return str(argv[argv.index(name) + 1])


def test_gui_copies_osprey_yaml_to_a_draft(rig: Rig) -> None:
    before = (rig.product / "osprey.yaml").read_text(encoding="utf-8")
    starter = Starter()
    assert gui(rig, starter) == 0
    draft = rig.product / ".install" / "osprey.draft.yaml"
    assert yaml.safe_load(draft.read_text(encoding="utf-8")) == yaml.safe_load(before)
    assert arg(starter.calls[0], "--draft") == str(draft)
    assert (rig.product / "osprey.yaml").read_text(encoding="utf-8") == before
    assert starter.calls[0]["draft_text"] == draft.read_text(encoding="utf-8")


def test_gui_starts_the_page_with_a_token_and_a_port(rig: Rig) -> None:
    starter = Starter()
    gui(rig, starter)
    call = starter.calls[0]
    assert call["argv"][1:3] == ["-m", "harness.install_page"]
    assert arg(call, "--product") == str(rig.product)
    assert len(arg(call, "--token")) >= 32
    assert 1024 <= int(arg(call, "--port")) <= 65535
    assert arg(call, "--answers") == str(rig.product / ".install" / "install.yaml")
    assert call["cwd"] == rig.product
    assert str(rig.product / "cli") in str(call["env"]["PYTHONPATH"])


def test_each_run_has_its_own_token(rig: Rig) -> None:
    first, second = Starter(), Starter()
    gui(rig, first)
    gui(rig, second)
    assert arg(first.calls[0], "--token") != arg(second.calls[0], "--token")


def test_gui_opens_the_link_carrying_that_token(rig: Rig) -> None:
    starter = Starter()
    gui(rig, starter)
    call = starter.calls[0]
    assert rig.opened == [f"http://127.0.0.1:{arg(call, '--port')}/?token={arg(call, '--token')}"]


def test_gui_waits_and_returns_the_pages_exit_code(rig: Rig) -> None:
    starter = Starter(code=7)
    assert gui(rig, starter) == 7
    assert starter.server.waited
    ok = Starter(code=0)
    assert gui(rig, ok) == 0


def test_gui_does_not_run_the_doctor_first(rig: Rig) -> None:
    rig.probes.missing.add("git")  # the doctor would refuse; the page shows it on Review instead
    starter = Starter()
    assert gui(rig, starter) == 0
    assert [c.argv[1:3] for c in rig.runner.calls] == [["-m", "harness.install_page_build"]]
    assert len(starter.calls) == 1


def test_gui_prints_no_secret(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    rig.install_deployment()
    (rig.deployment / "deployment.env").write_text("DB_PASSWORD=s3cr3t-value\n", encoding="utf-8")
    (rig.product / "osprey.yaml").write_text(
        yaml.safe_dump({"profile": "local-lite", "models": {"hosted_api_key": "k3y-value"}}),
        encoding="utf-8",
    )
    starter = Starter()
    gui(rig, starter)
    shown = capsys.readouterr()
    for text in (shown.out, shown.err):
        assert "s3cr3t-value" not in text and "k3y-value" not in text
    assert "install page" in shown.out.lower()
    assert "closes" in shown.out.lower() or "close" in shown.out.lower()


def test_gui_on_a_missing_checkout_is_refused(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    starter = Starter()
    code = command.main(
        ["install", "--mode", "lite", "--gui"],
        home_env={"OSPREYFLOW_HOME": str(rig.product / "nowhere")},
        recorded_home=lambda: None,
        probes=rig.probes,
        start_server=starter,
        open_url=rig.opened.append,
    )
    assert code == 1 and starter.calls == [] and rig.opened == []
    assert "OSPREYFLOW_HOME" in capsys.readouterr().err


def test_gui_makes_the_page_ready_before_it_starts_it(rig: Rig) -> None:
    """ADR-114 Amendment 11: built from this checkout, or the release's own, signed — first."""
    starter = Starter()
    assert gui(rig, starter) == 0
    (call,) = rig.runner.calls
    assert call.argv[1:] == ["-m", "harness.install_page_build", "--product", str(rig.product)]
    assert len(starter.calls) == 1


def test_with_no_page_to_serve_nothing_is_started(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.runner.fail["harness.install_page_build"] = 1
    starter = Starter()
    assert gui(rig, starter) == 1
    assert starter.calls == [] and rig.opened == []
    assert "install page" in capsys.readouterr().err
