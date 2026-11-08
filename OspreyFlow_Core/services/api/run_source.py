"""Which files a run of a Studio recipe reads, and whether they are the files Verify checked
(`spec/09_INGEST_STUDIO.md` §5, "Verify and Run read the same file"; build order step 30).

Found in the 3 November rehearsal (chapter 4): Verify read the draft's own `source_location`
while a pipeline's run read its source node's own location first
(`pipeline_run.run_published_pipeline`), so a file chosen in one place passed Verify and the run
loaded another. Both now ask `files_a_run_reads`, so they cannot disagree on which file; and Verify
records each file it read with the SHA-256 of its bytes (`VerifiedSource`), so a *Run now* whose
file is no longer that file, by name or by content, is refused in words before anything is read
into a store (`changed_since_verify`).
"""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel
from services.ingest.pipeline import pipeline_from_recipe

from schemas.ingest import PipelineGraph, PipelineNode, PipelineNodeKind, StudioRecipeDraft

from .studio_profile import SourceUnreadableError, _confined
from .studio_publish import load_published_recipe

__all__ = [
    "SourceChangedSinceVerifyError",
    "VerifiedSource",
    "branch_location",
    "changed_since_verify",
    "files_a_run_reads",
    "identify",
    "pipeline_of",
    "topological",
]

_CHUNK = 1 << 20


class VerifiedSource(BaseModel):
    """One file Verify read: where, and the SHA-256 of its bytes when it read them. Kept on the
    recipe's registry row (`studio_recipes.verified_sources`), never served to the Glass."""

    location: str
    sha256: str


class SourceChangedSinceVerifyError(Exception):
    """A *Run now* whose file is not the one Verify checked. The message is the sentence the
    Glass shows; it names files by their file names, never the server's path to them."""


def topological(graph: PipelineGraph) -> list[PipelineNode]:
    """Kahn's order, ties broken by node id — the save gate guarantees acyclicity, but a runner
    ordering is re-derived here rather than trusted from the stored node list's accidents."""
    by_id = {n.id: n for n in graph.nodes}
    indegree = dict.fromkeys(by_id, 0)
    forward: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.source in by_id and edge.target in by_id:
            indegree[edge.target] += 1
            forward.setdefault(edge.source, []).append(edge.target)
    queue = deque(sorted(node_id for node_id, n in indegree.items() if n == 0))
    ordered: list[PipelineNode] = []
    while queue:
        at = queue.popleft()
        ordered.append(by_id[at])
        for nxt in sorted(forward.get(at, [])):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return ordered


def pipeline_of(draft: StudioRecipeDraft, repo_root: Path | None) -> PipelineGraph:
    """The pipeline a run executes: the committed recipe's for a published row, else the draft's
    own (or a v1 draft's canonical chain)."""
    recipe = (
        load_published_recipe(draft, repo_root)
        if draft.git_path and repo_root is not None
        else None
    )
    if recipe is not None and recipe.pipeline is not None:
        return recipe.pipeline
    return pipeline_from_recipe(draft)


def branch_location(node: PipelineNode, source_location: str | None) -> str | None:
    """The file one source branch reads: its node's own location, else the run's, else (left
    `None` here) the recipe's recorded one."""
    return node.config.get("source_location") or source_location


def files_a_run_reads(
    draft: StudioRecipeDraft, *, repo_root: Path | None, source_location: str | None = None
) -> list[str]:
    """Every file a run of `draft` reads, each once, in the order the run reads them — the one
    answer Verify and Run both use. A recipe holding a pipeline reads one file per source branch
    (`pipeline_run.run_published_pipeline`); one without, its one file (`run_published_recipe`)."""
    if draft.pipeline is None:
        locations = [source_location or draft.source_location]
    else:
        locations = [
            branch_location(node, source_location) or draft.source_location
            for node in topological(pipeline_of(draft, repo_root))
            if node.kind is PipelineNodeKind.SOURCE
        ]
    return list(dict.fromkeys(location for location in locations if location))


def identify(location: str, dataset_id: str | None) -> VerifiedSource:
    """The file at `location` as it is now: read through the same confinement every source read
    passes (`studio_profile._confined`, for the recipe's dataset), its bytes hashed in chunks."""
    digest = hashlib.sha256()
    try:
        with Path(_confined(location, dataset_id)).open("rb") as handle:
            while chunk := handle.read(_CHUNK):
                digest.update(chunk)
    except OSError as exc:
        raise SourceUnreadableError(str(exc)) from exc
    return VerifiedSource(location=location, sha256=digest.hexdigest())


def _name(location: str) -> str:
    return Path(location).name or location


def changed_since_verify(
    verified: Sequence[VerifiedSource],
    now: Sequence[VerifiedSource],
    asked: str | None = None,
) -> str | None:
    """`None` when the run would read exactly the files Verify checked, byte for byte; otherwise
    the sentence that says what changed and asks for Verify again.

    `asked`: a file the person named for this run. One Verify did not check is refused even where
    the runner would not have read it — a source node naming its own file is read before a run's
    (`branch_location`), so the named file was once silently not loaded at all."""
    checked = {v.location: v.sha256 for v in verified}
    was = ", ".join(_name(v.location) for v in verified) or "no file"
    if asked and asked not in checked:
        return _another_file(was, _name(asked))
    if list(verified) == list(now):
        return None
    for source in now:
        if source.location in checked and checked[source.location] != source.sha256:
            return (
                f"{_name(source.location)} has changed since Test checked it. Nothing was "
                "loaded. Run Test again, then run."
            )
    return _another_file(was, ", ".join(_name(s.location) for s in now) or "no file")


def _another_file(was: str, would: str) -> str:
    return (
        f"Test checked {was}; this run would read {would}. Nothing was loaded. A run reads "
        "only the file Test checked: choose this file as the source and run Test again, "
        "then run."
    )
