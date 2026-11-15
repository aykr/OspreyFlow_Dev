# One stable release: v0.6.0

From the owner, 15 November 2026. **This replaces every earlier plan of mine for v0.5.2.** Read it before making today's candidate or starting step 6. Neither should happen as planned.

## Why

No client has installed any version of this product. I do not need a v0.5.1 followed by a v0.5.2, or an upgrade path between them. I need one stable release that holds everything agreed, which everyone installs fresh. The route to v0.5.2 has turned into repeated candidates, CI runs and install tests, each caused by a late addition of mine. This plan removes that.

## My decisions

1. **The release is v0.6.0.** v0.5.2 is never published. v0.5.0 and v0.5.1 are history.
2. **Fresh install only.** No upgrade from any earlier version is built, tested or promised. The release notes say so in one plain sentence.
3. **The list below is the scope, and it is closed.** Anything raised after today, by me or by a lane, goes to v0.6.1. That includes my own ideas.
4. **Scope before date.** v0.6.0 is released when the whole list is done.
5. **One of each at the end:** one package, one CI run on it, one package test, one release. No candidates and no package tests during the build.
6. **Nothing runs tonight as a package test.** Cancel today's remade candidate, its CI gate and step 6.

## The shape of the work

| Stage | What happens |
|---|---|
| Build | Every lane builds its items in parallel on main. Each lane runs its own unit tests. CI runs in the background and nobody waits on it |
| Test | When the list is merged: CI green on main, and the leak test and the timings at client size once more, since search and Ask & Chat will have changed |
| Package | One candidate, made once |
| Package test | Once: a fresh install of v0.6.0 on the stand-in for the client's platform, with its checks, the dashboards check, the acceptance scenarios, backup and restore, the manifest verify, and both decommission routes. No v0.5.1 and no upgrade steps |
| Release | On my word. Then both demos are built fresh from v0.6.0, and the client installs it |

## The list

Everything already merged on main is in. To build:

| # | Item | My note |
|---|---|---|
| 3 | Ask & Chat history as an accordion | As your own note: earlier questions collapse to their question line, the newest answer stays open, each line a real button, markers in a closed answer out of the Tab order. About 5 to 6 hours. No "open all" and no remembered state |
| 4 | Ask & Chat full-page view | Fills the main area with a back link to the view left, as the search results page does |
| 5 | "Show all on graph" under an answer, with "Save as a view" | |
| 6 | The GOV.UK look's type: Admin's remaining monospace words, and one confirming pass over every screen | The panels and the case line are already done |
| 7 | Two demos on one server, for ospreyflow.app (Part 3) | In the release, not after it |
| 8 | The search speed fix, if the profile finds the fixed cost | **Only if the fix is 1 to 2 hours.** Otherwise it goes to v0.6.1 and you tell me what the profile found |
| 9 | The rename to v0.6.0 | The product's version, the CHANGELOG (v0.5.2's notes become v0.6.0's), the guides' headers, the manifest and the client page tables. Past decision records keep their words |
| 10 | The basemap built as a step of the demo's install recipe | |
| 11 | The package test reshaped | Fresh install only. The images built once and kept when the cluster is remade, or the release's own images used |
| 14 | Alert sources say why a hotlist or watch stopped | From CARRIES |
| 18 | The run service admits only the intended service identity, not any app-only token of the tenant | From CARRIES. A security gap |
| 23 | The cloud-platform shape's memory sizes from measured use | So the client page is right |

## The demos' maps and model, set up on the server

The two Admin forms (`admin-forms/OWNER_PROMPT_2026-11-15.md`) are **not in v0.6.0**. They go to v0.6.1, and nothing of them is built now. What I wanted from them for the demos is done on the server instead, by you:

**Map tiles.**
- Build the local basemap on the demo server with the product's own command, for the built-in region `great-britain` (England, Scotland and Wales). That covers what the demos need. No new region is added.
- This is the large case. The build holds the whole download in memory, and it also loads the region's place names into the demo as a dataset. Before running it, tell me the download's size, the memory and time you expect, and how many place names it will add. If it will not fit beside the demo on the server, say so before trying a smaller region.
- It is a step of the demo's install recipe (item 10), so both demos have a working Map view from their first build.
- Run it when the server is quiet, and tell me how long it took and how much memory it used.

**Gemini.**
- Both demos offer Gemini in Ask & Chat beside the deployment's own model, declared in each demo's settings with a current model name that you check against the provider.
- Use the Gemini key that is already on the demo server. Do not read it, print it, copy it into any file of the repository, or put it in a message. If a demo needs the key entered again, tell me and I enter it myself at the hidden prompt.
- Tell me how the spend limit works with two demos on one key, and what a visitor sees when it is reached.
- After the build, prove it from a browser: the engine choice appears, and one question is answered by Gemini.

**For v0.6.1, not now:** the two Admin forms (model engines and map providers, with the key given in the screen), suppression taking effect (R7 step 2), people shown by name, a model allowance per visitor, Laurium's document reading from a screen, the dead batch job's status, Entra groups to roles, scheduled loads while the owner is away, a disabled engine's way out closed, connection limits from settings, fine-grained access control on search, and the production-shape work. Record them as one list.

## The date

I would like v0.6.0 by **Monday 16 November**. I know that may not be possible with item 7 on the list, and decision 4 stands: scope comes before date.

So tell me, within an hour of reading this:

1. Your estimate for each item, and the lane.
2. The earliest date for the whole list, through to the release.
3. What could be released on Monday 16 if I chose the date over the list, so I can see the difference.

I will then confirm the date. Do not drop an item to meet Monday without asking.

## What I need from you besides

- **The route and the heartbeat** rewritten to this shape: the items, then the five stages. One screen.
- **What you need from me for item 7** (the DNS names, the certificate's renewal, the model for the second site, the window for the GOV.UK demo), as one list today, so the lane is never waiting on me.
- **The demo:** no update from a candidate. It is rebuilt once, from v0.6.0. The sign-in proposal for client visitors still comes to me.
- **A draft of three lines for the client:** one install of v0.6.0, in place of v0.5.1 and then v0.5.2, and when.

## Rules that do not change

- Synthetic data only. No credentials in any file or message. Nothing published, and nothing made reachable from the internet, without my word.
- Both looks and the accessibility checks. Tests red first.
- Protected files come to me as diffs.
- Any ruling of yours that would remove or defer something on this list comes to me first.
