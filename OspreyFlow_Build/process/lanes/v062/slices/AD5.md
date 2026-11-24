# Slice AD5 · AD5 · The invite form reads everything it needs before it offers a choice (one loader; the two faults AD2 was merged with)

- **Build id:** AD5 (the invite form's loader). **The owner's ruling of 19 November 2026:** AD2 is merged as it is, with two faults in behaviour open; they become this build. **The owner's word of the night of 23 November 2026:** a part for every build whose needs are met; AD5's needs (AD2, PL4) are merged. The scout's list of every read is below, as the plan's own note required ("scouted first").
- **Dial setting:** balanced. **Rounds limit:** the dial's (8).
- **After:** nothing unmerged. **It touches `apps/workspace` (React) only in the Admin People section** and never the plain modules in `packages/glass-shared` beyond what the loader needs.

## The two faults (BACKLOG, the AD2 set-aside row, 19 November)

1. **The form can be drawn before the roles catalogue has loaded, and when that load fails.** `InviteGate` draws the form when the inviter's details and the handling scheme are ready; the form also reads the roles catalogue to decide which role boxes it offers.
2. **A handling scheme whose classification list is empty counts as loaded.** `useSchemeRead` checks only that the list is an array, so an empty list becomes "ready" with no levels, and the form then states what the inviter can give on the strength of nothing.

## Every read the invite form makes (the scout's list, 23 November 2026; re-read each line)

All in `OspreyFlow_Core/apps/workspace/src/admin/` unless stated:

- `AdminPlace.tsx` about lines 163 to 169: `GET /v1/me` (the inviter); a failure sets "unavailable"; provided through context at about line 208. `inviter.ts` lines 9 to 14: the context's default is "waiting".
- `sections/People.tsx` about lines 161 to 181 (`useSchemeRead`): `GET /v1/handling-scheme` (about line 168). **Fault 2 is line 172**: only `Array.isArray(body.classification)`.
- `sections/People.tsx` about lines 1300 to 1312 (`readContext`): `listRoles(api)`, the roles catalogue, **with the error swallowed (about line 1309): fault 1**; `InviteGate` does not wait on it.
- `sections/People.tsx` about line 1310: `peopleRows(api)` (`OspreyFlow_Core/packages/glass-shared/src/admin/api.ts` about line 237), which feeds the context's rows.
- `sections/People.tsx` about lines 1314 to 1325: an effect calling `listPeople`, `listArrivals`, `signInKind` (which decides whether the invite gate is drawn at all, about line 1406) and `readContext`.
- `sections/People.tsx` about lines 1017 to 1047 (`InviteGate`): draws the form only when the inviter read and the scheme read are both ready; **the roles catalogue is not among them.** About lines 1049 to 1076 (`InviteForm`): the scheme, the inviter, `givableLevels` and `givableCodes` (glass-shared), and the context through `withheldRights` (about lines 1071 and 1072). About line 1093: `invitePerson` (a write, not a read).
- **The scout did not find the URL behind `listRoles`** (probably `/v1/admin/roles`): read it.

## What (red first; planted faults at the shape the code really sees: rule 15)

1. **One loader that waits for everything the form reads** (the list above, and anything you find that it omits: **say so in your report if you find one**), and **the form drawn only when every read has arrived**: while any read is still loading or has failed, the form shows the loading message or an error message in words, **never a choice and never a statement of what the inviter can give.** (The owner's design rule for AD2, 19 November.) Each read's failure shows its own words and does not hide a different failure.
2. **An empty classification list is not "loaded".** It is shown as an error in words (the handling scheme has no levels), never as a form that offers nothing.
3. **Tests (vitest, a new file named in the row), each red first on main:** the roles catalogue late (the form is not drawn until it arrives) and failed (the error in words, no form); the scheme with an empty classification list; the inviter's details failed; **each read late and failed in turn, so no order of arrival draws the form early.** **A test double that refuses what the real route's giver rule refuses (rule 15: the AD2 double refused less):** read the Conduit's invite route and its giver rule (`OspreyFlow_Build/tests/services/api/test_admin_sections.py` and the route in `OspreyFlow_Core/services/api/app.py`) and model the refusals, not only the happy path.
4. **Keyboard (rule 13):** the keyboard walkthrough reaches the invite form today (the AD2 plan said the walk's invite test stays or goes with this part: say which and why). If the form's loading and error states add an action, it gets its own step in `OspreyFlow_Core/apps/workspace/keyboard/admin.spec.ts` in the same change.
5. **Nothing else.** No change to what the form offers once everything has loaded, to the Conduit, to the plain `givableCodes` and `givableLevels`, or to any other Admin section.

## Acceptance test

`OspreyFlow_Core/apps/workspace/src/admin/sections/PeopleInviteLoads.test.tsx` (new, vitest, red first), run as `npm exec --workspace apps/workspace -- vitest run PeopleInviteLoads` (the filter `npm test` ignores: see AD1b's row).

## Checks

The new test; the existing `PeopleInvite.test.tsx` and the other Admin vitest files; `npm run lint`, `npm run typecheck`, `node scripts/no_react_check.mjs` from `OspreyFlow_Core`; `OspreyFlow_Build/tests/test_doc_citations_check.py`; `ruff check .`. Before your final report run by hand what the conductor runs again: eslint on every file changed.

## Round 2 (the conductor, 24 November 2026, 00:30 UTC): one fault and one gap, both in the loader you built

**This names an access rule (the form must never offer more than the inviter may give, rule 3). It is a fault in your own check, so you fix it; it is reported to the owner in the morning, never accepted narrower.**

1. **Fault: the roles catalogue check is too weak, and it is the same fault as fault 2 had for the scheme.** `People.tsx` about line 1338 refuses only `!Array.isArray(c.built_in) || !Array.isArray(c.custom)`, so `{built_in: [], custom: []}` counts as loaded, `rolesRead` becomes "ready", and the form is drawn offering every role, Admin included, to a giver who does not hold its rights (`rightsOf` reads `ctx.builtIn[role] ?? []`, which is empty, so nothing is withheld). **Do this:** the catalogue counts as loaded only when it **names every built-in role the form offers** (the form's `ROLES` list, about lines 54 to 60) with its rights; an empty or partial catalogue is an error **in words** (the roles could not be read in full), never a form. Red first: an empty `built_in`, a `built_in` that lacks one role the form offers, and one that has every role, each drawn or refused as the rule says, and the form never offering a box for a role the catalogue does not carry.
2. **Fix the false fixture:** `AdminPlace.test.tsx` about line 31 answers `{built_in: [], custom: []}` with the comment "as the real routes answer them". **The real route never sends that shape** (`list_roles_route`, `OspreyFlow_Core/services/api/app.py` about lines 17309 to 17326, always returns the built-in roles). Make the fixture answer the real shape (the built-in roles with their rights) and correct the comment.
3. **Gap: the fetch double claims refusals it does not model.** `PeopleInviteLoads.test.tsx`'s header says the double "refuses a read the real route refuses too: the roles catalogue and the people routes need `manage_people`", but its GET branches (`roles`, `sign-in`, `people`, `people/rows`) answer whatever rights the giver holds; only POST people reads the held set. **Model it:** a giver without `manage_people` is refused on the roles, sign-in and people reads (the real routes carry `require_right(MANAGE_PEOPLE)`; read the route's refusal shape), and a test shows the form then shows the error in words and offers nothing. Or, if you cannot, correct the header to say what the double does and add the case to the report as owed. **Prefer modelling it.**
4. Nothing else. Re-run your checks and `npm run lint`, `npm run typecheck`, `node scripts/no_react_check.mjs`.

## Never merge another part's unmerged tip (the owner, 23 November 2026)

**Never merge another part's unmerged tip, or any branch but main, into your branch.** Take main in when the line tells you to, and nothing else. If your part needs another part's change that has not merged, stop and tell the conductor.

## Out of scope

Any Conduit change; `packages/glass-shared` beyond what the loader needs (the plain parts moved in PL4); the GOV.UK pages' Admin (AD3). **A finding that names a key, a credential or a security rule is stopped and reported, never accepted narrower.** The invite form decides what a person may give (access control, rule 3): **a fault that lets the form offer more than the inviter may give is stopped and reported.**
