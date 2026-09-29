"""Fixtures shared by the harness tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_rendered_realm_leaks_in_from_the_developers_own_checkout(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Admin console requires sign-in once a realm has been rendered (ADR-051), and it looks for
    one under `out_root`, which defaults to this checkout's own `deploy/generated`. On a machine
    where the deployment has been applied that folder holds a real `realm.json`, so a test that does
    not pass its own `out_root` would find an enforced console, and pass in CI while failing on the
    owner's machine. Every harness test therefore starts from an empty default; the tests that
    want enforcement build their own `out_root` with a realm in it."""
    empty = tmp_path_factory.mktemp("no-deployment") / "generated"
    monkeypatch.setattr("harness.webapp.DEFAULT_OUT_ROOT", empty)
