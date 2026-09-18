"""The golden set's first case — folded in from Stage 1's own smoke-test document
(`tests/scenarios/fixtures/witness_statement.py`) rather than a second hand-labelled document,
per Stage 1/3's original scoping.

Hand-labelled by reading the fixture text directly: three people are actually named in it — Dana
MERCER (the statement's own author, named in "Statement of: Dana MERCER"), Callum PRICE (the
subject of the alleged-harassment complaint), and Susan OKAFOR (the duty governor). All three are
genuine positives for `persons_mentioned`; anything else the model returns (locations, roles,
"security team") is a false positive.
"""

from __future__ import annotations

from tests.golden.harness import GoldenCase
from tests.scenarios.fixtures.witness_statement import (
    WITNESS_STATEMENT_SCHEMA,
    WITNESS_STATEMENT_TEXT,
)

WITNESS_STATEMENT_CASE = GoldenCase(
    id="witness-statement-1",
    text=WITNESS_STATEMENT_TEXT,
    json_schema=WITNESS_STATEMENT_SCHEMA,
    expected={"persons_mentioned": ["Dana MERCER", "Callum PRICE", "Susan OKAFOR"]},
)
