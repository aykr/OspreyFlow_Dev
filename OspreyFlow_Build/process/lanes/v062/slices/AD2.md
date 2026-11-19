# Slice AD2 · AD2 · Invite a person offers only what the inviter can give, and the refusal sits by the button

- **Build id:** AD2
- **Dial setting:** balanced
- **Rounds limit:** 2
- **After:** SE1 (same track, one at a time)
- **Status of this brief:** APPROVED by the owner, 18 November 2026.

## What

Found 17 Nov on the GOV.UK demo (`BACKLOG.md`, "Findings from the owner's laptop reinstall"): the demo admin
(OFFICIAL, P) chose OFFICIAL-SENSITIVE with P, C, R and got 403 `above_your_clearance`; the refusal showed only in the
form's intro text, so Invite seemed to do nothing. Wanted: offer only what the admin can give, and put the refusal by
the button as an error summary. Spec: `spec/02_GLASS_FRONTEND.md` lines ~644, 676, 1314 (a refusal is said on the form,
in words; GOV.UK forms use an error summary).

What exists (scouted 18 Nov): the form is `InviteForm`, `apps/workspace/src/admin/sections/People.tsx:993-1127`; its
options come from `useScheme` (`:150-161`, `GET /v1/handling-scheme`, the whole vocabulary); the inviter's own
clearance and receivable codes already come from `GET /v1/me` (`app.py:20117-20128`) into `DisplayPrincipal`
(`auth/userManager.ts:36-62`) but `AdminPlace` passes `People` only `rights`. The server check exists
(`app.py:17559-17586`, `_within_your_reach`: 403 `above_your_clearance`, then `handling_code_you_do_not_hold`) and stays
the authority; the client filter is a convenience, not a control. The refusal renders as `role="alert"` above the
fields (`People.tsx:1052`); the pattern to reuse is `govuk-error-summary` with a focusable heading
(`boards/BoardEditor.tsx:330-332`). No server or schema change is expected.

## Acceptance test

A new vitest file named PeopleInvite, beside `People.tsx` in `apps/workspace/src/admin/sections/`: an inviter at OFFICIAL is not offered
OFFICIAL-SENSITIVE, nor a handling code outside their receivable set; a 403 from the route (forced by the test's fetch
double, which also refuses the way the real route does) puts an error summary beside the Invite button, naming the
reason in words, and focus goes to it. Plus a new case in `apps/workspace/keyboard/admin.spec.ts` (rule 13): invite by
keyboard with a refused choice reaches the summary. Red today: the options include the higher clearance, and no summary
exists by the button.

## Checks

`src/admin` vitest; the server test `OspreyFlow_Build/tests/services/api/test_admin_routes.py` (unchanged, must stay
green); the keyboard spec for admin.

## Out of scope

The server check; the model form (AD1); PL4's shared-package move (this slice is merged before it starts).

## Round instruction from the owner (18 November 2026)

To the builder: the findings in your prompt are every finding from the last verifier. Fix those and nothing else: no other change, no tidy-up, no new scope.

To the verifier on this round: list every remaining finding in one pass, not the first few. Begin the "what" of each finding with "FAULT IN BEHAVIOUR:" when the shipped code does the wrong thing, or "GAP IN A TEST:" when the code may be right but no test would fail if it were wrong. The conductor reports the split to the owner.

## Owner's design rule for the next round (19 November 2026)

The invite form is drawn only once the inviter's details (the answer to GET /v1/me) have arrived, so no choice can be
made before them. This replaces any handling of a choice made before the details arrive: nothing is chosen early, so
nothing is filtered, reset or hidden afterwards. Add a test that fails if the form can be used before the details
arrive (the clearance select, the handling-code boxes and the Invite button are not there or not usable until then).
What the form shows while it waits, and what it says in words if the details cannot be had, is the builder's to settle;
a test shows each. The test gap on a clearance outside the scheme is fixed in the same round. Nothing else changes.
