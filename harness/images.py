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
    """One container in a rendered deployment."""

    service: str
    image: ImageRef
    #: False for the components a reduced or smaller profile drops.
    always: bool = True


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
