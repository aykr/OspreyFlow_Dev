# Friction-log fragments

ADR-142 decision 5 (P6). Lanes do not edit `process/07_BUILD_PLAN.md`'s friction log. Each change
writes its row as its own file here, `<yyyy-mm-dd>-<lane>-<slug>.md` (for example
`2026-11-07-studio-phase-6-canvas.md`), holding exactly one row of the friction-log table:

    | <yyyy-mm-dd> | <kind> | <what was seen> | <what was done> | <tests, commits> Hash: recorded at merge. |

five cells, dated as the file name is, the last cell ending "Hash: recorded at merge." After a merge the
orchestrator runs `python -m tools.friction_assemble --hash <merge hash>` (from `OspreyFlow_Core`, with
`OspreyFlow_Build` on `PYTHONPATH`), which appends the rows in date order, fills each hash and removes
the fragments. This file is not a fragment and is left alone.
