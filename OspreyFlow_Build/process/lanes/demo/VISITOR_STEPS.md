# Giving a client their own sign-in on the GOV.UK demo

For the owner, from the orchestrator, 14 November 2026, after the owner's answers that evening (MORNING.md,
"evening (3)") and studio's proposal (`process/lanes/studio/demo-signins/PROPOSAL.md`). Nothing here is printed,
logged or written to a file by any tool: you type each password and code yourself and hand them over yourself.

**Before the first sign-in:** the open-defects list (`OPEN_DEFECTS_FOR_SIGNINS.md`, beside this file) is empty or
each item is accepted by you.

## Once: the Demo visitor role

The orchestrator makes this at the demo update; it is listed here so you can check it.

1. Sign in to https://govuk.ospreyflow.app as the demo administrator.
2. **Admin › Roles › New role**, named **Demo visitor**.
3. Give it the Analyst's rights **except** these five: *Create a case*, *Share a case*, *Remove a case*, *Export*
   and *Export override*. Save. (A visitor holding any of them could make a case of their own, become its Author and
   add any dataset their markings allow, or take data out.)

## For each visitor

1. **Admin › People and roles › Add person**: their name and e-mail, the role **Demo visitor** only, never Admin.
   Set their clearance, unit and handling codes to the demo's visitor values (OFFICIAL, the demo's unit, no codes
   beyond what the demo cases need).
2. The page shows a **one-time code once**, in your browser. Send it to the visitor yourself; they set their own
   password at first sign-in. Nothing keeps the code.
3. **Make their case**: open the demo dataset's case list as yourself, **New case** named for the visitor, over the
   shared demo datasets; then **Share** it with them at **Editor**. Each visitor works in their own case, so one
   person's changes are never the next person's starting point.
4. **The access gate**: the demo also asks for the site's access key before the sign-in page. Give the visitor the
   key with their code, by a different channel from the code if you can.

## The model's spend

The demo's model (Gemini) has **one shared limit** for everyone. Set it in **Admin › Models** to what you are willing
to spend while clients use the demo, and check it there. When it is reached, a visitor is told in words that the
limit has been reached; nothing hangs and nothing is recorded.

## When a visitor is done

1. **Admin › People and roles**: find them and **Remove**. Their sign-in stops at once.
2. Their case: leave it for your records, or **Remove** it.
3. **Never restore a backup to remove visitors.** A restore brings every person back without a password, the
   administrator included (B9 in the defects list).
