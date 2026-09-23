"""The golden-set CI gate — `docs/03_CONDUIT_MIDDLEWARE.md` §5.2, standing rule 5:
"A change that degrades recall on any type fails the build unless
explicitly accepted with a recorded reason."

**The tolerance, and where it comes from.** `RECALL_TOLERANCE`/`PRECISION_TOLERANCE` are not round
numbers, and were re-measured once (`tests/golden/harness.py`'s own docstring has the full story)
after a matcher bug was found and fixed: two apparent zero-recall extremes in the original
measurement turned out to be formatting variants (`dana_mercer`, `MERCER Dana`) the harness wasn't
normalising, not real model failures. After the fix, a 20-run manual trial's *per-run* recall
never went below 0.67, and independent `N_RUNS=12` batch means landed at 0.69, 0.75 and 0.77 —
call it a spread of roughly 0.1 for recall from run-to-run sampling noise alone, on an unchanged
model, with precision noisier still (batch means from 0.51 to 0.67). A zero-tolerance "must not
decrease from baseline" gate would fail this specific pinned model's own build routinely on
nothing but noise; 0.15 is set above the observed spread for both metrics with headroom, not at
it.

**Failing on recall, warning on precision.** The standing rule names recall specifically ("degrades
recall on any type fails the build") — a silent extraction is worse than a noisy one, since a
missed entity never reaches an analyst's review queue at all (`09_INGEST_STUDIO.md` §7), while a
false positive is at least visible there to reject. A precision drop beyond tolerance is reported
but does not fail the build on its own.

**Accepted regressions.** `tests/golden/accepted_regressions.json` lists `{case_id, category,
reason, accepted_recall_floor}` entries — a real drop below tolerance for a `(case_id, category)`
pair with an entry there uses `accepted_recall_floor` instead of `baseline - RECALL_TOLERANCE` as
the failure threshold, so the acceptance is a recorded, reviewable file change, not a silenced
assertion in code.

Needs a live LiteLLM/Ollama (`make dev-up`) — same live-infra exclusion from plain `make test` as
the `ModelPort` conformance suite.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.golden.cases import ALL_CASES
from tests.golden.harness import run_golden_set, summarise

from adapters.model_litellm import CONFORMANCE_MODEL

RECALL_TOLERANCE = 0.15
PRECISION_TOLERANCE = 0.15

_GOLDEN_DIR = Path(__file__).parent
BASELINE = json.loads((_GOLDEN_DIR / "baseline.json").read_text())
ACCEPTED_REGRESSIONS = {
    (entry["case_id"], entry["category"]): entry
    for entry in json.loads((_GOLDEN_DIR / "accepted_regressions.json").read_text())
}


def _recall_floor(case_id: str, category: str, baseline_recall: float) -> float:
    accepted = ACCEPTED_REGRESSIONS.get((case_id, category))
    if accepted is not None:
        return float(accepted["accepted_recall_floor"])
    return baseline_recall - RECALL_TOLERANCE


async def test_golden_set_recall_has_not_regressed() -> None:
    results = await run_golden_set(ALL_CASES, model=CONFORMANCE_MODEL)
    current = summarise(results)

    failures: list[str] = []
    warnings: list[str] = []
    for case_id, categories in current.items():
        baseline_categories = BASELINE.get(case_id, {})
        for category, scores in categories.items():
            baseline_scores = baseline_categories.get(category)
            if baseline_scores is None:
                continue  # a new case/category has no prior baseline to regress against
            recall_floor = _recall_floor(case_id, category, baseline_scores["recall"])
            report = (
                f"{case_id}/{category}: recall {scores['recall']:.2f} "
                f"(baseline {baseline_scores['recall']:.2f}), "
                f"precision {scores['precision']:.2f} (baseline {baseline_scores['precision']:.2f})"
            )
            if scores["recall"] < recall_floor:
                failures.append(f"{report} — below floor {recall_floor:.2f}")
            elif scores["precision"] < baseline_scores["precision"] - PRECISION_TOLERANCE:
                warnings.append(report)

    for warning in warnings:
        print(f"golden set: precision regression (not gated): {warning}")  # noqa: T201

    assert not failures, "golden set recall regression:\n" + "\n".join(failures)
