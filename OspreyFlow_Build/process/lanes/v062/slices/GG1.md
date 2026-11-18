# Slice GG1 · GG1 · The drawn-merge sheet moves focus only when drawn and when sent

- **Build id:** GG1
- **Dial setting:** balanced
- **Rounds limit:** 2
- **After:** AD2 (same track, one at a time; both are in the workspace)
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

Edit `apps/workspace/keyboard/drawn-merge.spec.ts` (rule 13): changing a "goes in as" select leaves focus on that select
(and on a Match box after toggling it); the heading takes focus when the sheet is first drawn and again when it is sent.
New vitest case in `src/ingest/runs/drawnMerge.test.tsx` for the same two moments (it has no focus assertion today).
Red today: focus lands on the heading after the select change, the very line the old spec asserts.

## Checks

`src/ingest/runs` vitest; `keyboard/drawn-merge.spec.ts`; `keyboard/promotions` specs that share the sheet
(`promotions.test.tsx:162, :178`).

## Out of scope

Any other focus move in the audit's record; PL4. No server, schema or generated-type change.
