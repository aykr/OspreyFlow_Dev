"""The image set a rendered deployment runs, and how a digest gets attached to each.

`05_DEPLOYMENT.md` §2.1 requires `versions.lock` "with every image digest pinned" among the four
generated artefacts, and §7 repeats it as a security property: "Images signed and verified at pull;
digests pinned in `deploy/versions.lock`."

**Checked directly before this module was written: this repository pins no image digests anywhere.**
`deploy/compose/dev.yaml` carries tags (`arcadedata/arcadedb:24.11.1`), not digests, and nothing
else names an image at all. So a renderer that emitted a `versions.lock` full of digests today would
have had to invent them, and an invented `sha256:` is worse than an absent one — it looks verified.

**What this module does instead: resolve, and refuse.** A `DigestResolver` returns the real digest
for an image reference or `None`. The default asks the local Docker daemon, which knows the digest
of anything it has pulled. When any image cannot be resolved, `render` fails and names them, rather
than writing a lock file whose own name is a lie. `--allow-unpinned` exists for the case where a
developer wants the other three artefacts on a machine with no daemon; it marks every unresolved
entry `unresolved` in the lock file, in those words, so nothing downstream can mistake it for a pin.

The resolver is a seam for the tests, not a stand-in for the behaviour under test: what the tests
assert is that `versions.lock` names every image the compose file runs and that each carries a
digest, which is a property of the renderer, not of Docker.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass

#: An image reference as written in a compose file — `repository:tag`, never a bare repository.
#: Tags match `deploy/compose/dev.yaml`'s own pins where the two overlap (ArcadeDB, MinIO, Valkey,
#: PostgreSQL), so a rendered `local-lite` stack and the dev convenience stack do not silently run
#: different versions of the same store.
ImageRef = str

#: Returns the `sha256:...` digest for an image reference, or `None` when it cannot be determined.
DigestResolver = Callable[[ImageRef], str | None]


@dataclass(frozen=True)
class ServiceImage:
    """One container in a rendered deployment.

    **`build_context` is what separates the two kinds of image this deployment runs.** A
    third-party image (ArcadeDB, PostgreSQL, Keycloak…) is pulled from a registry at a pinned tag
    and has a digest a registry can vouch for. An OspreyFlow-owned image has neither: no registry
    publishes `ghcr.io/ospreyflow/api` today, so a rendered compose file naming one produces a
    stack that cannot start. Owned services therefore render a `build:` stanza pointing at the
    Dockerfile in this repository plus a local tag, so `docker compose build` produces them with no
    registry involved at all (ADR-049 Stage 2 §5a).
    """

    service: str
    image: ImageRef
    #: Repository-relative directory holding this service's Dockerfile. `None` for third-party
    #: images, and the thing that makes "is this ours" a property of the data rather than a string
    #: match on the image name.
    build_context: str | None = None
    #: Relative to `build_context`'s own parent — compose needs the Dockerfile path and the context
    #: root separately, because the Python images build from the repository root (they COPY
    #: `packages/` and `services/`) while their Dockerfile lives beside the service.
    dockerfile: str | None = None
    #: False for the components a reduced or smaller profile drops.
    always: bool = True

    @property
    def owned(self) -> bool:
        return self.build_context is not None


def docker_digest_resolver(image: ImageRef) -> str | None:
    """Asks the local Docker daemon for an image's own repo digest.

    Returns `None` — never raises and never guesses — when Docker is absent, the daemon is down, the
    image has not been pulled, or the image was built locally and so has no registry digest at all.
    Every one of those is "no digest available", and the caller's job is to refuse, not this one's.
    """
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", image],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    reference = result.stdout.strip()
    _, _, digest = reference.partition("@")
    return digest if digest.startswith("sha256:") else None


def unresolved_digest_resolver(image: ImageRef) -> str | None:
    """Resolves nothing. The explicit choice for `--allow-unpinned`, so that path is a named
    resolver rather than a branch that skips the real one."""
    return None


def registry_digest_resolver(image: ImageRef) -> str | None:
    """Asks the image's own registry for its manifest digest, rather than the local daemon.

    `harness/render.py`'s own `_render_versions_lock` names exactly why the bundle needs this and
    `docker_digest_resolver` above does not suffice for it: a bundle recipient's own daemon has
    pulled nothing yet, so a `local-docker-daemon` digest is a snapshot of *this* machine's cache —
    "which is a snapshot, not an authority" — where a registry-resolved one is independently
    checkable by anyone who receives the bundle, against the same registry, forever.

    `docker buildx imagetools inspect` queries the registry's own manifest API directly (no pull),
    and needs no `docker login` for a public image — verified directly against `python:3.12-slim`
    and `postgres:16-alpine` while this was written, on a machine with no registry credentials
    configured at all. Returns `None` on any failure (no `buildx`, no network, a private image with
    no credentials, an unknown tag) — the same "no digest available, the caller refuses" contract
    `docker_digest_resolver` already holds itself to, never a guess.
    """
    try:
        result = subprocess.run(
            [
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                image,
                "--format",
                "{{.Manifest.Digest}}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    digest = result.stdout.strip()
    return digest if digest.startswith("sha256:") else None
