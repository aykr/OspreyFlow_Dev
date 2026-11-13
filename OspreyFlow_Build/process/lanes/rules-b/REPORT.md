# rules-b lane · report · v052D, Ask & Chat parts D(i) and D(ii) (13 November 2026)

(The guides step's report is in git history, at 69ef543 and before.) Brief: `BRIEF_v052D.md`. Branch
`lane/rules-b-v052D`, rebased on main dec68d0. Built at **0482cb6**. Gated head: *pending, see Gates*.
ADR-098 Am 7, ADR-129 Am 4, ADR-135 Am 12 and ADR-144 Am 4 are written. D(iii), *Whole case* through the
search service, is the next part, after studio's search service lands (Fri 20 Nov).

## Reconciliation at the start
The paused session (sol) left `wip(rules-b)` f2016bf with only HANDOFF.md: the design was worked out and no code
was written. On the ayan account, `git reset --hard` was refused by the permission classifier. So the wip commit
was rebased onto main dec68d0, and the first commit after it (b060644) deletes HANDOFF.md. The guides step (the
pasted BRIEF.md) was already on main (`services/api/guides.py`, `home/guides.ts`). The first beat showed the
orchestrator's PAUSE nudge of 21:48:57Z, which predates the 21:49:35Z pause-done. The orchestrator confirmed it
was stale.

| Item | At the start | Now |
| --- | --- | --- |
| read_from, no-docs answer, read summary, will-read route | untouched | done: `test_questions_read_from.py` (24) |
| Panel: radios, About, Will read, engine named, unusable, failed list | untouched | done: `QuestionsPanel.test.tsx` (+10) |
| Bar reconciled (ADR-144 d4) | untouched | done, as `bar-v052D.patch` (case's files) |
| Keyboard and axe | untouched | done: `questions.spec.ts` new case; axe dark/light |
| Amendments | reserved | written (3d88885) |
| packages/schemas commit | none | 0482cb6, last |

## Exit criteria
| Criterion (BRIEF_v052D D(i), D(ii)) | Met | Proved by |
| --- | --- | --- |
| Radios Selected items · Everything on the graph · Whole case; the first the default with a selection | yes | `QuestionsPanel.test.tsx` *defaults to Selected items …*, *with nothing selected …*; `questions.spec.ts` *what to read from is chosen by arrow keys …* (red with the radios' onChange a no-op: `v052D/keyboard-plant.txt`) |
| "About: Tarbuck, Kyle and 1 other" / "About: everything on the graph" | yes | *defaults to Selected items …*; *never counts in the Glass* (red with the panel's own count) |
| "Will read: …" from the server, never counted in the client | yes | `test_questions_read_from.py` *will read counts what the question then reads and sends nothing*; the panel case above |
| The engine always named, even with one | yes | *will read names the engine that will answer, not the one chosen* (red); *names the engine … even when there is only one* (red) |
| Engines that cannot be used, with reasons | yes | *will read lists an engine the material's own handling code may not reach* (red), *… no model for questions*, *… handling may not reach*; panel *lists the engines that cannot answer …* |
| A failed engine list said as failed | yes | *says the engine list failed, never that there is none* (red) |
| The bar's Ask reconciled (ADR-144 d4) | yes, as a patch | `bar-v052D.patch`: `SelectionBar.test.tsx`, `selection.spec.ts` (green applied, slot 9) |
| NoDocumentsError and its 422 removed; no docs answered from links and events, and said | yes | *with no document the model answers from the links and events and the answer says so* (red with the refusal planted back); `test_no_documents_is_no_longer_a_refusal` |
| read_from: Selected items narrows to the selection, its links and their documents | yes | *selected items reads the selection, its links and their documents* (red) |
| read summary on the answer (packages/schemas, last) | yes | *the read summary is kept with the answer and read back* (red); `test_questions_store.py` live; 0482cb6 |
| Dry-run will-read route, the same rule | yes | the will-read cases; `test_route_rights.py`, `test_investigation_levels.py` |
| Engine list with reasons from the case refusals | yes | `_unusable` uses `ModelRoutes.offered(case_datasets, held)` as `GET …/models/engines` does |
| The rules on what may leave do not change | yes | `model_routing.py` untouched; will-read calls `RoutedModel.choose` as asking does |
| Rule 4: a reader without access is not counted, quoted or cited | yes | *a hidden document and item are not counted, quoted or cited* (red with the request's count); *the cleared reader is counted …*; *an answer whose summary counts a hidden document is not shown to a lower reader* |
| Keyboard and axe in both looks; QUESTIONS_ACTIONS as a diff | yes | 21/21 keyboard (`v052D/keyboard-run2.txt`); axe dark+light (`v052D/axe-run2.txt`); `registry-v052D.patch` |

## Gates (raw, under `gates/`)
Pending: own review and the orchestrator's, then one rebase and one round (make test and make -k ci on the server
via `stack_lease.sh offline`, a leased live run including `test_route_rights.py` and `test_questions_store.py`).

## Decisions taken
1. **The wip commit.** `reset --hard` was refused, so it is rebased, not dropped; HANDOFF.md is deleted in
   b060644. The orchestrator agreed. The merger may squash both.
2. **No `read_from` is the selection when there is one, else the graph** (the brief's "default when something is
   selected"). `selection` with nothing selected is 422 `nothing_to_read`. The panel never sends it: *Selected
   items* is disabled, "(nothing is selected)", until something is.
3. **`selected` counts the selected nodes and links the asker's view holds; `first_selected` names nodes only.**
   A link alone gives "About: 1 selected item".
4. **Will-read is audited** (`will_read_question`, the stricter option: it is a read of the case), which needs
   admin's `audit_section.py`: `audit-v052D.patch`.
5. **Only hosted engines are listed as unusable.** A deployment with no local model says so through the routing's
   refusal words, not as a listed engine.
6. **One new keyboard id** (`choose-what-to-read-from-by-keyboard`), not the handoff's three. *Will read* and *Will
   be answered by* are announced (an `aria-live` region), not activated. The engine choice already has its id.
7. **The engine picker stays hidden below two engines** (ADR-135 d5, the Q3 answer): the engine is still always
   named, by will-read's line.
8. **Every `ReadSummary` and `WillRead` field is required in the schema**, since the Conduit always sends it, so
   the generated TS types carry no optional fields the panel would have to guard.
9. **In a case view, *Read from* applies within the view** (the graph is the view's items).
10. **Whole case is disabled in the panel and refused 422 by the server**, the interim the owner accepted
    (handoff), until D(iii).
11. **The will-read block is an `aria-live="polite"` region, not a second `role="status"`**, so the view's status
    line stays the panel's one status (the in-view keyboard case reads `getByRole("status")`).

## Out of the lane's map (sent as patches, `process/lanes/rules-b/v052D/`)
See `PATCHES.md` § v052D.

## Requests to the orchestrator
- Apply `audit-v052D.patch` and `spec03-v052D.patch` with the merge (each gate red without it), and
  `registry-v052D.patch` (the new keyboard case registers its id).
- `bar-v052D.patch` to case/case-b (agreed with case-b, 13 Nov: folded into their shared action list if theirs
  lands first); `user-guide-v052D.patch` to docs.

## Questions for the owner
None.

## Still running
Nothing.
