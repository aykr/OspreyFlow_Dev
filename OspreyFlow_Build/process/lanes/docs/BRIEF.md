# Docs lane · brief sites · the two new websites, ospreyflow.org and ospreyflow.net (Housekeeping)

Written by the orchestrator, 12 November 2026, at the owner's request, for the docs session on `sol`, from **main**
(branch `lane/docs-sites` from `main`). D2c is closed (its last brief is BRIEF_D2c4.md). Opus, medium.

**Priority and the server.** The demo rebuild tonight, rules' lists, GitHub CI and the v0.5.1 release keep priority
for the server, merges and reviews. This step needs no server at all: everything here runs on the Mac. Nothing of it
runs on the server, and never from 12:00 UK on Friday 13 November. Item 6 (screenshots) waits until after Friday's
demo. Not pushed; nothing published; no repository created.

**The owner's request, verbatim (it governs):**

> Take over the two new websites. The drafts are in "Claude outputs/ospreyflow_sites_2026-11-12.zip": ospreyflow.org
> (7 pages, the open-source project) and ospreyflow.net (5 pages, Solirius Reply's services), with build.py, which
> generates both. Static files, no external requests, no script.
>
> 1. Bring them into OspreyFlow_Build/marketing_site as two sites beside the current one. Recommend whether to keep
>    build.py as the generator or keep the pages hand-written, and say why. Do not change or remove the current
>    six-page site yet.
> 2. Hold every new page to the existing rules, with tests shown red first: the product statement and "Solirius
>    Reply"; "designed to meet the GDS Service Standard", with the three checks planned; no client named, no
>    competitor named, i2 only once its ADR is accepted; no local path; no credential; every internal link and
>    anchor resolves.
> 3. Check every factual claim on the Features, Get started and UK public sector pages against main and the guides,
>    and correct what is wrong. Mark what is in the last release and what is only on main. List what you changed.
> 4. The Team page names six people on purpose (my decision). The publish script's personal-identifier rule would
>    refuse it. Propose the smallest change that allows the Team page's names and nothing else, as a diff for me.
> 5. Publishing: each domain needs its own Pages site. Propose how publish_pages.sh publishes each site to its own
>    repository, which I will create myself. Do not create any repository, and publish nothing until I say.
> 6. Screenshots: replace the drafts' images with fresh captures from the rebuilt demo once it is frozen after
>    Friday, synthetic data only, in both looks.
> 7. Propose what happens to the current site at aykr.github.io/OspreyFlow once the new ones are live.
>
> Still mine to decide; leave these as they are and list them back to me: the spelling of Matthew's surname; the
> contact address on .net and the security-report address on .org (highlighted placeholders); the "How it is
> built" paragraph on the Team page; whether Laurium is named under "Coming next".

**Order of work.**
1. **First, within the hour, message the orchestrator** with: your recommendation for item 1 (generator or
   hand-written, and why); item 4's diff (the smallest change to publish_pages.sh's personal-identifier rule that
   allows the Team page's six names and nothing else, with a test that a seventh name or the same names on any
   other page is still refused); item 5's proposal and diff (each site to its own repository, the owner creating
   them; nothing run); and an estimate for items 1 to 3 and 7. Build nothing past reading until then.
2. Then items 1 to 3 and 7's proposal, on the Mac, each rule's test shown red first. Then "ready".
3. Item 6 after Friday's demo, when the orchestrator says.

**Never.** No change to the current six-page site, and no publish, push or repository. No local path, credential,
client or competitor name in any page. Leave the owner's four decisions exactly as they are. osprey-small is never
touched.
