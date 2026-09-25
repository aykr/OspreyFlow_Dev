"""`harness/images.py`'s `registry_digest_resolver` — ADR-049's Stage 2 §5b: `_render_versions_
lock`'s own comment names why the bundle needs registry resolution rather than the local-daemon
one `docker_digest_resolver` already provides: a bundle recipient's own daemon has pulled nothing
yet. The real, positive case (a real public image, a real registry round trip) is exercised for
real by the bundle's own exit test (`tests/harness/test_bundle_exit_test.py`), which needs Docker
and network access this fast unit tier does not assume; this file covers the failure contract,
which needs neither.
"""

from __future__ import annotations

from harness.images import registry_digest_resolver


def test_an_image_that_does_not_exist_resolves_to_none() -> None:
    """No digest available is `None`, never a guess — the same contract `docker_digest_resolver`
    already holds itself to, checked here for the registry-backed resolver."""
    assert registry_digest_resolver("ospreyflow/this-image-does-not-exist-anywhere:latest") is None


def test_a_malformed_image_reference_resolves_to_none_rather_than_raising() -> None:
    assert registry_digest_resolver("not a valid image ref!!") is None
