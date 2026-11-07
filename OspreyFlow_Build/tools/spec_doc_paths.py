"""The documents the product-tree link check and the build-calendar check scan (the owner's ruling
of 7 November 2026, "Widen to all of spec/").

Before the ruling both gates scanned `tools/route_coverage_check.py`'s fixed `APACHE_DOC_PATHS`, so
anything a lane wrote in a folder under `spec/` (`spec/glass_redesign/`,
`spec/ingest_studio_redesign/`) was never checked. Now every `spec/**/*.md` is scanned, plus the
fixed list's documents outside `spec/` (`DEMO_GUIDE.md`, `README.md`), except:

- `spec/06_DECISIONS.md`: the decision log cites the process tree and build phases as part of its
  history, and always has been out of scope (ADR-034 §B9);
- `spec/ADR_RESERVATIONS.md`: the orchestrator's ledger of reserved numbers; its rows quote the
  amendments' titles, which name the build phases they record;
- `spec/ingest_studio_redesign/BUILD_PLAN_INGEST_STUDIO.md`: a build plan, a schedule of phases by
  nature, kept beside the brief it plans.

`APACHE_DOC_PATHS` itself is unchanged, because the route and domain-model coverage gates read it.
Their red-then-green proof is `tests/test_spec_doc_paths.py`.
"""

from __future__ import annotations

from pathlib import Path

from tools.layout import REPO as REPO_ROOT
from tools.route_coverage_check import APACHE_DOC_PATHS

EXCLUDED = (
    "spec/06_DECISIONS.md",
    "spec/ADR_RESERVATIONS.md",
    "spec/ingest_studio_redesign/BUILD_PLAN_INGEST_STUDIO.md",
)


def spec_doc_paths(root: Path = REPO_ROOT) -> tuple[Path, ...]:
    """Every scanned document under `root`: the fixed list's non-spec documents and every spec file."""
    excluded = {root / e for e in EXCLUDED}
    spec = sorted(p for p in (root / "spec").rglob("*.md") if p not in excluded)
    fixed = [p for p in APACHE_DOC_PATHS if root == REPO_ROOT and "spec" not in p.relative_to(root).parts]
    return tuple(dict.fromkeys([*fixed, *spec]))


SCANNED_DOC_PATHS = spec_doc_paths()
