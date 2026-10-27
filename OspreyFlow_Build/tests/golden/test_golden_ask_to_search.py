"""The ask-to-search measured run (`06_DECISIONS.md` ADR-129 decision 2): the twenty questions of
`cases/pid_ask_to_search.py` asked of a real model through `PatternProposer`, the code the route
runs, and scored by `harness.score_pattern`.

**Skipped unless `OSPREY_GOLDEN_ASK_MODEL` names the model to measure.** It is the LiteLLM model
name the deployment points extraction at (`OSPREY_EXTRACTION_MODEL`, for instance
`qwen2.5:7b-instruct`), not the conformance suite's 0.5B pin: that model is chosen for speed, and
what ADR-129 says a local 7B model will sometimes get wrong is the thing measured here. The calls go
to the LiteLLM proxy `LITELLM_HOST`/`LITELLM_PORT` name (default `localhost:4000`), so it needs the
dev stack. `OSPREY_GOLDEN_ASK_RUNS` (default 3) is how many times each question is asked.

**The floor.** `baseline.json` holds a placeholder for this case (`recall: null`) until a first
measured run is recorded: with it, this test reports the measurement and does not fail, and says so.
Once a recall is recorded the floor is that less `harness.PATTERN_RECALL_TOLERANCE`, and a
measurement below it fails. The gate itself is shown red against a planted wrong pattern by
`tests/test_ask_to_search_golden_gate.py`, which runs in `make ci`.

Run `-s` to see each question's mean recall: a low one is a question the model gets wrong.
"""

from __future__ import annotations

import json
import os
import statistics
from pathlib import Path

import pytest
from services.api.pattern_ask import PatternProposer

from adapters.model_litellm.testing import model_litellm_adapter
from ontology.packs import load_deployment_ontology
from tests.golden.cases.pid_ask_to_search import CASE_ID, PID_ASK_TO_SEARCH_CASES
from tests.golden.harness import (
    PATTERN_CATEGORY,
    pattern_gate,
    run_pattern_cases,
    summarise_patterns,
)

MODEL = os.environ.get("OSPREY_GOLDEN_ASK_MODEL")
RUNS = int(os.environ.get("OSPREY_GOLDEN_ASK_RUNS", "3"))
BASELINE = json.loads((Path(__file__).parent / "baseline.json").read_text())

pytestmark = pytest.mark.skipif(
    not MODEL, reason="set OSPREY_GOLDEN_ASK_MODEL to measure ask to search against a live model"
)


async def test_ask_to_search_recall_has_not_regressed() -> None:
    assert MODEL is not None
    ontology = load_deployment_ontology()
    async with model_litellm_adapter() as adapter:
        proposer = PatternProposer(adapter, default_model=MODEL)
        scores = await run_pattern_cases(proposer, PID_ASK_TO_SEARCH_CASES, ontology, n_runs=RUNS)

    for case in PID_ASK_TO_SEARCH_CASES:
        mean = statistics.mean(s.recall for s in scores[case.id])
        print(f"golden set: {case.id} recall {mean:.2f}  {case.question}")  # noqa: T201

    measured = summarise_patterns(CASE_ID, scores)[CASE_ID][PATTERN_CATEGORY]
    print(  # noqa: T201
        f"golden set: {CASE_ID}/{PATTERN_CATEGORY} over {RUNS} runs with {MODEL}: "
        f"recall {measured['recall']:.4f}, precision {measured['precision']:.4f}"
    )
    result = pattern_gate(CASE_ID, measured["recall"], BASELINE)
    print(f"golden set: {result.status}: {result.message}")  # noqa: T201
    assert result.status != "failed", result.message
