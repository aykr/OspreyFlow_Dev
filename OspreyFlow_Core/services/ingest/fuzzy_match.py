"""The fuzzy match, expert mode's similarity step (ADR-140 decision 13; ADR-006 Amendment 1;
R5, R13; brief §5.4). `schemas.staging.FuzzyMatchStep` is its record.

**What it does.** Every row of `left` is kept. Each is compared with the rows of `right` by the
Splink-backed comparisons already in the product (`exact`, `jaro_winkler`, `levenshtein`: the
ontology's closed registry, `ontology.resolution_functions`, through Splink's `comparison_library`
as `services/resolve` uses it, with the same untrained priors, ADR-021), optionally only among pairs
agreeing on a blocking key. A left row whose best-scoring right row scores at least `threshold`
takes the columns `add` names from it and the score as `match_score`; a row below keeps those cells
empty, is **kept, and counted** (rule 2: "2 of 6 matched at 0.85 or more"). A matched row's refs are
both rows', as a Join's are.

**What it never does.** It merges nothing (ADR-006; rule 6): the two records stay two rows, and
Map writes them as two elements. The match is written by the engine as a scored `SAME_AS` between
the two elements `same_as` names, marked `inferred` (rule 5), and every value Map binds from a
matched column is `inferred` with the score until a person confirms the `SAME_AS`
(`services/ingest/fuzzy_links.py`). The threshold is part of the pipeline's version.

**Bounded, never truncated** (rule 2): without a blocking key every pair is compared, so a step
whose tables would make more than `FUZZY_PAIR_LIMIT` pairs is refused in words, never cut short.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from typing import Any

import pandas as pd
import splink
from splink.duckdb.comparison_library import (
    exact_match,
    jaro_winkler_at_thresholds,
    levenshtein_at_thresholds,
)
from splink.duckdb.linker import DuckDBLinker

from ontology.resolution_functions import ResolutionFunctionCall, blocking_rule_sql
from schemas.staging import MATCH_SCORE, FuzzyBlocking, FuzzyComparison, FuzzyMatchStep

from .staging_catalogue import (
    StagedTable,
    StagedTableRow,
    StagingError,
    StepReport,
    _added_names,
)

#: Pairs a fuzzy match may compare with no blocking key (rule 2: refused above, never truncated).
FUZZY_PAIR_LIMIT = 1_000_000

#: The comparison each method names (`ontology.resolution_functions.COMPARISON_FUNCTIONS`).
_COMPARISONS = {
    "exact": exact_match,
    "jaro_winkler": jaro_winkler_at_thresholds,
    "levenshtein": levenshtein_at_thresholds,
}

#: What a fuzzy match's `SAME_AS` names as its model (as `services/resolve.resolver.MODEL_VERSION`).
MODEL_VERSION = f"splink-{splink.__version__}-staging-fuzzy-1"

_LEFT, _RIGHT = "a_left", "b_right"


def _folded(value: str | None) -> str | None:
    """As `services/resolve.resolver._cast` reads a string: case-folded (Splink's string
    similarity is case-sensitive), an empty cell as nothing."""
    if value is None or not value.strip():
        return None
    return value.strip().casefold()


def _year_of(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value.strip()[:10]) if value else None
    except ValueError:
        return None


def _frame(table: StagedTable, columns: Mapping[str, str], years: frozenset[str]) -> pd.DataFrame:
    """`unique_id` and one column per comparison or blocking key, named as Splink compares them."""
    data: dict[str, list[Any]] = {"unique_id": [str(i) for i in range(len(table.rows))]}
    for name, column in columns.items():
        read = _year_of if name in years else _folded
        data[name] = [read(row.cells.get(column)) for row in table.rows]
    return pd.DataFrame(data)


def _scores(
    step: FuzzyMatchStep, left: StagedTable, right: StagedTable
) -> dict[int, tuple[float, int]]:
    """Each left row's best right row and its score, at or above the threshold: left row ->
    (score, right row). Ties go to the right row that comes first."""
    left_columns = {f"c{i}": c.left for i, c in enumerate(step.compare)}
    right_columns = {f"c{i}": c.right for i, c in enumerate(step.compare)}
    left_columns |= {f"b{i}": b.left for i, b in enumerate(step.block_on)}
    right_columns |= {f"b{i}": b.right for i, b in enumerate(step.block_on)}
    years = frozenset(f"b{i}" for i, b in enumerate(step.block_on) if b.method == "year")
    settings = {
        "link_type": "link_only",
        "blocking_rules_to_generate_predictions": [
            blocking_rule_sql(ResolutionFunctionCall(b.method, (f"b{i}",)))
            for i, b in enumerate(step.block_on)
        ],
        "comparisons": [_COMPARISONS[c.method](f"c{i}") for i, c in enumerate(step.compare)],
        "retain_matching_columns": False,
        "retain_intermediate_calculation_columns": False,
        # The prior that a pair matches: one in the right table's rows, as each left row is
        # expected to be at most one of them (a link, not a dedupe). Splink's default (one in ten
        # thousand) is a population's, and would put an exact match of one name near 0.1.
        "probability_two_random_records_match": 1 / max(len(right.rows), 2),
    }
    from services.resolve import duckdb_setup

    con = duckdb_setup.new_connection()
    # Splink warns that its m and u values are untrained: by design (ADR-021's addendum).
    quiet = logging.getLogger("splink")
    level = quiet.level
    quiet.setLevel(logging.ERROR)
    try:
        linker = DuckDBLinker(
            [_frame(left, left_columns, years), _frame(right, right_columns, years)],
            settings,
            connection=con,
            input_table_aliases=[_LEFT, _RIGHT],
            # Splink would otherwise configure the process's root logger.
            set_up_basic_logging=False,
        )
        predictions = linker.predict(threshold_match_probability=step.threshold)
        found = predictions.as_pandas_dataframe()
    finally:
        quiet.setLevel(level)
        con.close()
    best: dict[int, tuple[float, int]] = {}
    for record in found.to_dict("records"):
        score = float(record["match_probability"])
        if score < step.threshold:
            continue
        if record["source_dataset_l"] == _LEFT:
            at, other = int(record["unique_id_l"]), int(record["unique_id_r"])
        else:
            at, other = int(record["unique_id_r"]), int(record["unique_id_l"])
        held = best.get(at)
        if held is None or score > held[0] or (score == held[0] and other < held[1]):
            best[at] = (score, other)
    return best


def score_text(score: float) -> str:
    """A score as the staged cell holds it: four places, as the run report reads it."""
    return f"{score:.4f}"


def run_fuzzy_step(
    step: FuzzyMatchStep, left: StagedTable, right: StagedTable
) -> tuple[StagedTable, StepReport]:
    compared_columns: list[FuzzyComparison | FuzzyBlocking] = [*step.compare, *step.block_on]
    problems = [
        f"step {step.id!r} compares {column!r}, which {table.name!r} has not"
        for compared in compared_columns
        for column, table in ((compared.left, left), (compared.right, right))
        if column not in table.columns
    ]
    if problems:
        raise StagingError(list(dict.fromkeys(problems)))
    pairs = _added_names(step.id, right, step.add, left.columns)
    if MATCH_SCORE in left.columns or MATCH_SCORE in {name for _, name in pairs}:
        raise StagingError(
            [
                f"step {step.id!r} gives a {MATCH_SCORE} column, which its left table or its added "
                "columns already name"
            ]  # fmt: skip
        )
    if not step.block_on and len(left.rows) * len(right.rows) > FUZZY_PAIR_LIMIT:
        raise StagingError(
            [
                f"step {step.id!r} would compare {len(left.rows) * len(right.rows):,} pairs, "
                "more than "
                f"{FUZZY_PAIR_LIMIT:,}: declare a blocking key (block_on), so only pairs agreeing "
                "on it are compared"
            ]  # fmt: skip
        )
    best = _scores(step, left, right) if left.rows and right.rows else {}
    out: list[StagedTableRow] = []
    for index, row in enumerate(left.rows):
        match = best.get(index)
        if match is None:
            cells = dict(row.cells) | {name: None for _, name in pairs} | {MATCH_SCORE: None}
            out.append(StagedTableRow(cells, row.refs))
            continue
        score, at = match
        other = right.rows[at]
        cells = (
            dict(row.cells)
            | {name: other.cells.get(column) for column, name in pairs}
            | {MATCH_SCORE: score_text(score)}
        )
        out.append(StagedTableRow(cells, row.refs + other.refs))
    met = {at for _, at in best.values()}
    report = StepReport(
        step.id,
        "fuzzy_match",
        rows_in=len(left.rows),
        rows_out=len(out),
        unmatched=len(left.rows) - len(best),
        right_rows_in=len(right.rows),
        right_unmatched=len(right.rows) - len(met),
        threshold=step.threshold,
        matched=len(best),
    )
    columns = left.columns + [name for _, name in pairs] + [MATCH_SCORE]
    return StagedTable(step.id, columns, out), report
