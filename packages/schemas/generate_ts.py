"""Generate TypeScript types from the Phase 0 placeholder Pydantic models.

Pydantic is the source of truth (``docs/CLAUDE.md`` conventions). Each model's
``model_json_schema()`` output is piped through ``json-schema-to-typescript``
(the ``json2ts`` CLI) to produce ``packages/schemas/generated/<Model>.ts``.

Run directly to regenerate: ``python3 packages/schemas/generate_ts.py``.
``make schemas-check`` uses this to prove the drift gate: it regenerates into a
temp directory and diffs against what is committed here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas._phase0_placeholders import ALL_MODELS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
JSON2TS = REPO_ROOT / "node_modules" / ".bin" / "json2ts"

HEADER = (
    "// AUTO-GENERATED — do not edit by hand.\n"
    "// Source: packages/schemas/_phase0_placeholders.py via generate_ts.py\n"
)


def generate(out_dir: Path, models: Sequence[type[BaseModel]] = ALL_MODELS) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for model in models:
        schema = model.model_json_schema()
        result = subprocess.run(
            [str(JSON2TS), "--bannerComment", ""],
            input=json.dumps(schema),
            capture_output=True,
            text=True,
            check=True,
        )
        (out_dir / f"{model.__name__}.ts").write_text(HEADER + result.stdout)
        names.append(model.__name__)

    index_lines = [HEADER]
    for name in names:
        index_lines.append(f'export type {{ {name} }} from "./{name}";')
    (out_dir / "index.ts").write_text("\n".join(index_lines) + "\n")


if __name__ == "__main__":
    generate(REPO_ROOT / "packages" / "schemas" / "generated")
    print(f"Generated {len(ALL_MODELS)} types.")
