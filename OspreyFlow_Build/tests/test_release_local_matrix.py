"""`tools/release_local.py` builds what `.github/workflows/release.yml` builds (its own docstring: "mirrors
the release workflow's matrix exactly"), each from its own context: Laurium's image from its folder
alone (`06_DECISIONS.md` ADR-135 Amendments 6 and 9; the orchestrator's round 2 on P12 part 2, item 3).
Read from the workflow itself, so a matrix entry with no twin here, or a different Dockerfile, build
argument or context, fails.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from tools.release_local import SERVICES

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"


def _matrix() -> list[dict[str, str]]:
    workflow = yaml.safe_load(WORKFLOW.read_text("utf-8"))
    return list(workflow["jobs"]["build-scan-push"]["strategy"]["matrix"]["include"])


def test_release_local_builds_what_the_release_builds() -> None:
    wanted = []
    for entry in _matrix():
        arg = (entry.get("build_args") or "").split("=", 1)[0] or None
        wanted.append((entry["service"], entry["dockerfile"], arg, entry.get("context") or "."))
    assert list(SERVICES) == wanted


def test_lauriums_image_is_built_from_its_own_folder() -> None:
    laurium = [s for s in SERVICES if s[0] == "laurium"]
    assert laurium == [("laurium", "services/laurium/Dockerfile", None, "services/laurium")]
