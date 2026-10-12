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


def test_no_subcommand_starts_no_server_and_points_to_the_install_page(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ADR-114 decision 3 ("Remove them outright"): the Set-up console no longer listens for good.
    No subcommand — or only the webapp's own flags — is a refusal naming the guided install page,
    and the webapp is never started."""
    started: list[object] = []
    with patch("harness.webapp.main", lambda argv: started.append(argv) or 0):
        assert main([]) == 2
        assert main(["--host", "127.0.0.1", "--port", "7217"]) == 2
    assert started == []
    assert "ospreyflow install --gui" in capsys.readouterr().err


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
