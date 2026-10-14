"""Each release publishes the Enterprise chart (ADR-114 Amendment 17): packaged at the tag's version,
pushed to the registry as an OCI artifact, signed keyless by digest and as a file, verified with the
rest of the release before it is published, and attached to the release.

Read from `.github/workflows/release.yml` itself; the commands the steps run were proved against a
throwaway registry with a throwaway key (the amendment has the run). The keyless identity is proved
only by the first real release, as the images' was.
"""

from __future__ import annotations

from typing import Any

import yaml

from harness.render import REPO_ROOT

RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"


def _release_job() -> dict[str, Any]:
    workflow = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    job = workflow["jobs"]["release"]
    assert isinstance(job, dict)
    return job


def _script(job: dict[str, Any]) -> str:
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


def test_the_chart_is_packaged_at_the_tags_version() -> None:
    script = _script(_release_job())
    assert "helm package deploy/helm/ospreyflow" in script
    assert '--version "${GITHUB_REF_NAME#v}"' in script
    assert '--app-version "$GITHUB_REF_NAME"' in script


def test_the_chart_is_pushed_and_signed_by_digest() -> None:
    job = _release_job()
    assert job["permissions"].get("packages") == "write"
    script = _script(job)
    assert "helm push" in script and 'oci://ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/charts' in script
    assert 'cosign sign --yes "$CHART_REF"' in script


def test_the_chart_file_is_signed_verified_and_attached() -> None:
    script = _script(_release_job())
    tgz = 'ospreyflow-${GITHUB_REF_NAME#v}.tgz'
    assert f'cosign sign-blob --yes --bundle "{tgz}.sigstore.json" "{tgz}"' in script
    verify = next(s["run"] for s in _release_job()["steps"] if "harness.signatures" in str(s.get("run")))
    assert f'--blob "{tgz}"' in verify and f'--blob-signature "{tgz}.sigstore.json"' in verify
    assert '--artifact "$CHART_REF"' in verify
    publish = next(s["run"] for s in _release_job()["steps"] if "gh release create" in str(s.get("run")))
    assert f'"{tgz}" "{tgz}.sigstore.json"' in publish


def test_the_chart_is_verified_before_the_release_is_published() -> None:
    steps = [str(s.get("run", "")) for s in _release_job()["steps"]]
    push = next(i for i, s in enumerate(steps) if "helm push" in s)
    verify = next(i for i, s in enumerate(steps) if "harness.signatures" in s)
    publish = next(i for i, s in enumerate(steps) if "gh release create" in s)
    assert push < verify < publish
