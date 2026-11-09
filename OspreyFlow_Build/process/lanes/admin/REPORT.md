# admin lane · report · L2.7: *Needs you*, Admin's tips and Home's *What you can do* (9 November 2026)

The branch is rebased onto main f382e12. The gate head is 2cad951. Every case was shown red by a plant at its call site
(`L2.7_RED_RECORD.md`), and the lane-reviewer ran before the gates; what it found is fixed (item 9).

| Exit criterion | State | Proving test |
| --- | --- | --- |
| 1. *Needs you*: an overdue promotion served only to a current recipient while it still waits; proposals counted only in the reader's reach, none above their clearance | met | `test_needs_you.py` (16; plants P1–P8); `needsYou/*.test.tsx` (J1–J9); keyboard `needs-you.spec.ts` |
| 2. Admin's *Proposed types* removed | met | `AdminPlace.test.tsx`, `AdminSections.test.tsx`; `test_link_type_routes.py`'s list case |
| 3. Connections' SQL, API and JSON fields; no secret returned | met | `test_admin_connection_fields.py` (the 422 echo, red first); `Connections.test.tsx` (K1–K3); keyboard (API, SQL, JSON, Test) |
| 4. The grading scheme, read-only | met | `GradingScheme.test.tsx`; `test_admin_sections.py`'s `REFERENCE_READS` pin; keyboard copy case |
| 5. Tips; refusals name the roles that can, never people; Home's section | met as far as sources exist (see "Left") | `adminWords.test.tsx` (T1–T4), `refusals.test.tsx`, `home/answersFor.test.tsx` (H1–H5); keyboard tips and Home cases |
| Keyboard (rule 13) | met | `gates/405bdf2.keyboard.txt`: 99 passed, plus `needs-you.spec.ts` 6/6 with its expectation corrected |
| axe in dark, light and GOV.UK | met | `gates/405bdf2.axe.txt`: 760/760 (it caught a WCAG 2.5.3 name at f170cfa, fixed) |

1. **Gates.**
   - `make -k ci` at 2cad951 (`gates/2cad951.ci.txt`): green except main's own E501 (fixed on main since, at b0671be), the 8 image scans, opentofu and chart. Docker is off here.
   - `make test` and test-js on the server at 405bdf2 (`gates/405bdf2.test.txt`).
   - Live on stack f (`gates/2cad951.live.txt`).
2. **Left, with why:**
   - Home's *through a team*, *Lead of*, *Covering*, *Owner of watches* and the waiting counts on *Author of* lines. No read gives them; spec 02 records this (rule 11).
   - An overdue promotion opens nothing for an Author without `operate_schedules` until L3.4's review screen exists.
   - The top bar re-reads on its minute, not on a Model tab decision (the review's minor 14).
3. **Commits:** `git log f382e12..2cad951`. The schemas commit (`NeedsYou`) is first.
4. **Requests at the merge:**
   - Apply `registry-L2.7.diff` (`NEEDS_YOU_ACTIONS`, eleven `ADMIN_ACTIONS` ids, and rules-b's two).
   - Land the schemas commit first.
   - Ratify these files outside admin's map:
     - rules': `home/{HomePage.tsx,answersFor.ts,answersFor.test.tsx,AnswersForSection.tsx}`, `shell/startScreen.tsx`, `rights/visibility.ts` (a comment);
     - studio's: `ingest/IngestStudio.tsx`, `keyboard/ingest-studio-harness.tsx`;
     - case-b's: `linktypes/ModelProposals.tsx` (`onDecided`), `services/api/link_type_store.py` and `link_types.py` (the narrowing), and `test_link_type_{routes,service,store}.py`;
     - no listed owner: `App.tsx`, `a11y/every-harness.spec.ts`, `test_route_rights.py`, `test_reports_viewer_journey.py`, spec 02 and 03;
     - from the two patches: `help/roles.ts`, `help/rightNames.test.ts`.
   - Case-b: `linktypes/ProposedTypes.tsx` and its keyboard spec and harness no longer have a screen. Remove them, or keep them for the pre-Amendment-3 routes.
5. **Decisions taken** (yours to overrule):
   - (a) *Needs you* is one route naming no right, each half gated by what it lists.
   - (b) An above-clearance proposal is a flag, never a count. It is read whole inside the Conduit and reduced there, since `without_words` keeps no status.
   - (c) The pre-Amendment-3 routes are kept with no screen, their list narrowed in the query. This tightens access.
   - (d) A secret's field that isn't name-shaped is never sent, and the Conduit redacts what it refuses.
   - (e) Grading scheme exempts its reference read, pinned to that one route.
   - (f) *Why* names the reader's own roles from `placesByRole.json`. A custom role is said as "a role your administrator made".
   - (g) Openings across a reload are held in the session.
6. **Questions:** none. **Still running:** nothing once the live run ends; stack f is brought down and released.
