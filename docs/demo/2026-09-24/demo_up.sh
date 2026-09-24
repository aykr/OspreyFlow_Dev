#!/usr/bin/env bash
# RETIRED, 24 September 2026 — superseded by `python -m harness.apply`.
#
# This script was the scripted bring-up the 23 September rehearsal produced. Everything it did is
# now a stage of the harness: render, preflight, build, up-and-wait, seed under the ordering guard,
# and the post-launch verify (06_DECISIONS.md ADR-049, Stage 2 §3).
#
#     python -m harness.apply --profile local-lite [--seed hmp,fixture-corp]
#
# Kept for one round so the runbook that cites it still resolves; deleted next round. It is not a
# pointer to a working alternative path — there is one path now, and this is not it.
set -euo pipefail
echo "demo_up.sh is retired. Use:  python -m harness.apply --profile local-lite" >&2
echo "See docs/07_BUILD_PLAN.md Stage 2 §3 for what it does and what is still blocked." >&2
exit 1
