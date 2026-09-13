# Prompts

Three things here: the one-off kickoff prompt, a reusable `/phase` command, and the prompts
worth having ready for the moments a build goes sideways.

---

## 1. Kickoff — run once, in plan mode

Press **Shift+Tab** to enter plan mode first. This prompt should produce a plan, not files.

> This repository contains a complete architecture specification in `docs/`. Read `CLAUDE.md`,
> then `docs/README.md`, `docs/00_ARCHITECTURE.md` and `docs/07_BUILD_PLAN.md`.
>
> Do not write any code yet. I want three things:
>
> 1. A summary of the system in your own words — tiers, the four ports, and what makes a
>    component swappable. If your summary and the spec disagree anywhere, that is a defect in
>    the spec and I want to know about it.
> 2. Anything in Phase 0 that the spec leaves ambiguous or contradicts itself on. Be specific
>    and quote the line. Do not paper over gaps.
> 3. A plan for Phase 0 only, mapped to its exit criterion: CI green, a GPL dependency fails
>    the build, and a Pydantic model change not reflected in the generated TypeScript fails the
>    build.
>
> Phase 0 is scaffolding and guard rails. No implementations, no adapters — `packages/ports`
> holds `Protocol` definitions only, and the conformance suites exist but fail loudly rather
> than skip.

Work through the questions it raises before approving. The ambiguities it finds in the spec are
worth more than the plan.

---

## 2. The `/phase` command

Save as `.claude/commands/phase.md`. Then starting a phase is `/phase 1`.

```markdown
---
description: Start a build phase from the specification
---

Start Phase $ARGUMENTS of the MantisNexus build.

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
```

Run it in plan mode. Approve the plan, then let it build.

---

## 3. Prompts worth having ready

**At the end of a phase, before you believe it.**

> Grill me on these changes. Where does this implementation diverge from `docs/`, and what did
> you assume that the spec does not actually state? List the assumptions explicitly — I care
> more about those than about the code.

**When the exit criterion passes but something feels thin.**

> Show me the test that proves the exit criterion for this phase, and walk me through what it
> would catch and what it would miss. Then tell me what a hostile reviewer would say about it.

**When a fix comes out mediocre.**

> Knowing everything you know now, scrap that and implement the version you would have written
> if you had understood the problem at the start.

**When Claude Code proposes something the spec forbids.**

> Check `docs/06_DECISIONS.md` before proceeding. If an ADR covers this, follow it. If you think
> the ADR is wrong, make the argument and stop — do not implement an alternative and explain
> afterwards.

**Before a phase that touches access control.**

> Every read path in this phase needs a test asserting that an unauthorised principal cannot
> observe the data *or infer its existence* — not via path length, not via a degree count, not
> via a histogram bucket. Write those tests first and show them failing.

**When context is getting long.**

> Summarise the state of this phase in under 200 words: what is done, what is not, and what the
> next session needs to know. I am going to `/clear`.

---

## 4. Two things not to do

**Do not paste the specification into a prompt.** It is in `docs/`. Pasting it wastes context
and, worse, creates a second copy that drifts from the committed one.

**Do not run several phases in one session.** The phases are ordered so that each rests on the
last, and a session carrying five phases of history makes worse decisions than a fresh one
pointed at the right two documents. `/clear` between phases.
