"""Synthetic witness statement — the running smoke-test document for schema-constrained text
extraction (`docs/07_BUILD_PLAN.md` Phase 6 Stage 1's own scoping), later folded into Stage 3's
golden set as its first hand-labelled example rather than writing a second document.

Wholly fictional (`CLAUDE.md` rule 9: no real intelligence data anywhere, ever) — the names,
dates and location are invented for this fixture. The scenario echoes the worked example already
in `09_INGEST_STUDIO.md` §7 (a communications-department call reporting alleged harassment) so the
extraction smoke test exercises the exact narrative shape the review-queue design was written
against, rather than an unrelated invented one.
"""

from __future__ import annotations

WITNESS_STATEMENT_TEXT = """\
WITNESS STATEMENT

Statement of: Dana MERCER
Date: 14 March 2026

At approximately 03:20 on 14/03/2026, I received a telephone call from the communications \
department at Fernhill Prison. The caller, a member of night staff, told me that a male \
prisoner had reported being harassed by a man he named as Callum PRICE. The prisoner said \
Callum PRICE had been telephoning him repeatedly and had threatened to have drugs thrown over \
the perimeter wall into the exercise yard.

I attended Fernhill Prison later that morning and spoke to the duty governor, Susan OKAFOR, who \
confirmed the call had been logged and that the matter had been referred to the prison's own \
security team.
"""

#: A minimal POLE-shaped JSON Schema for the smoke test — real per-type schema generation from
#: the ontology's checklist is Stage 6's own scope (`09_INGEST_STUDIO.md` §4); this is only enough
#: to prove `extract()` finds the named people in a real paragraph of prose, not a toy one-liner.
WITNESS_STATEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "persons_mentioned": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["persons_mentioned"],
    "additionalProperties": False,
}
