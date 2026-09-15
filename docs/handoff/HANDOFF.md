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

These instructions assume an empty repository. If you already have one — from an earlier attempt
at this project, or otherwise — skip the `mkdir` and `git init` and see Step 2, which covers what
to do about anything already there.

```bash
mkdir ospreyflow && cd ospreyflow
git init
mkdir -p docs
# copy the spec pack — all 12 files, keeping the design/ subfolder
cp -r /path/to/ospreyflow-spec-v1.1/* docs/
git add -A && git commit -m "docs: OspreyFlow specification pack v1.1"
```

Commit the pack before writing any code. Every later commit is then diffable against a fixed
baseline, and when a decision changes you can see which code predated it.

## Step 2 — Add `CLAUDE.md` at the repository root

Copy the `CLAUDE.md` next to this file into the repository root. It is short on purpose: it
points at the pack rather than repeating it, and states the rules that must hold in every session
regardless of what is being built.

### If a `CLAUDE.md` already exists — do not overwrite it blind

Find out which one it is first. Claude Code reads several memory files and concatenates them, so
"the CLAUDE.md in my root directory" can mean different things:

| File | Scope | What to do |
| --- | --- | --- |
| `~/.claude/CLAUDE.md` | **Your** preferences, every project on the machine | Leave it completely alone. This is not the project file and the one in `handoff/` does not belong here |
| `./CLAUDE.md` in the OspreyFlow repo | Project memory, shared via git | Merge — see below |
| `./CLAUDE.md` in some other repo | A different project | You are in the wrong directory |
| `./CLAUDE.local.md` | Your machine-specific project notes | Leave alone; it is gitignored and personal |

The quickest way to see what is actually loaded is to open Claude Code in the directory and run
`/memory`, which lists every memory file in the hierarchy with its path.

### Merging rather than replacing

If the existing file is project memory for this repository — most likely from an earlier run at
this build — read it before touching it. Two kinds of content, treated differently:

**Keep** anything true about your environment that the spec cannot know: build and test commands
that actually work, local tooling quirks, proxy or registry settings, paths, anything you learned
the hard way. This is the content with real value in a `CLAUDE.md` and it is not in the pack.

**Replace** anything describing architecture, conventions or rules. The pack is now the source of
truth for all of that, and two descriptions of the same architecture will drift and contradict
each other. Take the spec-pointer table and the ten standing rules from `handoff/CLAUDE.md`
wholesale.

If you would rather not merge by hand, this works well:

> I have an existing `CLAUDE.md` and a replacement at `docs/handoff/CLAUDE.md`. Read both. Keep
> anything in the existing file that is specific to my environment — commands that work, local
> quirks, paths. Take the architecture, conventions and rules from the replacement. Show me the
> merged file before writing it, and tell me what you dropped and why.

### Keep it short

Claude Code loads memory files on every turn, and adherence drops as they get longer — the
official guidance puts the threshold around 200 lines. `handoff/CLAUDE.md` is deliberately under
100 so a merge has room.

If it grows past that, two options rather than deleting content: split path-scoped rules into
`.claude/rules/*.md`, which load only when Claude works on matching files, or pull sections into
separate files referenced with `@path/to/file.md` imports. Note that imports load at launch too,
so they help organisation rather than context size. Details are at
https://docs.claude.com/en/docs/claude-code/memory.

## Step 3 — Add the phase command

A custom slash command in Claude Code is just a markdown file. Put one at
`.claude/commands/phase.md` and it becomes `/phase`, callable as `/phase 1`, `/phase 2` and so
on. The file's body is the prompt; `$ARGUMENTS` is replaced by whatever you type after the
command name.

Run this from the repository root. The quoted `'EOF'` matters — it stops the shell expanding
`$ARGUMENTS` before the file is written.

```bash
mkdir -p .claude/commands

cat > .claude/commands/phase.md <<'EOF'
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
EOF

git add .claude && git commit -m "chore: add /phase command"
```

To check it took, open Claude Code in the repository and type `/` — the command list appears,
with `phase` and its description in it. If it is missing, the usual causes are the file being
somewhere other than `.claude/commands/` relative to the directory you launched from, or a
malformed frontmatter block.

