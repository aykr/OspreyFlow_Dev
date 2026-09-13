# Handing the pack to Claude Code

How to get from this specification to a repository that builds. Three files matter: this one,
`CLAUDE.md` (copy to your repo root), and `PROMPTS.md` (the prompts to paste).

For installing and configuring Claude Code itself, follow the current official documentation at
https://docs.claude.com/en/docs/claude-code/overview — versions move, and this document
deliberately does not restate anything that will go stale.

---

## The principle: the spec lives in the repo, not in the prompt

The pack is about 31,000 words. Pasting it into a prompt is the wrong shape — it burns context
on every session, and the parts that matter differ per phase.

Instead: the pack goes into the repository as `docs/`, `CLAUDE.md` tells Claude Code it exists
and which parts are binding, and each prompt names the two or three documents relevant to that
phase. Claude Code reads what it needs, when it needs it.

---

## Step 1 — Create the repository and drop the pack in

```bash
mkdir mantisnexus && cd mantisnexus
git init
mkdir -p docs
# copy the spec pack — all 12 files, keeping the design/ subfolder
cp -r /path/to/mantisnexus-spec-v1.1/* docs/
git add -A && git commit -m "docs: MantisNexus specification pack v1.1"
```

Commit the pack before writing any code. Every later commit is then diffable against a fixed
baseline, and when a decision changes you can see which code predated it.

## Step 2 — Add `CLAUDE.md` at the repository root

Copy the file next to this one. It is short on purpose: it points at the pack rather than
repeating it, and it states the handful of rules that must hold in every session regardless of
what is being built.

Keep it under roughly 100 lines. A long `CLAUDE.md` is loaded on every turn and crowds out the
work.

## Step 3 — Add the phase commands

```bash
mkdir -p .claude/commands
```

`PROMPTS.md` contains a `/phase` command to save as `.claude/commands/phase.md`. It turns
starting a phase into `/phase 1` rather than pasting several paragraphs each time.

## Step 4 — Start in plan mode, one phase per session

Open Claude Code in the repository and press **Shift+Tab** to enter plan mode before asking for
anything. Plan mode makes Claude read and propose rather than start writing files, which is what
you want at the top of a phase — the plan is where a misreading of the spec is cheap to catch.

Run the kickoff prompt from `PROMPTS.md`. Review the plan against the phase's exit criteria in
`docs/07_BUILD_PLAN.md`. Approve, then let it build.

## Step 5 — Clear between phases

Run `/clear` at the end of each phase. Phase 3 does not need Phase 2's context, and a session
carrying five phases of history makes worse decisions than a fresh one pointed at the right two
documents.

The phase is done when its exit criterion passes in CI, not when the code looks finished. The
exit criteria are written as tests for exactly this reason.

---

## Session hygiene that matters for this project specifically

**Conformance suites before adapters.** Standing rule 1 in `docs/07_BUILD_PLAN.md`. If Claude
Code proposes writing an adapter first, stop it — an adapter written first defines the contract
by accident, and the whole swap-boundary claim rests on the suite being independent of it.

**Watch for silent truncation.** The most likely place Claude Code will quietly do the wrong
thing is the working-set cap. The correct behaviour is a typed `limit_exceeded` error offering
three choices. A `[:50000]` slice anywhere near the working set is a defect, not an
optimisation.

**Watch for filtering after retrieval.** Access control belongs in the adapter, injected into
the traversal or the `WHERE` clause. Filtering in the Conduit after the data comes back is the
easy implementation and it leaks existence through counts and timing.

**Push back on plausible-looking shortcuts.** Two that will come up: an expression language in
the Ingest Studio (ADR-018 refuses it) and merging entities at ingest (ADR-006 refuses it). Both
are reasonable-sounding and both are recorded refusals with reasons.

**Challenge the work.** A useful habit at the end of a phase: *"Grill me on these changes.
Where does this implementation diverge from the spec, and what did you assume that the spec
does not state?"* The assumptions are where the divergence hides.

---

## Order of work

Phases 0 to 2 are the ones to get right slowly. Everything after them is built on the ports, the
domain model and the ingest path, and errors there are expensive to unwind.

| Phase | Roughly | Notes |
| --- | --- | --- |
| 0 — Skeleton and guard rails | Small | Do not skip the licence check and the type-generation gate |
| 1 — Domain model and graph adapter | Large | The handling and provenance blocks must be in from the first write |
| 2 — Ingest, normalisation, staging | Large | Normalisers are the highest-value tests in the build |
| 3 — Conduit and working set | Medium | |
| 4 — The Glass, first light | Large | |
| 5 — Temporal and geospatial | Large | |
| 5a — Ingest Studio | Large | Prototype the Map screen back in Phase 2 (ADR-018) |
| 6 — Extraction and resolution | Large | Golden set with the first extraction commit, not after |
| 7 — Analytics, patterns, alerting | Medium | |
| 8 — Assessment, export, second profile | Large | |

A phase that produces no failing test before it produces code is a phase to be suspicious of.
