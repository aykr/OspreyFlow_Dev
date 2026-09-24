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


#: Registry responses that mean "I will not tell you", as opposed to "it is not here". A skip for
#: the first is honest; treating it as a pass would be a lie and as a failure would be noise.
_REFUSED_TO_ANSWER = ("toomanyrequests", "rate limit", "unauthorized", "denied", "timeout")

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
    """Three outcomes, not two, because the registry has three answers.

    **It resolves** — pass. **It says `manifest unknown`** — fail, which is the case this test was
    written for: two of eight references written for Stage 2 §5a did not exist, and a real
    `docker compose up` aborted the whole pull because of it. **It refuses to answer** — rate
    limited, unauthorised, timed out — which is not evidence either way, so this skips with the
    reason rather than inventing a verdict. A locally-present image satisfies any of the three,
    since `compose` will not need the registry for it.

    The skip is the honest weakness and is stated rather than hidden: a skipped reference is one
    nobody checked.
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

    error = (from_registry.stderr or "").strip().lower()

    # **"The registry refused to answer" is not "the image does not exist", and conflating them
    # makes this test worse than useless.** Anonymous Docker Hub manifest inspection is rate
    # limited, and a suite that goes red from rate limiting is one people learn to ignore — taking
    # the real finding with it the next time there is one. Observed directly: `postgres:16.4`
    # answered `toomanyrequests` minutes after answering correctly, while a genuinely absent tag
    # answers `manifest unknown`. The two are cleanly distinguishable, so they are distinguished.
    if any(marker in error for marker in _REFUSED_TO_ANSWER):
        locally = subprocess.run(
            ["docker", "image", "inspect", reference], capture_output=True, timeout=60, check=False
        )
        if locally.returncode == 0:
            return
        pytest.skip(
            f"the registry refused to answer for {reference} ({error.splitlines()[0]}) and it is "
            "not present locally — nobody checked this reference, which is not the same as it "
            "being fine"
        )

    locally = subprocess.run(
        ["docker", "image", "inspect", reference], capture_output=True, timeout=60, check=False
    )
    assert locally.returncode == 0, (
        f"{reference} resolves neither at its registry nor on this machine: {error}. A reference "
        "that does not exist aborts the whole `docker compose up`, taking every other image's "
        "download with it."
    )
