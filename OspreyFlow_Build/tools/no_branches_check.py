"""No branches anywhere (`06_DECISIONS.md` ADR-144 Amendment 1, the owner's ruling of 7 November
2026): no route, screen, module or test in the Glass or the Conduit makes, lists or reads a case's
branch once L3.2 merges. A case is the only container and a view is a saved lens on it.

It scans every source file under `apps/workspace/src` and `services/api` in `OspreyFlow_Core`
for the word *branch* in any case and any form (`branch`, `Branched`, `branchNodes`,
`BRANCH_CASE`, `/branch-by-filter`), and names each line that holds one. Two other meanings stay,
as the amendment's decision 4 says:

- **a pipeline's branch** in the Ingest Studio's DAG (one source's path through a pipeline): only
  in the files listed in `PIPELINE_FILES`, each named with why. A new file using the word in that
  sense is added here by name, so a case's branch can never hide in a folder the Studio owns
  (`ingest/studio/datasets.ts` named a case's `branched_from` beside the DAG's files);
- **a git branch**: only the exact flags in `GIT_TOKENS`;
- **history written before L3.2**: only the stored labels in `STORED_BEFORE_L3_2`, in the one
  file that relabels them.

Run as `PYTHONPATH=../OspreyFlow_Build python -m tools.no_branches_check` from `OspreyFlow_Core`;
exits 1 and names each line. `tests/test_no_branches_check.py` plants a branch word in the shapes
the real code used (a `.tsx` identifier, a route string, a Python attribute, a right's name) and
shows each flagged, and shows that a folder-wide exception would have hidden one.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from tools.layout import CORE

#: The trees the amendment names, relative to `OspreyFlow_Core`.
SCANNED = ("apps/workspace/src", "services/api")
SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".css", ".html", ".md"})

#: Files where *branch* means a pipeline's branch in the Studio's DAG, each by name.
PIPELINE_FILES: Mapping[str, str] = {
    "services/api/pipeline_run.py": "runs a pipeline, one branch per source",
    "services/api/recipe_run.py": "a pipeline run's report, per source branch",
    "services/api/recipe_runs.py": "the run ledger, one record per pipeline branch",
    "services/api/run_source.py": "the file one source branch of a pipeline reads",
    "apps/workspace/src/ingest/dag/pipelineGraphEdit.ts": "adds a source branch to the DAG",
    "apps/workspace/src/ingest/dag/pipelineGraphEdit.test.ts": "its tests",
    "apps/workspace/src/ingest/dag/PipelineCanvas.test.tsx": "the DAG canvas's tests",
    "apps/workspace/src/ingest/dag/PipelineStudio.test.tsx": "the DAG editor's tests",
    "apps/workspace/src/ingest/publish/PublishScreen.tsx": "a pipeline run's report per branch",
    "apps/workspace/src/ingest/publish/PublishScreen.test.tsx": "its tests",
    "apps/workspace/src/ingest/publish/PublishScreen.deduplicate.test.tsx": "its tests",
    "services/api/load_records.py": "a pipeline run's records, one per source branch",
}

#: The git meaning: these exact tokens, anywhere.
GIT_TOKENS = ("--initial-branch",)

#: History written before L3.2 (ADR-144 Amendment 1 decision 4 keeps history as written): the
#: labels case histories stored, which the relabelling SQL still has to recognise, or it would
#: rewrite those rows. Only these literals, and only in this file.
STORED_BEFORE_L3_2: Mapping[str, tuple[str, ...]] = {
    "services/api/history.py": ("'Branched from %'", "'Branched'"),
}

_WORD = re.compile(r"branch", re.IGNORECASE)


def findings(files: Mapping[str, str]) -> list[tuple[str, int, str]]:
    """Each `(path, line number, line)` holding the word outside the two kept meanings."""
    found: list[tuple[str, int, str]] = []
    for path, text in sorted(files.items()):
        if path in PIPELINE_FILES:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line
            for token in (*GIT_TOKENS, *STORED_BEFORE_L3_2.get(path, ())):
                stripped = stripped.replace(token, "")
            if _WORD.search(stripped):
                found.append((path, number, line.strip()))
    return found


def tree_files(core: Path = CORE, scanned: Iterable[str] = SCANNED) -> dict[str, str]:
    files: dict[str, str] = {}
    for top in scanned:
        for path in sorted((core / top).rglob("*")):
            if (
                path.is_file()
                and path.suffix in SUFFIXES
                and "node_modules" not in path.parts
                and "__pycache__" not in path.parts
            ):
                files[path.relative_to(core).as_posix()] = path.read_text(errors="replace")
    return files


def main() -> int:
    found = findings(tree_files())
    for path, number, line in found:
        print(f"{path}:{number}: {line}")
    if found:
        print(
            f"no-branches-check: {len(found)} line(s) name a branch (ADR-144 Amendment 1). A case "
            "is the only container and a view a saved lens on it; a pipeline's branch belongs in "
            "a file named in PIPELINE_FILES, a git branch only as a flag in GIT_TOKENS."
        )
        return 1
    print(f"no-branches-check: {len(tree_files())} files, no branch named.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
