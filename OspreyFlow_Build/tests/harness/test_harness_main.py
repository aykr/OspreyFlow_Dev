"""`python -m harness <subcommand>` — the dispatcher `harness/Dockerfile`'s own `ENTRYPOINT` uses.

Five named subcommands, every one a `harness` module (`bundle` left for the developer repository's
own Makefile, ADR-114 Amendment 2), and one named bug this module's own first real run found: `preflight` is a package, and `import_module("harness.preflight").main` raises
`AttributeError` — only `harness.preflight.__main__` carries `main()`, the same distinction
`python -m harness.preflight` itself resolves via `runpy` and a bare `import_module` does not.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from harness.__main__ import _SUBCOMMANDS, main


def test_every_named_subcommand_resolves_to_a_module_carrying_main() -> None:
    """The real bug this file exists to catch: `harness.preflight` (the package) has no `main` of
    its own — only `harness.preflight.__main__` does. A dict mapping `preflight` to the package
    name would import cleanly and fail only when actually dispatched to, which is exactly the gap
    between "the module resolves" and "the module has what this dispatcher needs" that a bare
    `importlib.import_module` smoke test would miss."""
    import importlib

    for subcommand, module_name in _SUBCOMMANDS.items():
        module = importlib.import_module(module_name)
        assert hasattr(module, "main"), (
            f"{subcommand!r} maps to {module_name!r}, which has no main() — "
            "docker run ... <image> " + subcommand + " would fail with AttributeError"
        )


def test_no_subcommand_dispatches_to_the_browser_setup_harness() -> None:
    """`Stage 2 §6` part A, built 26 September 2026: no subcommand is no longer a refusal — it is
    `harness.webapp.main`, `05_DEPLOYMENT.md` §2's own bootstrap command's real target. Patches
    the real entrypoint (the same shape `test_dispatches_to_the_right_module_with_the_remaining_
    arguments` already uses for a named subcommand) rather than calling it directly, since the
    real one blocks forever running a server."""
    calls: list[list[str] | None] = []

    def _fake_webapp_main(argv: list[str] | None) -> int:
        calls.append(argv)
        return 0

    with patch("harness.webapp.main", _fake_webapp_main):
        assert main([]) == 0
    assert calls == [[]]


def test_a_flag_like_first_argument_also_dispatches_to_the_webapp_not_an_unknown_subcommand() -> (
    None
):
    """`--host`/`--port`/`--config` are `harness.webapp._parse_args`'s own options, not subcommand
    names — every real subcommand is a bare word. Found needing this: the keyboard spec's own test
    server passes `--config` to point the webapp at a scratch file, and the first version of this
    dispatch (empty-argv-only) treated that as an unknown subcommand and refused it."""
    calls: list[list[str] | None] = []

    def _fake_webapp_main(argv: list[str] | None) -> int:
        calls.append(argv)
        return 0

    with patch("harness.webapp.main", _fake_webapp_main):
        result = main(["--host", "127.0.0.1", "--port", "7217"])

    assert result == 0
    assert calls == [["--host", "127.0.0.1", "--port", "7217"]]


def test_an_unknown_subcommand_is_named_and_refused() -> None:
    assert main(["not-a-real-subcommand"]) == 2


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_flags_exit_zero(flag: str) -> None:
    assert main([flag]) == 0


def test_dispatches_to_the_right_module_with_the_remaining_arguments() -> None:
    """Proves the dispatch itself, not just that each module happens to be importable: a fake
    `main()` records exactly the `argv` it was called with, so this also proves the subcommand
    token itself is stripped rather than passed through."""
    calls: list[list[str] | None] = []

    def _fake_main(argv: list[str] | None) -> int:
        calls.append(argv)
        return 0

    with patch("harness.render.main", _fake_main):
        result = main(["render", "--profile", "local-lite", "--check"])

    assert result == 0
    assert calls == [["--profile", "local-lite", "--check"]]


def test_bundle_is_no_longer_a_harness_subcommand() -> None:
    """`06_DECISIONS.md` ADR-114 Amendment 2: building a bundle is a release step of the developer
    repository (`make bundle` there), so the product's dispatcher names no module outside the
    `harness` package, and asking it for `bundle` is an unknown subcommand."""
    assert "bundle" not in _SUBCOMMANDS
    assert all(module.startswith("harness.") for module in _SUBCOMMANDS.values())
    assert main(["bundle"]) == 2
