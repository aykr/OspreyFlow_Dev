# Archive — superseded documents

Nothing in this folder is current. It is kept for reference and for tracing how a decision was
reached, not to be read as instruction. If an archived document disagrees with the numbered
specification pack in `docs/`, the pack is right.

Archived 18 September 2026, at the close of Phase 6, so that a future handover session reads one
current document per subject rather than choosing between two.

## `handoff/`

The bootstrap pack that got this specification from a folder of documents into a repository that
builds. Its job is done: the repository exists and Phases 0 through 6 are closed against it.

| File | Why it is here |
| --- | --- |
| `HANDOFF.md` | "How to get from this specification to a repository that builds" — a first-run procedure, complete since Phase 0 |
| `CLAUDE.md` | A proposed repository-root memory file. The live one at the repository root has since diverged substantially — it carries twelve standing rules (the original ten, plus two lifted from `SESSION_HANDOVER.md` on 19 September so they survive that handover being superseded) and the graphify section this copy never had. Two files of the same name saying different things is the confusion this archive exists to prevent |
| `PROMPTS.md` | The original kickoff prompt and the `/phase` command pattern. Current session prompts live in `docs/NEXT_STEPS_PHASE7.md` |

The `/phase` command idea in `PROMPTS.md` is still sound and is not superseded by anything; if it
is still in use, that is a reason to lift it into a live document rather than to keep reading it
from here.

## `SESSION_HANDOVER.md` — the 14 September original, archived 19 September

Superseded in substance by the Phase 6 → Phase 7 handover, which now lives at `docs/
SESSION_HANDOVER.md` in its place — one handover at one path, per this archive's own stated
purpose.

Eleven live citations of the old file by path turned up when the move was checked, not the three
first assumed, and not all four different things they cited. `06_DECISIONS.md` cited a standing
instruction ("a genuine spec gap gets fixed in the spec, not chat"); six `scripts/` modules cited
a second, separate passage ("no `osprey` CLI yet"); two Glass files cited a third ("invariants
stated in prose that no test exercises"). Those three passages are durable, cross-cutting facts
that happened to live only in a handover, not historical record — moved into `CLAUDE.md` (rules
11 and 12, and the Conventions section) rather than repeated per citation, and all nine of those
citations now point there. `tests/scenarios/fixtures/hmp_graph.py` cited a fourth passage
entirely (the Phase 1 ArcadeDB heap-pressure finding) — repointed to `deploy/compose/dev.yaml`,
which already carries the same finding consolidated with its own later occurrences.
`07_BUILD_PLAN.md`'s citation was the one genuinely citing this document as a historical record
rather than a rule (when the first Ingest Studio review happened) — it now points at this
archived copy directly, which is exactly the citation archiving a superseded-but-true record
should leave behind.

## `OSPREYFLOW_NEXT_STEPS.md` — a stale copy from outside `docs/`, archived 19 September

Found in a git-ignored `Claude outputs/` folder at the repository root (`.gitignore:31`), not
tracked and never staged — the same class of confusion this archive exists to prevent, just
outside `docs/` rather than inside it. Identical to `docs/NEXT_STEPS_PHASE7.md` in every section
except §5 and one housekeeping-prompt note: this copy still describes the handover/provenance
consolidation as an open problem, where the live `docs/` copy marks it resolved 19 September 2026
(see this file's own `SESSION_HANDOVER.md` entry above). Checked before moving, the same way the
`SESSION_HANDOVER.md` move was checked: a repository-wide, case-insensitive search (tracked and
untracked files) for this filename found no citation of it anywhere, by name or by path — nothing
reads from it.

## `mantisnexus-naming-brief.md` — predates the rename to OspreyFlow, archived 19 September

Also from the git-ignored `Claude outputs/` folder, also untracked. The background research behind
the product's own pre-launch name ("MantisNexus," with sub-marks "Mantis" and "Nexus") — the
research concluded and the rename happened; nothing in the live specification pack depends on this
document. Checked the same way: no citation of this filename anywhere in the repository. The one
live trace of the old name that checking this *did* turn up is `docs/DESIGN_PROVENANCE.md`'s own
title line, "MantisNexus — design provenance" — not this file's citation, a separate, live rename
artefact, corrected directly in that document (title only) rather than recorded here. That same
document's §1 table also names `MantisNexus_Brand_Foundations.html` as one of the six original
source inputs — checked and left alone deliberately: that is the real historical filename the
brand-foundations document was actually supplied under, before the project's own rename, and
correcting a citation of what a file was really called would misstate the record this document
exists to keep straight.

## `DESIGN_PROVENANCE.md` — not archived

Still stale in two sections as of 18 September — §4's defect table stopped at Phase 2 and §6
stated that an analyst review had not happened when it had — brought current on 19 September
(both sections corrected, §4 gaining rows for what Phases 3 through 6 found). The rest of it
remains the only record of why the seven overrides were made, so it stays in `docs/`, updated
rather than archived, the same reasoning that already applied before the correction: a document
wrong in two places is a correction task, not a reason to lose the eight places it is right.
