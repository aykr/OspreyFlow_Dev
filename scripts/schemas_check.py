"""`make schemas-check` — Phase 0 exit criterion 3 (`docs/07_BUILD_PLAN.md`):
a Pydantic model change not reflected in the generated TypeScript fails the build.

Regenerates the TypeScript into a temp directory and diffs it against what is
committed in `packages/schemas/generated/`.
"""

from __future__ import annotations

import filecmp
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from schemas.generate_ts import generate  # noqa: E402

COMMITTED_DIR = REPO_ROOT / "packages" / "schemas" / "generated"


def diff_against_committed(models: Sequence[type[BaseModel]]) -> list[str]:
    """Names of generated files that differ from (or are missing from) COMMITTED_DIR."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        generate(tmp_dir, models=models)
        committed_names = {p.name for p in COMMITTED_DIR.glob("*.ts")}
        generated_names = {p.name for p in tmp_dir.glob("*.ts")}
        differing: list[str] = []
        for name in sorted(committed_names | generated_names):
            committed_file = COMMITTED_DIR / name
            generated_file = tmp_dir / name
            if not committed_file.exists() or not generated_file.exists():
                differing.append(name)
            elif not filecmp.cmp(committed_file, generated_file, shallow=False):
                differing.append(name)
        return differing


def main() -> int:
    from schemas._phase0_placeholders import ALL_MODELS

    differing = diff_against_committed(ALL_MODELS)
    if differing:
        print("schemas-check: generated TypeScript is out of date for:", file=sys.stderr)
        for name in differing:
            print(f"  - {name}", file=sys.stderr)
        print(
            "Run `python3 packages/schemas/generate_ts.py` and commit the result.",
            file=sys.stderr,
        )
        return 1
    print(f"schemas-check: {len(ALL_MODELS)} generated types match committed output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
