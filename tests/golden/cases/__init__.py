"""Hand-labelled golden-set cases (`docs/07_BUILD_PLAN.md` Phase 6 Stage 3). Each module exports
one `GoldenCase`; `ALL_CASES` is what `tests/golden/test_golden_set.py` runs."""

from __future__ import annotations

from tests.golden.harness import GoldenCase

from .witness_statement import WITNESS_STATEMENT_CASE

ALL_CASES: tuple[GoldenCase, ...] = (WITNESS_STATEMENT_CASE,)
