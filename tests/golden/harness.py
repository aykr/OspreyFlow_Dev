"""The golden-set evaluation harness — `docs/03_CONDUIT_MIDDLEWARE.md` §5.2:
"Every model-facing prompt is versioned and evaluated. A prompt change
runs the golden set and reports the delta on the pull request." Phase 6 Stage 3.

**What this baseline number is, and what it is not.** `tests/golden/baseline.json`'s numbers
(currently ~0.75 recall, ~0.53 precision for the one case that exists) are a **regression
detector scoped specifically to the small, deterministic model `06_DECISIONS.md` ADR-020 pins for
CI** — `qwen2.5:0.5b-instruct`, chosen there for size, speed and (relative) determinism, not for
extraction quality. They are **not** a measurement of how well OspreyFlow extracts entities in a
real deployment. `03_CONDUIT_MIDDLEWARE.md` §5.2's own table names the production default as a
"Qwen/Llama-class 7–14B" model — fourteen to twenty-eight times larger than the CI pin — and this
harness has no opinion on what that model's precision/recall would be; it has never been run
against one. Reading a ~0.75 baseline as "this is roughly how good extraction is" would be a
category error: it measures a deliberately small, deliberately fast model chosen so a build gate
can call it 12 times in fifteen seconds, standing in for "did this prompt/model change break the
extraction path" — not "is the extraction path good". A real deployment's own extraction quality
is a question for the acceptance scenarios and a production-scale model, not this file.

**What "entity type" means here, and why.** The spec's own wording ("precision and recall per
entity type") presumes the ontology-driven, POLE-typed extraction schema Stage 6 builds
(`09_INGEST_STUDIO.md` §4's checklist-to-schema generator). That does not exist yet — Stage 1
deliberately kept `ExtractionRequest.json_schema` caller-supplied and schema-agnostic (ADR-005),
and Stage 3 inherits that same shape rather than inventing POLE awareness ahead of Stage 6. A
"category" here is simply an array-valued top-level field of a case's own `json_schema` (e.g.
`persons_mentioned`) — the closest schema-agnostic analogue to "entity type" available before
Stage 6 lands, narrower than the spec's literal wording and disclosed as such in
a disclosed gap rather than silently assumed to be the same thing.

**Why every case runs `N_RUNS` times, not once.** Stage 1's witness-statement smoke test and
Stage 2's own repeated-run checks both found genuine run-to-run recall variance from the pinned
small model — not test flakiness, real sampling variance (`docs/06_DECISIONS.md` ADR-020).
A golden-set number that means anything for gating a build has to be measured the same way: each
case's extraction runs `N_RUNS` times and every reported precision/recall is a mean across runs,
not a single sample that could land on either side of a real regression by chance. `N_RUNS = 12`
is not a guess: an early single run's recall for `persons_mentioned` ranged as low as 0.0 across
manual trials, and even the *mean* of five runs still varied batch-to-batch by roughly ±0.17.
Twelve runs tightened that considerably. Two of those apparent zero-recall extremes turned out,
on inspection, to be a matcher bug rather than model failure — see "Matching" below; after fixing
it, a 20-run manual trial's *per-run* (not per-batch-mean) recall never went below 0.67, which is
the real floor `test_golden_set.py`'s tolerance is set against, not the noisier pre-fix numbers.

**Matching.** An expected string and an extracted string match after normalising whitespace,
underscores and hyphens to a single space, sorting the resulting words, and casefolding —
deliberately not fuzzy (no edit-distance/embedding similarity): this is a golden-set evaluation,
not the Splink comparison Stage 4 will build, and a lenient matcher here would hide the exact
formatting drift the golden set exists to surface. Both normalisation steps were found, not
designed for in advance, checking a run that scored `recall=0.0` before trusting it as pure model
noise (the diagnostic the user asked for after Stage 3's first pass landed) — two of several
zero/low-recall runs across a 20-run manual trial turned out to be exactly this:

- `extracted=['dana_mercer', 'fernhill_prison', 'callum_price']` — both real people correctly
  identified, scored `recall=0.0` under plain `.strip().casefold()` because the model rendered
  them as identifier-style tokens that run.
- `extracted=['MERCER Dana', 'OKAFOR Susan']` — again both correctly identified, scored
  `recall=0.0` because the model swapped word order for that run.

Both are harness-matching gaps, not model failures, and conflating either with genuine model
recall would have made every precision/recall number measure the matcher's strictness as much as
the model's actual behaviour. The remaining low-recall runs in that same trial (a bare surname
with no forename, e.g. `'MERCER'` alone) are genuine partial-extraction misses, not matcher bugs
— normalising those away would mean substring/partial matching, which is fuzzy in exactly the
sense this harness deliberately avoids, so they are left as real recorded misses. Full
before/after numbers in `docs/06_DECISIONS.md` ADR-020's Stage 3 addendum. Matching is greedy
one-to-one per run: each expected item claims at most one extracted item and vice versa, so
duplicates cannot inflate either precision or recall.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from adapters.model_litellm.testing import model_litellm_adapter
from schemas.model import ExtractionRequest

N_RUNS = 12


@dataclass(frozen=True)
class GoldenCase:
    id: str
    text: str
    json_schema: dict[str, Any]
    #: category (a `json_schema` array-valued property name) -> the hand-labelled list of strings
    #: that should appear in the model's output for that property.
    expected: dict[str, list[str]]


@dataclass(frozen=True)
class RunScore:
    precision: float
    recall: float
    true_positives: int
    false_positives: int
    false_negatives: int


@dataclass(frozen=True)
class CategoryScore:
    category: str
    #: One `RunScore` per run — never collapsed before the caller can see the spread.
    runs: list[RunScore]

    @property
    def mean_precision(self) -> float:
        return statistics.mean(r.precision for r in self.runs)

    @property
    def mean_recall(self) -> float:
        return statistics.mean(r.recall for r in self.runs)


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    categories: dict[str, CategoryScore] = field(default_factory=dict)


def _normalise(value: str) -> str:
    collapsed = re.sub(r"[_\-\s]+", " ", value.strip()).casefold()
    #: Token order, not just separator character, is another formatting variant the model
    #: produces for the same correctly-identified entity — found the same way the underscore case
    #: was, not designed for in advance: a 20-run manual trial returned `"MERCER Dana"` for a
    #: person the model had otherwise identified correctly, scoring a false negative against
    #: `"Dana MERCER"` under separator-only normalisation. Sorting tokens is still exact-after-
    #: normalisation, not fuzzy — it cannot turn two *different* people into a match, only reorder
    #: one already-identical multiset of words.
    return " ".join(sorted(collapsed.split()))


def _score_run(expected: Sequence[str], extracted: Sequence[str]) -> RunScore:
    remaining_extracted = [_normalise(e) for e in extracted]
    true_positives = 0
    for item in expected:
        target = _normalise(item)
        if target in remaining_extracted:
            remaining_extracted.remove(target)
            true_positives += 1
    false_positives = len(remaining_extracted)
    false_negatives = len(expected) - true_positives

    precision = 1.0 if (true_positives + false_positives) == 0 else true_positives / (
        true_positives + false_positives
    )
    recall = 1.0 if (true_positives + false_negatives) == 0 else true_positives / (
        true_positives + false_negatives
    )
    return RunScore(
        precision=precision,
        recall=recall,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
    )


async def run_case(case: GoldenCase, *, model: str, n_runs: int = N_RUNS) -> CaseResult:
    category_runs: dict[str, list[RunScore]] = {category: [] for category in case.expected}

    async with model_litellm_adapter() as adapter:
        for _ in range(n_runs):
            request = ExtractionRequest(
                document_id=case.id, text=case.text, json_schema=case.json_schema, model=model
            )
            result = await adapter.extract(request)
            for category, expected_items in case.expected.items():
                extracted_items = result.data.get(category, [])
                category_runs[category].append(_score_run(expected_items, extracted_items))

    categories = {
        category: CategoryScore(category=category, runs=runs)
        for category, runs in category_runs.items()
    }
    return CaseResult(case_id=case.id, categories=categories)


async def run_golden_set(
    cases: Sequence[GoldenCase], *, model: str, n_runs: int = N_RUNS
) -> list[CaseResult]:
    return [await run_case(case, model=model, n_runs=n_runs) for case in cases]


def summarise(results: Sequence[CaseResult]) -> dict[str, dict[str, dict[str, float]]]:
    """`{case_id: {category: {"precision": mean, "recall": mean}}}` — the plain-JSON shape
    `tests/golden/baseline.json` stores and `test_golden_set.py` compares against. Only the mean
    is persisted; the per-run spread is for a human reading the live run's own output, not for the
    committed baseline to carry forward."""
    return {
        result.case_id: {
            category: {"precision": score.mean_precision, "recall": score.mean_recall}
            for category, score in result.categories.items()
        }
        for result in results
    }
