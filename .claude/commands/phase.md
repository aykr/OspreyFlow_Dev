---
description: Start a build phase from the specification
---

Start Phase $ARGUMENTS of the OspreyFlow build.

1. Read the Phase $ARGUMENTS section of `docs/07_BUILD_PLAN.md`, and every spec document it
   references. Read `docs/06_DECISIONS.md` for any ADR that governs this phase.
2. Check what already exists in the repository against that phase's scope. Do not rebuild
   what is there; do not assume anything is finished because a file exists.
3. Propose a plan covering every bullet in the phase scope, ending at the phase's exit
   criterion. Say explicitly how you will demonstrate the exit criterion passing.
4. Name anything the spec leaves ambiguous. Propose a resolution and wait — do not fill the
   gap silently.
5. Write the tests before the implementation. Where the phase involves a port adapter, the
   conformance suite comes first.

Standing rules from `CLAUDE.md` apply. Flag any point where following the spec seems wrong
rather than working around it.
