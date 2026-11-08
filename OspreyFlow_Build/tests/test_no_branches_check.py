"""`tools.no_branches_check` (ADR-144 Amendment 1; L3.2 part F), shown red before it is wired into
`make ci` (rule 15), with each planted word in the shape the real code used before L3.2.

- each shape flagged: `test_each_shape_the_code_used_is_flagged`;
- the two kept meanings left alone, and only where named:
  `test_a_pipelines_branch_and_a_git_flag_are_kept_only_where_named`;
- a folder-wide exception would have hidden a case's branch:
  `test_a_folder_wide_exception_would_have_hidden_a_cases_branch`;
- the real tree holds none: `test_the_tree_names_no_branch`.
"""

from __future__ import annotations

import pytest
from tools import no_branches_check as check
from tools.no_branches_check import findings, tree_files

#: The shapes the Glass and the Conduit held before L3.2, one per line.
PLANTED = {
    "apps/workspace/src/canvas/SelectionBar.tsx": "import { branchNodes } from './branchNodes';",
    "services/api/app.py": '    "/v1/investigations/{investigation_id}/branch-by-filter",',
    "services/api/investigations.py": "    branched_from: str | None = None",
    "services/api/rights.py": '    BRANCH_CASE = "branch_case"',
    "apps/workspace/src/investigation/CaseTree.tsx": "<li>Branch of {name}</li>",
    "apps/workspace/src/ingest/studio/datasets.ts": "c.branched_from ? 1 : 0",
}


@pytest.mark.parametrize("path", sorted(PLANTED))
def test_each_shape_the_code_used_is_flagged(path: str) -> None:
    clean = {"services/api/views.py": "a view is a saved lens on a case\n"}
    assert findings(clean) == []
    found = findings({**clean, path: f"first line\n{PLANTED[path]}\n"})
    assert found == [(path, 2, PLANTED[path].strip())]


def test_a_pipelines_branch_and_a_git_flag_are_kept_only_where_named() -> None:
    git = 'await _run_git("init", "--initial-branch=main")'
    dag = "every source branch through the engine"
    assert findings({"services/api/studio_publish.py": git}) == []
    assert findings({"services/api/pipeline_run.py": dag}) == []
    # The same pipeline sentence in a file not named is flagged: a new file is named on purpose.
    assert findings({"services/api/pipeline_new.py": dag}) != []
    # A git branch named any other way is flagged too.
    assert findings({"services/api/x.py": "git checkout -b my-branch"}) != []


def test_a_folder_wide_exception_would_have_hidden_a_cases_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15's second clause: the plant in the shape the real tree held (a case's
    `branched_from` in the Studio's own folder), against the exception a folder would give."""
    path = "apps/workspace/src/ingest/studio/datasets.ts"
    planted = {path: PLANTED[path]}
    assert findings(planted) != []
    folder_wide = {p: "the Studio's folder" for p in (path, *check.PIPELINE_FILES)}
    monkeypatch.setattr(check, "PIPELINE_FILES", folder_wide)
    assert findings(planted) == []


def test_the_tree_names_no_branch() -> None:
    found = findings(tree_files())
    assert found == [], "\n".join(f"{p}:{n}: {line}" for p, n, line in found[:40])
