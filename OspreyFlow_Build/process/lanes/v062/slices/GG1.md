# Slice GG1 · GG1 · The drawn-merge sheet moves focus only when drawn and when sent

- **Build id:** GG1
- **Dial setting:** balanced
- **Rounds limit:** 2
- **After:** nothing (unhooked by the owner, 19 November 2026: it ran after AD2 only for ordering; both change the workspace, so a conflicting merge is refused by the merge script and is then the second slice's to redo)
- **Status of this brief:** APPROVED by the owner, 18 November 2026.

## What

The fault, recorded once, at `OspreyFlow_Build/process/lanes/rules-b/v060-focus-move-audit/RECORD.md:51-54` (and
`lanes/MORNING.md:2205`, 16 Nov, WCAG 3.2.2): `drawnMerge.tsx`'s `[sheet, sent]` effect (`apps/workspace/src/ingest/runs/
drawnMerge.tsx:107-113`) moves focus onto the sheet's heading on every Match re-read, so a keyboard user who changes a
"goes in as" or "goes into" select is taken to the heading after each choice and must Tab back. Fix: move focus only
when the sheet is first drawn and when it is sent. The id "GG1" appears nowhere else in the repository and the fault is
not in `CARRIES.md` or `spec/`; this brief is its first complete statement. The branch `lane/rules-b-v060-focus-move-audit`
(74cc258) is not in this checkout and was not read; its `proof.spec.ts.txt` sketch may help the builder.

The existing keyboard spec enshrines the fault: `apps/workspace/keyboard/drawn-merge.spec.ts:88-91` and `:100` assert
the heading takes focus after each choice. That spec changes with the fix.

## Acceptance test

Two new files carry the new cases, because the existing spec asserts the fault and passes today (so an acceptance that ran
only the existing files would not be red on main): the keyboard spec OspreyFlow_Core/apps/workspace/keyboard/drawn-merge-focus.spec.ts (rule 13:
changing a "goes in as" select leaves focus on that select, and on a Match box after toggling it; the heading takes focus
when the sheet is first drawn and again when it is sent), and the vitest file
OspreyFlow_Core/apps/workspace/src/ingest/runs/drawnMergeFocus.test.tsx for the same two moments (the existing vitest file has no focus
assertion). Red today: focus lands on the heading after the select change. The existing keyboard spec, drawn-merge.spec.ts
(lines 88-91 and 100), asserts that the heading takes focus after each choice: the slice changes those assertions to
match the fix (it stays in the checks, which run every drawn-merge keyboard spec).

## Checks

`src/ingest/runs` vitest; `keyboard/drawn-merge.spec.ts`; `keyboard/promotions` specs that share the sheet
(`promotions.test.tsx:162, :178`).

## First step, from the conductor (19 November 2026)

Your branch was cut from main before the owner's commit c7fda31, which allows the 25 paths ADR-152 names. Until your branch
has it, the citations scan (test_the_repository_itself_is_clean) is red for files you did not touch, and no change of yours
can fix that. Before anything else, merge main into your branch (git merge main in your worktree), then run the checks. Do
not change any citation, allowlist or spec file.

## Out of scope

Any other focus move in the audit's record; PL4. No server, schema or generated-type change.
