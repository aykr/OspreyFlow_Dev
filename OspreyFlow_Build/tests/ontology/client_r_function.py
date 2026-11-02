"""The client's `add_strength_column`, transcribed into plain Python as fixture arithmetic, and a
synthetic link table to run through it (`06_DECISIONS.md` ADR-139 Amendments 2 and 3). No R is run:
each line below is the R line above it, so a reader can check the transcription line by line.

```r
add_strength_column <- function (edges_dt, the_col, abs_add, non_dup_add) {
  shared_values_table_1 <- edges_dt[, .(shared_values=get(the_col))][, .N, by = shared_values]
  shared_values_table_1[, edge_strength_1 := (1 - (N / sum(N)))]
  shared_values_table_1 <- shared_values_table_1[, .(shared_values, edge_strength_1)]
  setnames(shared_values_table_1, old = colnames(shared_values_table_1), new = c(the_col, "edge_strength_1"))
  edges_dt <- merge(edges_dt, shared_values_table_1, by = the_col, all.x = T)
  edges_dt[, edge_strength := edge_strength_1 + abs_add]
  edges_dt[, edge_strength_1 := NULL]
  edges_dt[!(type %like% "dup_"), edge_strength := edge_strength + non_dup_add]
}
```

**How a direct link's rarity term arises in their code.** The function adds `edge_strength_1` to
every row, a direct (non-`dup_`) row included. A direct row's `the_col` holds that row's own value,
so its term is `1 − N(v)/ΣN`, where `N(v)` counts every row of the table carrying the same value
and `ΣN` is the number of rows in the table, of every type. When a direct row's value is carried by
no other row, its term is `1 − 1/ΣN`.

**How OspreyFlow maps it** (`ontology/influencers.py`, the graph adapter): a `dup_*` row is a pair
linked through a shared value `a`, whose term is `1 − C(k, 2)/Σ_b C(k_b, 2)` over the values of
`a`'s kind in the dataset; a direct row is a stored link, whose term treats the link as a value of
its own held by its two ends among the visible links of its type in the dataset, `1 − 1/n`. The
two agree exactly when one call of the function holds rows of **one kind**: only `dup_*` rows
through values of one kind, or only direct rows of one link type each carrying a value no other row
carries. They do not agree for a table that mixes kinds (`dup_*` and direct rows together, two
shared-value kinds, or two direct types), because the client's `ΣN` then counts every row and
OspreyFlow's counts one kind; nor for direct rows sharing a value (OspreyFlow has one stored link
per pair and type). `test_client_parity.py` shows the first of these as a figure, and ADR-139
Amendment 3 puts both to the client as questions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Row:
    """One row of a client link table: two parties, the link's type and the shared value
    (`the_col`)."""

    dataset: str
    source: str
    target: str
    type: str
    value: str


def add_strength_column(
    edges_dt: Sequence[Row], the_col: str, abs_add: float, non_dup_add: float
) -> list[tuple[Row, float]]:
    """The R function, line by line. `the_col` is always `"value"` here: the column holding the
    shared value itself (the owner confirmed it)."""
    # shared_values_table_1 <- edges_dt[, .(shared_values=get(the_col))][, .N, by = shared_values]
    counts: dict[str, int] = {}
    for row in edges_dt:
        shared_value = getattr(row, the_col)
        counts[shared_value] = counts.get(shared_value, 0) + 1
    # shared_values_table_1[, edge_strength_1 := (1 - (N / sum(N)))]
    total = sum(counts.values())
    table_1 = {value: 1 - (n / total) for value, n in counts.items()}
    # setnames(...) renames the columns back to `the_col` and "edge_strength_1": no arithmetic.
    # edges_dt <- merge(edges_dt, shared_values_table_1, by = the_col, all.x = T)
    merged = [(row, table_1[getattr(row, the_col)]) for row in edges_dt]
    # edges_dt[, edge_strength := edge_strength_1 + abs_add]
    # edges_dt[, edge_strength_1 := NULL]
    strengths = [(row, edge_strength_1 + abs_add) for row, edge_strength_1 in merged]
    # edges_dt[!(type %like% "dup_"), edge_strength := edge_strength + non_dup_add]
    return [
        (row, strength + non_dup_add if "dup_" not in row.type else strength)
        for row, strength in strengths
    ]


#: The adds per dataset, as the client would pass them: `(abs_add, non_dup_add)`.
ADDS: dict[str, tuple[float, float]] = {
    "phones": (0.05, 0.2),
    "calls": (0.1, 0.2),
    "transfers": (0.15, 0.2),
}

#: A synthetic link table, one per dataset, of the shapes that map exactly (one kind per call):
#: - `phones`: `dup_phone` rows only. Phone ph1 is held by P1 and P2, ph2 by P3, P4 and P5 (three
#:   rows, every pair of them), ph3 by P1 and P6, ph4 by P2 and P6;
#: - `calls`: direct `call` rows only, between the endpoints X1 to X5, each carrying its own value;
#: - `transfers`: direct `money` rows only, between the accounts T1 to T3.
TABLE: list[Row] = [
    Row("phones", "P1", "P2", "dup_phone", "ph1"),
    Row("phones", "P3", "P4", "dup_phone", "ph2"),
    Row("phones", "P3", "P5", "dup_phone", "ph2"),
    Row("phones", "P4", "P5", "dup_phone", "ph2"),
    Row("phones", "P1", "P6", "dup_phone", "ph3"),
    Row("phones", "P2", "P6", "dup_phone", "ph4"),
    Row("calls", "X1", "X2", "call", "call-1"),
    Row("calls", "X2", "X3", "call", "call-2"),
    Row("calls", "X3", "X4", "call", "call-3"),
    Row("calls", "X4", "X5", "call", "call-4"),
    Row("transfers", "T1", "T2", "money", "transfer-1"),
    Row("transfers", "T2", "T3", "money", "transfer-2"),
]


def client_scores(table: Sequence[Row] = TABLE) -> dict[Row, float]:
    """The client's pipeline: the function called once per dataset's link table."""
    scores: dict[Row, float] = {}
    for dataset in dict.fromkeys(r.dataset for r in table):
        abs_add, non_dup_add = ADDS[dataset]
        rows = [r for r in table if r.dataset == dataset]
        scores.update(add_strength_column(rows, "value", abs_add, non_dup_add))
    return scores


#: The figures the table gives, worked by hand, so the transcription itself is checked:
#: phones: ΣN = 6, ph1, ph3, ph4: 1 − 1/6 + 0.05; ph2: 1 − 3/6 + 0.05;
#: calls: ΣN = 4, 1 − 1/4 + 0.1 + 0.2; transfers: ΣN = 2, 1 − 1/2 + 0.15 + 0.2.
BY_HAND: dict[tuple[str, str, str], float] = {
    ("phones", "P1", "P2"): 1 - 1 / 6 + 0.05,
    ("phones", "P3", "P4"): 1 - 3 / 6 + 0.05,
    ("phones", "P3", "P5"): 1 - 3 / 6 + 0.05,
    ("phones", "P4", "P5"): 1 - 3 / 6 + 0.05,
    ("phones", "P1", "P6"): 1 - 1 / 6 + 0.05,
    ("phones", "P2", "P6"): 1 - 1 / 6 + 0.05,
    ("calls", "X1", "X2"): 1 - 1 / 4 + 0.1 + 0.2,
    ("calls", "X2", "X3"): 1 - 1 / 4 + 0.1 + 0.2,
    ("calls", "X3", "X4"): 1 - 1 / 4 + 0.1 + 0.2,
    ("calls", "X4", "X5"): 1 - 1 / 4 + 0.1 + 0.2,
    ("transfers", "T1", "T2"): 1 - 1 / 2 + 0.15 + 0.2,
    ("transfers", "T2", "T3"): 1 - 1 / 2 + 0.15 + 0.2,
}

#: The client's direct row types, as OspreyFlow's link types.
LINK_TYPE = {"call": "COMMUNICATED_WITH", "money": "TRANSACTED"}
