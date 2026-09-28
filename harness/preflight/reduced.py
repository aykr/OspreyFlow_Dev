"""`05_DEPLOYMENT.md` §3's reduced variant — offered, never applied silently.

§3, in full, because the last clause is the whole design:

> "If Preflight finds less than 16 GB it offers a reduced variant that drops OpenSearch and falls
> back to PostgreSQL full-text, stating the trade-off on screen: search quality degrades and
> semantic search is unavailable, and the platform otherwise works. **It is offered, not applied
> silently.**"

So this module has two halves that are deliberately not joined: `offer_for()` decides whether there
is an offer to make and what it says, and `accept()` is the only thing that changes anything on
disk. Nothing calls `accept()` except the explicit `--accept-reduced` flag. A design where a
below-floor memory reading re-rendered the deployment by itself would satisfy every other sentence
in §3 and violate the last one.

**Accepting re-renders through Stage 2 §1's renderer rather than editing the rendered files.** The
reduced variant is a different `osprey.yaml` (`components.search: postgres-fulltext`), and
`05_DEPLOYMENT.md` §2.1 is explicit: "never hand-edit a generated artefact — regenerate instead."
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harness.preflight.result import CheckResult, Status
from harness.render import render, write
from schemas.deployment import OspreyConfig, SearchBackend

#: What the reduced variant actually drops, named rather than described, so the offer can list it.
DROPPED_COMPONENTS = ("opensearch",)


@dataclass(frozen=True)
class ReducedVariantOffer:
    """An offer, not a decision. `lines` is the operator-facing text; nothing here has changed."""

    lines: tuple[str, ...]

    def render_text(self) -> str:
        return "\n".join(self.lines)


def offer_for(results: list[CheckResult], config: OspreyConfig) -> ReducedVariantOffer | None:
    """Returns the offer when the memory check failed and the reduced variant is not already in
    force; `None` otherwise.

    Gated on the memory check having *failed* rather than on re-reading the memory figure here: §3
    ties the offer to "if Preflight finds less than 16 GB", and the memory check is what finds
    that. Reading the probe a second time would let the two disagree.
    """
    memory_result = next((r for r in results if r.check == "memory"), None)
    if memory_result is None or memory_result.status is not Status.FAIL:
        return None
    if config.components.search is SearchBackend.POSTGRES_FULLTEXT:
        return None

    return ReducedVariantOffer(
        lines=(
            "",
            "OFFERED — the reduced variant (spec/05_DEPLOYMENT.md §3). Nothing has been changed.",
            "",
            f"  Drops: {', '.join(DROPPED_COMPONENTS)}",
            "  Falls back to: PostgreSQL full-text search",
            "",
            "  The trade-off, stated rather than buried:",
            "  search quality degrades and semantic search is unavailable.",
            "  The platform otherwise works.",
            "",
            "  To accept, re-run with --accept-reduced. That re-renders this profile through",
            "  `harness.render` with components.search set to postgres-fulltext. It is the only",
            "  thing that changes deploy/generated/, and it will not happen without that flag.",
        )
    )


def accept(config: OspreyConfig, out_dir: Path) -> tuple[OspreyConfig, list[Path]]:
    """Applies the reduced variant and re-renders. Returns the amended config and what was written.

    Called only from `--accept-reduced`. The amended config is returned rather than written back to
    `osprey.yaml`: `osprey.yaml` is the operator's own file, reviewed in a pull request (§2.1), and
    a Preflight flag is not the right thing to be editing it. Persisting the choice belongs to the
    Components screen (Stage 2 §6), which is where a deployment's own answers are recorded.
    """
    reduced = config.model_copy(
        update={
            "components": config.components.model_copy(
                update={"search": SearchBackend.POSTGRES_FULLTEXT}
            )
        }
    )
    written = write(render(reduced, allow_unpinned=True), out_dir)
    return reduced, written