Because `.claude/commands/` is committed, anyone else on the repository gets the same command.
Commands you want only for yourself go in `~/.claude/commands/` instead.

The same pattern is worth reusing later. A `/grill` command holding the end-of-phase challenge
prompt from `PROMPTS.md` §3 saves retyping it ten times, and the habit of putting a prompt in a
file rather than in your head is the same discipline as putting the spec in `docs/`.

## Step 3a — Optional: index with a knowledge-graph tool

Skippable. Nothing later depends on it, and the honest expected benefit is in the region of
15–20% fewer tool calls on planning-shaped work. Worth having, not worth delaying the build for.

### First, check you actually have one

Tools in this class install in three different ways and the commands differ completely. Find out
which you have before running anything:

```bash
# a CLI on your PATH?
which graphify || pip show graphify 2>/dev/null || pipx list 2>/dev/null | grep -i graphify

# a Claude Code skill or plugin?
ls ~/.claude/skills/ .claude/skills/ 2>/dev/null
cat ~/.claude/plugins/installed_plugins.json 2>/dev/null

# an MCP server?
cat .mcp.json 2>/dev/null; grep -i graph ~/.claude.json 2>/dev/null | head
```

If all of those come back empty, it is not installed — adding a marketplace is not the same as
installing a plugin from it, and the difference is silent. Either install it properly from its
own documentation, or skip this step and carry on. Do not spend Phase 0's time on it.

### If it is a skill, plugin or MCP server

No terminal needed. Open Claude Code in the repository and ask:

> Use graphify to build a knowledge graph index of this repository. Exclude `node_modules`,
> `.venv`, `dist`, `build` and `tests/scenarios/fixtures`. Tell me where the index is written so
> I can gitignore it, and confirm how many files and nodes it indexed.

### If it is a CLI

Run `graphify --help` first — flags belong to the tool, not to this document.

```bash
cd ospreyflow
graphify install                      # registers it with Claude Code

cat > .graphifyignore <<'EOF'
node_modules/
.venv/
dist/
build/
tests/scenarios/fixtures/
**/*.parquet
**/*.pmtiles
EOF

graphify update .
echo ".graphify/" >> .gitignore        # whichever directory it actually writes
git add .graphifyignore .gitignore && git commit -m "chore: graph index config"
```

Point it at the repository root rather than `docs/`. Right now they amount to the same thing,
and nothing needs changing when code arrives at Phase 2.

### When to index

**`docs/` now, before the kickoff prompt.** The usual advice is to wait for a codebase, which is
wrong here. For the first several phases the read-heavy artefact is not the code — there barely
is any — it is the specification: about 31,000 words across 13 files, densely cross-referenced.
Following "see ADR-006" or "`01_DOMAIN_MODEL.md` §7" without an index means re-reading whole
documents to resolve one reference, in every session. Tools in this class index prose as well as
code, so that cross-reference web is exactly what they are good at.

**Code at the end of Phase 2, not before.** Phases 0 to 2 produce scaffolding, ports and the
ingest path — too little code to earn the upkeep, and it changes shape constantly. Re-index at
the end of each phase after that.

### Verify it earns its place

Ask something you already know the answer to, which needs a cross-reference rather than one file:

> Which decision records govern how entity resolution is stored, and which specification
> sections do they change? Answer from the graph, then tell me which files you would have had to
> read without it.

The answer is ADR-006 and ADR-018, touching `01_DOMAIN_MODEL.md` §4 and
`03_CONDUIT_MIDDLEWARE.md` §5.3. One or two queries means it is working. A scan of the whole
pack means you have a dependency rather than a benefit — drop it.

### Three rules that matter more here than usual

1. **The graph is a navigation aid, never a source of truth.** A stale graph answering from a
   pre-acceptance snapshot of `06_DECISIONS.md` is worse than no graph. When a decision or a
   spec section governs what is about to be built, the file gets read.
2. **Re-index whenever `docs/` changes**, particularly after an ADR status change. A
   `post-commit` hook filtering on `^docs/` handles it.
3. **Exclude fixtures** alongside the usual directories. Indexing synthetic test data produces
   confident answers about scaffolding.

Keep the generated index out of git. It is a derived artefact, like a build output.

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
