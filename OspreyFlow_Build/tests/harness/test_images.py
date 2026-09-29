"""`harness/images.py`'s `registry_digest_resolver` — ADR-049's Stage 2 §5b: `_render_versions_
lock`'s own comment names why the bundle needs registry resolution rather than the local-daemon
one `docker_digest_resolver` already provides: a bundle recipient's own daemon has pulled nothing
yet. The real, positive case (a real public image, a real registry round trip) is exercised for
real by the bundle's own exit test (`tests/harness/test_bundle_exit_test.py`), which needs Docker
and network access this fast unit tier does not assume; this file covers the failure contract,
which needs neither.
"""

from __future__ import annotations

import pytest
from harness import images
from harness.images import registry_digest_resolver


def test_an_image_that_does_not_exist_resolves_to_none() -> None:
    """No digest available is `None`, never a guess — the same contract `docker_digest_resolver`
    already holds itself to, checked here for the registry-backed resolver."""
    assert registry_digest_resolver("ospreyflow/this-image-does-not-exist-anywhere:latest") is None


def test_a_malformed_image_reference_resolves_to_none_rather_than_raising() -> None:
    assert registry_digest_resolver("not a valid image ref!!") is None


# --- `daemon_then_registry_digest_resolver` — round 11, `harness.render`'s own default ------------


def test_falls_back_to_the_registry_when_the_daemon_has_not_pulled_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real shape a fresh customer laptop is in: `render` runs before Launch ever calls `docker
    compose pull`, so the daemon has nothing — and this is exactly the case this round's fix
    exists for (a real published owned image must still resolve with no local pull)."""
    monkeypatch.setattr(images, "docker_digest_resolver", lambda _image: None)
    monkeypatch.setattr(images, "registry_digest_resolver", lambda _image: f"sha256:{'a' * 64}")
    assert (
        images.daemon_then_registry_digest_resolver("ghcr.io/ospreyflow/api:deadbeef")
        == f"sha256:{'a' * 64}"
    )


def test_prefers_the_daemon_over_the_registry_when_both_would_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _registry_should_not_be_called(_image: str) -> str | None:
        raise AssertionError("the registry must not be queried once the daemon already answered")

    monkeypatch.setattr(images, "docker_digest_resolver", lambda _image: f"sha256:{'b' * 64}")
    monkeypatch.setattr(images, "registry_digest_resolver", _registry_should_not_be_called)
    assert (
        images.daemon_then_registry_digest_resolver("ghcr.io/ospreyflow/api:deadbeef")
        == f"sha256:{'b' * 64}"
    )


def test_resolves_to_none_when_neither_the_daemon_nor_the_registry_knows_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(images, "docker_digest_resolver", lambda _image: None)
    monkeypatch.setattr(images, "registry_digest_resolver", lambda _image: None)
    assert images.daemon_then_registry_digest_resolver("ghcr.io/ospreyflow/api:deadbeef") is None
