"""`GET /v1/ingest/source-files` — what an analyst can pick from in the Studio's Connect stage.

**Owner ruling R6, 27 September 2026.** Round 13b's over-the-wire exit test found that a rendered
deployment gives an analyst no route by which to supply a source file at all: `POST
/v1/ingest/recipes` takes a `source_location` the *Conduit's own container* must be able to read,
and nothing was mounted there, so eight acceptance rows (B1-B3, B6-B8, B13-B18) could not be
performed through the analyst's own door. R6's answer is the ingest root — bind-mounted read-only
into the Conduit for every profile — surfaced *through the existing Ingest Studio* rather than as
a bare drop folder: this route lists what is in it, the analyst picks one, and Connect continues to
Profile -> Map on the existing canvas with `source_location` set to the chosen file's container
path.

**This module's whole job is to enumerate one directory and refuse everything else**, so the
refusals are the interesting part and each one has a test:

- **Nothing outside the root, ever.** Every candidate is resolved (`Path.resolve()`, which
  collapses `..` *and* follows symlinks) and then checked to be inside the resolved root with
  `Path.is_relative_to`. A string check on the *unresolved* path would pass a symlink pointing at
  `/etc`, which is the failure this shape exists to prevent — the resolve happens before the
  comparison, not after.
- **No recursion into subdirectories, and no directories in the listing.** A flat listing keeps
  the traversal surface to exactly one directory, and a Connect stage that cannot express "descend"
  cannot be talked into descending.
- **No dotfiles.** `.DS_Store` and friends are host debris, never evidence — the same class of
  junk `scripts/osprey_bundle.py` already filters out of a customer-facing artefact.
- **A missing root is an empty list, not an error.** Docker creates a bind-mount source that does
  not exist, so an operator who has not yet put anything there is in a normal state, and the
  Studio should say "nothing here" rather than 500.

**Not an upload route, deliberately** — R6 puts that after the milestone. Nothing here writes,
which is also why the mount is `:ro` in the rendered compose: the Conduit reads evidence and never
alters it.

**Access control.** `StudioRole.SOURCE_AUTHOR`, the same role that already gates creating a recipe
draft (`POST /v1/ingest/recipes`) — listing the files you are about to point a draft at is the same
action, one step earlier, and a principal who cannot create the draft has no use for the list.
Per `CLAUDE.md` rule 2 the role is checked as a dependency on the route rather than filtered
afterwards, and per rule 4 the refusal has its own test.

**What this route deliberately does not do: infer handling.** A file's name says nothing about its
classification, and guessing one here would put a handling decision in a directory listing. The
Studio's own Connect stage already collects the three mandatory gate answers (handling, legal
basis, source) from the analyst, and that is where they stay.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

#: The container path the renderer mounts `components.storage.ingest` at
#: (`harness/render.py`'s `INGEST_CONTAINER_PATH`), carried in as an environment variable rather
#: than hard-coded a second time — `tests/harness/test_render.py` has the case that fails if the
#: two stop agreeing. Defaults to the same literal so a developer running the Conduit by hand
#: (`DEMO_GUIDE.md` §3.2) needs no extra environment.
_DEFAULT_INGEST_ROOT = "/var/lib/osprey/ingest"


def ingest_root() -> Path:
    return Path(os.environ.get("OSPREY_INGEST_ROOT", _DEFAULT_INGEST_ROOT))


class IngestSourceFile(BaseModel):
    """One pickable file. `source_location` is what a `ConnectDraftInput` carries straight
    through — the analyst never types a path, which is the point of the listing."""

    name: str = Field(description="The file's own name, with no directory part")
    source_location: str = Field(description="The container path to give the recipe draft")
    size_bytes: int
    modified_at: float = Field(description="Unix timestamp, for ordering by recency in the Glass")


class IngestSourceListing(BaseModel):
    root: str
    files: list[IngestSourceFile]


@dataclass(frozen=True)
class _Candidate:
    name: str
    resolved: Path


def _candidates(root: Path) -> list[_Candidate]:
    """Every entry directly in `root`, resolved. Separated from the filtering below so the
    traversal rule can be tested against a resolved path rather than an `os.scandir` result."""
    try:
        entries = sorted(root.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return []
    except PermissionError:
        # Readable-by-nobody is an operator problem and an empty list would hide it, but this is a
        # *listing* route — the honest thing is to surface nothing and let Preflight's own disk
        # check (which reports this root) be where the operator sees the state of it.
        return []
    return [_Candidate(name=e.name, resolved=e.resolve()) for e in entries]


def is_inside(root: Path, candidate: Path) -> bool:
    """**Resolve first, then compare.** `candidate` is already resolved by `_candidates`; `root`
    is resolved here so a deployment whose ingest root is itself reached through a symlink still
    compares like with like. A comparison on unresolved paths would accept a symlink inside the
    root that points anywhere on the filesystem."""
    try:
        return candidate.is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def list_source_files(root: Path | None = None) -> IngestSourceListing:
    root = root if root is not None else ingest_root()
    files: list[IngestSourceFile] = []
    for candidate in _candidates(root):
        if candidate.name.startswith("."):
            continue
        if not is_inside(root, candidate.resolved):
            # A symlink out of the root. Skipped silently rather than reported: naming it would
            # tell a caller that a path outside the root exists, which is the existence leak
            # `03_CONDUIT_MIDDLEWARE.md` §3 collapses everywhere else.
            continue
        try:
            stat = candidate.resolved.stat()
        except OSError:
            continue
        if not candidate.resolved.is_file():
            continue
        files.append(
            IngestSourceFile(
                name=candidate.name,
                # The *mount* path, not the resolved one — a resolved path could name the host
                # layout behind a symlink, and the recipe engine reads through the mount anyway.
                source_location=str(root / candidate.name),
                size_bytes=stat.st_size,
                modified_at=stat.st_mtime,
            )
        )
    files.sort(key=lambda f: (-f.modified_at, f.name))
    return IngestSourceListing(root=str(root), files=files)
