"""The golden-set evaluation harness — `spec/03_CONDUIT_MIDDLEWARE.md` §5.2:
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

**Why every case runs `N_RUNS` times, not once.** Stage 1's witness-statement smoke test and Stage
2's own repeated-run checks both found genuine run-to-run recall variance from the pinned small
model — not test flakiness, real sampling variance (`spec/06_DECISIONS.md` ADR-020). A golden-set
number that means anything for gating a build has to be measured the same way: each case's
extraction runs `N_RUNS` times and every reported precision/recall is a mean across runs, not a
single sample that could land on either side of a real regression by chance. `N_RUNS` was first 12,
and that was not a guess: an early single run's recall for `persons_mentioned` ranged as low as 0.0
across manual trials, and even the *mean* of five runs still varied batch-to-batch by roughly ±0.17.
Twelve runs tightened that considerably. Two of those apparent zero-recall extremes turned out, on
inspection, to be a matcher bug rather than model failure — see "Matching" below; after fixing it, a
20-run manual trial's *per-run* (not per-batch-mean) recall never went below 0.67, which is the real
floor `test_golden_set.py`'s tolerance is set against, not the noisier pre-fix numbers.

**Twelve became 48 (owner, 20 October 2026).** Twelve was too few: the gate failed CI on noise about
one run in 35–40 (`witness-statement-1/persons_mentioned` at 0.58 against the 0.60 floor, 19 and 20
October, nothing changed). Sixty batches of twelve against CI's pinned Ollama and LiteLLM measured
the batch mean at 0.719 with a spread of 0.062, one batch of 60 below the floor; one run's recall
varies by about 0.21 (three expected people: 0, 1/3, 2/3 or 1). Forty-eight runs bring the spread to
about 0.031, the floor almost four spreads under the mean, and a real drop of 0.15 is still caught —
shown red with one of the three people planted out of the model's answer
(`process/HANDOVER_2026-10-20.md` §3 has the measurement). The baseline (0.75) is one batch's mean,
above the measured one, and is left as it was.

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
before/after numbers in `spec/06_DECISIONS.md` ADR-020's Stage 3 addendum. Matching is greedy
one-to-one per run: each expected item claims at most one extracted item and vice versa, so
duplicates cannot inflate either precision or recall.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from adapters.model_litellm.testing import model_litellm_adapter
from schemas.domain import OntologySchema, PatternNode, PatternQuery
from schemas.model import ExtractionRequest

if TYPE_CHECKING:
    from services.api.pattern_ask import PatternProposer

N_RUNS = 48


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


# --- ask to search (`06_DECISIONS.md` ADR-129 decision 2) --------------------------------------
#
# A second kind of case: a question and the pattern a person would draw for it, scored by recall of
# the pattern's own parts rather than of extracted strings. It sits beside the extraction cases, not
# inside `GoldenCase`, because there is no document and no `json_schema` to fill: what is measured
# is `services.api.pattern_ask.PatternProposer`, the code the route runs, against a real model.
#
# **What is scored.** A pattern is read as a multiset of elements: each node's type; each link as
# (type, the types of its two ends, in order unless the link is undirected); each condition as
# (node type, property, value); each pinned node as (node type, its placeholder). The variable
# letters the model chose are not scored, since only the parts matter. Recall is the share of the
# expected pattern's elements the proposed one holds (a multiset, so "two different documents"
# needs two); precision is the share of the proposed pattern's elements that were expected. A
# question the Conduit must refuse is scored correct, recall and precision 1.0, only when the
# proposer refused (`CouldNotExpress`); a pattern proposed for it scores 0.0, and a refusal of an
# answerable question scores recall 0.0. Gating is on recall, as the extraction cases are: a pattern
# that is too wide is shown with its count and edited, one that is missing a part is the wrong
# question.

#: What `baseline.json` calls the one category of the ask-to-search case.
PATTERN_CATEGORY = "pattern_recall"

#: Set from the first measured run (`ADR-129`: "a recall floor is set from the first measured
#: run"), as `test_golden_set.RECALL_TOLERANCE` is for extraction: the floor is the baseline recall
#: less this. Owner's to set from the measured spread, not derived here.
PATTERN_RECALL_TOLERANCE = 0.15

#: How far above the best constant answer's F1 a measurement must be to pass (see
#: `best_constant_answer`). The best constant is found over a finite family, so it is a lower bound
#: on what an answer that ignores the question can score; the margin covers what the search missed.
PATTERN_CONSTANT_MARGIN = 0.05


@dataclass(frozen=True)
class PatternGoldenCase:
    id: str
    question: str
    #: The pattern a person would draw, in the route's own type, with `$selected_n` where the
    #: question means what the analyst selected; `None` for a question that must be refused.
    expected: PatternQuery | None
    #: How many items the analyst is taken to have selected: the placeholders the model is offered.
    selected: int = 0


@dataclass(frozen=True)
class PatternScore:
    precision: float
    recall: float

    @property
    def f1(self) -> float:
        total = self.precision + self.recall
        return 0.0 if total == 0 else 2 * self.precision * self.recall / total


def _pattern_elements(
    pattern: PatternQuery, undirected: Collection[str]
) -> Counter[tuple[str, ...]]:
    kind = {n.var: n.entity_type or "" for n in pattern.nodes}
    elements: Counter[tuple[str, ...]] = Counter()
    for node in pattern.nodes:
        elements[("type", kind[node.var])] += 1
        if node.node_id:
            elements[("pin", kind[node.var], node.node_id)] += 1
        for name, value in node.where.items():
            elements[("where", kind[node.var], name, _normalise(value))] += 1
    for edge in pattern.edges:
        ends = (kind[edge.from_var], kind[edge.to_var])
        if edge.edge_type in undirected:
            ends = (min(ends), max(ends))
        elements[("link", edge.edge_type, *ends)] += 1
    return elements


def score_pattern(
    expected: PatternQuery | None,
    proposed: PatternQuery | None,
    *,
    undirected: Collection[str] = frozenset(),
) -> PatternScore:
    """One run's score. `proposed` is `None` when the Conduit refused the question. `undirected`
    names the link types whose two ends may be written either way round (the ontology's own)."""
    if expected is None:
        correct = 1.0 if proposed is None else 0.0
        return PatternScore(precision=correct, recall=correct)
    if proposed is None:
        return PatternScore(precision=1.0, recall=0.0)
    wanted = _pattern_elements(expected, undirected)
    got = _pattern_elements(proposed, undirected)
    held = sum((wanted & got).values())
    return PatternScore(
        precision=1.0 if not got else held / sum(got.values()),
        recall=1.0 if not wanted else held / sum(wanted.values()),
    )


async def run_pattern_cases(
    proposer: PatternProposer,
    cases: Sequence[PatternGoldenCase],
    ontology: OntologySchema,
    *,
    n_runs: int,
) -> dict[str, list[PatternScore]]:
    """Asks each question `n_runs` times through the proposer, the code the route runs, and scores
    each answer: `{case id: [one score per run]}`. A refusal is `None`, scored as a refusal. The
    live test passes a proposer over a real model; the gate's own tests pass one over a fake that
    answers in the shape a real model's constrained output takes."""
    from services.api.pattern_ask import CouldNotExpress  # deferred: keeps the harness light

    undirected = {e.name for e in ontology.edge_types if not e.directed}
    scores: dict[str, list[PatternScore]] = {}
    for case in cases:
        runs: list[PatternScore] = []
        for _ in range(n_runs):
            try:
                proposal = await proposer.propose(
                    case.question, ontology, placeholders=case.selected
                )
            except CouldNotExpress:
                proposed = None
            else:
                proposed = proposal.pattern
            runs.append(score_pattern(case.expected, proposed, undirected=undirected))
        scores[case.id] = runs
    return scores


def summarise_patterns(
    case_id: str, scores_by_question: Mapping[str, Sequence[PatternScore]]
) -> dict[str, dict[str, dict[str, float]]]:
    """The shape `baseline.json` stores for the ask-to-search case: each question's mean over its
    runs, then the mean over the questions, so no question is weighted by how often it was asked."""
    per_question = [
        (
            statistics.mean(s.precision for s in runs),
            statistics.mean(s.recall for s in runs),
        )
        for runs in scores_by_question.values()
    ]
    return {
        case_id: {
            PATTERN_CATEGORY: {
                "precision": statistics.mean(p for p, _ in per_question),
                "recall": statistics.mean(r for _, r in per_question),
            }
        }
    }


@dataclass(frozen=True)
class PatternGateResult:
    #: `not_yet_measured`: the baseline holds no recall yet, so there is nothing to fall below. It
    #: is never `passed`: a gate with no floor has not been run, and says so.
    status: Literal["passed", "failed", "not_yet_measured"]
    message: str


def _constant_candidates(cases: Sequence[PatternGoldenCase]) -> list[PatternQuery]:
    """Patterns that ignore the question, drawn from the cases themselves: each expected pattern
    whole, each of its links with their two ends, and each node type alone. A pattern naming a
    `$selected_n` placeholder is left out: the proposer offers one only for a question about the
    analyst's selection, so no constant answer can carry it to the others."""
    candidates: list[PatternQuery] = []
    for case in cases:
        if case.expected is None or any(n.node_id for n in case.expected.nodes):
            continue
        candidates.append(case.expected)
        by_var = {n.var: n for n in case.expected.nodes}
        for edge in case.expected.edges:
            ends = (by_var[edge.from_var], by_var[edge.to_var])
            if ends[0].var != ends[1].var:
                candidates.append(PatternQuery(nodes=[*ends], edges=[edge]))
        candidates.extend(
            PatternQuery(nodes=[PatternNode(var="a", entity_type=n.entity_type)], edges=[])
            for n in case.expected.nodes
        )
    return candidates


def best_constant_answer(
    cases: Sequence[PatternGoldenCase], *, undirected: Collection[str] = frozenset()
) -> PatternScore:
    """The best score an answer that ignores the question can reach on these cases: one fixed
    pattern proposed for every answerable question, and every question that must be refused refused
    (the four a model that read nothing could still get right). Candidates are
    `_constant_candidates`; each is scored by the mean of its questions' recall and precision, as
    `summarise_patterns` takes them, and the best is the one with the highest F1. A lower bound: a
    pattern outside the family may do better."""
    best = PatternScore(precision=0.0, recall=0.0)
    for candidate in [None, *_constant_candidates(cases)]:
        scores = [
            score_pattern(
                case.expected, None if case.expected is None else candidate, undirected=undirected
            )
            for case in cases
        ]
        mean = PatternScore(
            precision=statistics.mean(s.precision for s in scores),
            recall=statistics.mean(s.recall for s in scores),
        )
        if mean.f1 > best.f1:
            best = mean
    return best


def pattern_gate(
    case_id: str,
    measured_recall: float,
    baseline: Mapping[str, Any],
    *,
    measured_precision: float,
    best_constant: PatternScore,
    tolerance: float = PATTERN_RECALL_TOLERANCE,
    margin: float = PATTERN_CONSTANT_MARGIN,
) -> PatternGateResult:
    """The ask-to-search gate, as the live test applies it. Two floors, both required:

    1. **Recall** below the baseline's recall less the tolerance fails; a baseline recall of `null`
       is not yet measured.
    2. **F1 of the measured recall and precision** below the best constant answer's F1 plus the
       margin fails. Found 27 October 2026: answering one wrong pattern to every answerable
       question scored recall 0.423 against a floor of 0.418, and the best pin-free constant
       scores recall 0.468, so the recall floor (baseline 0.568 less 0.15) was passed by an answer
       that ignores the question. A floor of the best constant's recall plus a margin would leave
       the model 0.05 of room and be beaten by any wider constant pattern (recall is gated and
       precision is not); F1 charges a wide pattern for its width: the best constant's F1 is 0.50
       and the measured model's 0.69. `best_constant` and `measured_precision` are required so that
       the gate cannot be called without them."""
    entry = baseline.get(case_id, {}).get(PATTERN_CATEGORY)
    recorded = None if entry is None else entry.get("recall")
    if recorded is None:
        return PatternGateResult(
            "not_yet_measured",
            f"{case_id}/{PATTERN_CATEGORY}: recall {measured_recall:.2f} measured; the baseline "
            "holds no recall yet, so no floor applies. Record it in baseline.json.",
        )
    floor = float(recorded) - tolerance
    measured = PatternScore(precision=measured_precision, recall=measured_recall)
    constant_floor = best_constant.f1 + margin
    report = (
        f"{case_id}/{PATTERN_CATEGORY}: recall {measured_recall:.2f} (baseline {recorded:.2f}), "
        f"F1 {measured.f1:.2f} (best constant answer {best_constant.f1:.2f})"
    )
    if measured_recall < floor:
        return PatternGateResult("failed", f"{report} — below floor {floor:.2f}")
    if measured.f1 < constant_floor:
        return PatternGateResult(
            "failed", f"{report} — F1 below the constant-answer floor {constant_floor:.2f}"
        )
    return PatternGateResult("passed", report)
