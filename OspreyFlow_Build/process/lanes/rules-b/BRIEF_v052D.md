# Rules-b lane · brief v052D · Ask & Chat (the owner's Part D, 13 November 2026)

Written by the orchestrator for a **rules-b session on `sol`**. Read `process/lanes/NAVIGATION_2026-11-13.md`
(Part D), `process/lanes/ROUTE_052.md`, and ADR-098, ADR-129 and ADR-135 d5. Branch `lane/rules-b-v052D` from main.
Offline. Nothing merges before v0.5.1's candidate is cut. The owner's order if something must give: D without "Whole
case" comes before C and E; D's "Whole case" comes last.

## D(i) and D(ii), now (about 2–2½ days)

**The panel** (`apps/workspace/src/questions/**`; ratified for this step):
- The read-from choice as radios: Selected items · Everything on the graph · Whole case. The first is the default
  when something is selected.
- "About: Tarbuck, Kyle and 1 other", or "About: everything on the graph".
- "Will read: …", **from the server** (below). Never counted in the client, which is the principal.png mismatch.
- The engine always named, even when there is only one.
- Engines that exist but can't be used for this case, listed with their reasons.
- A failed engine list said as failed, never shown as "none" (engines.tsx is platform's: ratified for this step).
- The bar's "Ask the model about these" reconciled with the new panel (ADR-144 d4).

**The server** (`services/api/questions.py`, `evidence_brief.py`; ratified):
- Remove `NoDocumentsError` and its 422. With no documents, the model answers from the links and events, and the
  answer says that is what it read.
- A `read_from` parameter: Selected items narrows to the selection, its links and their documents.
- A `read` summary on the answer (a shared `packages/schemas` commit, last on the branch).
- A dry-run "will read" route using the same rule.
- The engine list with reasons, from the existing case refusals.
- The rules on what may leave for an outside model **do not change**.

**Tests, red first:**
- A reader without access is not counted, quoted or cited (rule 4).
- Keyboard and axe in both looks, with QUESTIONS_ACTIONS ids sent as a diff to the orchestrator.

## D(iii) "Whole case", after the search service (3d) lands on Fri 20 Nov (about 1 day)

- Call the search service (ADR-149, studio's) with the question's words.
- Take the top results the person may see as numbered sources, and cite each one (a new citation kind).
- Say in one line that it finds things by names and words.
- Extend studio's leak test to Ask's sources.

**If it can't be ready by the freeze (Tue 24), tell the orchestrator**: the owner decides before it's shown as
unavailable.

## Amendments

ADR-098 d4 (documents required, and what is read), ADR-129 (what the brief is built from), ADR-135 d5 (the picker
below two engines) and ADR-144 d4. Ask the orchestrator for reservations.
