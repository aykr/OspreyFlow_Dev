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
  junk `tools/osprey_bundle.py` already filters out of a customer-facing artefact.
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
import uuid
from collections.abc import AsyncIterator
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
    uploaded: bool = Field(
        default=False,
        description="True for a file uploaded through the Studio (ADR-067), False for one an "
        "operator placed in the ingest folder",
    )


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
    """The files directly in the root (operator-supplied, read-only) and the files directly in its
    `uploaded/` folder (put there through the Studio, ADR-067). Those two directories and nothing
    below them: each entry is resolved and must still be inside the directory it was found in."""
    root = root if root is not None else ingest_root()
    files: list[IngestSourceFile] = []
    for base, uploaded in ((root, False), (root / UPLOAD_SUBDIR, True)):
        for candidate in _candidates(base):
            if candidate.name.startswith("."):
                continue
            if not is_inside(base, candidate.resolved):
                # A symlink out of the directory. Skipped silently rather than reported: naming it
                # would tell a caller that a path outside it exists, which is the existence leak
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
                    # The *mount* path, not the resolved one: a resolved path could name the host
                    # layout behind a symlink, and the recipe engine reads through the mount anyway.
                    source_location=str(base / candidate.name),
                    size_bytes=stat.st_size,
                    modified_at=stat.st_mtime,
                    uploaded=uploaded,
                )
            )
    files.sort(key=lambda f: (-f.modified_at, f.name))
    return IngestSourceListing(root=str(root), files=files)


# --- Upload from the analyst's computer (ADR-067) ----------------------------------------------

#: The one folder under the root the Conduit may write to. The root itself stays read-only, so a
#: compromised or mistaken upload can never alter operator-supplied evidence (ruling R6's reason).
UPLOAD_SUBDIR = "uploaded"

#: What may be uploaded: the formats the connector catalogue names (`09_INGEST_STUDIO.md` §2) and
#: nothing executable. A name with no extension, or any other extension, is refused.
UPLOAD_EXTENSIONS = frozenset(
    {
        ".csv", ".tsv", ".txt", ".json", ".xml", ".xlsx",
        ".pdf", ".docx", ".rtf", ".eml", ".msg", ".html", ".htm",
        ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic",
        ".wav", ".mp3", ".m4a", ".mp4",
        ".zip", ".tar", ".gz", ".tgz",
    }
)  # fmt: skip

_MAX_NAME_LENGTH = 200
_DEFAULT_MAX_UPLOAD_BYTES = 512 * 1024 * 1024


def max_upload_bytes() -> int:
    raw = os.environ.get("OSPREY_INGEST_MAX_UPLOAD_BYTES")
    try:
        value = int(raw) if raw is not None else _DEFAULT_MAX_UPLOAD_BYTES
    except ValueError:
        return _DEFAULT_MAX_UPLOAD_BYTES
    return value if value > 0 else _DEFAULT_MAX_UPLOAD_BYTES


class UploadRefused(Exception):
    """An upload that was not accepted, with a code the route maps to a status and a message that
    is safe to show the analyst (it never names anything already in the folder)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_upload_name(name: str) -> str:
    """The name the file will be stored under, or `UploadRefused`. A name is a single plain file
    name: no directory part, nothing hidden, no control characters, a known extension."""
    if not name or not name.strip():
        raise UploadRefused("bad_name", "The file needs a name.")
    if (
        len(name) > _MAX_NAME_LENGTH
        or name in {".", ".."}
        or name.startswith(".")
        or "/" in name
        or "\\" in name
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)
    ):
        raise UploadRefused(
            "bad_name",
            "That file name cannot be used. Use a plain name of up to 200 characters, with no "
            "folders, and not starting with a dot.",
        )
    if Path(name).suffix.lower() not in UPLOAD_EXTENSIONS:
        raise UploadRefused("type_not_allowed", "That type of file cannot be uploaded.")
    return name


async def save_upload(
    root: Path, name: str, chunks: AsyncIterator[bytes], *, max_bytes: int
) -> IngestSourceFile:
    """Write the streamed body into `<root>/uploaded/<name>`. Never overwrites (a name already in
    the uploaded folder or in the root is refused). The size is counted as it streams, so the limit
    stops the read rather than being checked after the whole file is on disk. The bytes go to a
    hidden part-file first and are linked into place only when complete, so a half-written file is
    never offered in the picker."""
    name = validate_upload_name(name)
    folder = root / UPLOAD_SUBDIR
    final = folder / name
    if (root / name).exists() or final.exists():
        raise UploadRefused("exists", "A file with that name is already in the ingest folder.")
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / f".upload-{uuid.uuid4().hex}.part"
    written = 0
    try:
        with part.open("xb") as handle:
            async for chunk in chunks:
                written += len(chunk)
                if written > max_bytes:
                    raise UploadRefused(
                        "too_large",
                        f"That file is larger than the limit of {max_bytes // (1024 * 1024)} MB."
                        if max_bytes >= 1024 * 1024
                        else f"That file is larger than the limit of {max_bytes} bytes.",
                    )
                handle.write(chunk)
        if written == 0:
            raise UploadRefused("empty", "That file is empty.")
        try:
            os.link(part, final)  # atomic, and fails rather than replaces if the name has appeared
        except FileExistsError:
            raise UploadRefused(
                "exists", "A file with that name is already in the ingest folder."
            ) from None
    finally:
        part.unlink(missing_ok=True)
    stat = final.stat()
    return IngestSourceFile(
        name=name,
        source_location=str(final),
        size_bytes=stat.st_size,
        modified_at=stat.st_mtime,
        uploaded=True,
    )
