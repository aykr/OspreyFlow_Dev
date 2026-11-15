# Giving a client their own sign-in on the GOV.UK demo

For the owner, from the orchestrator, 14 November 2026, after the owner's answers that evening (MORNING.md,
"evening (3)") and studio's proposal (`process/lanes/studio/demo-signins/PROPOSAL.md`). **Revised for v0.6.0**
(docs, 15 November 2026): the demo is rebuilt fresh from v0.6.0 on Wednesday 18 November
(`REBUILD_2026-11-18.md`). Nothing here is printed, logged or written to a file by any tool: you type each password
and code yourself and hand them over yourself.

**After the rebuild, nothing of the old demo's people carries over.** v0.6.0 is a new deployment with new stores:
the Demo visitor role, any visitor you added before, and their cases are not there. Add each visitor again, below.

**Before the first sign-in:** the open-defects list (`OPEN_DEFECTS_FOR_SIGNINS.md`, beside this file) is empty or
each item is accepted by you.

## Once: the Demo visitor role

The orchestrator makes it again at the v0.6.0 rebuild (`REBUILD_2026-11-18.md`, step 8); it is listed here so you
can check it.

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

Gemini there is Google's free tier, which may use visitors' questions to improve Google's products.

The demo offers Gemini (`gemini-3.8-flash`) in Ask & Chat beside its own model, and every answer names the engine
that gave it. Gemini has **one shared limit** for everyone: **1,000,000 tokens a day** in **Admin › Models**, set at
the rebuild, inside the free tier's daily limit, and reset at midnight UTC (midnight in the UK until March). Change it
there, and check its use under **Usage**. When it is reached, a visitor is told in words that the limit has been
reached; nothing hangs and nothing is recorded. Google's own limits on the free tier (15 requests a minute, 500 a
day) can refuse first: the visitor is then told, in words naming the engine, that the provider refused. The
deployment's own model still answers either way.

Gemini can be chosen only in a case whose datasets allow it: the rebuild sets each demo dataset's egress to `any`
in **Admin › Datasets**. A visitor's own case, made over those datasets, inherits that.

## When a visitor is done

1. **Admin › People and roles**: find them and **Remove**. Their sign-in stops at once.
2. Their case: leave it for your records, or **Remove** it.
3. **Never restore a backup to remove visitors.** A restore brings every person back without a password, the
   administrator included (B9 in the defects list).
