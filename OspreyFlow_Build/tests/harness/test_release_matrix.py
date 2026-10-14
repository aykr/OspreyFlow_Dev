"""Every image a pulled deployment names from the release's own registry is one the release builds
(`.github/workflows/release.yml`'s matrix) — ADR-114 Amendment 8 point 10, Amendment 10 point 6.

Found 14 October 2026: Superset was named `osprey/superset:local` in pull mode, an image that exists
only where it was built, and the release built none; nothing compared the two lists.
"""

from __future__ import annotations

import re

import yaml
from harness.render import OWNED_IMAGE_REGISTRY, REPO_ROOT, render
from schemas.deployment import OspreyConfig

from tests.harness.test_cluster_render import _resolver, cluster_config

RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"


def _built_by_the_release() -> set[str]:
    workflow = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    matrix = workflow["jobs"]["images"]["strategy"]["matrix"]["include"]
    return {entry["service"] for entry in matrix}


def _owned(text: str) -> set[str]:
    return set(re.findall(re.escape(OWNED_IMAGE_REGISTRY) + r"/([a-z0-9-]+):", text))


def test_a_pulled_small_deployment_names_only_images_the_release_builds() -> None:
    config = OspreyConfig.model_validate(
        {"profile": "small", "reporting": {"sync": True, "superset": True}}
    )
    compose = render(config, resolver=_resolver).artefacts["compose.yaml"]
    named = _owned(compose)
    assert {"api", "workspace", "superset"} <= named
    assert named <= _built_by_the_release()


def test_a_cluster_names_only_images_the_release_builds() -> None:
    values = render(cluster_config(), resolver=_resolver).artefacts["values.yaml"]
    named = _owned(values)
    assert {"api", "workspace", "worker", "report-sync", "superset", "ner"} <= named
    assert named <= _built_by_the_release()
