"""Regenerate `tests/golden/baseline.json` — `spec/03_CONDUIT_MIDDLEWARE.md` §5.2's "the golden
set... reports precision and recall per entity type against the previous version".

Run this deliberately, after a prompt or model change, and commit the result with a message
naming why the new numbers are accepted — the same discipline as any other accepted baseline
change in this repo (e.g. a Playwright visual baseline). `tests/golden/test_golden_set.py` is what
actually gates a build against whatever is committed here; this script only ever produces a new
candidate for a human to review and commit, never runs as part of CI itself.

Needs a live LiteLLM/Ollama (`make dev-up`), same as the `ModelPort` conformance suite.
"""

from __future__ import annotations

import asyncio
import json
import sys

from tools.layout import CORE
from tools.layout import REPO as REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "packages"))
sys.path.insert(0, str(CORE))

from adapters.model_litellm import CONFORMANCE_MODEL  # noqa: E402
from tests.golden.cases import ALL_CASES  # noqa: E402
from tests.golden.harness import run_golden_set, summarise  # noqa: E402

BASELINE_PATH = REPO_ROOT / "tests" / "golden" / "baseline.json"


async def main() -> None:
    results = await run_golden_set(ALL_CASES, model=CONFORMANCE_MODEL)
    summary = summarise(results)
    BASELINE_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {BASELINE_PATH} for {len(summary)} case(s):")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
