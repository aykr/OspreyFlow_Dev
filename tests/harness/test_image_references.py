"""Every third-party image the renderer names must actually exist.

**Why this test exists, precisely.** Eight third-party references were written for Stage 2 §5a from
memory rather than checked. Two did not exist — `minio/minio:RELEASE.2024-10-13T13-34-11Z` and
`ghcr.io/speaches-ai/speaches:0.6.2` — and nothing caught it until a real `docker compose up`
aborted the entire pull with `manifest unknown`, taking five other images' downloads with it. Every
unit test passed the whole time, because none of them asked the one question that mattered: does
this reference resolve?

This is `CLAUDE.md` rule 15's second worked example in a different costume — a check that only ever
runs against things it invented cannot discover that they are invented.

Needs a Docker daemon and network, so it is skipped without one rather than failing. That is a real
weakness and is stated rather than hidden: a skip here means nobody checked, and the two bad tags
would skip just as quietly as the six good ones.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
from harness.render import service_images

from schemas.deployment import OspreyConfig


def _daemon_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "info"], capture_output=True, timeout=30, check=False
        ).returncode
        == 0
    )


requires_docker = pytest.mark.skipif(
    not _daemon_available(), reason="needs a Docker daemon — a skip here means nobody checked"
)

THIRD_PARTY = [
    image.image for image in service_images(OspreyConfig.model_validate({})) if not image.owned
]


def test_the_renderer_names_some_third_party_images() -> None:
    """Guards the parametrised test below against passing by having nothing to check."""
    assert len(THIRD_PARTY) >= 6, THIRD_PARTY


@requires_docker
@pytest.mark.parametrize("reference", THIRD_PARTY)
def test_every_third_party_image_reference_resolves(reference: str) -> None:
    """Resolvable means: the registry knows it, **or** this machine already has it.

    `docker manifest inspect` asks the registry without pulling layers, which is the same question
    `docker compose up` asks at a fraction of the bytes — but some registries (quay.io among them)
    refuse anonymous manifest inspection, and reporting a working image as missing would make this
    check worse than useless. So a locally-present image counts.

    That fallback is weaker and the weakness is stated: an image nobody has ever pulled and whose
    registry refuses inspection would pass here. It still catches the case this test was written
    for — a reference that does not exist anywhere, which is neither inspectable nor local.
    """
    from_registry = subprocess.run(
        ["docker", "manifest", "inspect", reference],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if from_registry.returncode == 0:
        return
    locally = subprocess.run(
        ["docker", "image", "inspect", reference],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert locally.returncode == 0, (
        f"{reference} resolves neither at its registry nor on this machine: "
        f"{from_registry.stderr.strip()}. A reference that does not exist aborts the whole "
        "`docker compose up`, taking every other image's download with it."
    )
